from __future__ import annotations

import os
import shutil
import json
import asyncio
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..app_paths import get_output_databases_dir
from ..logging_config import get_logger
from ..path_fix import PathFixRoute
from ..session_last_message import build_session_last_message_table
from ..media_helpers import _wxgf_to_image_bytes

logger = get_logger(__name__)

router = APIRouter(route_class=PathFixRoute)

class ImportRequest(BaseModel):
    import_path: str = Field(..., description="已解密的数据库和资源所在目录的绝对路径")

def _is_valid_sqlite(path: Path) -> bool:
    SQLITE_HEADER = b"SQLite format 3\x00"
    try:
        if not path.exists() or not path.is_file():
            return False
        with path.open("rb") as f:
            return f.read(len(SQLITE_HEADER)) == SQLITE_HEADER
    except Exception:
        return False

def _validate_import_structure(import_path: Path) -> dict:
    """
    验证导入目录结构：
    - databases/ (必须包含 contact.db, session.db)
    - resource/ (可选)
    - account.json (必须包含 username, nick)
    """
    db_dir = import_path / "databases"
    account_json_path = import_path / "account.json"
    
    if not db_dir.exists() or not db_dir.is_dir():
        raise HTTPException(status_code=400, detail="未找到 databases 目录")
    
    if not account_json_path.exists():
        raise HTTPException(status_code=400, detail="未找到 account.json 文件")
    
    # 验证关键数据库
    required_dbs = ["contact.db", "session.db"]
    for db_name in required_dbs:
        if not _is_valid_sqlite(db_dir / db_name):
            raise HTTPException(status_code=400, detail=f"databases 目录中未找到有效的 {db_name}")
            
    # 解析 account.json
    try:
        account_info = json.loads(account_json_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析 account.json 失败: {e}")
        
    username = account_info.get("username")
    nick = account_info.get("nick")
    
    if not username or not nick:
        raise HTTPException(status_code=400, detail="account.json 中缺少 username 或 nick")
        
    return {
        "username": username,
        "nick": nick,
        "avatar_url": account_info.get("avatar_url", ""),
        "has_resource": (import_path / "resource").exists()
    }

@router.post("/api/import_decrypted/preview", summary="预览待导入的账号信息")
async def preview_import(request: ImportRequest):
    import_path = Path(request.import_path.strip())
    if not import_path.exists() or not import_path.is_dir():
        raise HTTPException(status_code=400, detail="导入路径不存在或不是目录")
        
    return _validate_import_structure(import_path)

@router.get("/api/import_decrypted", summary="执行导入已解密的数据库和资源目录 (SSE)")
async def import_decrypted_directory(
    import_path: str = Query(..., description="已解密的数据库和资源所在目录的绝对路径")
):
    import_path_obj = Path(import_path.strip())
    
    def _sse(data: dict):
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def generate_progress():
        try:
            if not import_path_obj.exists() or not import_path_obj.is_dir():
                yield _sse({"type": "error", "message": "导入路径不存在或不是目录"})
                return

            yield _sse({"type": "progress", "percent": 5, "message": "正在验证目录结构..."})
            # 1. 验证并获取账号信息
            try:
                info = await asyncio.to_thread(_validate_import_structure, import_path_obj)
            except HTTPException as e:
                yield _sse({"type": "error", "message": e.detail})
                return
            except Exception as e:
                yield _sse({"type": "error", "message": f"验证失败: {e}"})
                return
            
            account_name = info["username"]
            yield _sse({"type": "progress", "percent": 10, "message": f"验证成功: {account_name}"})
            
            # 2. 准备输出目录
            output_base = get_output_databases_dir()
            account_output_dir = output_base / account_name
            await asyncio.to_thread(account_output_dir.mkdir, parents=True, exist_ok=True)

            yield _sse({"type": "progress", "percent": 15, "message": "正在准备目标目录..."})

            # 3. 导入 databases 目录下的 .db 文件
            db_src_dir = import_path_obj / "databases"
            db_files = [f for f in db_src_dir.iterdir() if f.is_file() and f.suffix == ".db"]
            imported_files = []
            
            for i, item in enumerate(db_files):
                target = account_output_dir / item.name
                def _do_import_db(src, dst):
                    if dst.exists():
                        dst.unlink()
                    try:
                        os.link(src, dst)
                    except Exception:
                        shutil.copy2(src, dst)
                
                try:
                    await asyncio.to_thread(_do_import_db, item, target)
                    imported_files.append(item.name)
                except Exception as e:
                    logger.error(f"导入数据库失败: {item.name}, error: {e}")
                
                percent = 15 + int((i + 1) / (len(db_files) or 1) * 15)
                yield _sse({"type": "progress", "percent": percent, "message": f"正在导入数据库: {item.name}"})

            # 4. 导入 resource 目录
            resource_src = import_path_obj / "resource"
            if resource_src.exists() and resource_src.is_dir():
                yield _sse({"type": "progress", "percent": 30, "message": "正在导入资源文件 (这可能需要一些时间)..."})
                resource_dst = account_output_dir / "resource"
                
                def _do_import_resource(src, dst):
                    if dst.exists():
                        if dst.is_symlink() or dst.is_file():
                            dst.unlink()
                        else:
                            shutil.rmtree(dst)
                    try:
                        os.symlink(src, dst, target_is_directory=True)
                    except Exception:
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                
                try:
                    await asyncio.to_thread(_do_import_resource, resource_src, resource_dst)
                except Exception as e:
                    logger.error(f"导入 resource 目录失败: {e}")
                
                # 5. 转换 .wxgf 资源 (新增加的流程)
                yield _sse({"type": "progress", "percent": 50, "message": "正在搜索并转换 .wxgf 图片..."})
                
                if resource_dst.exists():
                    # 搜索 wxgf 文件
                    def _find_wxgf(root_dir):
                        found = []
                        for root, _, files in os.walk(root_dir):
                            for f in files:
                                if f.lower().endswith(".wxgf"):
                                    found.append(Path(root) / f)
                        return found
                    
                    wxgf_files = await asyncio.to_thread(_find_wxgf, resource_dst)
                    
                    if wxgf_files:
                        total_wxgf = len(wxgf_files)
                        converted_count = 0
                        for i, wxgf_path in enumerate(wxgf_files):
                            def _convert_one(p):
                                jpg_p = p.with_suffix(".wxgf.jpg")
                                if not jpg_p.exists():
                                    data = p.read_bytes()
                                    if data.startswith(b"wxgf"):
                                        converted = _wxgf_to_image_bytes(data)
                                        if converted:
                                            jpg_p.write_bytes(converted)
                                            return True
                                else:
                                    return True # 已经存在视为成功
                                return False

                            try:
                                success = await asyncio.to_thread(_convert_one, wxgf_path)
                                if success:
                                    converted_count += 1
                            except Exception as e:
                                logger.error(f"转换 wxgf 失败: {wxgf_path}, {e}")
                            
                            if i % max(1, total_wxgf // 20) == 0 or i == total_wxgf - 1:
                                progress_val = 50 + int((i + 1) / total_wxgf * 30)
                                yield _sse({"type": "progress", "percent": progress_val, "message": f"转换 wxgf 图片: {i+1}/{total_wxgf}"})
                        
                        logger.info(f"账号 {account_name} 转换完成: {converted_count}/{total_wxgf} 个 .wxgf 文件")
                
            # 6. 复制 account.json
            yield _sse({"type": "progress", "percent": 85, "message": "正在更新账号配置..."})
            try:
                await asyncio.to_thread(shutil.copy2, import_path_obj / "account.json", account_output_dir / "account.json")
            except Exception:
                pass

            # 7. 保存来源信息
            def _save_source_info(dst, path, info):
                (dst / "_source.json").write_text(
                    json.dumps(
                        {
                            "db_storage_path": str(path), 
                            "import_mode": "manual_import", 
                            "imported_at": __import__('datetime').datetime.now().isoformat(),
                            "original_info": info
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

            try:
                await asyncio.to_thread(_save_source_info, account_output_dir, import_path_obj, info)
            except Exception:
                pass

            # 8. 构建缓存
            yield _sse({"type": "progress", "percent": 90, "message": "正在构建会话缓存 (这可能需要较长时间)..."})
            try:
                await asyncio.to_thread(
                    build_session_last_message_table,
                    account_output_dir,
                    rebuild=True,
                    include_hidden=True,
                    include_official=True,
                )
            except Exception as e:
                logger.error(f"构建会话缓存失败: {e}")

            yield _sse({
                "type": "complete",
                "status": "success",
                "account": account_name,
                "nick": info["nick"],
                "message": f"成功导入账号 {info['nick']} ({account_name})"
            })

        except Exception as e:
            logger.error(f"导入过程中发生异常: {e}", exc_info=True)
            yield _sse({"type": "error", "message": f"导入失败: {str(e)}"})

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no"
    }
    return StreamingResponse(generate_progress(), headers=headers)
