from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from ..app_paths import get_output_databases_dir
from ..chat_realtime_autosync import CHAT_REALTIME_AUTOSYNC
from ..logging_config import get_logger
from ..path_fix import PathFixRoute
from ..key_store import upsert_account_keys_in_store
from ..wechat_decrypt import (
    WeChatDatabaseDecryptor,
    build_decrypt_summary_message,
    decrypt_wechat_databases,
    scan_account_databases_from_path,
)

logger = get_logger(__name__)

router = APIRouter(route_class=PathFixRoute)


def _normalize_decrypt_guard_accounts(accounts: Any) -> list[str]:
    if not accounts:
        return []

    out: list[str] = []
    seen: set[str] = set()
    for account in accounts:
        key = str(account or "").strip()
        if (not key) or (key in seen):
            continue
        seen.add(key)
        out.append(key)
    out.sort()
    return out


def _resolve_decrypt_guard_accounts(db_storage_path: str) -> list[str]:
    try:
        scan_result = scan_account_databases_from_path(db_storage_path)
    except Exception:
        logger.exception("[decrypt] pre-scan accounts failed db_storage_path=%s", db_storage_path)
        return []

    if scan_result.get("status") == "error":
        return []

    return _normalize_decrypt_guard_accounts((scan_result.get("account_databases") or {}).keys())


def _get_realtime_sync_all_lock(account: str):
    from .chat import _realtime_sync_all_lock

    return _realtime_sync_all_lock(account)


def _release_decrypt_account_guards(guards: list[tuple[str, Any]], *, reason: str) -> None:
    for account, lock in reversed(list(guards or [])):
        try:
            lock.release()
            logger.info("[decrypt] released realtime sync_all lock account=%s reason=%s", account, reason)
        except Exception:
            logger.exception("[decrypt] release realtime sync_all lock failed account=%s reason=%s", account, reason)

        try:
            CHAT_REALTIME_AUTOSYNC.resume_account(account, reason=reason)
            logger.info("[decrypt] resumed realtime autosync for account after decrypt account=%s reason=%s", account, reason)
        except Exception:
            logger.exception(
                "[decrypt] resume realtime autosync failed account=%s reason=%s",
                account,
                reason,
            )


def _acquire_decrypt_account_guards(accounts: Any, *, reason: str) -> list[tuple[str, Any]]:
    guards: list[tuple[str, Any]] = []

    for account in _normalize_decrypt_guard_accounts(accounts):
        paused = False
        try:
            CHAT_REALTIME_AUTOSYNC.pause_account(account, reason=reason)
            paused = True
            logger.info("[decrypt] paused realtime autosync for account during decrypt account=%s reason=%s", account, reason)

            lock = _get_realtime_sync_all_lock(account)
            logger.info("[decrypt] waiting realtime sync_all lock account=%s reason=%s", account, reason)
            lock.acquire()
            logger.info("[decrypt] acquired realtime sync_all lock account=%s reason=%s", account, reason)
            guards.append((account, lock))
        except Exception:
            if paused:
                try:
                    CHAT_REALTIME_AUTOSYNC.resume_account(account, reason=f"{reason}:acquire_failed")
                    logger.info(
                        "[decrypt] resumed realtime autosync after guard acquire failure account=%s reason=%s",
                        account,
                        f"{reason}:acquire_failed",
                    )
                except Exception:
                    logger.exception(
                        "[decrypt] resume realtime autosync after guard acquire failure failed account=%s reason=%s",
                        account,
                        reason,
                    )
            _release_decrypt_account_guards(guards, reason=reason)
            raise

    return guards


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

        guard_accounts = _resolve_decrypt_guard_accounts(request.db_storage_path)
        guards = _acquire_decrypt_account_guards(guard_accounts, reason="decrypt:post")
        try:
            # 使用新的解密API
            results = decrypt_wechat_databases(
                db_storage_path=request.db_storage_path,
                key=request.key,
            )
        finally:
            _release_decrypt_account_guards(guards, reason="decrypt:post")

        if results["status"] == "error":
            logger.error(f"解密失败: {results['message']}")
            raise HTTPException(status_code=400, detail=results["message"])

        logger.info(f"解密完成: 成功 {results['successful_count']}/{results['total_databases']} 个数据库")
        if int(results.get("diagnostic_warning_count") or 0) > 0:
            logger.warning(
                "解密完成但检测到诊断告警: warning_dbs=%s total=%s",
                int(results.get("diagnostic_warning_count") or 0),
                int(results.get("total_databases") or 0),
            )

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
            "diagnostic_warning_count": int(results.get("diagnostic_warning_count") or 0),
        }

    except HTTPException:
        raise
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

        scan_result = scan_account_databases_from_path(p)
        if scan_result["status"] == "error":
            payload = {"type": "error", "message": scan_result["message"]}
            detected_accounts = scan_result.get("detected_accounts") or []
            if detected_accounts:
                payload["detected_accounts"] = detected_accounts
            yield _sse(payload)
            return

        account_databases = scan_result.get("account_databases", {})
        account_sources = scan_result.get("account_sources", {})
        total_databases = sum(len(dbs) for dbs in account_databases.values())

        decrypt_guards: list[tuple[str, Any]] = []
        try:
            guard_accounts = _normalize_decrypt_guard_accounts(account_databases.keys())
            if guard_accounts:
                yield _sse(
                    {
                        "type": "phase",
                        "phase": "decrypt_guard",
                        "message": "正在暂停实时同步并等待解密写锁...",
                    }
                )
                await asyncio.sleep(0)
                decrypt_guards = await asyncio.to_thread(
                    _acquire_decrypt_account_guards,
                    guard_accounts,
                    reason="decrypt:sse",
                )

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
            diagnostic_warning_count = 0
            overall_current = 0

            for account, dbs in account_databases.items():
                account_output_dir = base_output_dir / account
                account_output_dir.mkdir(parents=True, exist_ok=True)

                # Save a hint for later UI (same as non-stream endpoint).
                try:
                    source_info = account_sources.get(account, {})
                    source_db_storage_path = str(source_info.get("db_storage_path") or p)
                    wxid_dir = str(source_info.get("wxid_dir") or "")
                    (account_output_dir / "_source.json").write_text(
                        json.dumps(
                            {"db_storage_path": source_db_storage_path, "wxid_dir": wxid_dir},
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                except Exception:
                    pass

                account_success = 0
                account_processed: list[str] = []
                account_failed: list[str] = []
                account_db_diagnostics: dict[str, dict] = {}
                account_diagnostic_warning_count = 0

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
                    db_diagnostic = dict(getattr(decryptor, "last_result", {}) or {})
                    if not db_diagnostic:
                        db_diagnostic = {
                            "db_path": str(db_path),
                            "db_name": str(db_name),
                            "output_path": str(output_path),
                            "success": bool(ok),
                        }
                    db_diagnostic["account"] = str(account)
                    account_db_diagnostics[db_name] = db_diagnostic

                    if (
                        (not bool(db_diagnostic.get("success", ok)))
                        or int(db_diagnostic.get("failed_pages") or 0) > 0
                        or str(db_diagnostic.get("diagnostic_status") or "") != "ok"
                    ):
                        account_diagnostic_warning_count += 1

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

                    payload = {
                        "type": "progress",
                        "current": overall_current,
                        "total": total_databases,
                        "success_count": success_count,
                        "fail_count": fail_count,
                        "current_file": current_file,
                        "status": status,
                        "message": msg,
                    }
                    if db_diagnostic:
                        payload["diagnostic_status"] = str(db_diagnostic.get("diagnostic_status") or "")
                        payload["page_failures"] = int(db_diagnostic.get("failed_pages") or 0)
                        if db_diagnostic.get("failed_page_samples"):
                            payload["failed_page_samples"] = db_diagnostic.get("failed_page_samples")
                        if db_diagnostic.get("diagnostics"):
                            payload["diagnostics"] = db_diagnostic.get("diagnostics")

                    yield _sse(payload)

                    if overall_current % 5 == 0:
                        await asyncio.sleep(0)

                account_results[account] = {
                    "total": len(dbs),
                    "success": account_success,
                    "failed": len(dbs) - account_success,
                    "output_dir": str(account_output_dir),
                    "processed_files": account_processed,
                    "failed_files": account_failed,
                    "db_diagnostics": account_db_diagnostics,
                    "diagnostic_warning_count": int(account_diagnostic_warning_count),
                }
                diagnostic_warning_count += int(account_diagnostic_warning_count)

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
                "message": build_decrypt_summary_message(
                    success_count=success_count,
                    total_databases=total_databases,
                    diagnostic_warning_count=diagnostic_warning_count,
                ),
                "processed_files": processed_files,
                "failed_files": failed_files,
                "account_results": account_results,
                "diagnostic_warning_count": int(diagnostic_warning_count),
            }

            # Save db key for frontend autofill.
            try:
                for account in (account_results or {}).keys():
                    upsert_account_keys_in_store(str(account), db_key=k)
            except Exception:
                pass

            yield _sse({"type": "complete", **result})
        finally:
            if decrypt_guards:
                await asyncio.to_thread(_release_decrypt_account_guards, decrypt_guards, reason="decrypt:sse")

    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    return StreamingResponse(generate_progress(), media_type="text/event-stream", headers=headers)
