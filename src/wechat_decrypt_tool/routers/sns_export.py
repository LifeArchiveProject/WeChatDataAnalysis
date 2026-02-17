import asyncio
import json
import time
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..path_fix import PathFixRoute
from ..sns_export_service import SNS_EXPORT_MANAGER

router = APIRouter(route_class=PathFixRoute)

ExportScope = Literal["selected", "all"]


class SnsExportCreateRequest(BaseModel):
    account: Optional[str] = Field(None, description="账号目录名（可选，默认使用第一个）")
    scope: ExportScope = Field("selected", description="导出范围：selected=指定联系人；all=全部联系人")
    usernames: list[str] = Field(default_factory=list, description="朋友圈 username 列表（scope=selected 时使用）")
    use_cache: bool = Field(True, description="是否复用导出过程中的本地缓存（默认开启）")
    output_dir: Optional[str] = Field(None, description="导出目录绝对路径（可选；不填时使用默认目录）")
    file_name: Optional[str] = Field(None, description="导出 zip 文件名（可选，不含/含 .zip 都可）")


@router.post("/api/sns/exports", summary="创建朋友圈导出任务（离线 HTML zip）")
async def create_sns_export(req: SnsExportCreateRequest):
    job = SNS_EXPORT_MANAGER.create_job(
        account=req.account,
        scope=req.scope,
        usernames=req.usernames,
        use_cache=bool(req.use_cache),
        output_dir=req.output_dir,
        file_name=req.file_name,
    )
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
        media_type="application/zip",
        filename=job.zip_path.name,
    )


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

