"""Deterministic local image-key resolution compatible with WeFlow.

The resolver treats a V2 image as the source of truth.  A kvcomm code and a
wxid are only returned after their derived AES key decrypts a real V2 block to
a supported image signature.
"""

from __future__ import annotations

import hashlib
import heapq
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


V2_MAGIC = bytes((0x07, 0x08, 0x56, 0x32, 0x08, 0x07))
V2_CIPHERTEXT_START = 0x0F
AES_BLOCK_SIZE = 16

_KVCOMM_FILE_RE = re.compile(r"^key_(\d+)_.+\.statistic$", re.IGNORECASE)
_MONTH_DIR_RE = re.compile(r"^\d{4}-\d{2}$")
_SUFFIXED_WXID_RE = re.compile(r"^(wxid_[^_]+)(?:_.+)$", re.IGNORECASE)
_MAX_CODE = 0xFFFFFFFF
_MAX_PREFERRED_DIRS = 2_000
_SKIPPED_FALLBACK_DIR_PARTS = ("thumb", "emoticon")
@dataclass(frozen=True, slots=True)
class DerivedImageKeys:
    xor_key: int
    aes_key: str


@dataclass(frozen=True, slots=True)
class V2Template:
    path: Path
    ciphertext: bytes
    mtime_ns: int
    tail_xor_key: int | None
    tail_bytes: bytes = b""


@dataclass(frozen=True, slots=True)
class TemplateScanResult:
    templates: tuple[V2Template, ...]
    inferred_xor_key: int | None
    used_fallback: bool
    files_scanned: int
    xor_support: int = 0


@dataclass(frozen=True, slots=True)
class ImageKeyResolution:
    code: int
    wxid: str
    xor_key: int
    aes_key: str
    verified: bool
    template_path: Path
    inferred_xor_key: int | None

    def as_dict(self) -> dict[str, object]:
        """Return a key-service friendly representation."""
        return {
            "code": self.code,
            "wxid": self.wxid,
            "xor_key": self.xor_key,
            "xor_key_hex": f"0x{self.xor_key:02X}",
            "aes_key": self.aes_key,
            "verified": self.verified,
            "template_path": str(self.template_path),
            "inferred_xor_key": self.inferred_xor_key,
        }


def enumerate_kvcomm_codes(kvcomm_dir: str | os.PathLike[str]) -> tuple[int, ...]:
    """Enumerate all unique valid codes from a kvcomm cache directory."""
    codes: set[int] = set()
    try:
        with os.scandir(kvcomm_dir) as entries:
            for entry in entries:
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                match = _KVCOMM_FILE_RE.fullmatch(entry.name)
                if not match:
                    continue
                code = int(match.group(1))
                if 0 < code <= _MAX_CODE:
                    codes.add(code)
    except (OSError, TypeError, ValueError):
        return ()
    return tuple(sorted(codes))


def clean_wxid(value: str | None) -> str:
    """Remove the data-directory suffix from ``wxid_xxx_<suffix>`` values."""
    candidate = str(value or "").strip()
    if not candidate:
        return ""
    match = _SUFFIXED_WXID_RE.fullmatch(candidate)
    return match.group(1) if match else candidate


def collect_wxid_candidates(
    target_wxid: str | None = None,
    account: str | None = None,
    local_native_wxids: Iterable[str] | str | None = None,
) -> tuple[str, ...]:
    """Build candidates in target/account/native priority, then ``unknown``."""
    native_values: Iterable[str]
    if isinstance(local_native_wxids, str):
        native_values = (local_native_wxids,)
    else:
        native_values = local_native_wxids or ()

    candidates: list[str] = []
    seen: set[str] = set()
    for raw_value in (target_wxid, account, *native_values, "unknown"):
        value = clean_wxid(raw_value)
        if not value or value in seen:
            continue
        seen.add(value)
        candidates.append(value)
    return tuple(candidates)


def derive_image_keys(code: int, wxid: str) -> DerivedImageKeys:
    """Derive WeFlow's XOR byte and 16-byte ASCII AES key."""
    if isinstance(code, bool) or not isinstance(code, int) or not (0 < code <= _MAX_CODE):
        raise ValueError("code must be an integer in the range 1..0xffffffff")
    cleaned_wxid = clean_wxid(wxid)
    if not cleaned_wxid:
        raise ValueError("wxid must not be empty")

    digest = hashlib.md5(f"{code}{cleaned_wxid}".encode("utf-8")).hexdigest()
    return DerivedImageKeys(xor_key=code & 0xFF, aes_key=digest[:16])


def _decrypt_aes_block(aes_key: str | bytes, ciphertext: bytes) -> bytes | None:
    try:
        key_bytes = aes_key.encode("ascii") if isinstance(aes_key, str) else bytes(aes_key)
    except (UnicodeEncodeError, TypeError, ValueError):
        return None
    if len(key_bytes) < AES_BLOCK_SIZE or len(ciphertext) != AES_BLOCK_SIZE:
        return None

    try:
        decryptor = Cipher(algorithms.AES(key_bytes[:AES_BLOCK_SIZE]), modes.ECB()).decryptor()
        return decryptor.update(ciphertext) + decryptor.finalize()
    except (TypeError, ValueError):
        return None


def _detect_image_format(plaintext: bytes | None) -> str | None:
    if not plaintext:
        return None
    if plaintext.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if plaintext.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if plaintext.startswith(b"RIFF") and plaintext[8:12] == b"WEBP":
        return "webp"
    if plaintext.startswith((b"wxgf", b"WXGF")):
        return "wxgf"
    if plaintext.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    return None


def verify_aes_key(aes_key: str | bytes, ciphertext: bytes) -> bool:
    """Verify one AES key against the encrypted first block of a V2 image."""
    return _detect_image_format(_decrypt_aes_block(aes_key, ciphertext)) is not None


def _infer_xor_key_with_support(tails: Iterable[bytes]) -> tuple[int | None, int]:
    counts: Counter[bytes] = Counter()
    for tail in tails:
        try:
            pair = bytes(tail)
        except (TypeError, ValueError):
            continue
        if len(pair) == 2:
            counts[pair] += 1
    if not counts:
        return None, 0

    pair, support = counts.most_common(1)[0]
    first = pair[0] ^ 0xFF
    second = pair[1] ^ 0xD9
    return (first, support) if first == second else (None, support)


def infer_xor_key_from_v2_tails(tails: Iterable[bytes]) -> int | None:
    """Infer XOR from the most common raw trailer pair, matching WeFlow."""
    inferred, _ = _infer_xor_key_with_support(tails)
    return inferred


def _safe_mtime_ns(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def _list_child_dirs(path: Path) -> list[Path]:
    directories: list[Path] = []
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        directories.append(Path(entry.path))
                except OSError:
                    continue
    except OSError:
        return []
    return directories


def _offer_recent_template_files(
    directory: Path,
    heap: list[tuple[int, str, str]],
    capacity: int,
    excluded_paths: set[str] | None = None,
) -> None:
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if not entry.name.lower().endswith("_t.dat"):
                    continue
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    mtime_ns = entry.stat(follow_symlinks=False).st_mtime_ns
                except OSError:
                    continue

                path_text = str(Path(entry.path))
                path_key = os.path.normcase(os.path.abspath(path_text))
                if excluded_paths and path_key in excluded_paths:
                    continue
                heap_item = (mtime_ns, path_text.casefold(), path_text)
                if len(heap) < capacity:
                    heapq.heappush(heap, heap_item)
                elif heap_item > heap[0]:
                    heapq.heapreplace(heap, heap_item)
    except OSError:
        return


def _recent_paths(heap: list[tuple[int, str, str]]) -> tuple[Path, ...]:
    return tuple(Path(item[2]) for item in sorted(heap, reverse=True))


def _collect_preferred_paths(account_dir: Path, capacity: int) -> tuple[Path, ...]:
    attach_root = account_dir / "msg" / "attach"
    attach_dirs = _list_child_dirs(attach_root)
    attach_dirs.sort(key=lambda path: (-_safe_mtime_ns(path), path.name.casefold()))

    heap: list[tuple[int, str, str]] = []
    visited_dirs = 0
    for attach_dir in attach_dirs:
        if visited_dirs >= _MAX_PREFERRED_DIRS:
            break
        visited_dirs += 1
        month_dirs = [path for path in _list_child_dirs(attach_dir) if _MONTH_DIR_RE.fullmatch(path.name)]
        month_dirs.sort(key=lambda path: path.name, reverse=True)
        for month_dir in month_dirs:
            if visited_dirs >= _MAX_PREFERRED_DIRS:
                break
            visited_dirs += 1
            img_dirs = [path for path in _list_child_dirs(month_dir) if path.name.casefold() == "img"]
            for img_dir in img_dirs:
                if visited_dirs >= _MAX_PREFERRED_DIRS:
                    break
                visited_dirs += 1
                _offer_recent_template_files(img_dir, heap, capacity)
    return _recent_paths(heap)


def _collect_fallback_paths(
    account_dir: Path,
    capacity: int,
    max_dirs: int,
    excluded_paths: set[str],
) -> tuple[Path, ...]:
    queue = [
        path
        for path in (account_dir / "msg", account_dir / "cache", account_dir / "resource")
        if path.is_dir()
    ]
    heap: list[tuple[int, str, str]] = []
    visited_dirs = 0
    queue_index = 0

    while queue_index < len(queue) and visited_dirs < max_dirs:
        directory = queue[queue_index]
        queue_index += 1
        visited_dirs += 1
        _offer_recent_template_files(directory, heap, capacity, excluded_paths)

        child_dirs = _list_child_dirs(directory)
        child_dirs.sort(key=lambda path: path.name.casefold())
        for child in child_dirs:
            lower_name = child.name.casefold()
            if any(part in lower_name for part in _SKIPPED_FALLBACK_DIR_PARTS):
                continue
            if len(queue) >= max_dirs:
                break
            queue.append(child)
    return _recent_paths(heap)


def _read_v2_templates(paths: Sequence[Path], limit: int) -> tuple[tuple[V2Template, ...], int]:
    templates: list[V2Template] = []
    files_scanned = 0
    for path in paths:
        if len(templates) >= limit:
            break
        files_scanned += 1
        try:
            with path.open("rb") as stream:
                header = stream.read(V2_CIPHERTEXT_START + AES_BLOCK_SIZE)
                if len(header) < V2_CIPHERTEXT_START + AES_BLOCK_SIZE or not header.startswith(V2_MAGIC):
                    continue
                stream.seek(-2, os.SEEK_END)
                tail = stream.read(2)
        except (OSError, ValueError):
            continue

        tail_xor_key = infer_xor_key_from_v2_tails((tail,))
        templates.append(
            V2Template(
                path=path,
                ciphertext=header[V2_CIPHERTEXT_START : V2_CIPHERTEXT_START + AES_BLOCK_SIZE],
                mtime_ns=_safe_mtime_ns(path),
                tail_xor_key=tail_xor_key,
                tail_bytes=tail,
            )
        )
    return tuple(templates), files_scanned


def scan_v2_templates(
    account_dir: str | os.PathLike[str],
    *,
    limit: int = 32,
    max_fallback_dirs: int = 500,
) -> TemplateScanResult:
    """Find recent V2 thumbnail templates with bounded fallback traversal."""
    if limit <= 0:
        return TemplateScanResult(templates=(), inferred_xor_key=None, used_fallback=False, files_scanned=0)

    root = Path(account_dir)
    discovery_capacity = max(limit * 4, 64)
    preferred_paths = _collect_preferred_paths(root, discovery_capacity)
    templates, files_scanned = _read_v2_templates(preferred_paths, limit)
    used_fallback = False

    if not templates and max_fallback_dirs > 0:
        used_fallback = True
        excluded = {os.path.normcase(os.path.abspath(str(path))) for path in preferred_paths}
        fallback_paths = _collect_fallback_paths(
            root,
            discovery_capacity,
            max_fallback_dirs,
            excluded,
        )
        templates, fallback_scanned = _read_v2_templates(fallback_paths, limit)
        files_scanned += fallback_scanned

    inferred_xor_key, xor_support = _infer_xor_key_with_support(
        template.tail_bytes for template in templates
    )

    return TemplateScanResult(
        templates=templates,
        inferred_xor_key=inferred_xor_key,
        used_fallback=used_fallback,
        files_scanned=files_scanned,
        xor_support=xor_support,
    )


def current_v2_template(
    template_data: TemplateScanResult | Sequence[V2Template],
) -> V2Template | None:
    templates = tuple(
        template_data.templates if isinstance(template_data, TemplateScanResult) else template_data
    )
    return templates[0] if templates else None


def trusted_xor_for_verified_aes_key(
    aes_key: str | bytes,
    template_data: TemplateScanResult | Sequence[V2Template],
) -> int | None:
    templates = tuple(
        template_data.templates if isinstance(template_data, TemplateScanResult) else template_data
    )
    current = current_v2_template(templates)
    if current is None:
        return None
    image_format = _detect_image_format(_decrypt_aes_block(aes_key, current.ciphertext))
    if image_format is None:
        return None

    matching_jpeg_xor_keys: list[int] = []
    for template in templates:
        detected_format = _detect_image_format(_decrypt_aes_block(aes_key, template.ciphertext))
        if detected_format == "jpeg" and template.tail_xor_key is not None:
            matching_jpeg_xor_keys.append(template.tail_xor_key)

    if not matching_jpeg_xor_keys:
        return None
    return Counter(matching_jpeg_xor_keys).most_common(1)[0][0]


def verify_key_pair(
    xor_key: int,
    aes_key: str | bytes,
    template_data: TemplateScanResult | Sequence[V2Template],
    *,
    require_xor_match: bool = True,
) -> bool:
    """Verify a native or derived key pair against collected V2 templates."""
    if isinstance(xor_key, bool) or not isinstance(xor_key, int) or not (0 <= xor_key <= 0xFF):
        return False
    current_template = current_v2_template(template_data)
    if current_template is None:
        return False
    if require_xor_match:
        current_xor = trusted_xor_for_verified_aes_key(aes_key, template_data)
        if current_xor is None or current_xor != xor_key:
            return False
    return verify_aes_key(aes_key, current_template.ciphertext)


def resolve_local_image_key(
    *,
    kvcomm_dir: str | os.PathLike[str],
    account_dir: str | os.PathLike[str],
    target_wxid: str | None = None,
    account: str | None = None,
    local_native_wxids: Iterable[str] | str | None = None,
    template_scan: TemplateScanResult | None = None,
    template_limit: int = 32,
    max_fallback_dirs: int = 500,
) -> ImageKeyResolution | None:
    """Resolve the first code/wxid pair that passes real V2 AES validation."""
    codes = enumerate_kvcomm_codes(kvcomm_dir)
    if not codes:
        return None

    native_values: list[str] = []
    if isinstance(local_native_wxids, str):
        native_values.append(local_native_wxids)
    elif local_native_wxids:
        native_values.extend(local_native_wxids)
    native_values.append(Path(account_dir).name)

    wxids = collect_wxid_candidates(target_wxid, account, native_values)
    if not wxids:
        return None

    template_data = template_scan
    if template_data is None:
        template_data = scan_v2_templates(
            account_dir,
            limit=template_limit,
            max_fallback_dirs=max_fallback_dirs,
        )
    if not template_data.templates:
        return None

    current_template = current_v2_template(template_data)
    if current_template is None:
        return None
    current_xor_key = (
        template_data.inferred_xor_key
        if template_data.inferred_xor_key is not None and template_data.xor_support >= 2
        else current_template.tail_xor_key
    )
    ordered_codes = list(codes)
    if current_xor_key is not None:
        ordered_codes.sort(key=lambda code: (code & 0xFF != current_xor_key, code))

    for wxid in wxids:
        for code in ordered_codes:
            keys = derive_image_keys(code, wxid)
            if not verify_aes_key(keys.aes_key, current_template.ciphertext):
                continue
            return ImageKeyResolution(
                code=code,
                wxid=clean_wxid(wxid),
                xor_key=keys.xor_key,
                aes_key=keys.aes_key,
                verified=True,
                template_path=current_template.path,
                inferred_xor_key=current_xor_key,
            )
    return None


__all__ = [
    "AES_BLOCK_SIZE",
    "DerivedImageKeys",
    "ImageKeyResolution",
    "TemplateScanResult",
    "V2_MAGIC",
    "V2Template",
    "clean_wxid",
    "collect_wxid_candidates",
    "current_v2_template",
    "derive_image_keys",
    "enumerate_kvcomm_codes",
    "infer_xor_key_from_v2_tails",
    "resolve_local_image_key",
    "scan_v2_templates",
    "trusted_xor_for_verified_aes_key",
    "verify_aes_key",
    "verify_key_pair",
]
