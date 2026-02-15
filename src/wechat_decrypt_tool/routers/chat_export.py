import asyncio
import json
import time
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..chat_export_service import CHAT_EXPORT_MANAGER
from ..path_fix import PathFixRoute

router = APIRouter(route_class=PathFixRoute)

ExportFormat = Literal["json", "txt", "html"]
ExportScope = Literal["selected", "all", "groups", "singles"]
MediaKind = Literal["image", "emoji", "video", "video_thumb", "voice", "file"]
MessageType = Literal[
    "text",
    "image",
    "emoji",
    "video",
    "voice",
    "chatHistory",
    "file",
    "link",
    "transfer",
    "redPacket",
    "system",
    "quote",
    "voip",
]


class ChatExportCreateRequest(BaseModel):
    account: Optional[str] = Field(None, description="账号目录名（可选，默认使用第一个）")
    scope: ExportScope = Field("selected", description="导出范围：selected=指定会话；all=全部；groups=仅群聊；singles=仅单聊")
    usernames: list[str] = Field(default_factory=list, description="会话 username 列表（scope=selected 时使用）")
    format: ExportFormat = Field("json", description="导出格式：json/txt/html（zip 内每个会话一个文件；html 可离线打开 index.html 查看）")
    start_time: Optional[int] = Field(None, description="起始时间（Unix 秒，含）")
    end_time: Optional[int] = Field(None, description="结束时间（Unix 秒，含）")
    include_hidden: bool = Field(False, description="是否包含隐藏会话（scope!=selected 时）")
    include_official: bool = Field(False, description="是否包含公众号/官方账号会话（scope!=selected 时）")
    include_media: bool = Field(True, description="是否允许打包离线媒体（最终仍受 message_types 与 privacy_mode 约束）")
    media_kinds: list[MediaKind] = Field(
        default_factory=lambda: ["image", "emoji", "video", "video_thumb", "voice", "file"],
        description="允许打包的媒体类型（最终仍受 message_types 勾选约束）",
    )
    message_types: list[MessageType] = Field(
        default_factory=list,
        description="导出消息类型（renderType）过滤：为空=导出全部类型；不为空时，仅导出勾选类型",
    )
    output_dir: Optional[str] = Field(None, description="导出目录绝对路径（可选；不填时使用默认目录）")
    allow_process_key_extract: bool = Field(
        False,
        description="预留字段：本项目不从微信进程提取媒体密钥，请使用 wx_key 获取并保存/批量解密",
    )
    download_remote_media: bool = Field(
        False,
        description="HTML 导出时允许联网下载链接/引用缩略图等远程媒体（提高离线完整性）",
    )
    html_page_size: int = Field(
        1000,
        description="HTML 导出分页大小（每页消息数）；<=0 表示禁用分页（单文件，打开大聊天可能很卡）",
    )
    privacy_mode: bool = Field(
        False,
        description="隐私模式导出：隐藏会话/用户名/内容，不打包头像与媒体",
    )
    file_name: Optional[str] = Field(None, description="导出 zip 文件名（可选，不含/含 .zip 都可）")


@router.post("/api/chat/exports", summary="创建聊天记录导出任务（离线 zip）")
async def create_chat_export(req: ChatExportCreateRequest):
    job = CHAT_EXPORT_MANAGER.create_job(
        account=req.account,
        scope=req.scope,
        usernames=req.usernames,
        export_format=req.format,
        start_time=req.start_time,
        end_time=req.end_time,
        include_hidden=req.include_hidden,
        include_official=req.include_official,
        include_media=req.include_media,
        media_kinds=req.media_kinds,
        message_types=req.message_types,
        output_dir=req.output_dir,
        allow_process_key_extract=req.allow_process_key_extract,
        download_remote_media=req.download_remote_media,
        html_page_size=req.html_page_size,
        privacy_mode=req.privacy_mode,
        file_name=req.file_name,
    )
    return {"status": "success", "job": job.to_public_dict()}


@router.get("/api/chat/exports", summary="列出导出任务（内存）")
async def list_chat_exports():
    jobs = [j.to_public_dict() for j in CHAT_EXPORT_MANAGER.list_jobs()]
    jobs.sort(key=lambda x: int(x.get("createdAt") or 0), reverse=True)
    return {"status": "success", "jobs": jobs}


@router.get("/api/chat/exports/{export_id}", summary="获取导出任务状态")
async def get_chat_export(export_id: str):
    job = CHAT_EXPORT_MANAGER.get_job(str(export_id or "").strip())
    if not job:
        raise HTTPException(status_code=404, detail="Export not found.")
    return {"status": "success", "job": job.to_public_dict()}


@router.get("/api/chat/exports/{export_id}/download", summary="下载导出 zip")
async def download_chat_export(export_id: str):
    job = CHAT_EXPORT_MANAGER.get_job(str(export_id or "").strip())
    if not job:
        raise HTTPException(status_code=404, detail="Export not found.")
    if not job.zip_path or (not job.zip_path.exists()):
        raise HTTPException(status_code=409, detail="Export not ready.")
    return FileResponse(
        str(job.zip_path),
        media_type="application/zip",
        filename=job.zip_path.name,
    )


@router.get("/api/chat/exports/{export_id}/events", summary="导出任务进度 SSE")
async def stream_chat_export_events(export_id: str, request: Request):
    export_id = str(export_id or "").strip()
    job0 = CHAT_EXPORT_MANAGER.get_job(export_id)
    if not job0:
        raise HTTPException(status_code=404, detail="Export not found.")

    async def gen():
        last_payload = ""
        last_heartbeat = 0.0

        while True:
            if await request.is_disconnected():
                break

            job = CHAT_EXPORT_MANAGER.get_job(export_id)
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


@router.delete("/api/chat/exports/{export_id}", summary="取消导出任务")
async def cancel_chat_export(export_id: str):
    ok = CHAT_EXPORT_MANAGER.cancel_job(str(export_id or "").strip())
    if not ok:
        raise HTTPException(status_code=404, detail="Export not found.")
    return {"status": "success"}
