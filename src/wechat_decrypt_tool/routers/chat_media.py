import asyncio
from functools import lru_cache
import hashlib
import ipaddress
import mimetypes
import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from ..logging_config import get_logger
from ..media_helpers import (
    _convert_silk_to_wav,
    _detect_image_extension,
    _detect_image_media_type,
    _is_probably_valid_image,
    _iter_media_source_candidates,
    _order_media_candidates,
    _ensure_decrypted_resource_for_md5,
    _fallback_search_media_by_file_id,
    _fallback_search_media_by_md5,
    _get_decrypted_resource_path,
    _get_resource_dir,
    _guess_media_type_by_path,
    _iter_emoji_source_candidates,
    _read_and_maybe_decrypt_media,
    _resolve_account_db_storage_dir,
    _resolve_account_dir,
    _resolve_account_wxid_dir,
    _resolve_media_path_for_kind,
    _resolve_media_path_from_hardlink,
    _try_fetch_emoticon_from_remote,
    _try_find_decrypted_resource,
    _try_strip_media_prefix,
)
from ..path_fix import PathFixRoute

logger = get_logger(__name__)

router = APIRouter(route_class=PathFixRoute)


@lru_cache(maxsize=4096)
def _fast_probe_image_path_in_chat_attach(
    *,
    wxid_dir_str: str,
    username: str,
    md5: str,
) -> Optional[str]:
    """Fast-ish fallback for image md5 misses not indexed by hardlink.db.

    Many `*_t.dat` / `*_h.dat` variants live under:
      `{wxid_dir}/msg/attach/{md5(username)}/.../Img/{md5}(_t|_h).dat`

    When `hardlink.db` has image tables, we avoid global `rglob` by default for performance.
    This scoped walk makes those thumbnails discoverable without enabling `deep_scan`.
    """
    wxid_dir_str = str(wxid_dir_str or "").strip()
    username = str(username or "").strip()
    md5_norm = str(md5 or "").strip().lower()

    if not wxid_dir_str or not username or (not _is_valid_md5(md5_norm)):
        return None

    try:
        wxid_dir = Path(wxid_dir_str)
    except Exception:
        return None

    try:
        chat_hash = hashlib.md5(username.encode()).hexdigest()
    except Exception:
        return None

    base_dir = wxid_dir / "msg" / "attach" / chat_hash
    try:
        if not (base_dir.exists() and base_dir.is_dir()):
            return None
    except Exception:
        return None

    def variant_rank(stem: str) -> int:
        n = str(stem or "").lower()
        if n.endswith(("_b", ".b")):
            return 0
        if n.endswith(("_h", ".h")):
            return 1
        if n.endswith(("_c", ".c")):
            return 3
        if n.endswith(("_t", ".t")):
            return 4
        return 2

    best_key: Optional[tuple[int, int, int, float, str]] = None
    best_path: Optional[str] = None

    try:
        for dirpath, _dirnames, filenames in os.walk(base_dir):
            for fn in filenames:
                fn_low = str(fn).lower()
                if not fn_low.startswith(md5_norm):
                    continue
                p = Path(dirpath) / fn
                try:
                    if not p.is_file():
                        continue
                except Exception:
                    continue

                ext = str(p.suffix or "").lower()
                if ext not in {".dat", ".jpg", ".jpeg", ".png", ".gif", ".webp"}:
                    continue

                stem = str(p.stem or "")
                rank = variant_rank(stem)
                ext_penalty = 1 if ext == ".dat" else 0
                try:
                    st = p.stat()
                    sz = int(st.st_size)
                    mt = float(st.st_mtime)
                except Exception:
                    sz = 0
                    mt = 0.0

                key = (rank, ext_penalty, -sz, -mt, str(p))
                if best_key is None or key < best_key:
                    best_key = key
                    best_path = str(p)
                    # Found a non-.dat big variant; that's good enough.
                    if rank == 0 and ext_penalty == 0 and sz > 0:
                        return best_path
    except Exception:
        return None

    return best_path


@lru_cache(maxsize=64)
def _hardlink_has_table_prefix(hardlink_db_path: str, prefix: str) -> bool:
    p = str(hardlink_db_path or "").strip()
    pref = str(prefix or "").strip()
    if not p or not pref:
        return False
    try:
        conn = sqlite3.connect(p)
    except Exception:
        return False
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name LIKE ? LIMIT 1",
            (f"{pref}%",),
        ).fetchone()
        return bool(row)
    except Exception:
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _fast_probe_video_path_by_md5(
    *,
    md5: str,
    wxid_dir: Optional[Path],
    db_storage_dir: Optional[Path],
    want_thumb: bool,
) -> Optional[Path]:
    md5_norm = str(md5 or "").strip().lower()
    if not md5_norm:
        return None

    bases: list[Path] = []
    for root in [wxid_dir, db_storage_dir]:
        if not root:
            continue
        bases.extend([root / "msg" / "video", root / "video"])

    uniq_bases: list[Path] = []
    seen: set[str] = set()
    for b in bases:
        try:
            rb = str(b.resolve())
        except Exception:
            rb = str(b)
        if rb in seen:
            continue
        seen.add(rb)
        try:
            if b.exists() and b.is_dir():
                uniq_bases.append(b)
        except Exception:
            continue

    if not uniq_bases:
        return None

    if want_thumb:
        variants = [
            f"{md5_norm}_thumb.jpg",
            f"{md5_norm}_thumb.jpeg",
            f"{md5_norm}_thumb.png",
            f"{md5_norm}_thumb.webp",
            f"{md5_norm}_thumb.dat",
            f"{md5_norm}.jpg",
            f"{md5_norm}.jpeg",
            f"{md5_norm}.png",
            f"{md5_norm}.gif",
            f"{md5_norm}.webp",
            f"{md5_norm}.dat",
        ]
    else:
        variants = [
            f"{md5_norm}.mp4",
            f"{md5_norm}.m4v",
            f"{md5_norm}.mov",
            f"{md5_norm}.dat",
        ]

    def is_month_dir_name(name: str) -> bool:
        n = str(name or "")
        return (
            len(n) == 7
            and n[4] == "-"
            and n[:4].isdigit()
            and n[5:7].isdigit()
        )

    for base in uniq_bases:
        dirs_to_check: list[Path] = [base]
        try:
            for child in base.iterdir():
                try:
                    if child.is_dir() and is_month_dir_name(child.name):
                        dirs_to_check.append(child)
                except Exception:
                    continue
        except Exception:
            pass

        for d in dirs_to_check:
            for name in variants:
                p = d / name
                try:
                    if p.exists() and p.is_file():
                        return p
                except Exception:
                    continue

    return None


@router.get("/api/chat/avatar", summary="获取联系人头像")
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


class EmojiDownloadRequest(BaseModel):
    account: Optional[str] = Field(None, description="账号目录名（可选，默认使用第一个）")
    md5: str = Field(..., description="表情 MD5")
    emoji_url: str = Field(..., description="表情 CDN URL")
    force: bool = Field(False, description="是否强制重新下载并覆盖")


def _is_valid_md5(s: str) -> bool:
    import re

    v = str(s or "").strip().lower()
    return bool(re.fullmatch(r"[0-9a-f]{32}", v))


def _is_safe_http_url(url: str) -> bool:
    u = str(url or "").strip()
    if not u:
        return False
    try:
        p = urlparse(u)
    except Exception:
        return False
    if p.scheme not in ("http", "https"):
        return False
    host = (p.hostname or "").strip()
    if not host:
        return False
    if host in {"localhost"}:
        return False
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return False
    except Exception:
        pass
    return True


def _detect_media_type_and_ext(data: bytes) -> tuple[bytes, str, str]:
    payload = data
    media_type = "application/octet-stream"
    ext = "dat"

    try:
        payload2, mt2 = _try_strip_media_prefix(payload)
        if mt2 != "application/octet-stream":
            payload = payload2
            media_type = mt2
    except Exception:
        pass

    if media_type == "application/octet-stream":
        mt0 = _detect_image_media_type(payload[:32])
        if mt0 != "application/octet-stream":
            media_type = mt0

    if media_type == "application/octet-stream":
        try:
            if len(payload) >= 8 and payload[4:8] == b"ftyp":
                media_type = "video/mp4"
        except Exception:
            pass

    if media_type.startswith("image/"):
        ext = _detect_image_extension(payload)
    elif media_type == "video/mp4":
        ext = "mp4"
    else:
        ext = "dat"

    return payload, media_type, ext


@router.post("/api/chat/media/emoji/download", summary="下载表情消息资源到本地 resource")
async def download_chat_emoji(req: EmojiDownloadRequest):
    md5 = str(req.md5 or "").strip().lower()
    emoji_url = str(req.emoji_url or "").strip()

    if not _is_valid_md5(md5):
        raise HTTPException(status_code=400, detail="Invalid md5.")
    if not _is_safe_http_url(emoji_url):
        raise HTTPException(status_code=400, detail="Invalid emoji_url (only public http/https allowed).")

    account_dir = _resolve_account_dir(req.account)

    existing = _try_find_decrypted_resource(account_dir, md5)
    if existing and existing.exists() and (not req.force):
        return {
            "status": "success",
            "account": account_dir.name,
            "md5": md5,
            "saved": True,
            "already_exists": True,
            "path": str(existing),
            "resource_dir": str(existing.parent),
        }

    def _download_bytes() -> bytes:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
            "Accept": "*/*",
        }
        r = requests.get(emoji_url, headers=headers, timeout=20, stream=True)
        try:
            r.raise_for_status()
            max_bytes = 30 * 1024 * 1024
            chunks: list[bytes] = []
            total = 0
            for ch in r.iter_content(chunk_size=64 * 1024):
                if not ch:
                    continue
                chunks.append(ch)
                total += len(ch)
                if total > max_bytes:
                    raise HTTPException(status_code=400, detail="Emoji download too large (>30MB).")
            return b"".join(chunks)
        finally:
            try:
                r.close()
            except Exception:
                pass

    try:
        data = await asyncio.to_thread(_download_bytes)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"emoji_download failed: md5={md5} url={emoji_url} err={e}")
        raise HTTPException(status_code=500, detail=f"Emoji download failed: {e}")

    if not data:
        raise HTTPException(status_code=500, detail="Emoji download returned empty body.")

    payload, media_type, ext = _detect_media_type_and_ext(data)
    out_path = _get_decrypted_resource_path(account_dir, md5, ext)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists() and (not req.force):
        return {
            "status": "success",
            "account": account_dir.name,
            "md5": md5,
            "saved": True,
            "already_exists": True,
            "path": str(out_path),
            "resource_dir": str(out_path.parent),
            "media_type": media_type,
            "bytes": len(payload),
        }

    try:
        out_path.write_bytes(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write emoji file: {e}")

    logger.info(f"emoji_download: md5={md5} url={emoji_url} -> {out_path} bytes={len(payload)} mt={media_type}")
    return {
        "status": "success",
        "account": account_dir.name,
        "md5": md5,
        "saved": True,
        "already_exists": False,
        "path": str(out_path),
        "resource_dir": str(out_path.parent),
        "media_type": media_type,
        "bytes": len(payload),
    }


@router.get("/api/chat/media/image", summary="获取图片消息资源")
async def get_chat_image(
    md5: Optional[str] = None,
    file_id: Optional[str] = None,
    account: Optional[str] = None,
    username: Optional[str] = None,
    deep_scan: bool = False,
):
    if (not md5) and (not file_id):
        raise HTTPException(status_code=400, detail="Missing md5/file_id.")

    # Some WeChat versions put non-MD5 identifiers in the "md5" field; treat them as file_id.
    if md5 and (not file_id) and (not _is_valid_md5(str(md5))):
        file_id = str(md5)
        md5 = None
    account_dir = _resolve_account_dir(account)

    # md5 模式：优先从解密资源目录读取（更快）
    if md5:
        decrypted_path = _try_find_decrypted_resource(account_dir, str(md5).lower())
        if decrypted_path:
            data = decrypted_path.read_bytes()
            media_type = _detect_image_media_type(data[:32])
            if media_type != "application/octet-stream" and _is_probably_valid_image(data, media_type):
                return Response(content=data, media_type=media_type)
            # Corrupted cached file (e.g. wrong ext / partial data): remove and regenerate from source.
            try:
                if decrypted_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
                    decrypted_path.unlink()
            except Exception:
                pass

    # 回退：从微信数据目录实时定位并解密
    wxid_dir = _resolve_account_wxid_dir(account_dir)
    hardlink_db_path = account_dir / "hardlink.db"
    db_storage_dir = _resolve_account_db_storage_dir(account_dir)
    hardlink_has_image_table = _hardlink_has_table_prefix(str(hardlink_db_path), "image_hardlink_info")

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
        raise HTTPException(
            status_code=404,
            detail="wxid_dir/db_storage_path not found. Please decrypt with db_storage_path to enable media lookup.",
        )

    p: Optional[Path] = None
    candidates: list[Path] = []

    if md5:
        p = _resolve_media_path_from_hardlink(
            hardlink_db_path,
            roots[0],
            md5=str(md5),
            kind="image",
            username=username,
            extra_roots=roots[1:],
        )

        # Some WeChat versions send both md5 + file_id; md5 may be missing from hardlink.db while file_id still works.
        if (not p) and file_id:
            for r in [wxid_dir, db_storage_dir]:
                if not r:
                    continue
                hit = _fallback_search_media_by_file_id(
                    str(r),
                    str(file_id),
                    kind="image",
                    username=str(username or ""),
                )
                if hit:
                    p = Path(hit)
                    break

        # Fast fallback for thumbnails not indexed by hardlink.db: scan only this chat's attach directory.
        if (not p) and wxid_dir and username:
            hit = _fast_probe_image_path_in_chat_attach(
                wxid_dir_str=str(wxid_dir),
                username=str(username),
                md5=str(md5),
            )
            if hit:
                p = Path(hit)

        # Deep scan is extremely expensive for misses (~seconds per md5). Only enable when:
        # - user explicitly requests `deep_scan=1`, OR
        # - hardlink.db doesn't have the image table (older/partial data).
        allow_deep_scan = bool(deep_scan) or (not hardlink_has_image_table)
        if (not p) and wxid_dir and allow_deep_scan:
            hit = _fallback_search_media_by_md5(str(wxid_dir), str(md5), kind="image")
            if hit:
                p = Path(hit)
                try:
                    candidates.extend(_iter_media_source_candidates(Path(hit)))
                except Exception:
                    pass
    elif file_id:
        # 一些版本图片消息无 MD5，仅提供 cdnthumburl 等“文件标识”
        for r in [wxid_dir, db_storage_dir]:
            if not r:
                continue
            hit = _fallback_search_media_by_file_id(
                str(r),
                str(file_id),
                kind="image",
                username=str(username or ""),
            )
            if hit:
                p = Path(hit)
                break

    if not p:
        raise HTTPException(status_code=404, detail="Image not found.")

    candidates.extend(_iter_media_source_candidates(p))
    candidates = _order_media_candidates(candidates)

    logger.info(f"chat_image: md5={md5} file_id={file_id} candidates={len(candidates)} first={p}")

    data = b""
    media_type = "application/octet-stream"
    chosen: Optional[Path] = None
    for src_path in candidates:
        try:
            data, media_type = _read_and_maybe_decrypt_media(src_path, account_dir=account_dir, weixin_root=wxid_dir)
        except Exception:
            continue

        if media_type.startswith("image/") and (not _is_probably_valid_image(data, media_type)):
            continue

        if media_type != "application/octet-stream":
            chosen = src_path
            break

    if not chosen:
        raise HTTPException(status_code=422, detail="Image found but failed to decode/decrypt.")

    # 仅在 md5 有效时缓存到 resource 目录；file_id 可能非常长，避免写入超长文件名
    if md5 and media_type.startswith("image/"):
        try:
            out_md5 = str(md5).lower()
            ext = _detect_image_extension(data)
            out_path = _get_decrypted_resource_path(account_dir, out_md5, ext)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if not out_path.exists():
                out_path.write_bytes(data)
        except Exception:
            pass

    logger.info(
        f"chat_image: md5={md5} file_id={file_id} chosen={chosen} media_type={media_type} bytes={len(data)}"
    )
    return Response(content=data, media_type=media_type)


@router.get("/api/chat/media/emoji", summary="获取表情消息资源")
async def get_chat_emoji(md5: str, account: Optional[str] = None, username: Optional[str] = None):
    if not md5:
        raise HTTPException(status_code=400, detail="Missing md5.")
    account_dir = _resolve_account_dir(account)

    # 优先从解密资源目录读取（更快）
    decrypted_path = _try_find_decrypted_resource(account_dir, md5.lower())
    if decrypted_path:
        data = decrypted_path.read_bytes()
        media_type = _detect_image_media_type(data[:32])
        if media_type != "application/octet-stream" and _is_probably_valid_image(data, media_type):
            return Response(content=data, media_type=media_type)
        try:
            if decrypted_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
                decrypted_path.unlink()
        except Exception:
            pass

    wxid_dir = _resolve_account_wxid_dir(account_dir)
    p = _resolve_media_path_for_kind(account_dir, kind="emoji", md5=str(md5), username=username)

    data = b""
    media_type = "application/octet-stream"
    if p:
        data, media_type = _read_and_maybe_decrypt_media(p, account_dir=account_dir, weixin_root=wxid_dir)

    if media_type == "application/octet-stream":
        # Some emojis are stored encrypted (see emoticon.db); try remote fetch as fallback.
        data2, mt2 = _try_fetch_emoticon_from_remote(account_dir, str(md5).lower())
        if data2 is not None and mt2:
            data, media_type = data2, mt2

    if (not p) and media_type == "application/octet-stream":
        raise HTTPException(status_code=404, detail="Emoji not found.")

    if media_type.startswith("image/"):
        try:
            out_md5 = str(md5).lower()
            ext = _detect_image_extension(data)
            out_path = _get_decrypted_resource_path(account_dir, out_md5, ext)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if not out_path.exists():
                out_path.write_bytes(data)
        except Exception:
            pass
    return Response(content=data, media_type=media_type)


@router.get("/api/chat/media/video_thumb", summary="获取视频缩略图资源")
async def get_chat_video_thumb(
    md5: Optional[str] = None,
    file_id: Optional[str] = None,
    account: Optional[str] = None,
    username: Optional[str] = None,
    deep_scan: bool = False,
):
    if (not md5) and (not file_id):
        raise HTTPException(status_code=400, detail="Missing md5/file_id.")
    account_dir = _resolve_account_dir(account)

    # 优先从解密资源目录读取（更快）
    if md5:
        decrypted_path = _try_find_decrypted_resource(account_dir, str(md5).lower())
        if decrypted_path:
            data = decrypted_path.read_bytes()
            media_type = _detect_image_media_type(data[:32])
            return Response(content=data, media_type=media_type)

    # 回退到原始逻辑
    wxid_dir = _resolve_account_wxid_dir(account_dir)
    hardlink_db_path = account_dir / "hardlink.db"
    extra_roots: list[Path] = []
    db_storage_dir = _resolve_account_db_storage_dir(account_dir)
    hardlink_has_video_table = _hardlink_has_table_prefix(str(hardlink_db_path), "video_hardlink_info")
    if db_storage_dir:
        extra_roots.append(db_storage_dir)

    roots: list[Path] = []
    if wxid_dir:
        roots.append(wxid_dir)
    if db_storage_dir:
        roots.append(db_storage_dir)
    if not roots:
        raise HTTPException(
            status_code=404,
            detail="wxid_dir/db_storage_path not found. Please decrypt with db_storage_path to enable media lookup.",
        )
    p: Optional[Path] = None
    if md5:
        p = _resolve_media_path_from_hardlink(
            hardlink_db_path,
            roots[0],
            md5=str(md5),
            kind="video_thumb",
            username=username,
            extra_roots=roots[1:],
        )

        # Many WeChat builds store video thumbnails directly as `{md5}_thumb.jpg` under msg/video/YYYY-MM.
        # This fast probe avoids an expensive recursive scan on misses.
        if (not p) and (wxid_dir or db_storage_dir):
            p = _fast_probe_video_path_by_md5(
                md5=str(md5),
                wxid_dir=wxid_dir,
                db_storage_dir=db_storage_dir,
                want_thumb=True,
            )

        allow_deep_scan = bool(deep_scan) or (not hardlink_has_video_table)
        if (not p) and wxid_dir and allow_deep_scan:
            hit = _fallback_search_media_by_md5(str(wxid_dir), str(md5), kind="video_thumb")
            if hit:
                p = Path(hit)
    if (not p) and file_id:
        for r in [wxid_dir, db_storage_dir]:
            if not r:
                continue
            hit = _fallback_search_media_by_file_id(str(r), str(file_id), kind="video_thumb", username=str(username or ""))
            if hit:
                p = Path(hit)
                break
    if not p:
        raise HTTPException(status_code=404, detail="Video thumbnail not found.")

    data, media_type = _read_and_maybe_decrypt_media(p, account_dir=account_dir, weixin_root=wxid_dir)
    return Response(content=data, media_type=media_type)


@router.get("/api/chat/media/video", summary="获取视频资源")
async def get_chat_video(
    md5: Optional[str] = None,
    file_id: Optional[str] = None,
    account: Optional[str] = None,
    username: Optional[str] = None,
    deep_scan: bool = False,
):
    if (not md5) and (not file_id):
        raise HTTPException(status_code=400, detail="Missing md5/file_id.")
    account_dir = _resolve_account_dir(account)
    md5_norm = str(md5 or "").strip().lower() if md5 else ""

    if md5_norm:
        # 优先从解密资源目录读取（更快，且支持 Range）
        decrypted_path = _try_find_decrypted_resource(account_dir, md5_norm)
        if decrypted_path:
            mt = _guess_media_type_by_path(decrypted_path, fallback="video/mp4")
            return FileResponse(str(decrypted_path), media_type=mt)

    wxid_dir = _resolve_account_wxid_dir(account_dir)
    hardlink_db_path = account_dir / "hardlink.db"
    extra_roots: list[Path] = []
    db_storage_dir = _resolve_account_db_storage_dir(account_dir)
    hardlink_has_video_table = _hardlink_has_table_prefix(str(hardlink_db_path), "video_hardlink_info")
    if db_storage_dir:
        extra_roots.append(db_storage_dir)

    roots: list[Path] = []
    if wxid_dir:
        roots.append(wxid_dir)
    if db_storage_dir:
        roots.append(db_storage_dir)
    if not roots:
        raise HTTPException(
            status_code=404,
            detail="wxid_dir/db_storage_path not found. Please decrypt with db_storage_path to enable media lookup.",
        )
    p: Optional[Path] = None
    if md5_norm:
        p = _resolve_media_path_from_hardlink(
            hardlink_db_path,
            roots[0],
            md5=md5_norm,
            kind="video",
            username=username,
            extra_roots=roots[1:],
        )
        if (not p) and (wxid_dir or db_storage_dir):
            p = _fast_probe_video_path_by_md5(
                md5=md5_norm,
                wxid_dir=wxid_dir,
                db_storage_dir=db_storage_dir,
                want_thumb=False,
            )
        allow_deep_scan = bool(deep_scan) or (not hardlink_has_video_table)
        if (not p) and wxid_dir and allow_deep_scan:
            hit = _fallback_search_media_by_md5(str(wxid_dir), md5_norm, kind="video")
            if hit:
                p = Path(hit)
    if (not p) and file_id:
        for r in [wxid_dir, db_storage_dir]:
            if not r:
                continue
            hit = _fallback_search_media_by_file_id(str(r), str(file_id), kind="video", username=str(username or ""))
            if hit:
                p = Path(hit)
                break
    if not p:
        raise HTTPException(status_code=404, detail="Video not found.")

    # 直接可播放的 MP4：直接 FileResponse（支持 Range）
    try:
        with open(p, "rb") as f:
            head = f.read(8)
        if len(head) >= 8 and head[4:8] == b"ftyp":
            media_type = _guess_media_type_by_path(p, fallback="video/mp4")
            return FileResponse(str(p), media_type=media_type)
    except Exception:
        pass

    # 尝试解密/去前缀并落盘（避免一次性返回大文件 bytes）
    if md5_norm:
        try:
            materialized = _ensure_decrypted_resource_for_md5(
                account_dir,
                md5=md5_norm,
                source_path=p,
                weixin_root=wxid_dir,
            )
        except Exception:
            materialized = None
        if materialized:
            media_type = _guess_media_type_by_path(materialized, fallback="video/mp4")
            return FileResponse(str(materialized), media_type=media_type)

    # 最后兜底：直接返回处理后的 bytes（不支持 Range）
    data, media_type = _read_and_maybe_decrypt_media(p, account_dir=account_dir, weixin_root=wxid_dir)
    if media_type == "application/octet-stream":
        media_type = _guess_media_type_by_path(p, fallback="video/mp4")
    return Response(content=data, media_type=media_type)


@router.get("/api/chat/media/voice", summary="获取语音消息资源")
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


@router.post("/api/chat/media/open_folder", summary="在资源管理器中打开媒体文件所在位置")
async def open_chat_media_folder(
    kind: str,
    md5: Optional[str] = None,
    file_id: Optional[str] = None,
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
        if not md5 and not file_id:
            raise HTTPException(status_code=400, detail="Missing md5/file_id.")

        if md5 and (not file_id) and (not _is_valid_md5(str(md5))):
            file_id = str(md5)
            md5 = None

        if md5:
            p = _resolve_media_path_for_kind(account_dir, kind=kind_key, md5=str(md5), username=username)
        if (not p) and file_id:
            wxid_dir = _resolve_account_wxid_dir(account_dir)
            db_storage_dir = _resolve_account_db_storage_dir(account_dir)
            for r in [wxid_dir, db_storage_dir]:
                if not r:
                    continue
                hit = _fallback_search_media_by_file_id(
                    str(r),
                    str(file_id),
                    kind=str(kind_key),
                    username=str(username or ""),
                )
                if hit:
                    p = Path(hit)
                    break

        resolved_before_materialize = p
        materialized_ok = False
        opened_kind = "resolved"

        if p and kind_key in {"image", "emoji", "video_thumb"} and md5:
            wxid_dir = _resolve_account_wxid_dir(account_dir)
            source_path = p
            if kind_key == "emoji":
                candidates: list[Path] = []
                try:
                    md5s = str(md5 or "").lower().strip()
                except Exception:
                    md5s = str(md5)

                try:
                    if p is not None and p.exists() and p.is_file():
                        if (not str(p.suffix or "")) and md5s and str(p.name).lower() == md5s:
                            candidates.extend(_iter_emoji_source_candidates(p.parent, md5s))
                            if p not in candidates:
                                candidates.append(p)
                        else:
                            candidates.append(p)
                            candidates.extend(_iter_emoji_source_candidates(p.parent, md5s))
                    else:
                        candidates = _iter_emoji_source_candidates(p, md5s)
                except Exception:
                    candidates = _iter_emoji_source_candidates(p, str(md5))

                # de-dup while keeping order
                seen: set[str] = set()
                uniq: list[Path] = []
                for c in candidates:
                    try:
                        k = str(c.resolve())
                    except Exception:
                        k = str(c)
                    if k in seen:
                        continue
                    seen.add(k)
                    uniq.append(c)
                candidates = uniq

                try:
                    preferred: list[Path] = []
                    if md5s:
                        for c in candidates:
                            try:
                                if md5s in str(c.name).lower():
                                    preferred.append(c)
                            except Exception:
                                continue
                    if preferred:
                        rest = [c for c in candidates if c not in preferred]
                        candidates = preferred + rest
                except Exception:
                    pass
                if not candidates and p is not None:
                    candidates = [p]
                for cand in candidates:
                    source_path = cand
                    materialized = _ensure_decrypted_resource_for_md5(
                        account_dir,
                        md5=str(md5),
                        source_path=source_path,
                        weixin_root=wxid_dir,
                    )
                    if materialized:
                        p = materialized
                        materialized_ok = True
                        opened_kind = "decrypted"
                        break

                if not materialized_ok:
                    try:
                        sz = -1
                        head_hex = ""
                        try:
                            if source_path and source_path.exists() and source_path.is_file():
                                sz = int(source_path.stat().st_size)
                                with open(source_path, "rb") as f:
                                    head_hex = f.read(32).hex()
                        except Exception:
                            pass
                        logger.info(
                            f"open_folder: emoji materialize failed: resolved={str(resolved_before_materialize)} source={str(source_path)} size={sz} head32={head_hex}"
                        )
                    except Exception:
                        pass

                    try:
                        resource_dir = _get_resource_dir(account_dir)
                        sub_dir = str(md5).lower()[:2] if len(str(md5)) >= 2 else "00"
                        fallback_dir = resource_dir / sub_dir
                        fallback_dir.mkdir(parents=True, exist_ok=True)
                        p = fallback_dir
                        opened_kind = "resource_dir"
                    except Exception:
                        try:
                            resource_dir = _get_resource_dir(account_dir)
                            sub_dir = str(md5).lower()[:2] if len(str(md5)) >= 2 else "00"
                            fallback_dir = resource_dir / sub_dir
                            fallback_dir.mkdir(parents=True, exist_ok=True)
                            p = fallback_dir
                            opened_kind = "resource_dir"
                        except Exception:
                            pass
            else:
                materialized = _ensure_decrypted_resource_for_md5(
                    account_dir,
                    md5=str(md5),
                    source_path=source_path,
                    weixin_root=wxid_dir,
                )
                if materialized:
                    p = materialized
                    materialized_ok = True
                    opened_kind = "decrypted"

        if kind_key == "emoji" and md5:
            try:
                existing2 = _try_find_decrypted_resource(account_dir, str(md5).lower())
                if existing2:
                    p = existing2
                    opened_kind = "decrypted"
            except Exception:
                pass

    if not p:
        if kind_key == "emoji":
            wxid_dir = _resolve_account_wxid_dir(account_dir)
            resource_dir = _get_resource_dir(account_dir)
            candidates: list[Path] = []
            if md5:
                sub_dir = str(md5).lower()[:2] if len(str(md5)) >= 2 else "00"
                c1 = resource_dir / sub_dir
                if c1.exists() and c1.is_dir():
                    candidates.append(c1)
            if resource_dir.exists() and resource_dir.is_dir():
                candidates.append(resource_dir)
            if wxid_dir:
                for c in [
                    wxid_dir / "msg" / "emoji",
                    wxid_dir / "msg" / "emoticon",
                    wxid_dir / "emoji",
                    wxid_dir,
                ]:
                    try:
                        if c.exists() and c.is_dir():
                            candidates.append(c)
                    except Exception:
                        continue
            candidates.append(account_dir)
            p = candidates[0]
        else:
            raise HTTPException(status_code=404, detail="File not found.")

    try:
        target = str(p.resolve())
    except Exception:
        target = str(p)

    logger.info(f"open_folder: kind={kind_key} md5={md5} file_id={file_id} server_id={server_id} -> {target}")

    if os.name != "nt":
        raise HTTPException(status_code=400, detail="open_folder is only supported on Windows.")

    try:
        tp = Path(target)
        if tp.exists() and tp.is_dir():
            subprocess.Popen(["explorer.exe", str(tp)])
        elif tp.exists():
            subprocess.Popen(["explorer.exe", "/select,", str(tp)])
        else:
            subprocess.Popen(["explorer.exe", str(tp.parent)])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open explorer: {e}")

    file_found = False
    try:
        tp2 = Path(target)
        if kind_key == "emoji":
            file_found = bool(tp2.exists())
        else:
            if tp2.exists() and tp2.is_file():
                file_found = True
    except Exception:
        pass

    resp = {"status": "success", "path": target}
    if kind_key == "emoji":
        resp["file_found"] = bool(file_found)
        resp["materialized"] = bool(materialized_ok) if "materialized_ok" in locals() else bool(file_found)
        resp["opened"] = str(opened_kind) if "opened_kind" in locals() else "unknown"
    return resp
