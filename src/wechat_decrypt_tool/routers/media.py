import asyncio
import concurrent.futures
import json
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from ..logging_config import get_logger
from ..media_helpers import (
    _collect_emoticon_download_catalog,
    _collect_all_dat_files,
    _decrypt_and_save_resource,
    _get_decrypted_resource_path,
    _detect_image_extension,
    _detect_image_media_type,
    _is_probably_valid_image,
    _get_resource_dir,
    _load_media_keys,
    _resolve_account_dir,
    _resolve_account_wxid_dir,
    _save_media_keys,
    _try_fetch_emoticon_from_remote,
    _try_find_decrypted_resource,
)
from ..path_fix import PathFixRoute
from ..key_store import upsert_account_keys_in_store

logger = get_logger(__name__)

router = APIRouter(route_class=PathFixRoute)


def _summarize_aes_key(value: Optional[str]) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) <= 8:
        return raw
    return f"{raw[:4]}...{raw[-4:]}(len={len(raw)})"


def _summarize_media_keys(*, xor_key: Optional[str] = None, aes_key: Optional[str] = None) -> dict:
    xor_str = str(xor_key or "").strip()
    aes_str = str(aes_key or "").strip()
    return {
        "xor_key": xor_str,
        "aes_key": _summarize_aes_key(aes_str),
        "has_xor": bool(xor_str),
        "has_aes": bool(aes_str),
    }


def _guess_emoji_extension(payload: bytes, media_type: Optional[str]) -> str:
    mt = str(media_type or "").strip().lower()
    if mt.startswith("image/"):
        return _detect_image_extension(payload)
    if mt == "video/mp4":
        return "mp4"
    return "dat"


def _is_valid_cached_emoji(path) -> bool:
    if not path:
        return False
    try:
        if not path.exists() or not path.is_file():
            return False
        data = path.read_bytes()
    except Exception:
        return False

    if not data:
        return False

    try:
        if len(data) >= 8 and data[4:8] == b"ftyp":
            return True
    except Exception:
        pass

    media_type = _detect_image_media_type(data[:32])
    if media_type == "application/octet-stream":
        return False
    return _is_probably_valid_image(data, media_type)


def _normalize_emoji_download_concurrency(value: Optional[int]) -> int:
    try:
        n = int(value or 20)
    except Exception:
        n = 20
    if n < 1:
        return 1
    if n > 100:
        return 100
    return n


def _normalize_media_decrypt_concurrency(value: Optional[int]) -> int:
    try:
        n = int(value or 10)
    except Exception:
        n = 10
    if n < 1:
        return 1
    if n > 64:
        return 64
    return n


def _is_valid_cached_image(path) -> bool:
    if not path:
        return False
    try:
        if not path.exists() or not path.is_file():
            return False
        data = path.read_bytes()
    except Exception:
        return False
    if not data:
        return False
    media_type = _detect_image_media_type(data[:32])
    if media_type == "application/octet-stream":
        return False
    return _is_probably_valid_image(data, media_type)


class MediaKeysSaveRequest(BaseModel):
    """媒体密钥保存请求模型（用户手动提供）"""

    account: Optional[str] = Field(None, description="账号目录名（可选，默认使用第一个）")
    xor_key: str = Field(..., description="XOR密钥（十六进制格式，如 0xA5 或 A5）")
    aes_key: Optional[str] = Field(None, description="AES密钥（可选，至少16字符，V4-V2需要）")


class MediaDecryptRequest(BaseModel):
    """媒体解密请求模型"""

    account: Optional[str] = Field(None, description="账号目录名（可选，默认使用第一个）")
    xor_key: Optional[str] = Field(None, description="XOR密钥（十六进制，如 0xA5 或 A5）")
    aes_key: Optional[str] = Field(None, description="AES密钥（16字符ASCII字符串）")


@router.post("/api/media/keys", summary="保存图片解密密钥")
async def save_media_keys_api(request: MediaKeysSaveRequest):
    """手动保存图片解密密钥

    参数:
    - xor_key: XOR密钥（十六进制格式，如 0xA5 或 A5）
    - aes_key: AES密钥（可选，至少16个字符；V4-V2需要）
    """
    account_dir = _resolve_account_dir(request.account)
    logger.info(
        "[media] save_media_keys start: request_account=%s resolved_account=%s keys=%s",
        str(request.account or "").strip(),
        account_dir.name,
        _summarize_media_keys(xor_key=request.xor_key, aes_key=request.aes_key),
    )

    # 解析XOR密钥
    try:
        xor_hex = request.xor_key.strip().lower().replace("0x", "")
        xor_int = int(xor_hex, 16)
    except Exception:
        raise HTTPException(status_code=400, detail="XOR密钥格式无效，请使用十六进制格式如 0xA5")

    # 验证AES密钥（可选）
    aes_str = str(request.aes_key or "").strip()
    if aes_str and len(aes_str) < 16:
        raise HTTPException(status_code=400, detail="AES密钥长度不足，需要至少16个字符")

    # 保存密钥
    aes_key16 = aes_str[:16].encode("ascii", errors="ignore") if aes_str else None
    _save_media_keys(account_dir, xor_int, aes_key16)
    try:
        upsert_account_keys_in_store(
            account_dir.name,
            image_xor_key=f"0x{xor_int:02X}",
            image_aes_key=aes_str[:16] if aes_str else "",
        )
    except Exception:
        pass
    logger.info(
        "[media] save_media_keys done: account=%s keys=%s",
        account_dir.name,
        _summarize_media_keys(xor_key=f"0x{xor_int:02X}", aes_key=aes_str[:16] if aes_str else ""),
    )

    return {
        "status": "success",
        "message": "密钥已保存",
        "xor_key": f"0x{xor_int:02X}",
        "aes_key": aes_str[:16] if aes_str else "",
    }


@router.post("/api/media/decrypt_all", summary="批量解密所有图片资源")
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
    logger.info(
        "[media] decrypt_all start: request_account=%s resolved_account=%s provided_keys=%s",
        str(request.account or "").strip(),
        account_dir.name,
        _summarize_media_keys(xor_key=request.xor_key, aes_key=request.aes_key),
    )

    if not wxid_dir:
        raise HTTPException(
            status_code=400,
            detail="未找到微信数据目录，请确保已正确配置 db_storage_path",
        )

    # 获取密钥
    xor_key_int: Optional[int] = None
    aes_key16: Optional[bytes] = None

    if request.xor_key:
        try:
            xor_hex = request.xor_key.strip().lower().replace("0x", "")
            xor_key_int = int(xor_hex, 16)
        except Exception:
            raise HTTPException(status_code=400, detail="XOR密钥格式无效")

    if request.aes_key:
        aes_str = request.aes_key.strip()
        if len(aes_str) >= 16:
            aes_key16 = aes_str[:16].encode("ascii", errors="ignore")

    # 如果未提供密钥，尝试从缓存加载
    if xor_key_int is None or aes_key16 is None:
        cached = _load_media_keys(account_dir)
        logger.info(
            "[media] decrypt_all cache lookup: account=%s cached_keys=%s",
            account_dir.name,
            _summarize_media_keys(
                xor_key=f"0x{int(cached.get('xor')):02X}" if cached.get("xor") is not None else "",
                aes_key=str(cached.get("aes") or "").strip(),
            ),
        )
        if xor_key_int is None:
            xor_key_int = cached.get("xor")
        if aes_key16 is None:
            aes_str = str(cached.get("aes") or "").strip()
            if len(aes_str) >= 16:
                aes_key16 = aes_str[:16].encode("ascii", errors="ignore")
    logger.info(
        "[media] decrypt_all effective_keys: account=%s keys=%s",
        account_dir.name,
        _summarize_media_keys(
            xor_key=f"0x{int(xor_key_int):02X}" if xor_key_int is not None else "",
            aes_key=(aes_key16 or b"").decode("ascii", errors="ignore") if aes_key16 else "",
        ),
    )

    if xor_key_int is None:
        raise HTTPException(
            status_code=400,
            detail="未找到XOR密钥，请先使用 wx_key 获取并通过前端填写（或调用 /api/media/keys 保存）",
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
            dat_path, md5, account_dir, xor_key_int, aes_key16
        )

        if success:
            success_count += 1
        else:
            fail_count += 1
            if len(failed_files) < 100:  # 只记录前100个失败
                failed_files.append(
                    {
                        "file": str(dat_path),
                        "md5": md5,
                        "error": msg,
                    }
                )

    logger.info(f"解密完成: 成功={success_count}, 跳过={skip_count}, 失败={fail_count}")

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


@router.get("/api/media/resource/{md5}", summary="获取已解密的资源文件")
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


@router.get("/api/media/decrypt_all_stream", summary="批量解密所有图片资源（SSE实时进度）")
async def decrypt_all_media_stream(
    request: Request,
    account: Optional[str] = None,
    xor_key: Optional[str] = None,
    aes_key: Optional[str] = None,
    concurrency: int = 10,
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

    async def is_client_disconnected() -> bool:
        try:
            return await request.is_disconnected()
        except Exception:
            return False

    def sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def generate_progress():
        started_at = time.perf_counter()
        try:
            if await is_client_disconnected():
                logger.info("[SSE] 客户端已断开，取消图片解密任务")
                return

            account_dir = _resolve_account_dir(account)
            wxid_dir = _resolve_account_wxid_dir(account_dir)
            worker_count = _normalize_media_decrypt_concurrency(concurrency)
            logger.info(
                "[media] decrypt_all_stream start: request_account=%s resolved_account=%s provided_keys=%s requested_concurrency=%s effective_concurrency=%s",
                str(account or "").strip(),
                account_dir.name,
                _summarize_media_keys(xor_key=xor_key, aes_key=aes_key),
                concurrency,
                worker_count,
            )

            if not wxid_dir:
                yield sse({"type": "error", "message": "未找到微信数据目录"})
                return

            xor_key_int: Optional[int] = None
            aes_key16: Optional[bytes] = None

            if xor_key:
                try:
                    xor_hex = xor_key.strip().lower().replace("0x", "")
                    xor_key_int = int(xor_hex, 16)
                except Exception:
                    yield sse({"type": "error", "message": "XOR密钥格式无效"})
                    return

            if aes_key:
                aes_str = aes_key.strip()
                if len(aes_str) >= 16:
                    aes_key16 = aes_str[:16].encode("ascii", errors="ignore")

            if xor_key_int is None or aes_key16 is None:
                cached = _load_media_keys(account_dir)
                logger.info(
                    "[media] decrypt_all_stream cache lookup: account=%s cached_keys=%s",
                    account_dir.name,
                    _summarize_media_keys(
                        xor_key=f"0x{int(cached.get('xor')):02X}" if cached.get("xor") is not None else "",
                        aes_key=str(cached.get("aes") or "").strip(),
                    ),
                )
                if xor_key_int is None:
                    xor_key_int = cached.get("xor")
                if aes_key16 is None:
                    aes_str = str(cached.get("aes") or "").strip()
                    if len(aes_str) >= 16:
                        aes_key16 = aes_str[:16].encode("ascii", errors="ignore")
            logger.info(
                "[media] decrypt_all_stream effective_keys: account=%s keys=%s",
                account_dir.name,
                _summarize_media_keys(
                    xor_key=f"0x{int(xor_key_int):02X}" if xor_key_int is not None else "",
                    aes_key=(aes_key16 or b"").decode("ascii", errors="ignore") if aes_key16 else "",
                ),
            )

            if xor_key_int is None:
                yield sse({"type": "error", "message": "未找到XOR密钥，请先使用 wx_key 获取并保存/填写"})
                return

            scan_started_at = time.perf_counter()
            logger.info(f"[SSE] 开始扫描 {wxid_dir} 中的.dat文件...")
            yield sse({"type": "scanning", "message": "正在扫描图片文件..."})
            await asyncio.sleep(0)

            dat_files = _collect_all_dat_files(wxid_dir)
            total_files = len(dat_files)
            scan_elapsed_ms = round((time.perf_counter() - scan_started_at) * 1000, 1)
            logger.info(
                "[media] decrypt_all_stream scan_done: account=%s total=%s elapsed_ms=%s",
                account_dir.name,
                total_files,
                scan_elapsed_ms,
            )

            if await is_client_disconnected():
                logger.info("[SSE] 扫描完成后客户端已断开，停止图片解密任务")
                return

            resource_dir = _get_resource_dir(account_dir)
            resource_dir.mkdir(parents=True, exist_ok=True)

            if total_files == 0:
                yield sse(
                    {
                        "type": "complete",
                        "message": "未发现需要解密的图片文件",
                        "total": 0,
                        "concurrency": worker_count,
                        "success_count": 0,
                        "skip_count": 0,
                        "fail_count": 0,
                        "output_dir": str(resource_dir),
                    }
                )
                return

            yield sse(
                {
                    "type": "start",
                    "total": total_files,
                    "concurrency": worker_count,
                    "requested_concurrency": concurrency,
                    "message": f"开始解密 {total_files} 个图片文件（并发 {worker_count}）",
                }
            )
            await asyncio.sleep(0)

            if await is_client_disconnected():
                logger.info("[SSE] 开始解密前客户端已断开，停止图片解密任务")
                return

            success_count = 0
            skip_count = 0
            fail_count = 0
            processed_count = 0
            failed_files: list[dict] = []
            cache_hit_count = 0
            decrypt_attempt_count = 0
            decrypt_fail_count = 0
            slow_decrypt_count = 0
            total_cache_ms = 0.0
            total_decrypt_ms = 0.0
            max_decrypt_ms = 0.0
            last_summary_at = time.perf_counter()

            stop_event = asyncio.Event()
            work_queue: asyncio.Queue = asyncio.Queue()
            result_queue: asyncio.Queue = asyncio.Queue()
            for item_index, item in enumerate(dat_files, start=1):
                work_queue.put_nowait((item_index, item[0], item[1]))
            for _ in range(worker_count):
                work_queue.put_nowait(None)

            loop = asyncio.get_running_loop()
            executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=worker_count,
                thread_name_prefix="media-decrypt",
            )

            def process_one(item_index: int, dat_path: Path, md5: str, worker_id: int) -> dict:
                file_name = dat_path.name
                item_started_at = time.perf_counter()
                cache_started_at = time.perf_counter()
                existing = _try_find_decrypted_resource(account_dir, md5)
                if existing and _is_valid_cached_image(existing):
                    return {
                        "item_index": item_index,
                        "worker_id": worker_id,
                        "file_name": file_name,
                        "md5": md5,
                        "status": "skip",
                        "message": "已存在",
                        "cache_ms": round((time.perf_counter() - cache_started_at) * 1000, 1),
                        "decrypt_ms": 0.0,
                        "elapsed_ms": round((time.perf_counter() - item_started_at) * 1000, 1),
                    }
                if existing:
                    try:
                        existing.unlink(missing_ok=True)
                    except Exception:
                        pass
                cache_elapsed_ms = round((time.perf_counter() - cache_started_at) * 1000, 1)

                decrypt_started_at = time.perf_counter()
                success, msg = _decrypt_and_save_resource(dat_path, md5, account_dir, xor_key_int, aes_key16)
                decrypt_elapsed_ms = round((time.perf_counter() - decrypt_started_at) * 1000, 1)
                status = "success" if success else "fail"
                message = "解密成功" if success else str(msg or "解密失败")
                return {
                    "item_index": item_index,
                    "worker_id": worker_id,
                    "file_name": file_name,
                    "md5": md5,
                    "status": status,
                    "message": message,
                    "cache_ms": cache_elapsed_ms,
                    "decrypt_ms": decrypt_elapsed_ms,
                    "elapsed_ms": round((time.perf_counter() - item_started_at) * 1000, 1),
                }

            async def worker(worker_id: int):
                while not stop_event.is_set():
                    item = await work_queue.get()
                    try:
                        if item is None:
                            return
                        item_index, dat_path, md5 = item
                        if stop_event.is_set():
                            return
                        try:
                            result = await loop.run_in_executor(executor, process_one, item_index, dat_path, md5, worker_id)
                        except Exception as exc:
                            result = {
                                "item_index": item_index,
                                "worker_id": worker_id,
                                "file_name": dat_path.name,
                                "md5": md5,
                                "status": "fail",
                                "message": f"处理失败: {exc}",
                                "cache_ms": 0.0,
                                "decrypt_ms": 0.0,
                                "elapsed_ms": 0.0,
                            }
                        if not stop_event.is_set():
                            await result_queue.put(result)
                    finally:
                        work_queue.task_done()

            worker_tasks = [asyncio.create_task(worker(i + 1)) for i in range(worker_count)]
            logger.info(
                "[media] decrypt_all_stream workers_started: account=%s total=%s concurrency=%s",
                account_dir.name,
                total_files,
                worker_count,
            )

            try:
                while processed_count < total_files:
                    if await is_client_disconnected():
                        stop_event.set()
                        logger.info(
                            "[SSE] 客户端已断开，停止图片解密任务: account=%s current=%s total=%s success=%s skip=%s fail=%s concurrency=%s elapsed_ms=%s",
                            account_dir.name,
                            processed_count,
                            total_files,
                            success_count,
                            skip_count,
                            fail_count,
                            worker_count,
                            round((time.perf_counter() - started_at) * 1000, 1),
                        )
                        return

                    try:
                        result = await asyncio.wait_for(result_queue.get(), timeout=0.5)
                    except asyncio.TimeoutError:
                        continue

                    processed_count += 1
                    status = str(result.get("status") or "")
                    cache_ms = float(result.get("cache_ms") or 0.0)
                    decrypt_ms = float(result.get("decrypt_ms") or 0.0)
                    elapsed_ms = float(result.get("elapsed_ms") or 0.0)
                    total_cache_ms += cache_ms
                    total_decrypt_ms += decrypt_ms

                    if status == "success":
                        success_count += 1
                        decrypt_attempt_count += 1
                        max_decrypt_ms = max(max_decrypt_ms, decrypt_ms)
                        if decrypt_ms >= 1000:
                            slow_decrypt_count += 1
                    elif status == "skip":
                        skip_count += 1
                        cache_hit_count += 1
                    else:
                        fail_count += 1
                        decrypt_attempt_count += 1
                        decrypt_fail_count += 1
                        max_decrypt_ms = max(max_decrypt_ms, decrypt_ms)
                        if decrypt_ms >= 1000:
                            slow_decrypt_count += 1
                        if len(failed_files) < 100:
                            failed_files.append(
                                {
                                    "file": str(result.get("file_name") or ""),
                                    "md5": str(result.get("md5") or ""),
                                    "error": str(result.get("message") or ""),
                                }
                            )
                        logger.warning(
                            "[media] decrypt_all_stream item_fail: account=%s file=%s md5=%s worker=%s cache_ms=%s decrypt_ms=%s elapsed_ms=%s message=%s",
                            account_dir.name,
                            result.get("file_name"),
                            result.get("md5"),
                            result.get("worker_id"),
                            cache_ms,
                            decrypt_ms,
                            elapsed_ms,
                            result.get("message"),
                        )

                    if elapsed_ms >= 1000:
                        logger.info(
                            "[media] decrypt_all_stream slow_item: account=%s file=%s md5=%s status=%s worker=%s cache_ms=%s decrypt_ms=%s elapsed_ms=%s",
                            account_dir.name,
                            result.get("file_name"),
                            result.get("md5"),
                            status,
                            result.get("worker_id"),
                            cache_ms,
                            decrypt_ms,
                            elapsed_ms,
                        )

                    now = time.perf_counter()
                    if processed_count % 200 == 0 or (now - last_summary_at) >= 15:
                        elapsed_s = max(now - started_at, 0.001)
                        logger.info(
                            "[media] decrypt_all_stream progress_stats: account=%s current=%s total=%s success=%s skip=%s fail=%s concurrency=%s throughput_per_s=%s avg_decrypt_ms=%s max_decrypt_ms=%s slow_decrypt=%s",
                            account_dir.name,
                            processed_count,
                            total_files,
                            success_count,
                            skip_count,
                            fail_count,
                            worker_count,
                            round(processed_count / elapsed_s, 2),
                            round(total_decrypt_ms / max(decrypt_attempt_count, 1), 1),
                            round(max_decrypt_ms, 1),
                            slow_decrypt_count,
                        )
                        last_summary_at = now

                    yield sse(
                        {
                            "type": "progress",
                            "current": processed_count,
                            "total": total_files,
                            "concurrency": worker_count,
                            "success_count": success_count,
                            "skip_count": skip_count,
                            "fail_count": fail_count,
                            "current_file": result.get("file_name"),
                            "status": status,
                            "message": result.get("message"),
                            "worker_id": result.get("worker_id"),
                            "cache_ms": round(cache_ms, 1),
                            "decrypt_ms": round(decrypt_ms, 1),
                            "elapsed_ms": round(elapsed_ms, 1),
                        }
                    )
                    result_queue.task_done()

                    if processed_count % 20 == 0:
                        await asyncio.sleep(0)
            finally:
                stop_event.set()
                for task in worker_tasks:
                    task.cancel()
                if worker_tasks:
                    await asyncio.gather(*worker_tasks, return_exceptions=True)
                executor.shutdown(wait=False, cancel_futures=True)

            avg_decrypt_ms = round(total_decrypt_ms / max(decrypt_attempt_count, 1), 1)
            total_elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
            logger.info(
                "[media] decrypt_all_stream complete: account=%s total=%s success=%s skip=%s fail=%s concurrency=%s cache_hit=%s decrypt_attempt=%s decrypt_fail=%s avg_decrypt_ms=%s max_decrypt_ms=%s slow_decrypt=%s elapsed_ms=%s",
                account_dir.name,
                total_files,
                success_count,
                skip_count,
                fail_count,
                worker_count,
                cache_hit_count,
                decrypt_attempt_count,
                decrypt_fail_count,
                avg_decrypt_ms,
                round(max_decrypt_ms, 1),
                slow_decrypt_count,
                total_elapsed_ms,
            )

            yield sse(
                {
                    "type": "complete",
                    "total": total_files,
                    "concurrency": worker_count,
                    "success_count": success_count,
                    "skip_count": skip_count,
                    "fail_count": fail_count,
                    "output_dir": str(resource_dir),
                    "decrypt_stats": {
                        "cache_hit_count": cache_hit_count,
                        "decrypt_attempt_count": decrypt_attempt_count,
                        "decrypt_fail_count": decrypt_fail_count,
                        "avg_cache_ms": round(total_cache_ms / max(total_files, 1), 1),
                        "avg_decrypt_ms": avg_decrypt_ms,
                        "max_decrypt_ms": round(max_decrypt_ms, 1),
                        "slow_decrypt_count": slow_decrypt_count,
                    },
                    "failed_files": failed_files[:20],
                    "message": f"解密完成: 成功 {success_count}, 跳过 {skip_count}, 失败 {fail_count}（并发 {worker_count}）",
                }
            )

        except Exception as e:
            logger.error(f"[SSE] 解密过程出错: {e}")
            yield sse({"type": "error", "message": str(e)})

    return StreamingResponse(
        generate_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/media/emoji/download_all_stream", summary="批量下载所有表情资源（SSE实时进度）")
async def download_all_emojis_stream(
    request: Request,
    account: Optional[str] = None,
    force: bool = False,
    concurrency: int = 20,
):
    async def is_client_disconnected() -> bool:
        try:
            return await request.is_disconnected()
        except Exception:
            return False

    def sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def generate_progress():
        started_at = time.perf_counter()
        try:
            if await is_client_disconnected():
                logger.info("[SSE] 客户端已断开，取消表情下载任务")
                return

            account_dir = _resolve_account_dir(account)
            worker_count = _normalize_emoji_download_concurrency(concurrency)
            logger.info(
                "[media] emoji_download_all_stream start: request_account=%s resolved_account=%s force=%s requested_concurrency=%s effective_concurrency=%s",
                str(account or "").strip(),
                account_dir.name,
                bool(force),
                concurrency,
                worker_count,
            )

            scan_started_at = time.perf_counter()
            yield sse({"type": "scanning", "message": "正在扫描表情资源..."})
            await asyncio.sleep(0)

            candidate_map, scan_stats = _collect_emoticon_download_catalog(account_dir)
            md5_list = list(candidate_map.keys())
            total_files = len(md5_list)
            scan_elapsed_ms = round((time.perf_counter() - scan_started_at) * 1000, 1)
            source_breakdown = scan_stats.get("source_counts") or {}
            logger.info(
                "[media] emoji_download_all_stream scan_done: account=%s total=%s source_breakdown=%s stats=%s elapsed_ms=%s",
                account_dir.name,
                total_files,
                source_breakdown,
                scan_stats,
                scan_elapsed_ms,
            )

            if await is_client_disconnected():
                logger.info("[SSE] 扫描完成后客户端已断开，停止表情下载任务")
                return

            resource_dir = _get_resource_dir(account_dir)
            resource_dir.mkdir(parents=True, exist_ok=True)

            if total_files == 0:
                yield sse(
                    {
                        "type": "complete",
                        "message": "未发现可下载的表情资源",
                        "total": 0,
                        "success_count": 0,
                        "skip_count": 0,
                        "fail_count": 0,
                        "output_dir": str(resource_dir),
                        "source_breakdown": source_breakdown,
                        "source_stats": scan_stats,
                    }
                )
                return

            yield sse(
                {
                    "type": "start",
                    "total": total_files,
                    "concurrency": worker_count,
                    "requested_concurrency": concurrency,
                    "source_breakdown": source_breakdown,
                    "source_stats": scan_stats,
                    "message": f"开始下载 {total_files} 个表情资源（并发 {worker_count}）",
                }
            )
            await asyncio.sleep(0)

            if await is_client_disconnected():
                logger.info("[SSE] 开始下载前客户端已断开，停止表情下载任务")
                return

            success_count = 0
            skip_count = 0
            fail_count = 0
            processed_count = 0
            failed_files: list[dict] = []
            cache_hit_count = 0
            fetch_attempt_count = 0
            fetch_fail_count = 0
            write_attempt_count = 0
            write_fail_count = 0
            slow_fetch_count = 0
            slow_write_count = 0
            total_cache_ms = 0.0
            total_fetch_ms = 0.0
            total_write_ms = 0.0
            max_fetch_ms = 0.0
            max_write_ms = 0.0
            last_summary_at = time.perf_counter()

            stop_event = asyncio.Event()
            work_queue: asyncio.Queue = asyncio.Queue()
            result_queue: asyncio.Queue = asyncio.Queue()
            for item_index, md5 in enumerate(md5_list, start=1):
                work_queue.put_nowait((item_index, md5))
            for _ in range(worker_count):
                work_queue.put_nowait(None)

            loop = asyncio.get_running_loop()
            executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=worker_count,
                thread_name_prefix="emoji-download",
            )

            def process_one(item_index: int, md5: str, worker_id: int) -> dict:
                item_started_at = time.perf_counter()
                source_info = candidate_map.get(md5, {})
                source_names = ",".join(str(s) for s in (source_info.get("sources") or []))
                url_count = len(source_info.get("urls") or [])
                cache_started_at = time.perf_counter()

                existing = _try_find_decrypted_resource(account_dir, md5)
                if existing:
                    if (not force) and _is_valid_cached_emoji(existing):
                        return {
                            "item_index": item_index,
                            "worker_id": worker_id,
                            "md5": md5,
                            "source": source_names,
                            "url_count": url_count,
                            "status": "skip",
                            "message": "已存在",
                            "path": str(existing),
                            "cache_ms": round((time.perf_counter() - cache_started_at) * 1000, 1),
                            "fetch_ms": 0.0,
                            "write_ms": 0.0,
                            "elapsed_ms": round((time.perf_counter() - item_started_at) * 1000, 1),
                        }
                    try:
                        existing.unlink(missing_ok=True)
                    except Exception:
                        pass
                cache_elapsed_ms = round((time.perf_counter() - cache_started_at) * 1000, 1)

                fetch_started_at = time.perf_counter()
                try:
                    payload, media_type = _try_fetch_emoticon_from_remote(account_dir, md5, source_info)
                    fetch_error = ""
                except Exception as exc:
                    payload, media_type = None, None
                    fetch_error = str(exc)
                fetch_elapsed_ms = round((time.perf_counter() - fetch_started_at) * 1000, 1)

                if not payload or not media_type:
                    message = "未找到可下载地址或下载失败"
                    if fetch_error:
                        message = f"{message}: {fetch_error}"
                    return {
                        "item_index": item_index,
                        "worker_id": worker_id,
                        "md5": md5,
                        "source": source_names,
                        "url_count": url_count,
                        "status": "fail",
                        "phase": "fetch",
                        "message": message,
                        "error": fetch_error,
                        "cache_ms": cache_elapsed_ms,
                        "fetch_ms": fetch_elapsed_ms,
                        "write_ms": 0.0,
                        "elapsed_ms": round((time.perf_counter() - item_started_at) * 1000, 1),
                    }

                ext = _guess_emoji_extension(payload, media_type)
                write_started_at = time.perf_counter()
                try:
                    output_path = _get_decrypted_resource_path(account_dir, md5, ext)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(payload)
                except Exception as exc:
                    return {
                        "item_index": item_index,
                        "worker_id": worker_id,
                        "md5": md5,
                        "source": source_names,
                        "url_count": url_count,
                        "status": "fail",
                        "phase": "write",
                        "message": f"写入失败: {exc}",
                        "error": str(exc),
                        "cache_ms": cache_elapsed_ms,
                        "fetch_ms": fetch_elapsed_ms,
                        "write_ms": round((time.perf_counter() - write_started_at) * 1000, 1),
                        "elapsed_ms": round((time.perf_counter() - item_started_at) * 1000, 1),
                    }

                return {
                    "item_index": item_index,
                    "worker_id": worker_id,
                    "md5": md5,
                    "source": source_names,
                    "url_count": url_count,
                    "status": "success",
                    "message": "下载成功",
                    "path": str(output_path),
                    "media_type": media_type,
                    "bytes": len(payload),
                    "cache_ms": cache_elapsed_ms,
                    "fetch_ms": fetch_elapsed_ms,
                    "write_ms": round((time.perf_counter() - write_started_at) * 1000, 1),
                    "elapsed_ms": round((time.perf_counter() - item_started_at) * 1000, 1),
                }

            async def worker(worker_id: int):
                while not stop_event.is_set():
                    item = await work_queue.get()
                    try:
                        if item is None:
                            return
                        item_index, md5 = item
                        if stop_event.is_set():
                            return
                        try:
                            result = await loop.run_in_executor(executor, process_one, item_index, md5, worker_id)
                        except Exception as exc:
                            result = {
                                "item_index": item_index,
                                "worker_id": worker_id,
                                "md5": md5,
                                "source": "",
                                "url_count": 0,
                                "status": "fail",
                                "phase": "worker",
                                "message": f"处理失败: {exc}",
                                "error": str(exc),
                                "cache_ms": 0.0,
                                "fetch_ms": 0.0,
                                "write_ms": 0.0,
                                "elapsed_ms": 0.0,
                            }
                        if not stop_event.is_set():
                            await result_queue.put(result)
                    finally:
                        work_queue.task_done()

            worker_tasks = [asyncio.create_task(worker(i + 1)) for i in range(worker_count)]
            logger.info(
                "[media] emoji_download_all_stream workers_started: account=%s total=%s concurrency=%s",
                account_dir.name,
                total_files,
                worker_count,
            )

            try:
                while processed_count < total_files:
                    if await is_client_disconnected():
                        stop_event.set()
                        logger.info(
                            "[SSE] 客户端已断开，停止表情下载任务: account=%s current=%s total=%s success=%s skip=%s fail=%s concurrency=%s elapsed_ms=%s",
                            account_dir.name,
                            processed_count,
                            total_files,
                            success_count,
                            skip_count,
                            fail_count,
                            worker_count,
                            round((time.perf_counter() - started_at) * 1000, 1),
                        )
                        return

                    try:
                        result = await asyncio.wait_for(result_queue.get(), timeout=0.5)
                    except asyncio.TimeoutError:
                        continue

                    processed_count += 1
                    status = str(result.get("status") or "")
                    phase = str(result.get("phase") or "")
                    md5 = str(result.get("md5") or "")
                    source_names = str(result.get("source") or "")
                    item_elapsed_ms = float(result.get("elapsed_ms") or 0.0)
                    cache_ms = float(result.get("cache_ms") or 0.0)
                    fetch_ms = float(result.get("fetch_ms") or 0.0)
                    write_ms = float(result.get("write_ms") or 0.0)
                    total_cache_ms += cache_ms
                    total_fetch_ms += fetch_ms
                    total_write_ms += write_ms
                    if fetch_ms:
                        fetch_attempt_count += 1
                        max_fetch_ms = max(max_fetch_ms, fetch_ms)
                        if fetch_ms >= 3000:
                            slow_fetch_count += 1
                    if write_ms:
                        write_attempt_count += 1
                        max_write_ms = max(max_write_ms, write_ms)
                        if write_ms >= 1000:
                            slow_write_count += 1

                    if status == "success":
                        success_count += 1
                    elif status == "skip":
                        skip_count += 1
                        cache_hit_count += 1
                    else:
                        fail_count += 1
                        if phase == "write":
                            write_fail_count += 1
                        else:
                            fetch_fail_count += 1
                        if len(failed_files) < 100:
                            failed_files.append({"md5": md5, "error": str(result.get("message") or "")})
                        logger.debug(
                            "[media] emoji_download_all_stream fail_detail: account=%s md5=%s phase=%s source=%s worker=%s url_count=%s cache_ms=%s fetch_ms=%s write_ms=%s elapsed_ms=%s error=%s",
                            account_dir.name,
                            md5,
                            phase,
                            source_names,
                            result.get("worker_id"),
                            result.get("url_count"),
                            cache_ms,
                            fetch_ms,
                            write_ms,
                            item_elapsed_ms,
                            result.get("error"),
                        )

                    if item_elapsed_ms >= 1000:
                        logger.info(
                            "[media] emoji_download_all_stream slow_item: account=%s md5=%s status=%s phase=%s source=%s worker=%s cache_ms=%s fetch_ms=%s write_ms=%s elapsed_ms=%s bytes=%s",
                            account_dir.name,
                            md5,
                            status,
                            phase,
                            source_names,
                            result.get("worker_id"),
                            cache_ms,
                            fetch_ms,
                            write_ms,
                            item_elapsed_ms,
                            result.get("bytes") or 0,
                        )

                    now = time.perf_counter()
                    if processed_count % 200 == 0 or (now - last_summary_at) >= 15:
                        elapsed_s = max(now - started_at, 0.001)
                        logger.info(
                            "[media] emoji_download_all_stream progress_stats: account=%s current=%s total=%s success=%s skip=%s fail=%s concurrency=%s throughput_per_s=%s avg_fetch_ms=%s max_fetch_ms=%s avg_write_ms=%s max_write_ms=%s slow_fetch=%s slow_write=%s",
                            account_dir.name,
                            processed_count,
                            total_files,
                            success_count,
                            skip_count,
                            fail_count,
                            worker_count,
                            round(processed_count / elapsed_s, 2),
                            round(total_fetch_ms / max(fetch_attempt_count, 1), 1),
                            round(max_fetch_ms, 1),
                            round(total_write_ms / max(write_attempt_count, 1), 1),
                            round(max_write_ms, 1),
                            slow_fetch_count,
                            slow_write_count,
                        )
                        last_summary_at = now

                    event_payload = {
                        "type": "progress",
                        "current": processed_count,
                        "total": total_files,
                        "success_count": success_count,
                        "skip_count": skip_count,
                        "fail_count": fail_count,
                        "current_file": md5,
                        "source": source_names,
                        "status": status,
                        "message": str(result.get("message") or ""),
                        "concurrency": worker_count,
                        "worker_id": result.get("worker_id"),
                        "elapsed_ms": round(item_elapsed_ms, 1),
                        "cache_ms": round(cache_ms, 1),
                        "fetch_ms": round(fetch_ms, 1),
                        "write_ms": round(write_ms, 1),
                    }
                    if result.get("path"):
                        event_payload["path"] = result.get("path")
                    if result.get("media_type"):
                        event_payload["media_type"] = result.get("media_type")
                    yield sse(event_payload)
                    result_queue.task_done()

                    if processed_count % 20 == 0:
                        await asyncio.sleep(0)
            finally:
                stop_event.set()
                for task in worker_tasks:
                    task.cancel()
                if worker_tasks:
                    await asyncio.gather(*worker_tasks, return_exceptions=True)
                executor.shutdown(wait=False, cancel_futures=True)

            total_elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
            avg_fetch_ms = round(total_fetch_ms / max(fetch_attempt_count, 1), 1)
            avg_write_ms = round(total_write_ms / max(write_attempt_count, 1), 1)
            logger.info(
                "[media] emoji_download_all_stream complete: account=%s total=%s success=%s skip=%s fail=%s concurrency=%s cache_hit=%s fetch_attempt=%s fetch_fail=%s write_attempt=%s write_fail=%s avg_fetch_ms=%s max_fetch_ms=%s avg_write_ms=%s max_write_ms=%s slow_fetch=%s slow_write=%s source_breakdown=%s elapsed_ms=%s",
                account_dir.name,
                total_files,
                success_count,
                skip_count,
                fail_count,
                worker_count,
                cache_hit_count,
                fetch_attempt_count,
                fetch_fail_count,
                write_attempt_count,
                write_fail_count,
                avg_fetch_ms,
                round(max_fetch_ms, 1),
                avg_write_ms,
                round(max_write_ms, 1),
                slow_fetch_count,
                slow_write_count,
                source_breakdown,
                total_elapsed_ms,
            )
            yield sse(
                {
                    "type": "complete",
                    "total": total_files,
                    "success_count": success_count,
                    "skip_count": skip_count,
                    "fail_count": fail_count,
                    "output_dir": str(resource_dir),
                    "concurrency": worker_count,
                    "download_stats": {
                        "cache_hit_count": cache_hit_count,
                        "fetch_attempt_count": fetch_attempt_count,
                        "fetch_fail_count": fetch_fail_count,
                        "write_attempt_count": write_attempt_count,
                        "write_fail_count": write_fail_count,
                        "avg_cache_ms": round(total_cache_ms / max(total_files, 1), 1),
                        "avg_fetch_ms": avg_fetch_ms,
                        "max_fetch_ms": round(max_fetch_ms, 1),
                        "avg_write_ms": avg_write_ms,
                        "max_write_ms": round(max_write_ms, 1),
                        "slow_fetch_count": slow_fetch_count,
                        "slow_write_count": slow_write_count,
                    },
                    "source_breakdown": source_breakdown,
                    "source_stats": scan_stats,
                    "failed_files": failed_files[:20],
                    "message": f"表情下载完成: 成功 {success_count}, 跳过 {skip_count}, 失败 {fail_count}（并发 {worker_count}）",
                }
            )
        except Exception as exc:
            logger.error("[media] emoji_download_all_stream error: %s", exc, exc_info=True)
            yield sse({"type": "error", "message": str(exc)})

    return StreamingResponse(
        generate_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
