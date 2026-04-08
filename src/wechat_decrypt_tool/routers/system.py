from fastapi import APIRouter
from pydantic import BaseModel
import asyncio
from concurrent.futures import ThreadPoolExecutor

router = APIRouter()


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