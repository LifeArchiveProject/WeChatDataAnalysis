"""微信解密工具的FastAPI Web服务器"""

import hashlib
import time
import re
import json
import os
import subprocess
import html
import ctypes
import base64
import mimetypes
import sqlite3
import struct
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional, Callable, Any
from urllib.parse import quote

try:
    import zstandard as zstd  # type: ignore
except Exception:
    zstd = None

try:
    import psutil  # type: ignore
except Exception:
    psutil = None

from fastapi import FastAPI, HTTPException, Request
from fastapi.routing import APIRoute
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse, StreamingResponse
from pydantic import BaseModel, Field
import asyncio

from .logging_config import setup_logging, get_logger
from .wechat_decrypt import decrypt_wechat_databases

# 初始化日志系统
setup_logging()
logger = get_logger(__name__)

# 仓库根目录（用于定位 output/databases）
_REPO_ROOT = Path(__file__).resolve().parents[2]
_OUTPUT_DATABASES_DIR = _REPO_ROOT / "output" / "databases"


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


def _should_keep_session(username: str, include_official: bool) -> bool:
    """会话过滤：默认排除公众号/系统会话（参考 echotrace 的过滤策略）"""
    if not username:
        return False

    if not include_official and username.startswith("gh_"):
        return False

    if username.startswith(("weixin", "qqmail", "fmessage", "medianote", "floatbottle", "newsapp")):
        return False

    if "@kefu.openim" in username:
        return False
    if "@openim" in username:
        return False
    if "service_" in username:
        return False

    if username in {
        "brandsessionholder",
        "brandservicesessionholder",
        "notifymessage",
        "opencustomerservicemsg",
        "notification_messages",
        "userexperience_alarm",
    }:
        return False

    return username.endswith("@chatroom") or username.startswith("wxid_") or ("@" not in username)


def _format_session_time(ts: Optional[int]) -> str:
    """格式化会话时间：今天显示 HH:MM，否则显示 MM/DD"""
    if not ts:
        return ""
    try:
        dt = datetime.fromtimestamp(int(ts))
        now = datetime.now()
        if dt.date() == now.date():
            return dt.strftime("%H:%M")
        return dt.strftime("%m/%d")
    except Exception:
        return ""


def _infer_last_message_brief(msg_type: Optional[int], sub_type: Optional[int]) -> str:
    """当 summary/draft 为空时，用类型生成占位摘要（英文文案）"""
    t = int(msg_type or 0)
    s = int(sub_type or 0)

    if t == 1:
        return "[Text]"
    if t == 3:
        return "[Image]"
    if t == 34:
        return "[Voice]"
    if t == 42:
        return "[Contact Card]"
    if t == 43:
        return "[Video]"
    if t == 47:
        return "[Emoji]"
    if t == 48:
        return "[Location]"
    if t == 49:
        if s == 5:
            return "[Link]"
        if s == 6:
            return "[File]"
        if s in (33, 36):
            return "[Mini Program]"
        if s == 57:
            return "[Quote]"
        if s in (63, 88):
            return "[Live]"
        if s == 87:
            return "[Announcement]"
        if s == 2000:
            return "[Transfer]"
        if s == 2003:
            return "[Red Packet]"
        if s == 19:
            return "[Chat History]"
        return "[App Message]"
    if t == 10000:
        return "[System]"
    return "[Message]"


def _infer_message_brief_by_local_type(local_type: Optional[int]) -> str:
    t = int(local_type or 0)
    if t == 1:
        return ""
    if t == 3:
        return "[Image]"
    if t == 34:
        return "[Voice]"
    if t == 43:
        return "[Video]"
    if t == 47:
        return "[Emoji]"
    if t == 48:
        return "[Location]"
    if t == 50:
        return "[VoIP]"
    if t == 10000:
        return "[System]"
    if t == 244813135921:
        return "[Quote]"
    if t == 17179869233:
        return "[Link]"
    if t == 21474836529:
        return "[Article]"
    if t == 154618822705:
        return "[Mini Program]"
    if t == 12884901937:
        return "[Music]"
    if t == 8594229559345:
        return "[Red Packet]"
    if t == 81604378673:
        return "[Chat History]"
    if t == 266287972401:
        return "[Pat]"
    if t == 8589934592049:
        return "[Transfer]"
    if t == 270582939697:
        return "[Live]"
    if t == 25769803825:
        return "[File]"
    return "[Message]"


def _quote_ident(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def _resolve_msg_table_name(conn: sqlite3.Connection, username: str) -> Optional[str]:
    if not username:
        return None
    md5_hex = hashlib.md5(username.encode("utf-8")).hexdigest()
    expected = f"msg_{md5_hex}".lower()

    expected_chat = f"chat_{md5_hex}".lower()

    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = [r[0] for r in rows if r and r[0]]

    for name in names:
        if str(name).lower() == expected:
            return str(name)

    for name in names:
        if str(name).lower() == expected_chat:
            return str(name)

    for name in names:
        ln = str(name).lower()
        if ln.startswith("msg_") and md5_hex in ln:
            return str(name)
        if ln.startswith("chat_") and md5_hex in ln:
            return str(name)

    for name in names:
        if md5_hex in str(name).lower():
            return str(name)

    partial = md5_hex[:24]
    for name in names:
        if partial in str(name).lower():
            return str(name)

    return None


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
    if kind_key == "image" or kind_key == "emoji":
        prefix = "image_hardlink_info"
    elif kind_key == "video" or kind_key == "video_thumb":
        prefix = "video_hardlink_info"
    elif kind_key == "file":
        prefix = "file_hardlink_info"
    else:
        return None

    conn = sqlite3.connect(str(hardlink_db_path))
    conn.row_factory = sqlite3.Row
    try:
        table_name = _resolve_hardlink_table_name(conn, prefix)
        if not table_name:
            return None

        quoted = _quote_ident(table_name)
        row = conn.execute(
            f"SELECT dir1, dir2, file_name FROM {quoted} WHERE md5 = ? ORDER BY modify_time DESC LIMIT 1",
            (md5,),
        ).fetchone()
        if not row:
            return None

        dir1 = str(row["dir1"] or "").strip()
        dir2 = str(row["dir2"] or "").strip()
        file_name = str(row["file_name"] or "").strip()
        if not dir1 or not dir2 or not file_name:
            return None

        dir_name = dir2
        dir2id_table = _resolve_hardlink_dir2id_table_name(conn)
        
        # WeChat 4.x: dir2id table only has 'username' column, use rowid to lookup
        if dir2id_table:
            try:
                # First try WeChat 4.x schema: lookup by rowid
                drow = conn.execute(
                    f"SELECT username FROM {_quote_ident(dir2id_table)} WHERE rowid = ? LIMIT 1",
                    (int(dir2),),
                ).fetchone()
                if drow and drow[0]:
                    dir_name = str(drow[0])
            except Exception:
                # Fallback to old schema with dir_id and username columns
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

        # Try multiple path patterns for different WeChat versions
        file_stem = Path(file_name).stem
        file_variants = [file_name, f"{file_stem}_h.dat", f"{file_stem}_t.dat"]
        
        for root in roots:
            # Pattern 1: Old structure - {root}/{dir1}/{dir_name}/{file}
            for fv in file_variants:
                p = (root / dir1 / dir_name / fv).resolve()
                try:
                    if p.exists() and p.is_file():
                        return p
                except Exception:
                    continue
            
            # Pattern 2: WeChat 4.x - {root}/msg/attach/{chat_hash}/{dir_name}/Img/{file}
            # chat_hash is MD5 of the username/chat_id
            if username:
                import hashlib
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
    
    # 根据类型选择搜索目录
    if kind_key == "file":
        search_dirs = [root / "msg" / "file"]
    else:
        search_dirs = [
            root / "msg" / "attach",
            root / "msg" / "file",
            root / "msg" / "video",
            root / "cache",
        ]
    
    # 根据类型选择搜索模式
    if kind_key == "file":
        # 文件类型：搜索所有包含md5的文件
        patterns = [
            f"*{md5}*",  # 任何包含md5的文件
        ]
    else:
        # 优先顺序: _h.dat (高清) > _t.dat (缩略图) > 普通 .dat > 其他格式
        # 因为基础 .dat 可能是 wxgf 容器格式，而 _h.dat/_t.dat 是真正的图片
        patterns = [
            f"{md5}_h.dat",  # 高清图优先
            f"{md5}_t.dat",  # 缩略图次之
            f"{md5}.dat",    # 基础 dat
            f"{md5}*.dat",   # 其他 dat 变体
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


@lru_cache(maxsize=16)
def _get_wechat_template_most_common_last2(weixin_root_str: str) -> Optional[bytes]:
    try:
        root = Path(weixin_root_str)
        if not root.exists() or not root.is_dir():
            return None
    except Exception:
        return None

    try:
        template_files = list(root.rglob("*_t.dat"))
    except Exception:
        template_files = []

    if not template_files:
        return None

    template_files.sort(key=_extract_yyyymm_for_sort, reverse=True)
    last_bytes_list: list[bytes] = []
    for file in template_files[:16]:
        try:
            with open(file, "rb") as f:
                f.seek(-2, 2)
                b2 = f.read(2)
                if b2 and len(b2) == 2:
                    last_bytes_list.append(b2)
        except Exception:
            continue

    if not last_bytes_list:
        return None
    return Counter(last_bytes_list).most_common(1)[0][0]


def _extract_yyyymm_for_sort(p: Path) -> str:
    m = re.search(r"(\d{4}-\d{2})", str(p))
    return m.group(1) if m else "0000-00"


@lru_cache(maxsize=16)
def _find_wechat_xor_key(weixin_root_str: str) -> Optional[int]:
    try:
        root = Path(weixin_root_str)
        if not root.exists() or not root.is_dir():
            return None
    except Exception:
        return None

    most_common = _get_wechat_template_most_common_last2(weixin_root_str)
    if not most_common or len(most_common) != 2:
        return None
    x, y = most_common[0], most_common[1]
    xor_key = x ^ 0xFF
    if xor_key != (y ^ 0xD9):
        return None
    return xor_key


def _get_wechat_v2_ciphertext(weixin_root: Path, most_common_last2: bytes) -> Optional[bytes]:
    try:
        template_files = list(weixin_root.rglob("*_t.dat"))
    except Exception:
        return None
    if not template_files:
        return None

    template_files.sort(key=_extract_yyyymm_for_sort, reverse=True)
    sig = b"\x07\x08V2\x08\x07"
    for file in template_files:
        try:
            with open(file, "rb") as f:
                if f.read(6) != sig:
                    continue
                f.seek(-2, 2)
                if f.read(2) != most_common_last2:
                    continue
                f.seek(0xF)
                ct = f.read(16)
                if ct and len(ct) == 16:
                    return ct
        except Exception:
            continue
    return None


def _verify_wechat_aes_key(ciphertext: bytes, key16: bytes) -> bool:
    try:
        from Crypto.Cipher import AES

        cipher = AES.new(key16[:16], AES.MODE_ECB)
        plain = cipher.decrypt(ciphertext)
        if plain.startswith(b"\xff\xd8\xff"):
            return True
        if plain.startswith(b"\x89PNG\r\n\x1a\n"):
            return True
        return False
    except Exception:
        return False


class _MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", ctypes.c_ulong),
        ("RegionSize", ctypes.c_size_t),
        ("State", ctypes.c_ulong),
        ("Protect", ctypes.c_ulong),
        ("Type", ctypes.c_ulong),
    ]


def _find_weixin_pid() -> Optional[int]:
    if psutil is None:
        return None
    for p in psutil.process_iter(["name"]):
        try:
            name = (p.info.get("name") or "").lower()
            if name in {"weixin.exe", "wechat.exe"}:
                return int(p.pid)
        except Exception:
            continue
    return None


def _extract_wechat_aes_key_from_process(ciphertext: bytes) -> Optional[bytes]:
    pid = _find_weixin_pid()
    if not pid:
        return None

    PROCESS_VM_READ = 0x0010
    PROCESS_QUERY_INFORMATION = 0x0400
    MEM_COMMIT = 0x1000
    MEM_PRIVATE = 0x20000

    kernel32 = ctypes.windll.kernel32

    OpenProcess = kernel32.OpenProcess
    OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_ulong]
    OpenProcess.restype = ctypes.c_void_p

    ReadProcessMemory = kernel32.ReadProcessMemory
    ReadProcessMemory.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    ReadProcessMemory.restype = ctypes.c_bool

    VirtualQueryEx = kernel32.VirtualQueryEx
    VirtualQueryEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    VirtualQueryEx.restype = ctypes.c_size_t

    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [ctypes.c_void_p]
    CloseHandle.restype = ctypes.c_bool

    handle = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not handle:
        return None

    stop = threading.Event()
    result: list[Optional[bytes]] = [None]
    pattern = re.compile(rb"[^a-z0-9]([a-z0-9]{32})[^a-z0-9]", flags=re.IGNORECASE)

    def read_mem(addr: int, size: int) -> Optional[bytes]:
        buf = ctypes.create_string_buffer(size)
        read = ctypes.c_size_t(0)
        ok = ReadProcessMemory(handle, ctypes.c_void_p(addr), buf, size, ctypes.byref(read))
        if not ok or read.value <= 0:
            return None
        return buf.raw[: read.value]

    def scan_region(base: int, region_size: int) -> Optional[bytes]:
        chunk = 4 * 1024 * 1024
        offset = 0
        tail = b""
        while offset < region_size and not stop.is_set():
            to_read = min(chunk, region_size - offset)
            b = read_mem(base + offset, int(to_read))
            if not b:
                return None
            data = tail + b
            for m in pattern.finditer(data):
                cand32 = m.group(1)
                cand16 = cand32[:16]
                if _verify_wechat_aes_key(ciphertext, cand16):
                    return cand16
            tail = data[-64:] if len(data) > 64 else data
            offset += to_read
        return None

    regions: list[tuple[int, int]] = []
    mbi = _MEMORY_BASIC_INFORMATION()
    addr = 0
    try:
        while VirtualQueryEx(handle, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            try:
                if int(mbi.State) == MEM_COMMIT and int(mbi.Type) == MEM_PRIVATE:
                    base = int(mbi.BaseAddress)
                    size = int(mbi.RegionSize)
                    if size > 0:
                        regions.append((base, size))
                addr = int(mbi.BaseAddress) + int(mbi.RegionSize)
            except Exception:
                addr += 0x1000
            if addr <= 0:
                break

        with ThreadPoolExecutor(max_workers=min(32, max(1, len(regions)))) as ex:
            for found in ex.map(lambda r: scan_region(r[0], r[1]), regions):
                if found:
                    result[0] = found
                    stop.set()
                    break
    finally:
        CloseHandle(handle)

    return result[0]


def _save_media_keys(account_dir: Path, xor_key: int, aes_key16: bytes) -> None:
    try:
        payload = {
            "xor": int(xor_key),
            "aes": aes_key16.decode("ascii", errors="ignore"),
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


# ===================== 解密资源目录相关辅助函数 =====================

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
    for ext in ["jpg", "png", "gif", "webp", "dat"]:
        p = target_dir / f"{md5}.{ext}"
        if p.exists():
            return p
    return None


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


def _read_and_maybe_decrypt_media(path: Path, account_dir: Optional[Path] = None, weixin_root: Optional[Path] = None) -> tuple[bytes, str]:
    # Fast path: already a normal image
    with open(path, "rb") as f:
        head = f.read(64)

    mt = _detect_image_media_type(head)
    if mt != "application/octet-stream":
        return path.read_bytes(), mt

    data = path.read_bytes()

    dec, mt2 = _try_xor_decrypt_by_magic(data)
    if dec is not None and mt2:
        return dec, mt2

    # Try WeChat .dat v1/v2 decrypt.
    version = _detect_wechat_dat_version(data)
    if version in (0, 1, 2):
        root = weixin_root
        if root is None and account_dir is not None:
            root = _resolve_account_wxid_dir(account_dir)
        if root is None and account_dir is not None:
            ds = _resolve_account_db_storage_dir(account_dir)
            root = ds.parent if ds else None

        xor_key = _find_wechat_xor_key(str(root)) if root else None
        try:
            if version == 0 and xor_key is not None:
                out = _decrypt_wechat_dat_v3(data, xor_key)
                mt0 = _detect_image_media_type(out[:32])
                if mt0 != "application/octet-stream":
                    return out, mt0
            elif version == 1 and xor_key is not None:
                out = _decrypt_wechat_dat_v4(data, xor_key, b"cfcd208495d565ef")
                mt1 = _detect_image_media_type(out[:32])
                if mt1 != "application/octet-stream":
                    return out, mt1
            elif version == 2 and xor_key is not None and account_dir is not None and root is not None:
                keys = _load_media_keys(account_dir)
                aes_str = str(keys.get("aes") or "").strip()
                aes_key16 = aes_str.encode("ascii", errors="ignore")[:16] if aes_str else b""

                if not aes_key16:
                    most_common = _get_wechat_template_most_common_last2(str(root))
                    if most_common:
                        ct = _get_wechat_v2_ciphertext(Path(root), most_common)
                    else:
                        ct = None

                    if ct:
                        aes_key16 = _extract_wechat_aes_key_from_process(ct) or b""
                        if aes_key16:
                            _save_media_keys(account_dir, xor_key, aes_key16)

                if aes_key16:
                    out = _decrypt_wechat_dat_v4(data, xor_key, aes_key16)
                    mt2b = _detect_image_media_type(out[:32])
                    if mt2b != "application/octet-stream":
                        return out, mt2b
        except Exception:
            pass

    # Fallback: return as-is.
    mt3 = _guess_media_type_by_path(path, fallback="application/octet-stream")
    return data, mt3


def _query_head_image_usernames(head_image_db_path: Path, usernames: list[str]) -> set[str]:
    uniq = list(dict.fromkeys([u for u in usernames if u]))
    if not uniq:
        return set()
    if not head_image_db_path.exists():
        return set()

    conn = sqlite3.connect(str(head_image_db_path))
    try:
        placeholders = ",".join(["?"] * len(uniq))
        rows = conn.execute(
            f"SELECT username FROM head_image WHERE username IN ({placeholders})",
            uniq,
        ).fetchall()
        return {str(r[0]) for r in rows if r and r[0]}
    finally:
        conn.close()


def _build_avatar_url(account_dir_name: str, username: str) -> str:
    return f"/api/chat/avatar?account={quote(account_dir_name)}&username={quote(username)}"


def _decode_sqlite_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="ignore")
        except Exception:
            return ""
    if isinstance(value, memoryview):
        try:
            return bytes(value).decode("utf-8", errors="ignore")
        except Exception:
            return ""
    return str(value)


def _is_mostly_printable_text(s: str) -> bool:
    if not s:
        return False
    sample = s[:600]
    if not sample:
        return False
    printable = sum(1 for ch in sample if ch.isprintable() or ch in {"\n", "\r", "\t"})
    return (printable / len(sample)) >= 0.85


def _looks_like_xml(s: str) -> bool:
    if not s:
        return False
    t = s.lstrip()
    if t.startswith('"') and t.endswith('"'):
        t = t.strip('"').lstrip()
    return t.startswith("<")


def _decode_message_content(compress_value: Any, message_value: Any) -> str:
    msg_text = _decode_sqlite_text(message_value)

    # Try zstd decompression on message_value if it's binary zstd data (e.g., emoji messages)
    if isinstance(message_value, (bytes, bytearray, memoryview)):
        raw = bytes(message_value) if isinstance(message_value, memoryview) else message_value
        if raw.startswith(b'\x28\xb5\x2f\xfd') and zstd is not None:
            try:
                out = zstd.decompress(raw)
                s = out.decode("utf-8", errors="ignore")
                s = html.unescape(s.strip())
                if _looks_like_xml(s) or _is_mostly_printable_text(s):
                    msg_text = s
            except Exception:
                pass

    if compress_value is None:
        return msg_text

    def try_decode_text_blob(text: str) -> Optional[str]:
        t = (text or "").strip()
        if not t:
            return None

        # hex
        if len(t) >= 16 and len(t) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", t):
            try:
                raw = bytes.fromhex(t)
                if zstd is not None:
                    try:
                        out = zstd.decompress(raw)
                        s2 = out.decode("utf-8", errors="ignore")
                        s2 = html.unescape(s2.strip())
                        if _looks_like_xml(s2) or _is_mostly_printable_text(s2):
                            return s2
                    except Exception:
                        pass
                s2 = raw.decode("utf-8", errors="ignore")
                s2 = html.unescape(s2.strip())
                if _looks_like_xml(s2) or _is_mostly_printable_text(s2):
                    return s2
            except Exception:
                return None

        # base64
        if len(t) >= 24 and len(t) % 4 == 0 and re.fullmatch(r"[A-Za-z0-9+/=]+", t):
            try:
                raw = base64.b64decode(t)
                if zstd is not None:
                    try:
                        out = zstd.decompress(raw)
                        s2 = out.decode("utf-8", errors="ignore")
                        s2 = html.unescape(s2.strip())
                        if _looks_like_xml(s2) or _is_mostly_printable_text(s2):
                            return s2
                    except Exception:
                        pass
                s2 = raw.decode("utf-8", errors="ignore")
                s2 = html.unescape(s2.strip())
                if _looks_like_xml(s2) or _is_mostly_printable_text(s2):
                    return s2
            except Exception:
                return None

        return None

    # Some DBs store compress_content already as TEXT/XML.
    if isinstance(compress_value, str):
        s = html.unescape(compress_value.strip())
        s2 = try_decode_text_blob(s)
        if s2:
            return s2
        if _looks_like_xml(s) or _is_mostly_printable_text(s):
            return s
        return msg_text

    data: Optional[bytes] = None
    if isinstance(compress_value, memoryview):
        data = bytes(compress_value)
    elif isinstance(compress_value, (bytes, bytearray)):
        data = bytes(compress_value)

    if not data:
        return msg_text

    # Try zstd first.
    if zstd is not None:
        try:
            out = zstd.decompress(data)
            s = out.decode("utf-8", errors="ignore")
            s = html.unescape(s.strip())
            if _looks_like_xml(s) or _is_mostly_printable_text(s):
                return s
        except Exception:
            pass

    # Fallback to plain utf-8 decode.
    try:
        s = data.decode("utf-8", errors="ignore")
        s = html.unescape(s.strip())
        s2 = try_decode_text_blob(s)
        if s2:
            return s2
        if _looks_like_xml(s) or _is_mostly_printable_text(s):
            return s
    except Exception:
        pass

    return msg_text


_MD5_HEX_RE = re.compile(rb"(?i)[0-9a-f]{32}")


def _extract_md5_from_blob(blob: Any) -> str:
    if blob is None:
        return ""
    if isinstance(blob, memoryview):
        data = bytes(blob)
    elif isinstance(blob, (bytes, bytearray)):
        data = bytes(blob)
    else:
        try:
            data = bytes(blob)
        except Exception:
            return ""

    if not data:
        return ""
    m = _MD5_HEX_RE.findall(data)
    if not m:
        return ""
    best = Counter([x.lower() for x in m]).most_common(1)[0][0]
    try:
        return best.decode("ascii", errors="ignore")
    except Exception:
        return ""


def _resource_lookup_chat_id(resource_conn: sqlite3.Connection, username: str) -> Optional[int]:
    if not username:
        return None
    try:
        row = resource_conn.execute(
            "SELECT rowid FROM ChatName2Id WHERE user_name = ? LIMIT 1",
            (username,),
        ).fetchone()
        if row and row[0] is not None:
            return int(row[0])
    except Exception:
        return None
    return None


def _lookup_resource_md5(
    resource_conn: sqlite3.Connection,
    chat_id: Optional[int],
    message_local_type: int,
    server_id: int,
    local_id: int,
    create_time: int,
) -> str:
    if server_id <= 0 and local_id <= 0:
        return ""

    where_chat = ""
    params_prefix: list[Any] = []
    if chat_id is not None and int(chat_id) > 0:
        where_chat = " AND chat_id = ?"
        params_prefix.append(int(chat_id))

    where_type = ""
    if int(message_local_type) > 0:
        where_type = " AND message_local_type = ?"
        params_prefix.append(int(message_local_type))

    try:
        if server_id > 0:
            row = resource_conn.execute(
                "SELECT packed_info FROM MessageResourceInfo WHERE message_svr_id = ?" + where_chat + where_type + " ORDER BY message_id DESC LIMIT 1",
                [int(server_id)] + params_prefix,
            ).fetchone()
            if row and row[0] is not None:
                md5 = _extract_md5_from_blob(row[0])
                if md5:
                    return md5
    except Exception:
        pass

    try:
        if local_id > 0 and create_time > 0:
            row = resource_conn.execute(
                "SELECT packed_info FROM MessageResourceInfo WHERE message_local_id = ? AND message_create_time = ?" + where_chat + where_type + " ORDER BY message_id DESC LIMIT 1",
                [int(local_id), int(create_time)] + params_prefix,
            ).fetchone()
            if row and row[0] is not None:
                return _extract_md5_from_blob(row[0])
    except Exception:
        pass

    return ""


def _strip_cdata(s: str) -> str:
    if not s:
        return ""
    out = s.replace("<![CDATA[", "").replace("]]>", "")
    return out.strip()


def _extract_xml_tag_text(xml_text: str, tag: str) -> str:
    if not xml_text or not tag:
        return ""
    m = re.search(rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>", xml_text, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return ""
    return _strip_cdata(m.group(1) or "")


def _extract_xml_attr(xml_text: str, attr: str) -> str:
    if not xml_text or not attr:
        return ""
    m = re.search(rf"{re.escape(attr)}\s*=\s*['\"]([^'\"]+)['\"]", xml_text, flags=re.IGNORECASE)
    return (m.group(1) or "").strip() if m else ""


def _extract_xml_tag_or_attr(xml_text: str, name: str) -> str:
    v = _extract_xml_tag_text(xml_text, name)
    if v:
        return v
    return _extract_xml_attr(xml_text, name)


def _extract_refermsg_block(xml_text: str) -> str:
    if not xml_text:
        return ""
    m = re.search(r"(<refermsg[^>]*>.*?</refermsg>)", xml_text, flags=re.IGNORECASE | re.DOTALL)
    return (m.group(1) or "").strip() if m else ""


def _infer_transfer_status_text(
    is_sent: bool,
    paysubtype: str,
    receivestatus: str,
    sendertitle: str,
    receivertitle: str,
    senderdes: str,
    receiverdes: str,
) -> str:
    t = str(paysubtype or "").strip()
    rs = str(receivestatus or "").strip()

    # Final states first
    if rs == "1":
        return "已收款"
    if rs == "2":
        return "已退还"
    if rs == "3":
        return "已过期"

    if t == "4":
        return "已退还"
    if t == "9":
        return "已被退还"
    if t == "10":
        return "已过期"

    # Non-final states (match oh-my-wechat component)
    if t == "8":
        return "发起转账"
    if t == "3":
        # paysubtype=3 表示收款方已收款
        # 对于发起方（isSent=True）显示"已收款"，表示对方已收
        # 对于收款方（isSent=False）显示"已被接收"，表示自己收到转账
        return "已收款" if is_sent else "已被接收"
    if t == "1":
        return "转账"

    # Fallback to titles/descriptions
    title = sendertitle if is_sent else receivertitle
    if title:
        return title
    des = senderdes if is_sent else receiverdes
    if des:
        return des
    return "转账"


def _split_group_sender_prefix(text: str) -> tuple[str, str]:
    if not text:
        return "", text
    sep = text.find(":\n")
    if sep <= 0:
        return "", text
    prefix = text[:sep].strip()
    body = text[sep + 2 :].lstrip("\n")
    if not prefix or len(prefix) > 128:
        return "", text
    if re.search(r"\s", prefix):
        return "", text
    if prefix.startswith("wxid_") or prefix.endswith("@chatroom") or "@" in prefix:
        return prefix, body
    return "", text


def _extract_sender_from_group_xml(xml_text: str) -> str:
    if not xml_text:
        return ""

    v = _extract_xml_tag_text(xml_text, "fromusername")
    if v:
        return v
    v = _extract_xml_attr(xml_text, "fromusername")
    if v:
        return v
    return ""


def _parse_pat_message(text: str, contact_rows: dict[str, sqlite3.Row]) -> str:
    template = _extract_xml_tag_text(text, "template")
    if not template:
        return "[拍一拍]"
    wxids = list({m.group(1) for m in re.finditer(r"\$\{([^}]+)\}", template) if m.group(1)})
    rendered = template
    for wxid in wxids:
        row = contact_rows.get(wxid)
        name = _pick_display_name(row, wxid)
        rendered = rendered.replace(f"${{{wxid}}}", name)
    return rendered.strip() or "[拍一拍]"


def _parse_quote_message(text: str) -> str:
    title = _extract_xml_tag_text(text, "title")
    if title:
        return title
    refer = _extract_xml_tag_text(text, "content")
    if refer:
        return refer
    return "[引用消息]"


def _parse_app_message(text: str) -> dict[str, Any]:
    app_type_raw = _extract_xml_tag_text(text, "type")
    try:
        app_type = int(str(app_type_raw or "0").strip() or "0")
    except Exception:
        app_type = 0
    title = _extract_xml_tag_text(text, "title")
    des = _extract_xml_tag_text(text, "des")
    url = _extract_xml_tag_text(text, "url")

    if "<patmsg" in text.lower() or "<template>" in text.lower():
        return {
            "renderType": "system",
            "content": "[拍一拍]",
        }

    if app_type in (5, 68) and url:
        thumb_url = _extract_xml_tag_text(text, "thumburl")
        return {
            "renderType": "link",
            "content": des or title or "[链接]",
            "title": title or des or "",
            "url": url,
            "thumbUrl": thumb_url or "",
        }

    if app_type in (6, 74):
        file_name = title or ""
        total_len = _extract_xml_tag_text(text, "totallen")
        file_md5 = (
            _extract_xml_tag_or_attr(text, "md5")
            or _extract_xml_tag_or_attr(text, "filemd5")
            or _extract_xml_tag_or_attr(text, "file_md5")
        )
        return {
            "renderType": "file",
            "content": f"[文件] {file_name}".strip(),
            "title": file_name,
            "size": total_len or "",
            "fileMd5": file_md5 or "",
        }

    if app_type == 57 or "<refermsg" in text:
        refer_block = _extract_refermsg_block(text)

        # Avoid picking <title> inside <refermsg> by stripping the refermsg block first.
        try:
            text_wo_refer = re.sub(
                r"(<refermsg[^>]*>.*?</refermsg>)",
                "",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
        except Exception:
            text_wo_refer = text

        reply_text = _extract_xml_tag_text(text_wo_refer, "title") or _extract_xml_tag_text(
            text, "title"
        )
        refer_displayname = _extract_xml_tag_or_attr(refer_block, "displayname")
        refer_content = _extract_xml_tag_text(refer_block, "content")
        refer_type = _extract_xml_tag_or_attr(refer_block, "type")

        # Some DBs embed the reply text as the first line of refer_content (causing duplication in UI).
        # Try to strip it if it looks like a prefix.
        rt = (reply_text or "").strip()
        rc = (refer_content or "").strip()
        if rt and rc:
            if rc == rt:
                refer_content = ""
            else:
                lines = [ln.strip() for ln in rc.splitlines()]
                if lines and lines[0] == rt:
                    refer_content = "\n".join(rc.splitlines()[1:]).lstrip()
                elif rc.startswith(rt):
                    rest = rc[len(rt) :].lstrip()
                    refer_content = rest

        # Make quote preview friendlier based on refer_type.
        t = str(refer_type or "").strip()
        if t == "3":
            refer_content = "[图片]"
        elif t == "47":
            refer_content = "[表情]"
        elif t == "43" or t == "62":
            refer_content = "[视频]"
        elif t == "34":
            refer_content = "[语音]"
        elif t == "49" and refer_content:
            refer_content = f"[链接] {refer_content}".strip()
        return {
            "renderType": "quote",
            "content": reply_text or "[引用消息]",
            "quoteTitle": refer_displayname or "",
            "quoteContent": refer_content or "",
        }

    if app_type == 2000 or "<wcpayinfo" in text and ("transfer" in text.lower() or "paysubtype" in text.lower()):
        feedesc = _extract_xml_tag_or_attr(text, "feedesc")
        pay_memo = _extract_xml_tag_or_attr(text, "pay_memo")
        paysubtype = _extract_xml_tag_or_attr(text, "paysubtype")
        receivestatus = _extract_xml_tag_or_attr(text, "receivestatus")
        sendertitle = _extract_xml_tag_or_attr(text, "sendertitle")
        receivertitle = _extract_xml_tag_or_attr(text, "receivertitle")
        senderdes = _extract_xml_tag_or_attr(text, "senderdes")
        receiverdes = _extract_xml_tag_or_attr(text, "receiverdes")
        transferid = _extract_xml_tag_or_attr(text, "transferid")
        invalidtime = _extract_xml_tag_or_attr(text, "invalidtime")
        # 调试日志：记录转账消息的关键字段
        logger.debug(
            f"[转账解析] paysubtype={paysubtype}, receivestatus={receivestatus}, "
            f"transferid={transferid}, feedesc={feedesc}"
        )
        return {
            "renderType": "transfer",
            "content": (pay_memo or "").strip(),
            "title": (feedesc or title or "").strip(),
            "amount": feedesc or "",
            "paySubType": str(paysubtype or "").strip(),
            "receiveStatus": str(receivestatus or "").strip(),
            "senderTitle": sendertitle or "",
            "receiverTitle": receivertitle or "",
            "senderDes": senderdes or "",
            "receiverDes": receiverdes or "",
            "transferId": str(transferid or "").strip(),
            "invalidTime": str(invalidtime or "").strip(),
        }

    if app_type in (2001, 2003) or "<wcpayinfo" in text and ("redenvelope" in text.lower() or "sendertitle" in text.lower()):
        sendertitle = _extract_xml_tag_text(text, "sendertitle")
        receivertitle = _extract_xml_tag_text(text, "receivertitle")
        senderdes = _extract_xml_tag_text(text, "senderdes")
        receiverdes = _extract_xml_tag_text(text, "receiverdes")
        cover = _extract_xml_tag_text(text, "receiverc2cshowsourceurl")
        return {
            "renderType": "redPacket",
            "content": (sendertitle or receivertitle or title or "红包").strip() or "红包",
            "title": (senderdes or receiverdes or des or "").strip(),
            "coverUrl": cover or "",
        }

    if title or des:
        return {
            "renderType": "text",
            "content": title or des,
        }

    return {
        "renderType": "text",
        "content": "[应用消息]",
    }


def _iter_message_db_paths(account_dir: Path) -> list[Path]:
    if not account_dir.exists():
        return []

    candidates: list[Path] = []
    for p in account_dir.glob("*.db"):
        n = p.name
        ln = n.lower()
        if ln in {"session.db", "contact.db", "head_image.db"}:
            continue
        if ln == "message_resource.db":
            continue

        if re.match(r"^message(_\d+)?\.db$", ln):
            candidates.append(p)
            continue
        if re.match(r"^biz_message(_\d+)?\.db$", ln):
            candidates.append(p)
            continue
        if "message" in ln and ln.endswith(".db"):
            candidates.append(p)
            continue
    candidates.sort(key=lambda x: x.name)
    return candidates


def _pick_display_name(contact_row: Optional[sqlite3.Row], fallback_username: str) -> str:
    """显示名优先级：remark > nick_name > alias > username"""
    if contact_row is None:
        return fallback_username

    for key in ("remark", "nick_name", "alias"):
        try:
            v = contact_row[key]
        except Exception:
            v = None
        if isinstance(v, str) and v.strip():
            return v.strip()

    return fallback_username


def _pick_avatar_url(contact_row: Optional[sqlite3.Row]) -> Optional[str]:
    """头像URL优先级：big_head_url > small_head_url"""
    if contact_row is None:
        return None

    for key in ("big_head_url", "small_head_url"):
        try:
            v = contact_row[key]
        except Exception:
            v = None
        if isinstance(v, str) and v.strip():
            return v.strip()

    return None


def _load_contact_rows(contact_db_path: Path, usernames: list[str]) -> dict[str, sqlite3.Row]:
    """批量加载联系人行数据：先查 contact，再查 stranger 补缺"""
    uniq = list(dict.fromkeys([u for u in usernames if u]))
    if not uniq:
        return {}

    result: dict[str, sqlite3.Row] = {}

    conn = sqlite3.connect(str(contact_db_path))
    conn.row_factory = sqlite3.Row
    try:
        def query_table(table: str, targets: list[str]) -> None:
            if not targets:
                return
            placeholders = ",".join(["?"] * len(targets))
            sql = f"""
                SELECT username, remark, nick_name, alias, big_head_url, small_head_url
                FROM {table}
                WHERE username IN ({placeholders})
            """
            rows = conn.execute(sql, targets).fetchall()
            for r in rows:
                result[r["username"]] = r

        query_table("contact", uniq)
        missing = [u for u in uniq if u not in result]
        query_table("stranger", missing)
        return result
    finally:
        conn.close()


class PathFixRequest(Request):
    """自定义Request类，自动修复JSON中的路径问题并检测相对路径"""

    def _is_absolute_path(self, path: str) -> bool:
        """检测是否为绝对路径，支持Windows、macOS、Linux"""
        if not path:
            return False

        # Windows绝对路径：以盘符开头 (C:\, D:\, etc.)
        if re.match(r'^[A-Za-z]:[/\\]', path):
            return True

        # Unix-like系统绝对路径：以 / 开头
        if path.startswith('/'):
            return True

        return False

    def _validate_paths_in_json(self, json_data: dict) -> Optional[str]:
        """验证JSON中的路径，返回错误信息（如果有）"""
        logger.info(f"开始验证路径，JSON数据: {json_data}")
        # 检查db_storage_path字段（现在是必需的）
        if 'db_storage_path' not in json_data:
            return "缺少必需的db_storage_path参数，请提供具体的数据库存储路径。"

        if 'db_storage_path' in json_data:
            path = json_data['db_storage_path']

            # 检查路径是否为空
            if not path or not path.strip():
                return "db_storage_path参数不能为空，请提供具体的数据库存储路径。"

            logger.info(f"检查路径: {path}")
            is_absolute = self._is_absolute_path(path)
            logger.info(f"是否为绝对路径: {is_absolute}")
            if not is_absolute:
                error_msg = f"请提供绝对路径，当前输入的是相对路径: {path}。\n" \
                           f"Windows绝对路径示例: D:\\wechatMSG\\xwechat_files\\wxid_xxx\\db_storage"
                return error_msg

            # 检查路径是否存在
            logger.info(f"检查路径是否存在: {path}")
            path_exists = os.path.exists(path)
            logger.info(f"路径存在性: {path_exists}")
            if not path_exists:
                # 检查父目录
                parent_path = os.path.dirname(path)
                logger.info(f"检查父目录: {parent_path}")
                parent_exists = os.path.exists(parent_path)
                logger.info(f"父目录存在性: {parent_exists}")
                if parent_exists:
                    try:
                        files = os.listdir(parent_path)
                        logger.info(f"父目录内容: {files}")
                        error_msg = f"指定的路径不存在: {path}\n" \
                                   f"父目录存在但不包含 'db_storage' 文件夹。\n" \
                                   f"请检查路径是否正确，或确保微信数据已生成。"
                    except PermissionError:
                        logger.info(f"无法访问父目录，权限不足")
                        error_msg = f"指定的路径不存在: {path}\n" \
                                   f"无法访问父目录，可能是权限问题。"
                else:
                    error_msg = f"指定的路径不存在: {path}\n" \
                               f"父目录也不存在，请检查路径是否正确。"
                logger.info(f"返回路径错误: {error_msg}")
                return error_msg
            else:
                logger.info(f"路径存在，使用递归方式检查数据库文件")
                try:
                    # 使用与自动检测相同的逻辑：递归查找.db文件
                    db_files = []
                    for root, dirs, files in os.walk(path):
                        # 只处理db_storage目录下的数据库文件（与自动检测逻辑一致）
                        if "db_storage" not in root:
                            continue
                        for file_name in files:
                            if not file_name.endswith(".db"):
                                continue
                            # 排除不需要解密的数据库（与自动检测逻辑一致）
                            if file_name in ["key_info.db"]:
                                continue
                            db_path = os.path.join(root, file_name)
                            db_files.append(db_path)

                    logger.info(f"递归查找到的数据库文件: {db_files}")
                    if not db_files:
                        error_msg = f"路径存在但没有找到有效的数据库文件: {path}\n" \
                                   f"请确保该目录或其子目录包含微信数据库文件(.db文件)。\n" \
                                   f"注意：key_info.db文件会被自动排除。"
                        logger.info(f"返回错误: 递归查找未找到有效.db文件")
                        return error_msg
                    logger.info(f"路径验证通过，递归找到{len(db_files)}个有效数据库文件")
                except PermissionError:
                    error_msg = f"无法访问路径: {path}\n" \
                               f"权限不足，请检查文件夹权限。"
                    return error_msg
                except Exception as e:
                    logger.warning(f"检查路径内容时出错: {e}")
                    # 如果无法检查内容，继续执行，让后续逻辑处理

        return None

    async def body(self) -> bytes:
        """重写body方法，预处理JSON中的路径问题"""
        body = await super().body()

        # 只处理JSON请求
        content_type = self.headers.get("content-type", "")
        if "application/json" not in content_type:
            return body

        try:
            # 将bytes转换为字符串
            body_str = body.decode('utf-8')

            # 首先尝试解析JSON以验证路径
            try:
                json_data = json.loads(body_str)
                path_error = self._validate_paths_in_json(json_data)
                if path_error:
                    logger.info(f"检测到路径错误: {path_error}")
                    # 我们将错误信息存储在请求中，稍后在路由处理器中检查
                    self.state.path_validation_error = path_error
                    return body
            except json.JSONDecodeError as e:
                # JSON格式错误，继续尝试修复
                logger.info(f"JSON解析失败，尝试修复: {e}")
                pass

            # 使用正则表达式安全地处理Windows路径中的反斜杠
            # 需要处理两种情况：
            # 1. 以盘符开头的绝对路径：D:\path\to\file
            # 2. 不以盘符开头的相对路径：wechatMSG\xwechat_files\...

            # 匹配引号内包含反斜杠的路径（不管是否以盘符开头）
            pattern = r'"([^"]*?\\[^"]*?)"'

            def fix_path(match):
                path = match.group(1)
                # 将单个反斜杠替换为双反斜杠，但避免替换已经转义的反斜杠
                fixed_path = re.sub(r'(?<!\\)\\(?!\\)', r'\\\\', path)
                return f'"{fixed_path}"'

            # 应用修复
            fixed_body_str = re.sub(pattern, fix_path, body_str)

            # 记录修复信息（仅在有修改时）
            if fixed_body_str != body_str:
                logger.info(f"自动修复JSON路径格式: {body_str[:100]}... -> {fixed_body_str[:100]}...")

            # 修复后重新验证路径
            try:
                json_data = json.loads(fixed_body_str)
                logger.info(f"修复后解析JSON成功，开始验证路径")
                path_error = self._validate_paths_in_json(json_data)
                if path_error:
                    logger.info(f"修复后检测到路径错误: {path_error}")
                    self.state.path_validation_error = path_error
                    return fixed_body_str.encode('utf-8')
                else:
                    logger.info(f"修复后路径验证通过")
            except json.JSONDecodeError as e:
                logger.warning(f"修复后JSON仍然解析失败: {e}")

            return fixed_body_str.encode('utf-8')

        except Exception as e:
            # 如果处理失败，返回原始body
            logger.warning(f"JSON路径修复失败，使用原始请求体: {e}")
            return body


class PathFixRoute(APIRoute):
    """自定义APIRoute类，使用PathFixRequest并处理路径验证错误"""

    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> any:
            # 将Request替换为我们的自定义Request
            custom_request = PathFixRequest(request.scope, request.receive)

            # 检查是否有路径验证错误
            if hasattr(custom_request.state, 'path_validation_error'):
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=400,
                    detail=custom_request.state.path_validation_error
                )

            return await original_route_handler(custom_request)

        return custom_route_handler


app = FastAPI(
    title="微信数据库解密工具",
    description="现代化的微信数据库解密工具，支持微信信息检测和数据库解密功能",
    version="0.1.0"
)

# 设置自定义路由类
app.router.route_class = PathFixRoute

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/chat/avatar", summary="获取联系人头像")
async def get_chat_avatar(username: str, account: Optional[str] = None):
    if not username:
        raise HTTPException(status_code=400, detail="Missing username.")
    account_dir = _resolve_account_dir(account)
    head_image_db_path = account_dir / "head_image.db"
    if not head_image_db_path.exists():
        raise HTTPException(status_code=404, detail="head_image.db not found.")

    conn = sqlite3.connect(str(head_image_db_path))
    try:
        row = conn.execute(
            "SELECT image_buffer FROM head_image WHERE username = ? ORDER BY update_time DESC LIMIT 1",
            (username,),
        ).fetchone()
    finally:
        conn.close()

    if not row or row[0] is None:
        raise HTTPException(status_code=404, detail="Avatar not found.")

    data = bytes(row[0]) if isinstance(row[0], (memoryview, bytearray)) else row[0]
    if not isinstance(data, (bytes, bytearray)):
        data = bytes(data)
    media_type = _detect_image_media_type(data)
    return Response(content=data, media_type=media_type)


@app.get("/api/chat/media/image", summary="获取图片消息资源")
async def get_chat_image(md5: str, account: Optional[str] = None, username: Optional[str] = None):
    if not md5:
        raise HTTPException(status_code=400, detail="Missing md5.")
    account_dir = _resolve_account_dir(account)
    
    # 优先从解密资源目录读取（更快）
    decrypted_path = _try_find_decrypted_resource(account_dir, md5.lower())
    if decrypted_path:
        data = decrypted_path.read_bytes()
        media_type = _detect_image_media_type(data[:32])
        return Response(content=data, media_type=media_type)
    
    # 回退到原始逻辑：从微信数据目录实时解密
    wxid_dir = _resolve_account_wxid_dir(account_dir)
    hardlink_db_path = account_dir / "hardlink.db"
    extra_roots: list[Path] = []
    db_storage_dir = _resolve_account_db_storage_dir(account_dir)
    if db_storage_dir:
        extra_roots.append(db_storage_dir)

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
        raise HTTPException(status_code=404, detail="wxid_dir/db_storage_path not found. Please decrypt with db_storage_path to enable media lookup.")
    p = _resolve_media_path_from_hardlink(
        hardlink_db_path,
        roots[0],
        md5=str(md5),
        kind="image",
        username=username,
        extra_roots=roots[1:],
    )
    if (not p) and wxid_dir:
        hit = _fallback_search_media_by_md5(str(wxid_dir), str(md5))
        if hit:
            p = Path(hit)
    if not p:
        raise HTTPException(status_code=404, detail="Image not found.")

    data, media_type = _read_and_maybe_decrypt_media(p, account_dir=account_dir, weixin_root=wxid_dir)
    return Response(content=data, media_type=media_type)


@app.get("/api/chat/media/emoji", summary="获取表情消息资源")
async def get_chat_emoji(md5: str, account: Optional[str] = None, username: Optional[str] = None):
    if not md5:
        raise HTTPException(status_code=400, detail="Missing md5.")
    account_dir = _resolve_account_dir(account)
    
    # 优先从解密资源目录读取（更快）
    decrypted_path = _try_find_decrypted_resource(account_dir, md5.lower())
    if decrypted_path:
        data = decrypted_path.read_bytes()
        media_type = _detect_image_media_type(data[:32])
        return Response(content=data, media_type=media_type)
    
    # 回退到原始逻辑
    wxid_dir = _resolve_account_wxid_dir(account_dir)
    hardlink_db_path = account_dir / "hardlink.db"
    extra_roots: list[Path] = []
    db_storage_dir = _resolve_account_db_storage_dir(account_dir)
    if db_storage_dir:
        extra_roots.append(db_storage_dir)

    roots: list[Path] = []
    if wxid_dir:
        roots.append(wxid_dir)
    if db_storage_dir:
        roots.append(db_storage_dir)
    if not roots:
        raise HTTPException(status_code=404, detail="wxid_dir/db_storage_path not found. Please decrypt with db_storage_path to enable media lookup.")
    p = _resolve_media_path_from_hardlink(
        hardlink_db_path,
        roots[0],
        md5=str(md5),
        kind="emoji",
        username=username,
        extra_roots=roots[1:],
    )
    if (not p) and wxid_dir:
        hit = _fallback_search_media_by_md5(str(wxid_dir), str(md5))
        if hit:
            p = Path(hit)
    if not p:
        raise HTTPException(status_code=404, detail="Emoji not found.")

    data, media_type = _read_and_maybe_decrypt_media(p, account_dir=account_dir, weixin_root=wxid_dir)
    return Response(content=data, media_type=media_type)


@app.get("/api/chat/media/video_thumb", summary="获取视频缩略图资源")
async def get_chat_video_thumb(md5: str, account: Optional[str] = None, username: Optional[str] = None):
    if not md5:
        raise HTTPException(status_code=400, detail="Missing md5.")
    account_dir = _resolve_account_dir(account)
    
    # 优先从解密资源目录读取（更快）
    decrypted_path = _try_find_decrypted_resource(account_dir, md5.lower())
    if decrypted_path:
        data = decrypted_path.read_bytes()
        media_type = _detect_image_media_type(data[:32])
        return Response(content=data, media_type=media_type)
    
    # 回退到原始逻辑
    wxid_dir = _resolve_account_wxid_dir(account_dir)
    hardlink_db_path = account_dir / "hardlink.db"
    extra_roots: list[Path] = []
    db_storage_dir = _resolve_account_db_storage_dir(account_dir)
    if db_storage_dir:
        extra_roots.append(db_storage_dir)

    roots: list[Path] = []
    if wxid_dir:
        roots.append(wxid_dir)
    if db_storage_dir:
        roots.append(db_storage_dir)
    if not roots:
        raise HTTPException(status_code=404, detail="wxid_dir/db_storage_path not found. Please decrypt with db_storage_path to enable media lookup.")
    p = _resolve_media_path_from_hardlink(
        hardlink_db_path,
        roots[0],
        md5=str(md5),
        kind="video_thumb",
        username=username,
        extra_roots=roots[1:],
    )
    if (not p) and wxid_dir:
        hit = _fallback_search_media_by_md5(str(wxid_dir), str(md5))
        if hit:
            p = Path(hit)
    if not p:
        raise HTTPException(status_code=404, detail="Video thumbnail not found.")

    data, media_type = _read_and_maybe_decrypt_media(p, account_dir=account_dir, weixin_root=wxid_dir)
    return Response(content=data, media_type=media_type)


@app.get("/api/chat/media/video", summary="获取视频资源")
async def get_chat_video(md5: str, account: Optional[str] = None, username: Optional[str] = None):
    if not md5:
        raise HTTPException(status_code=400, detail="Missing md5.")
    account_dir = _resolve_account_dir(account)
    wxid_dir = _resolve_account_wxid_dir(account_dir)
    hardlink_db_path = account_dir / "hardlink.db"
    extra_roots: list[Path] = []
    db_storage_dir = _resolve_account_db_storage_dir(account_dir)
    if db_storage_dir:
        extra_roots.append(db_storage_dir)

    roots: list[Path] = []
    if wxid_dir:
        roots.append(wxid_dir)
    if db_storage_dir:
        roots.append(db_storage_dir)
    if not roots:
        raise HTTPException(status_code=404, detail="wxid_dir/db_storage_path not found. Please decrypt with db_storage_path to enable media lookup.")
    p = _resolve_media_path_from_hardlink(
        hardlink_db_path,
        roots[0],
        md5=str(md5),
        kind="video",
        username=username,
        extra_roots=roots[1:],
    )
    if (not p) and wxid_dir:
        hit = _fallback_search_media_by_md5(str(wxid_dir), str(md5))
        if hit:
            p = Path(hit)
    if not p:
        raise HTTPException(status_code=404, detail="Video not found.")
    media_type = _guess_media_type_by_path(p, fallback="video/mp4")
    return FileResponse(str(p), media_type=media_type)


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


@app.get("/api/chat/media/voice", summary="获取语音消息资源")
async def get_chat_voice(server_id: int, account: Optional[str] = None):
    if not server_id:
        raise HTTPException(status_code=400, detail="Missing server_id.")
    account_dir = _resolve_account_dir(account)
    media_db_path = account_dir / "media_0.db"
    if not media_db_path.exists():
        raise HTTPException(status_code=404, detail="media_0.db not found.")

    conn = sqlite3.connect(str(media_db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT voice_data FROM VoiceInfo WHERE svr_id = ? ORDER BY create_time DESC LIMIT 1",
            (int(server_id),),
        ).fetchone()
    except Exception:
        row = None
    finally:
        conn.close()

    if not row or row[0] is None:
        raise HTTPException(status_code=404, detail="Voice not found.")

    data = bytes(row[0]) if isinstance(row[0], (memoryview, bytearray)) else row[0]
    if not isinstance(data, (bytes, bytearray)):
        data = bytes(data)

    # Try to convert SILK to WAV for browser playback
    wav_data = _convert_silk_to_wav(data)
    if wav_data != data:
        return Response(
            content=wav_data,
            media_type="audio/wav",
        )

    # Fallback to raw SILK if conversion fails
    return Response(
        content=data,
        media_type="audio/silk",
        headers={"Content-Disposition": f"attachment; filename=voice_{int(server_id)}.silk"},
    )


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


@app.post("/api/chat/media/open_folder", summary="在资源管理器中打开媒体文件所在位置")
async def open_chat_media_folder(
    kind: str,
    md5: Optional[str] = None,
    server_id: Optional[int] = None,
    account: Optional[str] = None,
    username: Optional[str] = None,
):
    account_dir = _resolve_account_dir(account)

    kind_key = str(kind or "").strip().lower()
    if kind_key not in {"image", "emoji", "video", "video_thumb", "file", "voice"}:
        raise HTTPException(status_code=400, detail="Unsupported kind.")

    p: Optional[Path] = None
    if kind_key == "voice":
        if not server_id:
            raise HTTPException(status_code=400, detail="Missing server_id.")

        media_db_path = account_dir / "media_0.db"
        if not media_db_path.exists():
            raise HTTPException(status_code=404, detail="media_0.db not found.")

        conn = sqlite3.connect(str(media_db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT voice_data FROM VoiceInfo WHERE svr_id = ? ORDER BY create_time DESC LIMIT 1",
                (int(server_id),),
            ).fetchone()
        except Exception:
            row = None
        finally:
            conn.close()

        if not row or row[0] is None:
            raise HTTPException(status_code=404, detail="Voice not found.")

        data = bytes(row[0]) if isinstance(row[0], (memoryview, bytearray)) else row[0]
        if not isinstance(data, (bytes, bytearray)):
            data = bytes(data)

        export_dir = account_dir / "_exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        p = export_dir / f"voice_{int(server_id)}.silk"
        try:
            p.write_bytes(data)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to export voice: {e}")
    else:
        if not md5:
            raise HTTPException(status_code=400, detail="Missing md5.")
        p = _resolve_media_path_for_kind(account_dir, kind=kind_key, md5=str(md5), username=username)

    if not p:
        raise HTTPException(status_code=404, detail="File not found.")

    try:
        target = str(p.resolve())
    except Exception:
        target = str(p)

    if os.name != "nt":
        raise HTTPException(status_code=400, detail="open_folder is only supported on Windows.")

    try:
        subprocess.Popen(["explorer", "/select,", target])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open explorer: {e}")

    return {"status": "success", "path": target}


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录所有HTTP请求的中间件"""
    start_time = time.time()

    # 记录请求开始
    logger.info(f"请求开始: {request.method} {request.url}")

    # 处理请求
    response = await call_next(request)

    # 计算处理时间
    process_time = time.time() - start_time

    # 记录请求完成
    logger.info(f"请求完成: {request.method} {request.url} - 状态码: {response.status_code} - 耗时: {process_time:.3f}s")

    return response


class DecryptRequest(BaseModel):
    """解密请求模型"""
    key: str = Field(..., description="解密密钥，64位十六进制字符串")
    db_storage_path: str = Field(..., description="数据库存储路径，必须是绝对路径")





@app.get("/", summary="根端点")
async def root():
    """根端点"""
    logger.info("访问根端点")
    return {"message": "微信数据库解密工具 API"}





@app.get("/api/wechat-detection", summary="详细检测微信安装信息")
async def detect_wechat_detailed(data_root_path: Optional[str] = None):
    """详细检测微信安装信息，包括版本、路径、消息目录等。"""
    logger.info("开始执行微信检测")
    try:
        from .wechat_detection import detect_wechat_installation, detect_current_logged_in_account
        info = detect_wechat_installation(data_root_path=data_root_path)
        
        # 检测当前登录账号
        current_account_info = detect_current_logged_in_account(data_root_path)
        info['current_account'] = current_account_info

        # 添加一些统计信息
        stats = {
            'total_databases': len(info['databases']),
            'total_user_accounts': len(info['user_accounts']),
            'total_message_dirs': len(info['message_dirs']),
            'has_wechat_installed': info['wechat_install_path'] is not None,
            'detection_time': __import__('datetime').datetime.now().isoformat()
        }

        logger.info(f"微信检测完成: 检测到 {stats['total_user_accounts']} 个账户, {stats['total_databases']} 个数据库")

        return {
            'status': 'success',
            'data': info,
            'statistics': stats
        }
    except Exception as e:
        logger.error(f"微信检测失败: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'data': None,
            'statistics': None
        }


@app.get("/api/current-account", summary="检测当前登录账号")
async def detect_current_account(data_root_path: Optional[str] = None):
    """检测当前登录的微信账号"""
    logger.info("开始检测当前登录账号")
    try:
        from .wechat_detection import detect_current_logged_in_account
        result = detect_current_logged_in_account(data_root_path)
        
        logger.info(f"当前账号检测完成: {result.get('message', '无结果')}")
        
        return {
            'status': 'success',
            'data': result
        }
    except Exception as e:
        logger.error(f"当前账号检测失败: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'data': None
        }





@app.post("/api/decrypt", summary="解密微信数据库")
async def decrypt_databases(request: DecryptRequest):
    """使用提供的密钥解密指定账户的微信数据库

    参数:
    - key: 解密密钥（必选）- 64位十六进制字符串
    - db_storage_path: 数据库存储路径（必选），如 D:\\wechatMSG\\xwechat_files\\{微信id}\\db_storage

    注意：
    - 一个密钥只能解密对应账户的数据库
    - 必须提供具体的db_storage_path，不支持自动检测多账户
    - 支持自动处理Windows路径中的反斜杠转义问题
    """
    logger.info(f"开始解密请求: db_storage_path={request.db_storage_path}")
    try:
        # 验证密钥格式
        if not request.key or len(request.key) != 64:
            logger.warning(f"密钥格式无效: 长度={len(request.key) if request.key else 0}")
            raise HTTPException(status_code=400, detail="密钥格式无效，必须是64位十六进制字符串")

        # 使用新的解密API
        results = decrypt_wechat_databases(
            db_storage_path=request.db_storage_path,
            key=request.key
        )

        if results["status"] == "error":
            logger.error(f"解密失败: {results['message']}")
            raise HTTPException(status_code=400, detail=results["message"])

        logger.info(f"解密完成: 成功 {results['successful_count']}/{results['total_databases']} 个数据库")

        return {
            "status": "completed" if results["status"] == "success" else "failed",
            "total_databases": results["total_databases"],
            "success_count": results["successful_count"],
            "failure_count": results["failed_count"],
            "output_directory": results["output_directory"],
            "message": results["message"],
            "processed_files": results["processed_files"],
            "failed_files": results["failed_files"],
            "account_results": results.get("account_results", {})
        }

    except Exception as e:
        logger.error(f"解密API异常: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chat/accounts", summary="列出已解密账号")
async def list_chat_accounts():
    """列出 output/databases 下可用于聊天预览的账号目录"""
    accounts = _list_decrypted_accounts()
    if not accounts:
        return {
            "status": "error",
            "accounts": [],
            "default_account": None,
            "message": "No decrypted databases found. Please decrypt first.",
        }

    return {
        "status": "success",
        "accounts": accounts,
        "default_account": accounts[0],
    }


@app.get("/api/chat/sessions", summary="获取会话列表（聊天左侧列表）")
async def list_chat_sessions(
    request: Request,
    account: Optional[str] = None,
    limit: int = 400,
    include_hidden: bool = False,
    include_official: bool = False,
):
    """从 session.db + contact.db 读取会话列表，用于前端聊天界面动态渲染联系人"""
    if limit <= 0:
        raise HTTPException(status_code=400, detail="Invalid limit.")
    if limit > 2000:
        limit = 2000

    account_dir = _resolve_account_dir(account)
    session_db_path = account_dir / "session.db"
    contact_db_path = account_dir / "contact.db"
    head_image_db_path = account_dir / "head_image.db"
    base_url = str(request.base_url).rstrip("/")

    sconn = sqlite3.connect(str(session_db_path))
    sconn.row_factory = sqlite3.Row
    try:
        rows = sconn.execute(
            """
            SELECT
                username,
                unread_count,
                is_hidden,
                summary,
                draft,
                last_timestamp,
                sort_timestamp,
                last_msg_type,
                last_msg_sub_type
            FROM SessionTable
            ORDER BY sort_timestamp DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    finally:
        sconn.close()

    filtered: list[sqlite3.Row] = []
    usernames: list[str] = []
    for r in rows:
        username = r["username"] or ""
        if not username:
            continue
        if not include_hidden and int(r["is_hidden"] or 0) == 1:
            continue
        if not _should_keep_session(username, include_official=include_official):
            continue
        filtered.append(r)
        usernames.append(username)

    contact_rows = _load_contact_rows(contact_db_path, usernames)
    local_avatar_usernames = _query_head_image_usernames(head_image_db_path, usernames)

    sessions: list[dict[str, Any]] = []
    for r in filtered:
        username = r["username"]
        c_row = contact_rows.get(username)

        display_name = _pick_display_name(c_row, username)
        avatar_url = _pick_avatar_url(c_row)
        if not avatar_url and username in local_avatar_usernames:
            avatar_url = base_url + _build_avatar_url(account_dir.name, username)

        summary = (r["summary"] or "").strip() if isinstance(r["summary"], str) else (r["summary"] or "")
        draft = (r["draft"] or "").strip() if isinstance(r["draft"], str) else (r["draft"] or "")

        if draft:
            last_message = f"[Draft] {draft}"
        elif summary:
            last_message = summary
        else:
            last_message = _infer_last_message_brief(r["last_msg_type"], r["last_msg_sub_type"])

        last_time = _format_session_time(r["sort_timestamp"] or r["last_timestamp"])

        sessions.append(
            {
                "id": username,
                "username": username,
                "name": display_name,
                "avatar": avatar_url,
                "lastMessage": last_message,
                "lastMessageTime": last_time,
                "unreadCount": int(r["unread_count"] or 0),
                "isGroup": bool(username.endswith("@chatroom")),
            }
        )

    return {
        "status": "success",
        "account": account_dir.name,
        "total": len(sessions),
        "sessions": sessions,
    }


@app.get("/api/chat/messages", summary="获取会话消息列表")
async def list_chat_messages(
    request: Request,
    username: str,
    account: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    order: str = "asc",
):
    if not username:
        raise HTTPException(status_code=400, detail="Missing username.")
    if limit <= 0:
        raise HTTPException(status_code=400, detail="Invalid limit.")
    if limit > 500:
        limit = 500
    if offset < 0:
        offset = 0

    account_dir = _resolve_account_dir(account)
    db_paths = _iter_message_db_paths(account_dir)
    contact_db_path = account_dir / "contact.db"
    head_image_db_path = account_dir / "head_image.db"
    message_resource_db_path = account_dir / "message_resource.db"
    base_url = str(request.base_url).rstrip("/")
    if not db_paths:
        return {
            "status": "error",
            "account": account_dir.name,
            "username": username,
            "total": 0,
            "messages": [],
            "message": "No message databases found for this account.",
        }

    resource_conn: Optional[sqlite3.Connection] = None
    resource_chat_id: Optional[int] = None
    try:
        if message_resource_db_path.exists():
            resource_conn = sqlite3.connect(str(message_resource_db_path))
            resource_conn.row_factory = sqlite3.Row
            resource_chat_id = _resource_lookup_chat_id(resource_conn, username)
    except Exception:
        if resource_conn is not None:
            try:
                resource_conn.close()
            except Exception:
                pass
        resource_conn = None
        resource_chat_id = None

    want_asc = str(order or "").lower() != "desc"
    take = int(limit) + int(offset)
    take_probe = take + 1
    merged: list[dict[str, Any]] = []
    sender_usernames: list[str] = []
    pat_usernames: set[str] = set()
    is_group = bool(username.endswith("@chatroom"))
    has_more_any = False

    for db_path in db_paths:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            table_name = _resolve_msg_table_name(conn, username)
            if not table_name:
                continue

            my_wxid = account_dir.name
            my_rowid = None
            try:
                r = conn.execute(
                    "SELECT rowid FROM Name2Id WHERE user_name = ? LIMIT 1",
                    (my_wxid,),
                ).fetchone()
                if r is not None:
                    my_rowid = int(r[0])
            except Exception:
                my_rowid = None

            quoted_table = _quote_ident(table_name)
            sql_with_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, n.user_name AS sender_username "
                f"FROM {quoted_table} m "
                "LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid "
                "ORDER BY m.create_time DESC, m.sort_seq DESC, m.local_id DESC "
                "LIMIT ?"
            )
            sql_no_join = (
                "SELECT "
                "m.local_id, m.server_id, m.local_type, m.sort_seq, m.real_sender_id, m.create_time, "
                "m.message_content, m.compress_content, '' AS sender_username "
                f"FROM {quoted_table} m "
                "ORDER BY m.create_time DESC, m.sort_seq DESC, m.local_id DESC "
                "LIMIT ?"
            )

            # Force sqlite3 to return TEXT as raw bytes for this query, so we can zstd-decompress
            # compress_content reliably.
            conn.text_factory = bytes

            try:
                rows = conn.execute(sql_with_join, (take_probe,)).fetchall()
            except Exception:
                rows = conn.execute(sql_no_join, (take_probe,)).fetchall()
            if len(rows) > take:
                has_more_any = True
                rows = rows[:take]

            for r in rows:
                local_id = int(r["local_id"] or 0)
                create_time = int(r["create_time"] or 0)
                sort_seq = int(r["sort_seq"] or 0) if r["sort_seq"] is not None else 0
                local_type = int(r["local_type"] or 0)
                sender_username = _decode_sqlite_text(r["sender_username"]).strip()

                is_sent = False
                if my_rowid is not None:
                    try:
                        is_sent = int(r["real_sender_id"] or 0) == int(my_rowid)
                    except Exception:
                        is_sent = False

                raw_text = _decode_message_content(r["compress_content"], r["message_content"])
                raw_text = raw_text.strip()

                sender_prefix = ""
                if is_group and not raw_text.startswith("<") and not raw_text.startswith('"<'):
                    sender_prefix, raw_text = _split_group_sender_prefix(raw_text)

                if is_group and sender_prefix:
                    sender_username = sender_prefix

                if is_group and (raw_text.startswith("<") or raw_text.startswith('"<')):
                    xml_sender = _extract_sender_from_group_xml(raw_text)
                    if xml_sender:
                        sender_username = xml_sender

                if is_sent:
                    sender_username = account_dir.name
                elif (not is_group) and (not sender_username):
                    sender_username = username

                if sender_username:
                    sender_usernames.append(sender_username)

                render_type = "text"
                content_text = raw_text
                title = ""
                url = ""
                image_md5 = ""
                emoji_md5 = ""
                emoji_url = ""
                thumb_url = ""
                image_url = ""
                video_md5 = ""
                video_thumb_md5 = ""
                video_url = ""
                video_thumb_url = ""
                voice_length = ""
                quote_title = ""
                quote_content = ""
                amount = ""
                cover_url = ""
                file_size = ""
                pay_sub_type = ""
                transfer_status = ""
                file_md5 = ""
                transfer_id = ""

                if local_type == 10000:
                    render_type = "system"
                    if "revokemsg" in raw_text:
                        content_text = "撤回了一条消息"
                    else:
                        content_text = re.sub(r"</?[_a-zA-Z0-9]+[^>]*>", "", raw_text)
                        content_text = re.sub(r"\s+", " ", content_text).strip() or "[系统消息]"
                elif local_type == 49:
                    parsed = _parse_app_message(raw_text)
                    render_type = str(parsed.get("renderType") or "text")
                    content_text = str(parsed.get("content") or "")
                    title = str(parsed.get("title") or "")
                    url = str(parsed.get("url") or "")
                    quote_title = str(parsed.get("quoteTitle") or "")
                    quote_content = str(parsed.get("quoteContent") or "")
                    amount = str(parsed.get("amount") or "")
                    cover_url = str(parsed.get("coverUrl") or "")
                    thumb_url = str(parsed.get("thumbUrl") or "")
                    file_size = str(parsed.get("size") or "")
                    pay_sub_type = str(parsed.get("paySubType") or "")
                    file_md5 = str(parsed.get("fileMd5") or "")
                    transfer_id = str(parsed.get("transferId") or "")

                    if render_type == "transfer":
                        # 直接从原始 XML 提取 transferid（可能在 wcpayinfo 内）
                        if not transfer_id:
                            transfer_id = _extract_xml_tag_or_attr(raw_text, "transferid") or ""
                        transfer_status = _infer_transfer_status_text(
                            is_sent=is_sent,
                            paysubtype=pay_sub_type,
                            receivestatus=str(parsed.get("receiveStatus") or ""),
                            sendertitle=str(parsed.get("senderTitle") or ""),
                            receivertitle=str(parsed.get("receiverTitle") or ""),
                            senderdes=str(parsed.get("senderDes") or ""),
                            receiverdes=str(parsed.get("receiverDes") or ""),
                        )
                        if not content_text:
                            content_text = transfer_status or "转账"
                elif local_type == 266287972401:
                    render_type = "system"
                    template = _extract_xml_tag_text(raw_text, "template")
                    if template:
                        pat_usernames.update({m.group(1) for m in re.finditer(r"\$\{([^}]+)\}", template) if m.group(1)})
                        content_text = "[拍一拍]"
                    else:
                        content_text = "[拍一拍]"
                elif local_type == 244813135921:
                    render_type = "quote"
                    parsed = _parse_app_message(raw_text)
                    content_text = str(parsed.get("content") or "[引用消息]")
                    quote_title = str(parsed.get("quoteTitle") or "")
                    quote_content = str(parsed.get("quoteContent") or "")
                elif local_type == 3:
                    render_type = "image"
                    image_md5 = _extract_xml_attr(raw_text, "md5")
                    # Extract CDN URL and validate it looks like a proper URL
                    _cdn_url = (
                        _extract_xml_attr(raw_text, "cdnthumburl")
                        or _extract_xml_attr(raw_text, "cdnmidimgurl")
                        or _extract_xml_attr(raw_text, "cdnbigimgurl")
                    )
                    image_url = _cdn_url if _cdn_url.startswith(("http://", "https://")) else ""
                    if (not image_md5) and resource_conn is not None:
                        image_md5 = _lookup_resource_md5(
                            resource_conn,
                            resource_chat_id,
                            message_local_type=local_type,
                            server_id=int(r["server_id"] or 0),
                            local_id=local_id,
                            create_time=create_time,
                        )
                    content_text = "[图片]"
                elif local_type == 34:
                    render_type = "voice"
                    duration = _extract_xml_attr(raw_text, "voicelength")
                    voice_length = duration
                    content_text = f"[语音 {duration}秒]" if duration else "[语音]"
                elif local_type == 43 or local_type == 62:
                    render_type = "video"
                    video_md5 = _extract_xml_attr(raw_text, "md5")
                    video_thumb_md5 = _extract_xml_attr(raw_text, "cdnthumbmd5")
                    video_thumb_url = _extract_xml_attr(raw_text, "cdnthumburl")
                    video_url = _extract_xml_attr(raw_text, "cdnvideourl")
                    if (not video_thumb_md5) and resource_conn is not None:
                        video_thumb_md5 = _lookup_resource_md5(
                            resource_conn,
                            resource_chat_id,
                            message_local_type=local_type,
                            server_id=int(r["server_id"] or 0),
                            local_id=local_id,
                            create_time=create_time,
                        )
                    content_text = "[视频]"
                elif local_type == 47:
                    render_type = "emoji"
                    emoji_md5 = _extract_xml_attr(raw_text, "md5")
                    if not emoji_md5:
                        emoji_md5 = _extract_xml_tag_text(raw_text, "md5")
                    emoji_url = _extract_xml_attr(raw_text, "cdnurl")
                    if not emoji_url:
                        emoji_url = _extract_xml_tag_text(raw_text, "cdn_url")
                    if (not emoji_md5) and resource_conn is not None:
                        emoji_md5 = _lookup_resource_md5(
                            resource_conn,
                            resource_chat_id,
                            message_local_type=local_type,
                            server_id=int(r["server_id"] or 0),
                            local_id=local_id,
                            create_time=create_time,
                        )
                    content_text = "[表情]"
                elif local_type != 1:
                    if not content_text:
                        content_text = _infer_message_brief_by_local_type(local_type)
                    else:
                        if content_text.startswith("<") or content_text.startswith('"<'):
                            if "<appmsg" in content_text.lower():
                                parsed = _parse_app_message(content_text)
                                rt = str(parsed.get("renderType") or "")
                                if rt and rt != "text":
                                    render_type = rt
                                    content_text = str(parsed.get("content") or content_text)
                                    title = str(parsed.get("title") or title)
                                    url = str(parsed.get("url") or url)
                                    quote_title = str(parsed.get("quoteTitle") or quote_title)
                                    quote_content = str(parsed.get("quoteContent") or quote_content)
                                    amount = str(parsed.get("amount") or amount)
                                    cover_url = str(parsed.get("coverUrl") or cover_url)
                                    thumb_url = str(parsed.get("thumbUrl") or thumb_url)
                                    file_size = str(parsed.get("size") or file_size)
                                    pay_sub_type = str(parsed.get("paySubType") or pay_sub_type)
                                    file_md5 = str(parsed.get("fileMd5") or file_md5)
                                    transfer_id = str(parsed.get("transferId") or transfer_id)

                                    if render_type == "transfer":
                                        # 如果 transferId 仍为空，尝试从原始 XML 提取
                                        if not transfer_id:
                                            transfer_id = _extract_xml_tag_or_attr(content_text, "transferid") or ""
                                        transfer_status = _infer_transfer_status_text(
                                            is_sent=is_sent,
                                            paysubtype=pay_sub_type,
                                            receivestatus=str(parsed.get("receiveStatus") or ""),
                                            sendertitle=str(parsed.get("senderTitle") or ""),
                                            receivertitle=str(parsed.get("receiverTitle") or ""),
                                            senderdes=str(parsed.get("senderDes") or ""),
                                            receiverdes=str(parsed.get("receiverDes") or ""),
                                        )
                                        if not content_text:
                                            content_text = transfer_status or "转账"
                            t = _extract_xml_tag_text(content_text, "title")
                            d = _extract_xml_tag_text(content_text, "des")
                            content_text = t or d or _infer_message_brief_by_local_type(local_type)

                if not content_text:
                    content_text = _infer_message_brief_by_local_type(local_type)

                merged.append(
                    {
                        "id": f"{db_path.stem}:{table_name}:{local_id}",
                        "localId": local_id,
                        "serverId": int(r["server_id"] or 0),
                        "type": local_type,
                        "createTime": create_time,
                        "sortSeq": sort_seq,
                        "senderUsername": sender_username,
                        "isSent": bool(is_sent),
                        "renderType": render_type,
                        "content": content_text,
                        "title": title,
                        "url": url,
                        "imageMd5": image_md5,
                        "emojiMd5": emoji_md5,
                        "emojiUrl": emoji_url,
                        "thumbUrl": thumb_url,
                        "imageUrl": image_url,
                        "videoMd5": video_md5,
                        "videoThumbMd5": video_thumb_md5,
                        "videoUrl": video_url,
                        "videoThumbUrl": video_thumb_url,
                        "voiceLength": voice_length,
                        "quoteTitle": quote_title,
                        "quoteContent": quote_content,
                        "amount": amount,
                        "coverUrl": cover_url,
                        "fileSize": file_size,
                        "fileMd5": file_md5,
                        "paySubType": pay_sub_type,
                        "transferStatus": transfer_status,
                        "transferId": transfer_id,
                        "_rawText": raw_text if local_type == 266287972401 else "",
                    }
                )
        finally:
            conn.close()

    if resource_conn is not None:
        try:
            resource_conn.close()
        except Exception:
            pass

    # 后处理：关联转账消息的最终状态
    # 策略：优先使用 transferId 精确匹配，回退到金额+时间窗口匹配
    # paysubtype 含义：1=不明确 3=已收款 4=对方退回给你 8=发起转账 9=被对方退回 10=已过期

    # 收集已退还和已收款的转账ID和金额
    returned_transfer_ids: set[str] = set()  # 退还状态的 transferId
    received_transfer_ids: set[str] = set()  # 已收款状态的 transferId
    returned_amounts_with_time: list[tuple[str, int]] = []  # (金额, 时间戳) 用于退还回退匹配
    received_amounts_with_time: list[tuple[str, int]] = []  # (金额, 时间戳) 用于收款回退匹配

    for m in merged:
        if m.get("renderType") == "transfer":
            pst = str(m.get("paySubType") or "")
            tid = str(m.get("transferId") or "").strip()
            amt = str(m.get("amount") or "")
            ts = int(m.get("createTime") or 0)

            if pst in ("4", "9"):  # 退还状态
                if tid:
                    returned_transfer_ids.add(tid)
                if amt:
                    returned_amounts_with_time.append((amt, ts))
            elif pst == "3":  # 已收款状态
                if tid:
                    received_transfer_ids.add(tid)
                if amt:
                    received_amounts_with_time.append((amt, ts))

    # 更新原始转账消息的状态
    for m in merged:
        if m.get("renderType") == "transfer":
            pst = str(m.get("paySubType") or "")
            # 只更新未确定状态的原始转账消息（paysubtype=1 或 8）
            if pst in ("1", "8"):
                tid = str(m.get("transferId") or "").strip()
                amt = str(m.get("amount") or "")
                ts = int(m.get("createTime") or 0)

                # 优先检查退还状态（退还优先于收款）
                should_mark_returned = False
                should_mark_received = False

                # 策略1：精确 transferId 匹配
                if tid:
                    if tid in returned_transfer_ids:
                        should_mark_returned = True
                    elif tid in received_transfer_ids:
                        should_mark_received = True

                # 策略2：回退到金额+时间窗口匹配（24小时内同金额）
                if not should_mark_returned and not should_mark_received and amt:
                    for ret_amt, ret_ts in returned_amounts_with_time:
                        if ret_amt == amt and abs(ret_ts - ts) <= 86400:
                            should_mark_returned = True
                            break
                    if not should_mark_returned:
                        for rec_amt, rec_ts in received_amounts_with_time:
                            if rec_amt == amt and abs(rec_ts - ts) <= 86400:
                                should_mark_received = True
                                break

                if should_mark_returned:
                    m["paySubType"] = "9"
                    m["transferStatus"] = "已被退还"
                elif should_mark_received:
                    m["paySubType"] = "3"
                    # 根据 isSent 判断：发起方显示"已收款"，收款方显示"已被接收"
                    is_sent = m.get("isSent", False)
                    m["transferStatus"] = "已收款" if is_sent else "已被接收"

    uniq_senders = list(dict.fromkeys([u for u in (sender_usernames + list(pat_usernames)) if u]))
    sender_contact_rows = _load_contact_rows(contact_db_path, uniq_senders)
    local_sender_avatars = _query_head_image_usernames(head_image_db_path, uniq_senders)

    for m in merged:
        su = str(m.get("senderUsername") or "")
        if not su:
            continue
        row = sender_contact_rows.get(su)
        m["senderDisplayName"] = _pick_display_name(row, su)
        avatar_url = _pick_avatar_url(row)
        if not avatar_url and su in local_sender_avatars:
            avatar_url = base_url + _build_avatar_url(account_dir.name, su)
        m["senderAvatar"] = avatar_url

        # Media URL fallback: if CDN URLs missing, use local media endpoints.
        try:
            rt = str(m.get("renderType") or "")
            if rt == "image":
                if (not str(m.get("imageUrl") or "")) and str(m.get("imageMd5") or ""):
                    md5 = str(m.get("imageMd5") or "")
                    m["imageUrl"] = (
                        base_url
                        + f"/api/chat/media/image?account={quote(account_dir.name)}&md5={quote(md5)}&username={quote(username)}"
                    )
            elif rt == "emoji":
                if (not str(m.get("emojiUrl") or "")) and str(m.get("emojiMd5") or ""):
                    md5 = str(m.get("emojiMd5") or "")
                    m["emojiUrl"] = (
                        base_url
                        + f"/api/chat/media/emoji?account={quote(account_dir.name)}&md5={quote(md5)}&username={quote(username)}"
                    )
            elif rt == "video":
                if (not str(m.get("videoThumbUrl") or "")) and str(m.get("videoThumbMd5") or ""):
                    md5 = str(m.get("videoThumbMd5") or "")
                    m["videoThumbUrl"] = (
                        base_url
                        + f"/api/chat/media/video_thumb?account={quote(account_dir.name)}&md5={quote(md5)}&username={quote(username)}"
                    )
                if (not str(m.get("videoUrl") or "")) and str(m.get("videoMd5") or ""):
                    md5 = str(m.get("videoMd5") or "")
                    m["videoUrl"] = (
                        base_url
                        + f"/api/chat/media/video?account={quote(account_dir.name)}&md5={quote(md5)}&username={quote(username)}"
                    )
            elif rt == "voice":
                if str(m.get("serverId") or ""):
                    sid = int(m.get("serverId") or 0)
                    if sid:
                        m["voiceUrl"] = base_url + f"/api/chat/media/voice?account={quote(account_dir.name)}&server_id={sid}"
        except Exception:
            pass

        if int(m.get("type") or 0) == 266287972401:
            raw = str(m.get("_rawText") or "")
            if raw:
                m["content"] = _parse_pat_message(raw, sender_contact_rows)

        if "_rawText" in m:
            m.pop("_rawText", None)

    def sort_key(m: dict[str, Any]) -> tuple[int, int, int]:
        sseq = int(m.get("sortSeq") or 0)
        cts = int(m.get("createTime") or 0)
        lid = int(m.get("localId") or 0)
        primary = sseq or cts
        return (primary, cts, lid)

    merged.sort(key=sort_key, reverse=True)
    has_more_global = bool(has_more_any or (len(merged) > (int(offset) + int(limit))))
    page = merged[int(offset) : int(offset) + int(limit)]
    if want_asc:
        page = list(reversed(page))

    return {
        "status": "success",
        "account": account_dir.name,
        "username": username,
        "total": int(offset) + len(page) + (1 if has_more_global else 0),
        "hasMore": bool(has_more_global),
        "messages": page,
    }


# ===================== 图片密钥与资源解密相关 API =====================

class MediaKeysRequest(BaseModel):
    """媒体密钥请求模型"""
    account: Optional[str] = Field(None, description="账号目录名（可选，默认使用第一个）")
    force_extract: bool = Field(False, description="是否强制从微信进程重新提取密钥")


class MediaDecryptRequest(BaseModel):
    """媒体解密请求模型"""
    account: Optional[str] = Field(None, description="账号目录名（可选，默认使用第一个）")
    xor_key: Optional[str] = Field(None, description="XOR密钥（十六进制，如 0xA5 或 A5）")
    aes_key: Optional[str] = Field(None, description="AES密钥（16字符ASCII字符串）")


@app.get("/api/media/keys", summary="获取图片解密密钥")
async def get_media_keys(account: Optional[str] = None, force_extract: bool = False):
    """获取图片解密密钥（XOR和AES）
    
    如果已缓存密钥且不强制提取，直接返回缓存的密钥。
    否则尝试从微信进程中提取密钥。
    
    注意：提取AES密钥需要微信进程正在运行。
    """
    account_dir = _resolve_account_dir(account)
    wxid_dir = _resolve_account_wxid_dir(account_dir)
    
    # 尝试加载已缓存的密钥
    cached_keys = _load_media_keys(account_dir)
    if cached_keys and not force_extract:
        xor_key = cached_keys.get("xor")
        aes_key = cached_keys.get("aes")
        if xor_key is not None and aes_key:
            return {
                "status": "success",
                "source": "cache",
                "xor_key": f"0x{int(xor_key):02X}",
                "aes_key": str(aes_key)[:16] if aes_key else "",
                "message": "已从缓存加载密钥",
            }
    
    if not wxid_dir:
        return {
            "status": "error",
            "message": "未找到微信数据目录，请确保已正确配置 db_storage_path",
        }
    
    # 尝试提取XOR密钥
    xor_key = _find_wechat_xor_key(str(wxid_dir))
    if xor_key is None:
        return {
            "status": "error",
            "message": "无法提取XOR密钥，请确保微信数据目录中存在 _t.dat 模板文件",
        }
    
    # 尝试提取AES密钥（需要微信进程运行）
    aes_key16: Optional[bytes] = None
    aes_message = ""
    
    most_common = _get_wechat_template_most_common_last2(str(wxid_dir))
    if most_common:
        ct = _get_wechat_v2_ciphertext(wxid_dir, most_common)
        if ct:
            aes_key16 = _extract_wechat_aes_key_from_process(ct)
            if aes_key16:
                aes_message = "已从微信进程提取AES密钥"
                # 保存密钥到缓存
                _save_media_keys(account_dir, xor_key, aes_key16)
            else:
                aes_message = "无法从微信进程提取AES密钥（微信是否正在运行？）"
        else:
            aes_message = "未找到V2加密模板文件"
    else:
        aes_message = "未找到足够的模板文件用于提取AES密钥"
    
    return {
        "status": "success",
        "source": "extracted",
        "xor_key": f"0x{xor_key:02X}",
        "aes_key": aes_key16.decode("ascii", errors="ignore") if aes_key16 else "",
        "message": f"XOR密钥提取成功。{aes_message}",
    }


@app.post("/api/media/keys", summary="保存图片解密密钥")
async def save_media_keys_api(request: MediaKeysRequest, xor_key: str, aes_key: str):
    """手动保存图片解密密钥
    
    参数:
    - xor_key: XOR密钥（十六进制格式，如 0xA5 或 A5）
    - aes_key: AES密钥（16字符ASCII字符串）
    """
    account_dir = _resolve_account_dir(request.account)
    
    # 解析XOR密钥
    try:
        xor_hex = xor_key.strip().lower().replace("0x", "")
        xor_int = int(xor_hex, 16)
    except Exception:
        raise HTTPException(status_code=400, detail="XOR密钥格式无效，请使用十六进制格式如 0xA5")
    
    # 验证AES密钥
    aes_str = aes_key.strip()
    if len(aes_str) < 16:
        raise HTTPException(status_code=400, detail="AES密钥长度不足，需要至少16个字符")
    
    # 保存密钥
    _save_media_keys(account_dir, xor_int, aes_str[:16].encode("ascii", errors="ignore"))
    
    return {
        "status": "success",
        "message": "密钥已保存",
        "xor_key": f"0x{xor_int:02X}",
        "aes_key": aes_str[:16],
    }


@app.post("/api/media/decrypt_all", summary="批量解密所有图片资源")
async def decrypt_all_media(request: MediaDecryptRequest):
    """批量解密所有图片资源到 output/databases/{账号}/resource 目录
    
    解密后的图片按MD5哈希命名，存储在 resource/{md5前2位}/{md5}.{ext} 路径下。
    这样可以快速通过MD5定位资源文件。
    
    参数:
    - account: 账号目录名（可选）
    - xor_key: XOR密钥（可选，不提供则从缓存读取）
    - aes_key: AES密钥（可选，不提供则从缓存读取）
    """
    account_dir = _resolve_account_dir(request.account)
    wxid_dir = _resolve_account_wxid_dir(account_dir)
    
    if not wxid_dir:
        raise HTTPException(
            status_code=400,
            detail="未找到微信数据目录，请确保已正确配置 db_storage_path",
        )
    
    # 获取密钥
    xor_key: Optional[int] = None
    aes_key16: Optional[bytes] = None
    
    if request.xor_key:
        try:
            xor_hex = request.xor_key.strip().lower().replace("0x", "")
            xor_key = int(xor_hex, 16)
        except Exception:
            raise HTTPException(status_code=400, detail="XOR密钥格式无效")
    
    if request.aes_key:
        aes_str = request.aes_key.strip()
        if len(aes_str) >= 16:
            aes_key16 = aes_str[:16].encode("ascii", errors="ignore")
    
    # 如果未提供密钥，尝试从缓存加载
    if xor_key is None or aes_key16 is None:
        cached = _load_media_keys(account_dir)
        if xor_key is None:
            xor_key = cached.get("xor")
        if aes_key16 is None:
            aes_str = str(cached.get("aes") or "").strip()
            if len(aes_str) >= 16:
                aes_key16 = aes_str[:16].encode("ascii", errors="ignore")
    
    # 如果仍然没有XOR密钥，尝试自动提取
    if xor_key is None:
        xor_key = _find_wechat_xor_key(str(wxid_dir))
    
    if xor_key is None:
        raise HTTPException(
            status_code=400,
            detail="未找到XOR密钥，请先调用 /api/media/keys 获取密钥或手动提供",
        )
    
    # 收集所有.dat文件
    logger.info(f"开始扫描 {wxid_dir} 中的.dat文件...")
    dat_files = _collect_all_dat_files(wxid_dir)
    total_files = len(dat_files)
    logger.info(f"共发现 {total_files} 个.dat文件")
    
    if total_files == 0:
        return {
            "status": "success",
            "message": "未发现需要解密的.dat文件",
            "total": 0,
            "success_count": 0,
            "skip_count": 0,
            "fail_count": 0,
            "output_dir": str(_get_resource_dir(account_dir)),
        }
    
    # 开始解密
    success_count = 0
    skip_count = 0
    fail_count = 0
    failed_files: list[dict] = []
    
    resource_dir = _get_resource_dir(account_dir)
    resource_dir.mkdir(parents=True, exist_ok=True)
    
    for dat_path, md5 in dat_files:
        # 检查是否已解密
        existing = _try_find_decrypted_resource(account_dir, md5)
        if existing:
            skip_count += 1
            continue
        
        # 解密并保存
        success, msg = _decrypt_and_save_resource(
            dat_path, md5, account_dir, xor_key, aes_key16
        )
        
        if success:
            success_count += 1
        else:
            fail_count += 1
            if len(failed_files) < 100:  # 只记录前100个失败
                failed_files.append({
                    "file": str(dat_path),
                    "md5": md5,
                    "error": msg,
                })
    
    logger.info(
        f"解密完成: 成功={success_count}, 跳过={skip_count}, 失败={fail_count}"
    )
    
    return {
        "status": "success",
        "message": f"解密完成: 成功 {success_count}, 跳过 {skip_count}, 失败 {fail_count}",
        "total": total_files,
        "success_count": success_count,
        "skip_count": skip_count,
        "fail_count": fail_count,
        "output_dir": str(resource_dir),
        "failed_files": failed_files[:20] if failed_files else [],
    }


@app.get("/api/media/resource/{md5}", summary="获取已解密的资源文件")
async def get_decrypted_resource(md5: str, account: Optional[str] = None):
    """直接从解密资源目录获取图片
    
    如果资源已解密，直接返回解密后的文件。
    这比实时解密更快，适合频繁访问的场景。
    """
    if not md5 or len(md5) != 32:
        raise HTTPException(status_code=400, detail="无效的MD5")
    
    account_dir = _resolve_account_dir(account)
    p = _try_find_decrypted_resource(account_dir, md5.lower())
    
    if not p:
        raise HTTPException(status_code=404, detail="资源未找到，请先执行批量解密")
    
    data = p.read_bytes()
    media_type = _detect_image_media_type(data[:32])
    return Response(content=data, media_type=media_type)


@app.get("/api/media/decrypt_all_stream", summary="批量解密所有图片资源（SSE实时进度）")
async def decrypt_all_media_stream(
    account: Optional[str] = None,
    xor_key: Optional[str] = None,
    aes_key: Optional[str] = None,
):
    """批量解密所有图片资源，通过SSE实时推送进度
    
    返回格式为Server-Sent Events，每条消息包含:
    - type: progress/complete/error
    - current: 当前处理数量
    - total: 总文件数
    - success_count: 成功数
    - skip_count: 跳过数（已解密）
    - fail_count: 失败数
    - current_file: 当前处理的文件名
    - status: 当前文件状态（success/skip/fail）
    - message: 状态消息
    
    跳过原因：文件已经解密过
    失败原因：
    - 文件为空
    - V4-V2版本需要AES密钥但未提供
    - 未知加密版本
    - 解密结果为空
    - 解密后非有效图片格式
    """
    async def generate_progress():
        try:
            account_dir = _resolve_account_dir(account)
            wxid_dir = _resolve_account_wxid_dir(account_dir)
            
            if not wxid_dir:
                yield f"data: {json.dumps({'type': 'error', 'message': '未找到微信数据目录'})}\n\n"
                return
            
            # 获取密钥
            xor_key_int: Optional[int] = None
            aes_key16: Optional[bytes] = None
            
            if xor_key:
                try:
                    xor_hex = xor_key.strip().lower().replace("0x", "")
                    xor_key_int = int(xor_hex, 16)
                except Exception:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'XOR密钥格式无效'})}\n\n"
                    return
            
            if aes_key:
                aes_str = aes_key.strip()
                if len(aes_str) >= 16:
                    aes_key16 = aes_str[:16].encode("ascii", errors="ignore")
            
            # 如果未提供密钥，尝试从缓存加载
            if xor_key_int is None or aes_key16 is None:
                cached = _load_media_keys(account_dir)
                if xor_key_int is None:
                    xor_key_int = cached.get("xor")
                if aes_key16 is None:
                    aes_str = str(cached.get("aes") or "").strip()
                    if len(aes_str) >= 16:
                        aes_key16 = aes_str[:16].encode("ascii", errors="ignore")
            
            # 如果仍然没有XOR密钥，尝试自动提取
            if xor_key_int is None:
                xor_key_int = _find_wechat_xor_key(str(wxid_dir))
            
            if xor_key_int is None:
                yield f"data: {json.dumps({'type': 'error', 'message': '未找到XOR密钥，请先获取密钥'})}\n\n"
                return
            
            # 收集所有.dat文件
            logger.info(f"[SSE] 开始扫描 {wxid_dir} 中的.dat文件...")
            yield f"data: {json.dumps({'type': 'scanning', 'message': '正在扫描图片文件...'})}\n\n"
            await asyncio.sleep(0)  # 让出控制权
            
            dat_files = _collect_all_dat_files(wxid_dir)
            total_files = len(dat_files)
            logger.info(f"[SSE] 共发现 {total_files} 个.dat文件（仅图片）")
            
            if total_files == 0:
                yield f"data: {json.dumps({'type': 'complete', 'message': '未发现需要解密的图片文件', 'total': 0, 'success_count': 0, 'skip_count': 0, 'fail_count': 0})}\n\n"
                return
            
            # 发送总数信息
            yield f"data: {json.dumps({'type': 'start', 'total': total_files, 'message': f'开始解密 {total_files} 个图片文件'})}\n\n"
            await asyncio.sleep(0)
            
            # 开始解密
            success_count = 0
            skip_count = 0
            fail_count = 0
            failed_files: list[dict] = []
            
            resource_dir = _get_resource_dir(account_dir)
            resource_dir.mkdir(parents=True, exist_ok=True)
            
            for i, (dat_path, md5) in enumerate(dat_files):
                current = i + 1
                file_name = dat_path.name
                
                # 检查是否已解密
                existing = _try_find_decrypted_resource(account_dir, md5)
                if existing:
                    skip_count += 1
                    # 每100个跳过的文件发送一次进度，减少消息量
                    if skip_count % 100 == 0 or current == total_files:
                        yield f"data: {json.dumps({'type': 'progress', 'current': current, 'total': total_files, 'success_count': success_count, 'skip_count': skip_count, 'fail_count': fail_count, 'current_file': file_name, 'status': 'skip', 'message': '已存在'})}\n\n"
                        await asyncio.sleep(0)
                    continue
                
                # 解密并保存
                success, msg = _decrypt_and_save_resource(
                    dat_path, md5, account_dir, xor_key_int, aes_key16
                )
                
                if success:
                    success_count += 1
                    status = "success"
                    status_msg = "解密成功"
                    logger.debug(f"[SSE] 解密成功: {file_name}")
                else:
                    fail_count += 1
                    status = "fail"
                    status_msg = msg
                    logger.warning(f"[SSE] 解密失败: {file_name} - {msg}")
                    if len(failed_files) < 100:
                        failed_files.append({
                            "file": file_name,
                            "md5": md5,
                            "error": msg,
                        })
                
                # 每处理一个文件发送进度（成功或失败都发送）
                yield f"data: {json.dumps({'type': 'progress', 'current': current, 'total': total_files, 'success_count': success_count, 'skip_count': skip_count, 'fail_count': fail_count, 'current_file': file_name, 'status': status, 'message': status_msg})}\n\n"
                
                # 每处理10个文件让出一次控制权，避免阻塞
                if current % 10 == 0:
                    await asyncio.sleep(0)
            
            logger.info(f"[SSE] 解密完成: 成功={success_count}, 跳过={skip_count}, 失败={fail_count}")
            
            # 发送完成消息
            yield f"data: {json.dumps({'type': 'complete', 'total': total_files, 'success_count': success_count, 'skip_count': skip_count, 'fail_count': fail_count, 'output_dir': str(resource_dir), 'failed_files': failed_files[:20], 'message': f'解密完成: 成功 {success_count}, 跳过 {skip_count}, 失败 {fail_count}'})}\n\n"
            
        except Exception as e:
            logger.error(f"[SSE] 解密过程出错: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/api/health", summary="健康检查端点")
async def health_check():
    """健康检查端点"""
    logger.debug("健康检查请求")
    return {"status": "healthy", "service": "微信解密工具"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)