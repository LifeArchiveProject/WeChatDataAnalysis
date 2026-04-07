from __future__ import annotations

import os
import shutil
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..app_paths import get_output_databases_dir
from ..logging_config import get_logger
from ..path_fix import PathFixRoute
from ..session_last_message import build_session_last_message_table

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

@router.post("/api/import_decrypted", summary="执行导入已解密的数据库和资源目录")
async def import_decrypted_directory(request: ImportRequest):
    import_path = Path(request.import_path.strip())
    if not import_path.exists() or not import_path.is_dir():
        raise HTTPException(status_code=400, detail="导入路径不存在或不是目录")

    # 1. 验证并获取账号信息
    info = _validate_import_structure(import_path)
    account_name = info["username"]
    
    # 2. 准备输出目录
    output_base = get_output_databases_dir()
    account_output_dir = output_base / account_name
    account_output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"正在从 {import_path} 导入账号 {account_name} ...")

    # 3. 导入 databases 目录下的 .db 文件
    db_src_dir = import_path / "databases"
    imported_files = []
    for item in db_src_dir.iterdir():
        if item.is_file() and item.suffix == ".db":
            target = account_output_dir / item.name
            try:
                if target.exists():
                    target.unlink()
                os.link(item, target)
                imported_files.append(item.name)
            except Exception:
                try:
                    shutil.copy2(item, target)
                    imported_files.append(item.name)
                except Exception as e:
                    logger.error(f"导入数据库失败: {item.name}, error: {e}")

    # 4. 导入 resource 目录
    resource_src = import_path / "resource"
    if resource_src.exists() and resource_src.is_dir():
        resource_dst = account_output_dir / "resource"
        try:
            if resource_dst.exists():
                if resource_dst.is_symlink() or resource_dst.is_file():
                    resource_dst.unlink()
                else:
                    shutil.rmtree(resource_dst)
            
            try:
                os.symlink(resource_src, resource_dst, target_is_directory=True)
            except Exception:
                shutil.copytree(resource_src, resource_dst, dirs_exist_ok=True)
        except Exception as e:
            logger.error(f"导入 resource 目录失败: {e}")

    # 5. 复制 account.json
    try:
        shutil.copy2(import_path / "account.json", account_output_dir / "account.json")
    except Exception:
        pass

    # 6. 保存来源信息
    try:
        (account_output_dir / "_source.json").write_text(
            json.dumps(
                {
                    "db_storage_path": str(import_path), 
                    "import_mode": "manual_import", 
                    "imported_at": __import__('datetime').datetime.now().isoformat(),
                    "original_info": info
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass

    # 7. 构建缓存
    logger.info(f"正在为 {account_name} 构建会话缓存...")
    try:
        build_session_last_message_table(
            account_output_dir,
            rebuild=True,
            include_hidden=True,
            include_official=True,
        )
    except Exception as e:
        logger.error(f"构建会话缓存失败: {e}")

    return {
        "status": "success",
        "account": account_name,
        "nick": info["nick"],
        "imported_files": imported_files,
        "message": f"成功导入账号 {info['nick']} ({account_name})"
    }
