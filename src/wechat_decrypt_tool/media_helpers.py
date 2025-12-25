import ctypes
import datetime
import glob
import hashlib
import json
import mimetypes
import os
import re
import sqlite3
import struct
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException

from .logging_config import get_logger

logger = get_logger(__name__)


# 仓库根目录（用于定位 output/databases）
_REPO_ROOT = Path(__file__).resolve().parents[2]
_OUTPUT_DATABASES_DIR = _REPO_ROOT / "output" / "databases"
_PACKAGE_ROOT = Path(__file__).resolve().parent


def _list_decrypted_accounts() -> list[str]:
    """列出已解密输出的账号目录名（仅保留包含 session.db + contact.db 的账号）"""
    if not _OUTPUT_DATABASES_DIR.exists():
        return []

    accounts: list[str] = []
    for p in _OUTPUT_DATABASES_DIR.iterdir():
        if not p.is_dir():
            continue
        if (p / "session.db").exists() and (p / "contact.db").exists():
            accounts.append(p.name)

    accounts.sort()
    return accounts


def _resolve_account_dir(account: Optional[str]) -> Path:
    """解析账号目录，并进行路径安全校验（防止路径穿越）"""
    accounts = _list_decrypted_accounts()
    if not accounts:
        raise HTTPException(
            status_code=404,
            detail="No decrypted databases found. Please decrypt first.",
        )

    selected = account or accounts[0]
    base = _OUTPUT_DATABASES_DIR.resolve()
    candidate = (_OUTPUT_DATABASES_DIR / selected).resolve()

    if candidate != base and base not in candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid account path.")

    if not candidate.exists() or not candidate.is_dir():
        raise HTTPException(status_code=404, detail="Account not found.")

    if not (candidate / "session.db").exists():
        raise HTTPException(status_code=404, detail="session.db not found for this account.")
    if not (candidate / "contact.db").exists():
        raise HTTPException(status_code=404, detail="contact.db not found for this account.")

    return candidate


def _detect_image_media_type(data: bytes) -> str:
    if not data:
        return "application/octet-stream"

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


class _WxAMConfig(ctypes.Structure):
    _fields_ = [
        ("mode", ctypes.c_int),
        ("reserved", ctypes.c_int),
    ]


@lru_cache(maxsize=1)
def _get_wxam_decoder():
    if os.name != "nt":
        return None
    dll_path = _PACKAGE_ROOT / "native" / "VoipEngine.dll"
    if not dll_path.exists():
        logger.warning(f"WxAM decoder DLL not found: {dll_path}")
        return None
    try:
        voip_engine = ctypes.WinDLL(str(dll_path))
        fn = voip_engine.wxam_dec_wxam2pic_5
        fn.argtypes = [
            ctypes.c_int64,
            ctypes.c_int,
            ctypes.c_int64,
            ctypes.POINTER(ctypes.c_int),
            ctypes.c_int64,
        ]
        fn.restype = ctypes.c_int64
        logger.info(f"WxAM decoder loaded: {dll_path}")
        return fn
    except Exception as e:
        logger.warning(f"Failed to load WxAM decoder DLL: {dll_path} ({e})")
        return None


def _wxgf_to_image_bytes(data: bytes) -> Optional[bytes]:
    if not data or not data.startswith(b"wxgf"):
        return None
    fn = _get_wxam_decoder()
    if fn is None:
        return None

    max_output_size = 52 * 1024 * 1024
    for mode in (0, 3):
        try:
            config = _WxAMConfig()
            config.mode = int(mode)
            config.reserved = 0

            input_buffer = ctypes.create_string_buffer(data, len(data))
            output_buffer = ctypes.create_string_buffer(max_output_size)
            output_size = ctypes.c_int(max_output_size)

            result = fn(
                ctypes.addressof(input_buffer),
                int(len(data)),
                ctypes.addressof(output_buffer),
                ctypes.byref(output_size),
                ctypes.addressof(config),
            )
            if result != 0 or output_size.value <= 0:
                continue
            out = output_buffer.raw[: int(output_size.value)]
            if _detect_image_media_type(out[:32]) != "application/octet-stream":
                return out
        except Exception:
            continue
    return None


def _try_strip_media_prefix(data: bytes) -> tuple[bytes, str]:
    if not data:
        return data, "application/octet-stream"

    try:
        head = data[: min(len(data), 256 * 1024)]
    except Exception:
        head = data

    # wxgf container
    try:
        idx = head.find(b"wxgf")
    except Exception:
        idx = -1
    if idx >= 0 and idx <= 128 * 1024:
        try:
            payload = data[idx:]
            converted = _wxgf_to_image_bytes(payload)
            if converted:
                mtw = _detect_image_media_type(converted[:32])
                if mtw != "application/octet-stream":
                    return converted, mtw
        except Exception:
            pass

    # common image/video headers with small prefix
    sigs: list[tuple[bytes, str]] = [
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"GIF87a", "image/gif"),
        (b"GIF89a", "image/gif"),
    ]
    for sig, mt in sigs:
        try:
            j = head.find(sig)
        except Exception:
            j = -1
        if j >= 0 and j <= 128 * 1024:
            sliced = data[j:]
            mt2 = _detect_image_media_type(sliced[:32])
            if mt2 != "application/octet-stream":
                return sliced, mt2

    try:
        j = head.find(b"RIFF")
    except Exception:
        j = -1
    if j >= 0 and j <= 128 * 1024:
        sliced = data[j:]
        try:
            if len(sliced) >= 12 and sliced[8:12] == b"WEBP":
                return sliced, "image/webp"
        except Exception:
            pass

    try:
        j = head.find(b"ftyp")
    except Exception:
        j = -1
    if j >= 4 and j <= 128 * 1024:
        sliced = data[j - 4 :]
        try:
            if len(sliced) >= 8 and sliced[4:8] == b"ftyp":
                return sliced, "video/mp4"
        except Exception:
            pass

    return data, "application/octet-stream"


def _load_account_source_info(account_dir: Path) -> dict[str, Any]:
    p = account_dir / "_source.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _guess_wxid_dir_from_common_paths(account_name: str) -> Optional[Path]:
    try:
        home = Path.home()
    except Exception:
        return None

    roots = [
        home / "Documents" / "xwechat_files",
        home / "Documents" / "WeChat Files",
    ]

    # Exact match first
    for root in roots:
        c = root / account_name
        try:
            if c.exists() and c.is_dir():
                return c
        except Exception:
            continue

    # Then try prefix match: wxid_xxx_yyyy
    for root in roots:
        try:
            if not root.exists() or not root.is_dir():
                continue
            for p in root.iterdir():
                if not p.is_dir():
                    continue
                if p.name.startswith(account_name + "_"):
                    return p
        except Exception:
            continue
    return None


def _resolve_account_wxid_dir(account_dir: Path) -> Optional[Path]:
    info = _load_account_source_info(account_dir)
    wxid_dir = str(info.get("wxid_dir") or "").strip()
    if wxid_dir:
        try:
            p = Path(wxid_dir)
            if p.exists() and p.is_dir():
                return p
        except Exception:
            pass
    return _guess_wxid_dir_from_common_paths(account_dir.name)


def _resolve_account_db_storage_dir(account_dir: Path) -> Optional[Path]:
    info = _load_account_source_info(account_dir)
    db_storage_path = str(info.get("db_storage_path") or "").strip()
    if db_storage_path:
        try:
            p = Path(db_storage_path)
            if p.exists() and p.is_dir():
                return p
        except Exception:
            pass

    wxid_dir = _resolve_account_wxid_dir(account_dir)
    if wxid_dir:
        c = wxid_dir / "db_storage"
        try:
            if c.exists() and c.is_dir():
                return c
        except Exception:
            pass
    return None


def _quote_ident(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def _resolve_hardlink_table_name(conn: sqlite3.Connection, prefix: str) -> Optional[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ? ORDER BY name DESC",
        (f"{prefix}%",),
    ).fetchall()
    if not rows:
        return None
    return str(rows[0][0]) if rows[0] and rows[0][0] else None


def _resolve_hardlink_dir2id_table_name(conn: sqlite3.Connection) -> Optional[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'dir2id%' ORDER BY name DESC"
    ).fetchall()
    if not rows:
        return None
    return str(rows[0][0]) if rows[0] and rows[0][0] else None


def _resolve_media_path_from_hardlink(
    hardlink_db_path: Path,
    wxid_dir: Path,
    md5: str,
    kind: str,
    username: Optional[str],
    extra_roots: Optional[list[Path]] = None,
) -> Optional[Path]:
    if not hardlink_db_path.exists():
        return None

    kind_key = str(kind or "").lower().strip()
    prefixes: list[str]
    if kind_key == "image":
        prefixes = ["image_hardlink_info"]
    elif kind_key == "emoji":
        prefixes = [
            "emoji_hardlink_info",
            "emotion_hardlink_info",
            "image_hardlink_info",
        ]
    elif kind_key == "video" or kind_key == "video_thumb":
        prefixes = ["video_hardlink_info"]
    elif kind_key == "file":
        prefixes = ["file_hardlink_info"]
    else:
        return None

    conn = sqlite3.connect(str(hardlink_db_path))
    conn.row_factory = sqlite3.Row
    try:
        for prefix in prefixes:
            table_name = _resolve_hardlink_table_name(conn, prefix)
            if not table_name:
                continue

            quoted = _quote_ident(table_name)
            try:
                row = conn.execute(
                    f"SELECT dir1, dir2, file_name, modify_time FROM {quoted} WHERE md5 = ? ORDER BY modify_time DESC LIMIT 1",
                    (md5,),
                ).fetchone()
            except Exception:
                row = None
            if not row:
                continue

            file_name = str(row["file_name"] or "").strip()
            if not file_name:
                continue

            if kind_key in {"video", "video_thumb"}:
                roots: list[Path] = []
                for r in [wxid_dir] + (extra_roots or []):
                    if not r:
                        continue
                    try:
                        rr = r.resolve()
                    except Exception:
                        rr = r
                    if rr not in roots:
                        roots.append(rr)

                def _iter_video_base_dirs(r: Path) -> list[Path]:
                    bases: list[Path] = []
                    try:
                        if r.exists() and r.is_dir():
                            pass
                        else:
                            return bases
                    except Exception:
                        return bases

                    candidates = [
                        r / "msg" / "video",
                        r / "video",
                        r if str(r.name).lower() == "video" else None,
                    ]
                    for c in candidates:
                        if not c:
                            continue
                        try:
                            if c.exists() and c.is_dir():
                                bases.append(c)
                        except Exception:
                            continue

                    # de-dup while keeping order
                    seen: set[str] = set()
                    uniq: list[Path] = []
                    for b in bases:
                        try:
                            k = str(b.resolve())
                        except Exception:
                            k = str(b)
                        if k in seen:
                            continue
                        seen.add(k)
                        uniq.append(b)
                    return uniq

                modify_time = None
                try:
                    if row["modify_time"] is not None:
                        modify_time = int(row["modify_time"])
                except Exception:
                    modify_time = None

                guessed_month: Optional[str] = None
                if modify_time and modify_time > 0:
                    try:
                        dt = datetime.datetime.fromtimestamp(int(modify_time))
                        guessed_month = f"{dt.year:04d}-{dt.month:02d}"
                    except Exception:
                        guessed_month = None

                stem = Path(file_name).stem
                if kind_key == "video":
                    file_variants = [file_name]
                else:
                    # Prefer real thumbnails when possible.
                    file_variants = [
                        f"{stem}_thumb.jpg",
                        f"{stem}_thumb.jpeg",
                        f"{stem}_thumb.png",
                        f"{stem}_thumb.webp",
                        f"{stem}.jpg",
                        f"{stem}.jpeg",
                        f"{stem}.png",
                        f"{stem}.gif",
                        f"{stem}.webp",
                        f"{stem}.dat",
                        file_name,
                    ]

                for root in roots:
                    for base_dir in _iter_video_base_dirs(root):
                        dirs_to_check: list[Path] = []
                        if guessed_month:
                            dirs_to_check.append(base_dir / guessed_month)
                        dirs_to_check.append(base_dir)
                        for d in dirs_to_check:
                            try:
                                if not d.exists() or not d.is_dir():
                                    continue
                            except Exception:
                                continue
                            for fv in file_variants:
                                p = d / fv
                                try:
                                    if p.exists() and p.is_file():
                                        return p
                                except Exception:
                                    continue

                            # Fallback: scan within the month directory for the exact file_name.
                            if guessed_month:
                                try:
                                    for p in d.rglob(file_name):
                                        try:
                                            if p.is_file():
                                                return p
                                        except Exception:
                                            continue
                                except Exception:
                                    pass

                # Final fallback: locate by name under msg/video and cache.
                for base in _iter_video_base_dirs(wxid_dir):
                    try:
                        for p in base.rglob(file_name):
                            if p.is_file():
                                return p
                    except Exception:
                        pass
                return None

            if kind_key == "file":
                try:
                    full_row = conn.execute(
                        f"SELECT file_name, file_size, modify_time FROM {quoted} WHERE md5 = ? ORDER BY modify_time DESC LIMIT 1",
                        (md5,),
                    ).fetchone()
                except Exception:
                    full_row = None

                file_size: Optional[int] = None
                modify_time: Optional[int] = None
                if full_row is not None:
                    try:
                        if full_row["file_size"] is not None:
                            file_size = int(full_row["file_size"])
                    except Exception:
                        file_size = None
                    try:
                        if full_row["modify_time"] is not None:
                            modify_time = int(full_row["modify_time"])
                    except Exception:
                        modify_time = None

                roots: list[Path] = []
                for r in [wxid_dir] + (extra_roots or []):
                    if not r:
                        continue
                    try:
                        rr = r.resolve()
                    except Exception:
                        rr = r
                    if rr not in roots:
                        roots.append(rr)

                file_base_dirs: list[Path] = []
                for root in roots:
                    candidates = [
                        root / "msg" / "file",
                        root / "file" if root.name.lower() == "msg" else None,
                        root if root.name.lower() == "file" else None,
                    ]
                    for c in candidates:
                        if not c:
                            continue
                        try:
                            if c.exists() and c.is_dir() and c not in file_base_dirs:
                                file_base_dirs.append(c)
                        except Exception:
                            continue

                if not file_base_dirs:
                    return None

                guessed_month: Optional[str] = None
                if modify_time:
                    try:
                        dt = datetime.datetime.fromtimestamp(int(modify_time))
                        guessed_month = f"{dt.year:04d}-{dt.month:02d}"
                    except Exception:
                        guessed_month = None

                file_stem = Path(file_name).stem

                def _iter_month_dirs(base: Path) -> list[Path]:
                    out: list[Path] = []
                    try:
                        for child in base.iterdir():
                            try:
                                if not child.is_dir():
                                    continue
                            except Exception:
                                continue
                            name = str(child.name)
                            if re.fullmatch(r"\d{4}-\d{2}", name):
                                out.append(child)
                    except Exception:
                        return []
                    return sorted(out, key=lambda p: str(p.name))

                def _pick_best_hit(hits: list[Path]) -> Optional[Path]:
                    if not hits:
                        return None
                    if file_size is not None and file_size >= 0:
                        for h in hits:
                            try:
                                if h.stat().st_size == file_size:
                                    return h
                            except Exception:
                                continue
                    return hits[0]

                for base in file_base_dirs:
                    month_dirs = _iter_month_dirs(base)
                    month_names: list[str] = []
                    if guessed_month:
                        month_names.append(guessed_month)
                    for d in month_dirs:
                        n = str(d.name)
                        if n not in month_names:
                            month_names.append(n)

                    for month_name in month_names:
                        month_dir = base / month_name
                        try:
                            if not (month_dir.exists() and month_dir.is_dir()):
                                continue
                        except Exception:
                            continue

                        direct = month_dir / file_name
                        try:
                            if direct.exists() and direct.is_file():
                                return direct
                        except Exception:
                            pass

                        in_stem_dir = month_dir / file_stem / file_name
                        try:
                            if in_stem_dir.exists() and in_stem_dir.is_file():
                                return in_stem_dir
                        except Exception:
                            pass

                        hits: list[Path] = []
                        try:
                            for p in month_dir.rglob(file_name):
                                try:
                                    if p.is_file():
                                        hits.append(p)
                                        if len(hits) >= 20:
                                            break
                                except Exception:
                                    continue
                        except Exception:
                            hits = []

                        best = _pick_best_hit(hits)
                        if best:
                            return best

                    # Final fallback: search across all months (covers rare nesting patterns)
                    hits_all: list[Path] = []
                    try:
                        for p in base.rglob(file_name):
                            try:
                                if p.is_file():
                                    hits_all.append(p)
                                    if len(hits_all) >= 50:
                                        break
                            except Exception:
                                continue
                    except Exception:
                        hits_all = []

                    best_all = _pick_best_hit(hits_all)
                    if best_all:
                        return best_all

                    if guessed_month:
                        fallback_dir = base / guessed_month
                        try:
                            if fallback_dir.exists() and fallback_dir.is_dir():
                                return fallback_dir
                        except Exception:
                            pass

                    return base

                return None

            dir1 = str(row["dir1"] if row["dir1"] is not None else "").strip()
            dir2 = str(row["dir2"] if row["dir2"] is not None else "").strip()
            if not dir1 or not dir2:
                continue

            dir_name = dir2
            dir2id_table = _resolve_hardlink_dir2id_table_name(conn)

            if dir2id_table:
                try:
                    drow = conn.execute(
                        f"SELECT username FROM {_quote_ident(dir2id_table)} WHERE rowid = ? LIMIT 1",
                        (int(dir2),),
                    ).fetchone()
                    if drow and drow[0]:
                        dir_name = str(drow[0])
                except Exception:
                    if username:
                        try:
                            drow = conn.execute(
                                f"SELECT dir_name FROM {_quote_ident(dir2id_table)} WHERE dir_id = ? AND username = ? LIMIT 1",
                                (dir2, username),
                            ).fetchone()
                            if drow and drow[0]:
                                dir_name = str(drow[0])
                        except Exception:
                            pass

            roots: list[Path] = []
            for r in [wxid_dir] + (extra_roots or []):
                if not r:
                    continue
                try:
                    rr = r.resolve()
                except Exception:
                    rr = r
                if rr not in roots:
                    roots.append(rr)

            file_stem = Path(file_name).stem
            file_variants = [file_name, f"{file_stem}_h.dat", f"{file_stem}_t.dat"]

            for root in roots:
                for fv in file_variants:
                    p = (root / dir1 / dir_name / fv).resolve()
                    try:
                        if p.exists() and p.is_file():
                            return p
                    except Exception:
                        continue

                if username:
                    chat_hash = hashlib.md5(username.encode()).hexdigest()
                    for fv in file_variants:
                        p = (root / "msg" / "attach" / chat_hash / dir_name / "Img" / fv).resolve()
                        try:
                            if p.exists() and p.is_file():
                                return p
                        except Exception:
                            continue

        return None
    finally:
        conn.close()


@lru_cache(maxsize=4096)
def _fallback_search_media_by_md5(weixin_root_str: str, md5: str, kind: str = "") -> Optional[str]:
    if not weixin_root_str or not md5:
        return None
    try:
        root = Path(weixin_root_str)
    except Exception:
        return None

    kind_key = str(kind or "").lower().strip()

    def _fast_find_emoji_in_cache() -> Optional[str]:
        md5_prefix = md5[:2] if len(md5) >= 2 else ""
        if not md5_prefix:
            return None
        cache_root = root / "cache"
        try:
            if not cache_root.exists() or not cache_root.is_dir():
                return None
        except Exception:
            return None

        exact_names = [
            f"{md5}_h.dat",
            f"{md5}_t.dat",
            f"{md5}.dat",
            f"{md5}.gif",
            f"{md5}.webp",
            f"{md5}.png",
            f"{md5}.jpg",
        ]
        buckets = ["Emoticon", "emoticon", "Emoji", "emoji"]

        candidates: list[Path] = []
        try:
            children = list(cache_root.iterdir())
        except Exception:
            children = []

        for child in children:
            try:
                if not child.is_dir():
                    continue
            except Exception:
                continue
            for bucket in buckets:
                candidates.append(child / bucket / md5_prefix)

        for bucket in buckets:
            candidates.append(cache_root / bucket / md5_prefix)

        seen: set[str] = set()
        uniq: list[Path] = []
        for c in candidates:
            try:
                rc = str(c.resolve())
            except Exception:
                rc = str(c)
            if rc in seen:
                continue
            seen.add(rc)
            uniq.append(c)

        for base in uniq:
            try:
                if not base.exists() or not base.is_dir():
                    continue
            except Exception:
                continue

            for name in exact_names:
                p = base / name
                try:
                    if p.exists() and p.is_file():
                        return str(p)
                except Exception:
                    continue

            try:
                for p in base.glob(f"{md5}*"):
                    try:
                        if p.is_file():
                            return str(p)
                    except Exception:
                        continue
            except Exception:
                continue
        return None

    # 根据类型选择搜索目录
    if kind_key == "file":
        search_dirs = [root / "msg" / "file"]
    elif kind_key == "emoji":
        hit_fast = _fast_find_emoji_in_cache()
        if hit_fast:
            return hit_fast
        search_dirs = [
            root / "msg" / "emoji",
            root / "msg" / "emoticon",
            root / "emoji",
            root / "emoticon",
            root / "msg" / "attach",
            root / "msg" / "file",
            root / "msg" / "video",
        ]
    else:
        search_dirs = [
            root / "msg" / "attach",
            root / "msg" / "file",
            root / "msg" / "video",
            root / "cache",
        ]

    # 根据类型选择搜索模式
    if kind_key == "file":
        patterns = [
            f"*{md5}*",
        ]
    elif kind_key == "emoji":
        patterns = [
            f"{md5}_h.dat",
            f"{md5}_t.dat",
            f"{md5}.dat",
            f"{md5}*.dat",
            f"{md5}*.gif",
            f"{md5}*.webp",
            f"{md5}*.png",
            f"{md5}*.jpg",
            f"*{md5}*",
        ]
    else:
        patterns = [
            f"{md5}_h.dat",
            f"{md5}_t.dat",
            f"{md5}.dat",
            f"{md5}*.dat",
            f"{md5}*.jpg",
            f"{md5}*.jpeg",
            f"{md5}*.png",
            f"{md5}*.gif",
            f"{md5}*.webp",
            f"{md5}*.mp4",
        ]

    for d in search_dirs:
        try:
            if not d.exists() or not d.is_dir():
                continue
        except Exception:
            continue
        for pat in patterns:
            try:
                for p in d.rglob(pat):
                    try:
                        if p.is_file():
                            return str(p)
                    except Exception:
                        continue
            except Exception:
                continue
    return None


def _guess_media_type_by_path(path: Path, fallback: str = "application/octet-stream") -> str:
    try:
        mt = mimetypes.guess_type(str(path.name))[0]
        if mt:
            return mt
    except Exception:
        pass
    return fallback


def _try_xor_decrypt_by_magic(data: bytes) -> tuple[Optional[bytes], Optional[str]]:
    if not data:
        return None, None

    # (offset, magic, media_type)
    candidates: list[tuple[int, bytes, str]] = [
        (0, b"\x89PNG\r\n\x1a\n", "image/png"),
        (0, b"\xff\xd8\xff", "image/jpeg"),
        (0, b"GIF87a", "image/gif"),
        (0, b"GIF89a", "image/gif"),
        (0, b"wxgf", "application/octet-stream"),
        (1, b"wxgf", "application/octet-stream"),
        (2, b"wxgf", "application/octet-stream"),
        (3, b"wxgf", "application/octet-stream"),
        (4, b"wxgf", "application/octet-stream"),
        (5, b"wxgf", "application/octet-stream"),
        (6, b"wxgf", "application/octet-stream"),
        (7, b"wxgf", "application/octet-stream"),
        (8, b"wxgf", "application/octet-stream"),
        (9, b"wxgf", "application/octet-stream"),
        (10, b"wxgf", "application/octet-stream"),
        (11, b"wxgf", "application/octet-stream"),
        (12, b"wxgf", "application/octet-stream"),
        (13, b"wxgf", "application/octet-stream"),
        (14, b"wxgf", "application/octet-stream"),
        (15, b"wxgf", "application/octet-stream"),
        (0, b"RIFF", "application/octet-stream"),
        (4, b"ftyp", "video/mp4"),
    ]

    for offset, magic, mt in candidates:
        if len(data) < offset + len(magic):
            continue
        key = data[offset] ^ magic[0]
        ok = True
        for i in range(len(magic)):
            if (data[offset + i] ^ key) != magic[i]:
                ok = False
                break
        if not ok:
            continue

        decoded = bytes(b ^ key for b in data)

        if magic == b"wxgf":
            try:
                payload = decoded[offset:] if offset > 0 else decoded
                converted = _wxgf_to_image_bytes(payload)
                if converted:
                    mtw = _detect_image_media_type(converted[:32])
                    if mtw != "application/octet-stream":
                        return converted, mtw
            except Exception:
                pass
            continue

        if offset == 0 and magic == b"RIFF":
            if len(decoded) >= 12 and decoded[8:12] == b"WEBP":
                return decoded, "image/webp"
            continue

        if mt == "application/octet-stream":
            mt2 = _detect_image_media_type(decoded[:32])
            if mt2 != "application/octet-stream":
                return decoded, mt2
            continue

        return decoded, mt

    preview_len = 8192
    try:
        preview_len = min(int(preview_len), int(len(data)))
    except Exception:
        preview_len = 8192

    if preview_len > 0:
        for key in range(256):
            try:
                pv = bytes(b ^ key for b in data[:preview_len])
            except Exception:
                continue
            try:
                scan = pv
                if (
                    (scan.find(b"wxgf") >= 0)
                    or (scan.find(b"\x89PNG\r\n\x1a\n") >= 0)
                    or (scan.find(b"\xff\xd8\xff") >= 0)
                    or (scan.find(b"GIF87a") >= 0)
                    or (scan.find(b"GIF89a") >= 0)
                    or (scan.find(b"RIFF") >= 0)
                    or (scan.find(b"ftyp") >= 0)
                ):
                    decoded = bytes(b ^ key for b in data)
                    dec2, mt2 = _try_strip_media_prefix(decoded)
                    if mt2 != "application/octet-stream":
                        return dec2, mt2
            except Exception:
                continue

    return None, None


def _detect_wechat_dat_version(data: bytes) -> int:
    if not data or len(data) < 6:
        return -1
    sig = data[:6]
    if sig == b"\x07\x08V1\x08\x07":
        return 1
    if sig == b"\x07\x08V2\x08\x07":
        return 2
    return 0

@lru_cache(maxsize=4096)
def _fallback_search_media_by_file_id(
    weixin_root_str: str,
    file_id: str,
    kind: str = "",
    username: str = "",
) -> Optional[str]:
    """在微信数据目录里按文件名（file_id）兜底查找媒体文件。

    一些微信版本的图片消息不再直接提供 32 位 MD5，而是提供形如 `cdnthumburl` 的长串标识，
    本函数用于按文件名/前缀在 msg/attach、cache 等目录中定位对应的 .dat 资源文件。
    """
    if not weixin_root_str or not file_id:
        return None
    try:
        root = Path(weixin_root_str)
    except Exception:
        return None

    kind_key = str(kind or "").lower().strip()
    fid = str(file_id or "").strip()
    if not fid:
        return None

    # 优先在当前会话的 attach 子目录中查找（显著减少扫描范围）
    search_dirs: list[Path] = []
    if username:
        try:
            chat_hash = hashlib.md5(str(username).encode()).hexdigest()
            search_dirs.append(root / "msg" / "attach" / chat_hash)
        except Exception:
            pass

    if kind_key == "file":
        search_dirs.extend([root / "msg" / "file"])
    elif kind_key == "video" or kind_key == "video_thumb":
        search_dirs.extend([root / "msg" / "video", root / "cache"])
    else:
        search_dirs.extend([root / "msg" / "attach", root / "cache", root / "msg" / "file", root / "msg" / "video"])

    # de-dup while keeping order
    seen: set[str] = set()
    uniq_dirs: list[Path] = []
    for d in search_dirs:
        try:
            k = str(d.resolve())
        except Exception:
            k = str(d)
        if k in seen:
            continue
        seen.add(k)
        uniq_dirs.append(d)

    base = glob.escape(fid)
    has_suffix = bool(Path(fid).suffix)

    patterns: list[str] = []
    if has_suffix:
        patterns.append(base)
    else:
        patterns.extend(
            [
                f"{base}_h.dat",
                f"{base}_t.dat",
                f"{base}.dat",
                f"{base}*.dat",
                f"{base}.jpg",
                f"{base}.jpeg",
                f"{base}.png",
                f"{base}.gif",
                f"{base}.webp",
                f"{base}*",
            ]
        )

    for d in uniq_dirs:
        try:
            if not d.exists() or not d.is_dir():
                continue
        except Exception:
            continue
        for pat in patterns:
            try:
                for p in d.rglob(pat):
                    try:
                        if p.is_file():
                            return str(p)
                    except Exception:
                        continue
            except Exception:
                continue
    return None


def _save_media_keys(account_dir: Path, xor_key: int, aes_key16: Optional[bytes] = None) -> None:
    try:
        aes_str = ""
        if aes_key16:
            try:
                aes_str = aes_key16.decode("ascii", errors="ignore")[:16]
            except Exception:
                aes_str = ""
        payload = {
            "xor": int(xor_key),
            "aes": aes_str,
        }
        (account_dir / "_media_keys.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _decrypt_wechat_dat_v3(data: bytes, xor_key: int) -> bytes:
    return bytes(b ^ xor_key for b in data)


def _decrypt_wechat_dat_v4(data: bytes, xor_key: int, aes_key: bytes) -> bytes:
    from Crypto.Cipher import AES
    from Crypto.Util import Padding

    header, rest = data[:0xF], data[0xF:]
    signature, aes_size, xor_size = struct.unpack("<6sLLx", header)
    aes_size += AES.block_size - aes_size % AES.block_size

    aes_data = rest[:aes_size]
    raw_data = rest[aes_size:]

    cipher = AES.new(aes_key[:16], AES.MODE_ECB)
    decrypted_data = Padding.unpad(cipher.decrypt(aes_data), AES.block_size)

    if xor_size > 0:
        raw_data = rest[aes_size:-xor_size]
        xor_data = rest[-xor_size:]
        xored_data = bytes(b ^ xor_key for b in xor_data)
    else:
        xored_data = b""

    return decrypted_data + raw_data + xored_data


def _load_media_keys(account_dir: Path) -> dict[str, Any]:
    p = account_dir / "_media_keys.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_resource_dir(account_dir: Path) -> Path:
    """获取解密资源输出目录"""
    return account_dir / "resource"


def _get_decrypted_resource_path(account_dir: Path, md5: str, ext: str = "") -> Path:
    """根据MD5获取解密后资源的路径"""
    resource_dir = _get_resource_dir(account_dir)
    # 使用MD5前2位作为子目录，避免单目录文件过多
    sub_dir = md5[:2] if len(md5) >= 2 else "00"
    if ext:
        return resource_dir / sub_dir / f"{md5}.{ext}"
    return resource_dir / sub_dir / md5


def _detect_image_extension(data: bytes) -> str:
    """根据图片数据检测文件扩展名"""
    if not data:
        return "dat"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "gif"
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "webp"
    return "dat"


def _try_find_decrypted_resource(account_dir: Path, md5: str) -> Optional[Path]:
    """尝试在解密资源目录中查找已解密的资源"""
    if not md5:
        return None
    resource_dir = _get_resource_dir(account_dir)
    if not resource_dir.exists():
        return None
    sub_dir = md5[:2] if len(md5) >= 2 else "00"
    target_dir = resource_dir / sub_dir
    if not target_dir.exists():
        return None
    # 查找匹配MD5的文件（可能有不同扩展名）
    for ext in ["jpg", "png", "gif", "webp", "mp4", "dat"]:
        p = target_dir / f"{md5}.{ext}"
        if p.exists():
            return p
    return None


def _read_and_maybe_decrypt_media(
    path: Path,
    account_dir: Optional[Path] = None,
    weixin_root: Optional[Path] = None,
) -> tuple[bytes, str]:
    # Fast path: already a normal image
    with open(path, "rb") as f:
        head = f.read(64)

    mt = _detect_image_media_type(head)
    if mt != "application/octet-stream":
        return path.read_bytes(), mt

    if head.startswith(b"wxgf"):
        data0 = path.read_bytes()
        converted0 = _wxgf_to_image_bytes(data0)
        if converted0:
            mt0 = _detect_image_media_type(converted0[:32])
            if mt0 != "application/octet-stream":
                return converted0, mt0

    try:
        idx = head.find(b"wxgf")
    except Exception:
        idx = -1
    if 0 < idx <= 4:
        try:
            data0 = path.read_bytes()
            payload0 = data0[idx:]
            converted0 = _wxgf_to_image_bytes(payload0)
            if converted0:
                mt0 = _detect_image_media_type(converted0[:32])
                if mt0 != "application/octet-stream":
                    return converted0, mt0
        except Exception:
            pass

    try:
        data_pref = path.read_bytes()
        stripped, mtp = _try_strip_media_prefix(data_pref)
        if mtp != "application/octet-stream":
            return stripped, mtp
    except Exception:
        pass

    data = path.read_bytes()

    dec, mt2 = _try_xor_decrypt_by_magic(data)
    if dec is not None and mt2:
        return dec, mt2

    # Try WeChat .dat v1/v2 decrypt.
    version = _detect_wechat_dat_version(data)
    if version in (0, 1, 2):
        # 不在本项目内做任何密钥提取；仅使用用户保存的密钥（_media_keys.json）。
        xor_key: Optional[int] = None
        aes_key16 = b""
        if account_dir is not None:
            try:
                keys2 = _load_media_keys(account_dir)

                x2 = keys2.get("xor")
                if x2 is not None:
                    xor_key = int(x2)
                    if not (0 <= int(xor_key) <= 255):
                        xor_key = None
                    else:
                        logger.debug("使用 _media_keys.json 中保存的 xor key")

                aes_str = str(keys2.get("aes") or "").strip()
                if len(aes_str) >= 16:
                    aes_key16 = aes_str[:16].encode("ascii", errors="ignore")
            except Exception:
                xor_key = None
                aes_key16 = b""
        try:
            if version == 0 and xor_key is not None:
                out = _decrypt_wechat_dat_v3(data, xor_key)
                try:
                    out2, mtp2 = _try_strip_media_prefix(out)
                    if mtp2 != "application/octet-stream":
                        return out2, mtp2
                except Exception:
                    pass
                if out.startswith(b"wxgf"):
                    converted = _wxgf_to_image_bytes(out)
                    if converted:
                        out = converted
                        logger.info(f"wxgf->image: {path} -> {len(out)} bytes")
                    else:
                        logger.info(f"wxgf->image failed: {path}")
                mt0 = _detect_image_media_type(out[:32])
                if mt0 != "application/octet-stream":
                    return out, mt0
            elif version == 1 and xor_key is not None:
                out = _decrypt_wechat_dat_v4(data, xor_key, b"cfcd208495d565ef")
                try:
                    out2, mtp2 = _try_strip_media_prefix(out)
                    if mtp2 != "application/octet-stream":
                        return out2, mtp2
                except Exception:
                    pass
                if out.startswith(b"wxgf"):
                    converted = _wxgf_to_image_bytes(out)
                    if converted:
                        out = converted
                        logger.info(f"wxgf->image: {path} -> {len(out)} bytes")
                    else:
                        logger.info(f"wxgf->image failed: {path}")
                mt1 = _detect_image_media_type(out[:32])
                if mt1 != "application/octet-stream":
                    return out, mt1
            elif version == 2 and xor_key is not None and aes_key16:
                out = _decrypt_wechat_dat_v4(data, xor_key, aes_key16)
                try:
                    out2, mtp2 = _try_strip_media_prefix(out)
                    if mtp2 != "application/octet-stream":
                        return out2, mtp2
                except Exception:
                    pass
                if out.startswith(b"wxgf"):
                    converted = _wxgf_to_image_bytes(out)
                    if converted:
                        out = converted
                        logger.info(f"wxgf->image: {path} -> {len(out)} bytes")
                    else:
                        logger.info(f"wxgf->image failed: {path}")
                mt2b = _detect_image_media_type(out[:32])
                if mt2b != "application/octet-stream":
                    return out, mt2b
        except Exception:
            pass

    # Fallback: return as-is.
    mt3 = _guess_media_type_by_path(path, fallback="application/octet-stream")
    return data, mt3


def _ensure_decrypted_resource_for_md5(
    account_dir: Path,
    md5: str,
    source_path: Path,
    weixin_root: Optional[Path] = None,
) -> Optional[Path]:
    if not md5 or not source_path:
        return None

    md5_lower = str(md5).lower()
    existing = _try_find_decrypted_resource(account_dir, md5_lower)
    if existing:
        return existing

    try:
        if not source_path.exists() or not source_path.is_file():
            return None
    except Exception:
        return None

    data, mt0 = _read_and_maybe_decrypt_media(source_path, account_dir=account_dir, weixin_root=weixin_root)
    mt2 = str(mt0 or "").strip()
    if (not mt2) or mt2 == "application/octet-stream":
        mt2 = _detect_image_media_type(data[:32])
    if mt2 == "application/octet-stream":
        try:
            data2, mtp = _try_strip_media_prefix(data)
            if mtp != "application/octet-stream":
                data = data2
                mt2 = mtp
        except Exception:
            pass
    if mt2 == "application/octet-stream":
        try:
            if len(data) >= 8 and data[4:8] == b"ftyp":
                mt2 = "video/mp4"
        except Exception:
            pass
    if mt2 == "application/octet-stream":
        return None

    if str(mt2).startswith("image/"):
        ext = _detect_image_extension(data)
    elif str(mt2) == "video/mp4":
        ext = "mp4"
    else:
        ext = Path(str(source_path.name)).suffix.lstrip(".").lower() or "dat"
    output_path = _get_decrypted_resource_path(account_dir, md5_lower, ext)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not output_path.exists():
            output_path.write_bytes(data)
    except Exception:
        return None

    return output_path


def _collect_all_dat_files(wxid_dir: Path) -> list[tuple[Path, str]]:
    """收集所有需要解密的.dat文件，返回 (文件路径, md5) 列表"""
    results: list[tuple[Path, str]] = []
    if not wxid_dir or not wxid_dir.exists():
        return results

    # 搜索目录
    search_dirs = [
        wxid_dir / "msg" / "attach",
        wxid_dir / "cache",
    ]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        try:
            for dat_file in search_dir.rglob("*.dat"):
                if not dat_file.is_file():
                    continue
                # 从文件名提取MD5
                stem = dat_file.stem
                # 文件名格式可能是: md5.dat, md5_t.dat, md5_h.dat 等
                md5 = stem.split("_")[0] if "_" in stem else stem
                # 验证是否是有效的MD5（32位十六进制）
                if len(md5) == 32 and all(c in "0123456789abcdefABCDEF" for c in md5):
                    results.append((dat_file, md5.lower()))
        except Exception as e:
            logger.warning(f"扫描目录失败 {search_dir}: {e}")

    return results


def _decrypt_and_save_resource(
    dat_path: Path,
    md5: str,
    account_dir: Path,
    xor_key: int,
    aes_key: Optional[bytes],
) -> tuple[bool, str]:
    """解密单个资源文件并保存到resource目录

    Returns:
        (success, message)
    """
    try:
        data = dat_path.read_bytes()
        if not data:
            return False, "文件为空"

        version = _detect_wechat_dat_version(data)
        decrypted: Optional[bytes] = None

        if version == 0:
            # V3: 纯XOR解密
            decrypted = _decrypt_wechat_dat_v3(data, xor_key)
        elif version == 1:
            # V4-V1: 使用固定AES密钥
            decrypted = _decrypt_wechat_dat_v4(data, xor_key, b"cfcd208495d565ef")
        elif version == 2:
            # V4-V2: 需要动态AES密钥
            if aes_key and len(aes_key) >= 16:
                decrypted = _decrypt_wechat_dat_v4(data, xor_key, aes_key[:16])
            else:
                return False, "V4-V2版本需要AES密钥"
        else:
            # 尝试简单XOR解密
            dec, mt = _try_xor_decrypt_by_magic(data)
            if dec:
                decrypted = dec
            else:
                return False, f"未知加密版本: {version}"

        if not decrypted:
            return False, "解密结果为空"

        if decrypted.startswith(b"wxgf"):
            converted = _wxgf_to_image_bytes(decrypted)
            if converted:
                decrypted = converted

        # 检测图片类型
        ext = _detect_image_extension(decrypted)
        mt = _detect_image_media_type(decrypted[:32])
        if mt == "application/octet-stream":
            # 解密可能失败，跳过
            return False, "解密后非有效图片"

        # 保存到resource目录
        output_path = _get_decrypted_resource_path(account_dir, md5, ext)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(decrypted)

        return True, str(output_path)
    except Exception as e:
        return False, str(e)


def _convert_silk_to_wav(silk_data: bytes) -> bytes:
    """Convert SILK audio data to WAV format for browser playback."""
    import tempfile

    try:
        import pilk
    except ImportError:
        # If pilk not installed, return original data
        return silk_data

    try:
        # pilk.silk_to_wav works with file paths, so use temp files
        with tempfile.NamedTemporaryFile(suffix=".silk", delete=False) as silk_file:
            silk_file.write(silk_data)
            silk_path = silk_file.name

        wav_path = silk_path.replace(".silk", ".wav")

        try:
            pilk.silk_to_wav(silk_path, wav_path, rate=24000)
            with open(wav_path, "rb") as wav_file:
                wav_data = wav_file.read()
            return wav_data
        finally:
            # Clean up temp files
            import os

            try:
                os.unlink(silk_path)
            except Exception:
                pass
            try:
                os.unlink(wav_path)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"SILK to WAV conversion failed: {e}")
        return silk_data


def _resolve_media_path_for_kind(
    account_dir: Path,
    kind: str,
    md5: str,
    username: Optional[str],
) -> Optional[Path]:
    if not md5:
        return None

    kind_key = str(kind or "").strip().lower()

    # 优先查找解密后的资源目录（图片、表情、视频缩略图）
    if kind_key in {"image", "emoji", "video_thumb"}:
        decrypted_path = _try_find_decrypted_resource(account_dir, md5.lower())
        if decrypted_path:
            logger.debug(f"找到解密资源: {decrypted_path}")
            return decrypted_path

    # 回退到原始逻辑：从微信数据目录查找
    wxid_dir = _resolve_account_wxid_dir(account_dir)
    hardlink_db_path = account_dir / "hardlink.db"
    db_storage_dir = _resolve_account_db_storage_dir(account_dir)

    roots: list[Path] = []
    if wxid_dir:
        roots.append(wxid_dir)
        roots.append(wxid_dir / "msg" / "attach")
        roots.append(wxid_dir / "msg" / "file")
        roots.append(wxid_dir / "msg" / "video")
        roots.append(wxid_dir / "cache")
    if db_storage_dir:
        roots.append(db_storage_dir)
    if not roots:
        return None

    p = _resolve_media_path_from_hardlink(
        hardlink_db_path,
        roots[0],
        md5=str(md5),
        kind=str(kind),
        username=username,
        extra_roots=roots[1:],
    )
    if (not p) and wxid_dir:
        hit = _fallback_search_media_by_md5(str(wxid_dir), str(md5), kind=kind_key)
        if hit:
            p = Path(hit)
    return p


def _pick_best_emoji_source_path(resolved: Path, md5: str) -> Optional[Path]:
    if not resolved:
        return None
    try:
        if resolved.exists() and resolved.is_file():
            return resolved
    except Exception:
        pass

    try:
        if not (resolved.exists() and resolved.is_dir()):
            return None
    except Exception:
        return None

    md5s = str(md5 or "").lower().strip()
    if not md5s:
        return None

    candidates = [
        f"{md5s}_h.dat",
        f"{md5s}_t.dat",
        f"{md5s}.dat",
    ]
    exts = ["gif", "webp", "png", "jpg", "jpeg"]
    for ext in exts:
        candidates.append(f"{md5s}.{ext}")

    for name in candidates:
        p = resolved / name
        try:
            if p.exists() and p.is_file():
                return p
        except Exception:
            continue

    patterns = [f"{md5s}*.dat", f"{md5s}*", f"*{md5s}*"]
    for pat in patterns:
        try:
            for p in resolved.glob(pat):
                try:
                    if p.is_file():
                        return p
                except Exception:
                    continue
        except Exception:
            continue
    return None


def _iter_emoji_source_candidates(resolved: Path, md5: str, limit: int = 20) -> list[Path]:
    md5s = str(md5 or "").lower().strip()
    if not md5s:
        return []

    best = _pick_best_emoji_source_path(resolved, md5s)
    out: list[Path] = []
    if best:
        out.append(best)

    try:
        if not (resolved.exists() and resolved.is_dir()):
            return out
    except Exception:
        return out

    try:
        files = [p for p in resolved.iterdir() if p.is_file()]
    except Exception:
        files = []

    def score(p: Path) -> tuple[int, int, int]:
        name = str(p.name).lower()
        contains = 1 if md5s in name else 0
        ext = str(p.suffix).lower().lstrip(".")
        ext_rank = 0
        if ext == "dat":
            ext_rank = 3
        elif ext in {"gif", "webp"}:
            ext_rank = 2
        elif ext in {"png", "jpg", "jpeg"}:
            ext_rank = 1
        try:
            sz = int(p.stat().st_size)
        except Exception:
            sz = 0
        return (contains, ext_rank, sz)

    files_sorted = sorted(files, key=score, reverse=True)
    for p in files_sorted:
        if p not in out:
            out.append(p)
        if len(out) >= int(limit):
            break
    return out
