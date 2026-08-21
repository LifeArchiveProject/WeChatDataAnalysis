import asyncio
import json
import time
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, SecretStr

from ..path_fix import PathFixRoute
from ..native_core_export import decode_export_content_key, erase_export_content_key
from ..sns_export_service import SNS_EXPORT_MANAGER

router = APIRouter(route_class=PathFixRoute)

ExportScope = Literal["selected", "all"]
ExportFormat = Literal["html", "json", "txt", "excel"]
ExportOutputMode = Literal["zip", "folder"]


class SnsExportCreateRequest(BaseModel):
    account: Optional[str] = Field(None, description="账号目录名（可选，默认使用第一个）")
    scope: ExportScope = Field("selected", description="导出范围：selected=指定联系人；all=全部联系人")
    usernames: list[str] = Field(default_factory=list, description="朋友圈 username 列表（scope=selected 时使用）")
    format: ExportFormat = Field("html", description="导出格式：html/json/txt/excel")
    use_cache: bool = Field(True, description="是否复用导出过程中的本地缓存（默认开启）")
    output_dir: Optional[str] = Field(None, description="导出目录绝对路径（可选；不填时使用默认目录）")
    file_name: Optional[str] = Field(None, description="导出 zip 文件名（可选，不含/含 .zip 都可）")
    output_mode: ExportOutputMode = Field("zip", description="输出方式：zip=全量压缩包；folder=自动增量目录")
    folder_name: Optional[str] = Field(None, description="增量导出根目录名")
    baseline: Optional[dict[str, Any]] = Field(None, description="浏览器端读取的上轮增量基线")
    missing_files: list[str] = Field(
        default_factory=list,
        description="浏览器目录批量核对后发现缺失或大小不一致的受管理文件",
    )
    reset_baseline: bool = Field(False, description="是否忽略旧基线并完整重建")
    encrypt: bool = Field(False, description="是否使用 WEC1 加密最终导出文件")
    content_key_base64: Optional[SecretStr] = Field(
        None,
        description="WEC1 的 32 字节 Base64 内容密钥；仅 encrypt=true 时使用",
    )


@router.post("/api/sns/exports", summary="创建朋友圈导出任务（全量 ZIP 或增量目录）")
async def create_sns_export(req: SnsExportCreateRequest):
    if req.baseline is not None:
        baseline_size = len(json.dumps(req.baseline, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        if baseline_size > 128 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Incremental baseline is too large.")
    if len(req.missing_files) > 100_000:
        raise HTTPException(status_code=413, detail="Too many missing incremental files.")
    try:
        content_key = decode_export_content_key(
            req.content_key_base64.get_secret_value() if req.content_key_base64 else None,
            enabled=bool(req.encrypt),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        job = SNS_EXPORT_MANAGER.create_job(
            account=req.account,
            scope=req.scope,
            usernames=req.usernames,
            export_format=req.format,
            use_cache=bool(req.use_cache),
            output_dir=req.output_dir,
            file_name=req.file_name,
            output_mode=req.output_mode,
            folder_name=req.folder_name,
            baseline=req.baseline,
            missing_files=req.missing_files,
            reset_baseline=bool(req.reset_baseline),
            encrypt=bool(req.encrypt),
            content_key=content_key,
        )
    except Exception:
        erase_export_content_key(content_key)
        raise
    return {"status": "success", "job": job.to_public_dict()}


@router.get("/api/sns/exports", summary="列出导出任务（内存）")
async def list_sns_exports():
    jobs = [j.to_public_dict() for j in SNS_EXPORT_MANAGER.list_jobs()]
    jobs.sort(key=lambda x: int(x.get("createdAt") or 0), reverse=True)
    return {"status": "success", "jobs": jobs}


@router.get("/api/sns/exports/{export_id}", summary="获取导出任务状态")
async def get_sns_export(export_id: str):
    job = SNS_EXPORT_MANAGER.get_job(str(export_id or "").strip())
    if not job:
        raise HTTPException(status_code=404, detail="Export not found.")
    return {"status": "success", "job": job.to_public_dict()}


@router.get("/api/sns/exports/{export_id}/download", summary="下载导出 zip")
async def download_sns_export(export_id: str):
    job = SNS_EXPORT_MANAGER.get_job(str(export_id or "").strip())
    if not job:
        raise HTTPException(status_code=404, detail="Export not found.")
    if not job.zip_path or (not job.zip_path.exists()):
        raise HTTPException(status_code=409, detail="Export not ready.")
    return FileResponse(
        str(job.zip_path),
        media_type="application/octet-stream" if job.zip_path.suffix.lower() == ".wec" else "application/zip",
        filename=job.zip_path.name,
    )


@router.get("/api/sns/exports/{export_id}/files", summary="获取增量目录变化文件清单")
async def list_sns_export_files(export_id: str):
    job = SNS_EXPORT_MANAGER.get_job(str(export_id or "").strip())
    if not job:
        raise HTTPException(status_code=404, detail="Export not found.")
    if job.status != "done" or not job.change_manifest or not job.staged_files:
        raise HTTPException(status_code=409, detail="Incremental export not ready.")
    return {"status": "success", "manifest": job.change_manifest}


@router.get("/api/sns/exports/{export_id}/files/{file_id}", summary="下载单个增量变化文件")
async def download_sns_export_file(export_id: str, file_id: str):
    path = SNS_EXPORT_MANAGER.get_staged_file(
        str(export_id or "").strip(),
        str(file_id or "").strip(),
    )
    if path is None:
        raise HTTPException(status_code=404, detail="Export file not found.")
    return FileResponse(str(path), media_type="application/octet-stream", filename=path.name)


@router.post("/api/sns/exports/{export_id}/commit", summary="确认浏览器已完成增量目录写入")
async def commit_sns_export_files(export_id: str):
    if not SNS_EXPORT_MANAGER.commit_staged_files(str(export_id or "").strip()):
        raise HTTPException(status_code=404, detail="Export not found.")
    return {"status": "success"}


@router.get("/api/sns/exports/{export_id}/events", summary="导出任务进度 SSE")
async def stream_sns_export_events(export_id: str, request: Request):
    export_id = str(export_id or "").strip()
    job0 = SNS_EXPORT_MANAGER.get_job(export_id)
    if not job0:
        raise HTTPException(status_code=404, detail="Export not found.")

    async def gen():
        last_payload = ""
        last_heartbeat = 0.0

        while True:
            if await request.is_disconnected():
                break

            job = SNS_EXPORT_MANAGER.get_job(export_id)
            if not job:
                yield "event: error\ndata: " + json.dumps({"error": "Export not found."}, ensure_ascii=False) + "\n\n"
                break

            payload = json.dumps(job.to_public_dict(), ensure_ascii=False)
            if payload != last_payload:
                last_payload = payload
                yield f"data: {payload}\n\n"

            now = time.time()
            if now - last_heartbeat > 15:
                last_heartbeat = now
                yield ": ping\n\n"

            if job.status in {"done", "error", "cancelled"}:
                break

            await asyncio.sleep(0.6)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)


@router.delete("/api/sns/exports/{export_id}", summary="取消导出任务")
async def cancel_sns_export(export_id: str):
    ok = SNS_EXPORT_MANAGER.cancel_job(str(export_id or "").strip())
    if not ok:
        raise HTTPException(status_code=404, detail="Export not found.")
    return {"status": "success"}
