from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..img_helper import IMG_HELPER
from ..platform_support import is_windows, runtime_capabilities
from .wechat_detection import check_wechat_status

router = APIRouter()


@router.get("/api/system/platform", summary="获取当前平台与功能能力")
async def get_platform_capabilities():
    return runtime_capabilities()


def _open_folder_dialog(title: str, initial_dir: str) -> str:
    # 延迟导入并放在独立线程运行，避免阻塞 FastAPI 主线程或发生 GUI 线程冲突
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    root.attributes('-topmost', True)  # 确保弹窗在最前

    folder_path = filedialog.askdirectory(
        parent=root,
        title=title,
        initialdir=initial_dir
    )

    root.destroy()
    return folder_path


@router.get("/api/system/pick_directory", summary="唤起本地原生目录选择器")
async def pick_directory(title: str = "请选择目录", initial_dir: str = ""):
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor() as pool:
        # 在子线程中执行 GUI 操作
        folder_path = await loop.run_in_executor(pool, _open_folder_dialog, title, initial_dir)

    return {"path": folder_path}


@router.get("/api/system/img_helper/status", summary="获取大图下载辅助插件状态")
async def get_img_helper_status():
    return {"supported": is_windows(), "enabled": IMG_HELPER.is_enabled if is_windows() else False}


class ImgHelperToggleRequest(BaseModel):
    enabled: bool


@router.post("/api/system/img_helper/toggle", summary="开启/关闭大图下载辅助插件")
async def toggle_img_helper(req: ImgHelperToggleRequest):
    if not req.enabled:
        IMG_HELPER.disable()
        return {"status": "success", "supported": is_windows(), "enabled": False}

    if not is_windows():
        raise HTTPException(status_code=400, detail="自动下载大图 Hook 仅支持 Windows。")

    # Attempt to enable
    status_res = await check_wechat_status()
    wx_status = status_res.get("wx_status", {})
    if not wx_status.get("is_running") or not wx_status.get("pid"):
        raise HTTPException(status_code=400, detail="未检测到微信正在运行，请先打开微信再尝试！")

    pid = wx_status["pid"]
    ok, err = IMG_HELPER.enable(pid)
    if not ok:
        raise HTTPException(status_code=500, detail=f"开启失败: {err}")

    return {"status": "success", "supported": True, "enabled": True}
