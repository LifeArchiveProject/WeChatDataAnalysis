"""Read-only account snapshots and fail-closed macOS capture validation.

Both realtime roles must verify before a candidate becomes an account key.
Diagnostics deliberately contain role names and key modes, never key material.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .macos_db_key_capture import MacOSDBKeyCaptureFailure
from .wechat_decrypt import PAGE_SIZE, SQLITE_HEADER, _resolve_page1_key_material


REQUIRED_ACCOUNT_ROLES = ("message", "session")


def normalize_account_probe_pages(account_probe_pages: Mapping[str, bytes]) -> dict[str, bytes]:
    """Require complete encrypted snapshots for every required account role."""

    pages: dict[str, bytes] = {}
    for role in REQUIRED_ACCOUNT_ROLES:
        page = account_probe_pages.get(role)
        if not isinstance(page, (bytes, bytearray, memoryview)) or len(page) != PAGE_SIZE:
            raise MacOSDBKeyCaptureFailure(
                "account_probe_invalid", f"账号数据库校验缺少完整的 {role} 首页，未启动密钥捕获。"
            )
        page = bytes(page)
        if page.startswith(SQLITE_HEADER):
            raise MacOSDBKeyCaptureFailure(
                "account_probe_unencrypted", f"{role} 数据库不是加密来源，无法用于账号密钥校验。"
            )
        pages[role] = page
    return pages


def resolve_account_probe_paths(
    probe_db_path: str | Path, *, account_root: str | Path | None = None
) -> dict[str, Path]:
    """Resolve the same message/session layouts as realtime key validation.

    Only the selected database's own account is considered. In the absence of
    a db_storage ancestor, flat legacy layouts and immediate role folders are
    supported; we never recursively search neighbouring account directories.
    """

    try:
        selected_probe = Path(probe_db_path).expanduser().absolute()
        probe = selected_probe.resolve(strict=True)
        if not probe.is_file():
            raise OSError("probe is not a file")
        if account_root is not None:
            root = Path(account_root).expanduser().resolve(strict=True)
            if (root / "db_storage").is_dir():
                root = (root / "db_storage").resolve(strict=True)
        else:
            root = next((parent for parent in selected_probe.parents if parent.name == "db_storage"), None)
            if root is None:
                root = selected_probe.parent.parent if selected_probe.parent.name in REQUIRED_ACCOUNT_ROLES else selected_probe.parent
            root = root.resolve(strict=True)
        if not root.is_dir() or not probe.is_relative_to(root):
            raise OSError("probe is outside selected account")
    except (OSError, RuntimeError, ValueError) as exc:
        raise MacOSDBKeyCaptureFailure(
            "account_probe_path_invalid", "无法定位所选数据库的账号目录，未启动密钥捕获。"
        ) from exc

    def first_file(candidates: list[Path]) -> Path | None:
        for candidate in candidates:
            try:
                if candidate.is_file():
                    resolved = candidate.resolve(strict=True)
                    if not resolved.is_relative_to(root):
                        raise MacOSDBKeyCaptureFailure(
                            "account_probe_path_invalid", "账号数据库指向所选账号目录之外，已停止校验。"
                        )
                    return resolved
            except OSError:
                continue
        return None

    combined = first_file([root / "MicroMsg.db", root / "micromsg.db"])
    session = first_file([root / "session/session.db", root / "session.db", root / "Session.db"]) or combined
    message_candidates: list[Path] = []
    for directory, pattern in (
        (root / "message", "message_*.db"),
        (root, "message_*.db"),
        (root, "MSG*.db"),
        (root, "msg*.db"),
    ):
        try:
            message_candidates.extend(sorted(directory.glob(pattern)))
        except OSError:
            continue
    message = first_file(message_candidates) or combined
    paths = {"message": message, "session": session}
    missing = [role for role, path in paths.items() if path is None]
    if missing:
        raise MacOSDBKeyCaptureFailure(
            "account_probe_missing", "账号数据库校验缺少必需库：" + ", ".join(missing) + "。"
        )
    return {role: path for role, path in paths.items() if path is not None}


def read_account_probe_pages(
    probe_db_path: str | Path, *, account_root: str | Path | None = None
) -> dict[str, bytes]:
    """Snapshot both encrypted page-1 values before capture or database changes."""

    paths = resolve_account_probe_paths(probe_db_path, account_root=account_root)
    pages: dict[str, bytes] = {}
    read_pages: dict[Path, bytes] = {}
    for role, path in paths.items():
        try:
            if path not in read_pages:
                with path.open("rb", buffering=0) as stream:
                    read_pages[path] = stream.read(PAGE_SIZE)
            pages[role] = read_pages[path]
        except OSError as exc:
            raise MacOSDBKeyCaptureFailure(
                "account_probe_unreadable", f"无法读取 {role} 数据库首页，未启动密钥捕获。"
            ) from exc
    return normalize_account_probe_pages(pages)


def validate_account_candidate(candidate: str | bytes, account_probe_pages: Mapping[str, bytes]) -> dict[str, Any]:
    """Return non-secret validation metadata, or raise without exposing a key."""

    pages = normalize_account_probe_pages(account_probe_pages)
    try:
        material = bytes.fromhex(candidate.strip()) if isinstance(candidate, str) else bytes(candidate)
    except (TypeError, ValueError):
        material = b""
    if len(material) != 32:
        raise MacOSDBKeyCaptureFailure("account_key_invalid", "捕获候选格式无效，未保存账号密钥。")
    modes: dict[str, str] = {}
    for role, page in pages.items():
        resolved = _resolve_page1_key_material(material, page)
        if resolved is not None:
            modes[role] = str(resolved[2])
    missing = [role for role in REQUIRED_ACCOUNT_ROLES if role not in modes]
    if missing:
        raise MacOSDBKeyCaptureFailure(
            "account_key_validation_failed", "账号密钥未通过数据库校验：" + ", ".join(missing) + "；未保存候选。"
        )
    unique_modes = set(modes.values())
    return {
        "valid": True,
        "key_mode": next(iter(unique_modes)) if len(unique_modes) == 1 else "mixed",
        "validated_roles": list(REQUIRED_ACCOUNT_ROLES),
        "modes": modes,
    }
