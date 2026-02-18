from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from ..app_paths import get_output_databases_dir
from ..logging_config import get_logger
from ..path_fix import PathFixRoute
from ..key_store import upsert_account_keys_in_store
from ..wechat_decrypt import WeChatDatabaseDecryptor, decrypt_wechat_databases

logger = get_logger(__name__)

router = APIRouter(route_class=PathFixRoute)


class DecryptRequest(BaseModel):
    """解密请求模型"""

    key: str = Field(..., description="解密密钥，64位十六进制字符串")
    db_storage_path: str = Field(..., description="数据库存储路径，必须是绝对路径")


@router.post("/api/decrypt", summary="解密微信数据库")
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
            key=request.key,
        )

        if results["status"] == "error":
            logger.error(f"解密失败: {results['message']}")
            raise HTTPException(status_code=400, detail=results["message"])

        logger.info(f"解密完成: 成功 {results['successful_count']}/{results['total_databases']} 个数据库")

        # 成功解密后，按账号保存数据库密钥（用于前端自动回填）
        try:
            for account_name in (results.get("account_results") or {}).keys():
                upsert_account_keys_in_store(str(account_name), db_key=request.key)
        except Exception:
            pass

        return {
            "status": "completed" if results["status"] == "success" else "failed",
            "total_databases": results["total_databases"],
            "success_count": results["successful_count"],
            "failure_count": results["failed_count"],
            "output_directory": results["output_directory"],
            "message": results["message"],
            "processed_files": results["processed_files"],
            "failed_files": results["failed_files"],
            "account_results": results.get("account_results", {}),
        }

    except Exception as e:
        logger.error(f"解密API异常: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/decrypt_stream", summary="解密微信数据库（SSE实时进度）")
async def decrypt_databases_stream(
    request: Request,
    key: str | None = None,
    db_storage_path: str | None = None,
):
    """通过SSE实时推送数据库解密进度。

    注意：EventSource 只支持 GET，因此参数通过 querystring 传递。
    """

    def _sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def generate_progress():
        # 1) Basic validation (keep 200 + SSE error event, avoid 422 breaking EventSource).
        k = str(key or "").strip()
        p = str(db_storage_path or "").strip()

        if not k or len(k) != 64:
            yield _sse({"type": "error", "message": "密钥格式无效，必须是64位十六进制字符串"})
            return

        try:
            bytes.fromhex(k)
        except Exception:
            yield _sse({"type": "error", "message": "密钥必须是有效的十六进制字符串"})
            return

        if not p:
            yield _sse({"type": "error", "message": "请提供 db_storage_path 参数"})
            return

        storage_path = Path(p)
        if not storage_path.exists():
            yield _sse({"type": "error", "message": f"指定的数据库路径不存在: {p}"})
            return

        # 2) Scan databases.
        yield _sse({"type": "scanning", "message": "正在扫描数据库文件..."})
        await asyncio.sleep(0)

        account_name = "unknown_account"
        path_parts = storage_path.parts
        account_patterns = ["wxid_"]
        for part in path_parts:
            for pattern in account_patterns:
                if part.startswith(pattern):
                    parts = part.split("_")
                    if len(parts) >= 3:
                        account_name = "_".join(parts[:-1])
                    else:
                        account_name = part
                    break
            if account_name != "unknown_account":
                break

        if account_name == "unknown_account":
            for part in reversed(path_parts):
                if part != "db_storage" and len(part) > 3:
                    account_name = part
                    break

        databases: list[dict] = []
        for root, _dirs, files in os.walk(storage_path):
            if "db_storage" not in str(root):
                continue
            for file_name in files:
                if not file_name.endswith(".db"):
                    continue
                if file_name in ["key_info.db"]:
                    continue
                db_path = os.path.join(root, file_name)
                databases.append({"path": db_path, "name": file_name, "account": account_name})

        if not databases:
            yield _sse({"type": "error", "message": "未找到微信数据库文件！请检查 db_storage_path 是否正确"})
            return

        account_databases = {account_name: databases}
        total_databases = sum(len(dbs) for dbs in account_databases.values())

        yield _sse({"type": "start", "total": total_databases, "message": f"开始解密 {total_databases} 个数据库"})
        await asyncio.sleep(0)

        # 3) Init output dir & decryptor.
        base_output_dir = get_output_databases_dir()
        base_output_dir.mkdir(parents=True, exist_ok=True)

        try:
            decryptor = WeChatDatabaseDecryptor(k)
        except ValueError as e:
            yield _sse({"type": "error", "message": f"密钥错误: {e}"})
            return

        # 4) Decrypt per account, stream progress.
        success_count = 0
        fail_count = 0
        processed_files: list[str] = []
        failed_files: list[str] = []
        account_results: dict = {}
        overall_current = 0

        for account, dbs in account_databases.items():
            account_output_dir = base_output_dir / account
            account_output_dir.mkdir(parents=True, exist_ok=True)

            # Save a hint for later UI (same as non-stream endpoint).
            try:
                source_db_storage_path = p
                wxid_dir = ""
                if storage_path.name.lower() == "db_storage":
                    wxid_dir = str(storage_path.parent)
                else:
                    wxid_dir = str(storage_path)
                (account_output_dir / "_source.json").write_text(
                    json.dumps({"db_storage_path": source_db_storage_path, "wxid_dir": wxid_dir}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass

            account_success = 0
            account_processed: list[str] = []
            account_failed: list[str] = []

            for db_info in dbs:
                if await request.is_disconnected():
                    return

                overall_current += 1
                db_path = str(db_info.get("path") or "")
                db_name = str(db_info.get("name") or "")
                current_file = f"{account}/{db_name}" if account else db_name

                # Emit a "processing" event so UI updates immediately for large db files.
                yield _sse(
                    {
                        "type": "progress",
                        "current": overall_current,
                        "total": total_databases,
                        "success_count": success_count,
                        "fail_count": fail_count,
                        "current_file": current_file,
                        "status": "processing",
                        "message": "解密中...",
                    }
                )

                output_path = account_output_dir / db_name
                task = asyncio.create_task(asyncio.to_thread(decryptor.decrypt_database, db_path, str(output_path)))

                # Wait with heartbeat (can't yield while awaiting the thread directly).
                last_heartbeat = time.time()
                while not task.done():
                    if await request.is_disconnected():
                        return
                    now = time.time()
                    if now - last_heartbeat > 15:
                        last_heartbeat = now
                        # SSE comment heartbeat; browsers ignore but keeps proxies alive.
                        yield ": ping\n\n"
                    await asyncio.sleep(0.6)
                try:
                    ok = bool(task.result())
                except Exception:
                    ok = False

                if ok:
                    account_success += 1
                    success_count += 1
                    account_processed.append(str(output_path))
                    processed_files.append(str(output_path))
                    status = "success"
                    msg = "解密成功"
                else:
                    account_failed.append(db_path)
                    failed_files.append(db_path)
                    fail_count += 1
                    status = "fail"
                    msg = "解密失败"

                yield _sse(
                    {
                        "type": "progress",
                        "current": overall_current,
                        "total": total_databases,
                        "success_count": success_count,
                        "fail_count": fail_count,
                        "current_file": current_file,
                        "status": status,
                        "message": msg,
                    }
                )

                if overall_current % 5 == 0:
                    await asyncio.sleep(0)

            account_results[account] = {
                "total": len(dbs),
                "success": account_success,
                "failed": len(dbs) - account_success,
                "output_dir": str(account_output_dir),
                "processed_files": account_processed,
                "failed_files": account_failed,
            }

            # Build cache table (keep behavior consistent with the POST endpoint).
            if os.environ.get("WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE", "1") != "0":
                yield _sse(
                    {
                        "type": "phase",
                        "phase": "session_last_message",
                        "account": account,
                        "message": "正在构建会话缓存（最后一条消息）...",
                    }
                )
                await asyncio.sleep(0)

                try:
                    from ..session_last_message import build_session_last_message_table

                    task = asyncio.create_task(
                        asyncio.to_thread(
                            build_session_last_message_table,
                            account_output_dir,
                            rebuild=True,
                            include_hidden=True,
                            include_official=True,
                        )
                    )
                    last_heartbeat = time.time()
                    while not task.done():
                        if await request.is_disconnected():
                            return
                        now = time.time()
                        if now - last_heartbeat > 15:
                            last_heartbeat = now
                            yield ": ping\n\n"
                        await asyncio.sleep(0.6)
                    account_results[account]["session_last_message"] = task.result()
                except Exception as e:
                    account_results[account]["session_last_message"] = {"status": "error", "message": str(e)}

        status = "completed" if success_count > 0 else "failed"
        result = {
            "status": status,
            "total_databases": total_databases,
            "success_count": success_count,
            "failure_count": total_databases - success_count,
            "output_directory": str(base_output_dir.absolute()),
            "message": f"解密完成: 成功 {success_count}/{total_databases}",
            "processed_files": processed_files,
            "failed_files": failed_files,
            "account_results": account_results,
        }

        # Save db key for frontend autofill.
        try:
            for account in (account_results or {}).keys():
                upsert_account_keys_in_store(str(account), db_key=k)
        except Exception:
            pass

        yield _sse({"type": "complete", **result})

    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    return StreamingResponse(generate_progress(), media_type="text/event-stream", headers=headers)
