import asyncio
import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from ..logging_config import get_logger
from ..media_helpers import (
    _collect_all_dat_files,
    _decrypt_and_save_resource,
    _detect_image_media_type,
    _get_resource_dir,
    _load_media_keys,
    _resolve_account_dir,
    _resolve_account_wxid_dir,
    _save_media_keys,
    _try_find_decrypted_resource,
)
from ..path_fix import PathFixRoute

logger = get_logger(__name__)

router = APIRouter(route_class=PathFixRoute)


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
        if xor_key_int is None:
            xor_key_int = cached.get("xor")
        if aes_key16 is None:
            aes_str = str(cached.get("aes") or "").strip()
            if len(aes_str) >= 16:
                aes_key16 = aes_str[:16].encode("ascii", errors="ignore")

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

            if xor_key_int is None:
                yield f"data: {json.dumps({'type': 'error', 'message': '未找到XOR密钥，请先使用 wx_key 获取并保存/填写'})}\n\n"
                return

            # 收集所有.dat文件
            logger.info(f"[SSE] 开始扫描 {wxid_dir} 中的.dat文件...")
            yield f"data: {json.dumps({'type': 'scanning', 'message': '正在扫描图片文件...'})}\n\n"
            await asyncio.sleep(0)

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
                        yield (
                            f"data: {json.dumps({'type': 'progress', 'current': current, 'total': total_files, 'success_count': success_count, 'skip_count': skip_count, 'fail_count': fail_count, 'current_file': file_name, 'status': 'skip', 'message': '已存在'})}\n\n"
                        )
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
                        failed_files.append(
                            {
                                "file": file_name,
                                "md5": md5,
                                "error": msg,
                            }
                        )

                # 每处理一个文件发送进度（成功或失败都发送）
                yield (
                    f"data: {json.dumps({'type': 'progress', 'current': current, 'total': total_files, 'success_count': success_count, 'skip_count': skip_count, 'fail_count': fail_count, 'current_file': file_name, 'status': status, 'message': status_msg})}\n\n"
                )

                # 每处理10个文件让出一次控制权，避免阻塞
                if current % 10 == 0:
                    await asyncio.sleep(0)

            logger.info(f"[SSE] 解密完成: 成功={success_count}, 跳过={skip_count}, 失败={fail_count}")

            # 发送完成消息
            yield (
                f"data: {json.dumps({'type': 'complete', 'total': total_files, 'success_count': success_count, 'skip_count': skip_count, 'fail_count': fail_count, 'output_dir': str(resource_dir), 'failed_files': failed_files[:20], 'message': f'解密完成: 成功 {success_count}, 跳过 {skip_count}, 失败 {fail_count}'})}\n\n"
            )

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
        },
    )
