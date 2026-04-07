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

@router.post("/api/import_decrypted", summary="导入已解密的数据库和资源目录")
async def import_decrypted_directory(request: ImportRequest):
    """
    导入已解密的微信数据库和资源目录。
    该功能不需要密钥，直接将现有的已解密文件链接或复制到输出目录。
    """
    import_path = Path(request.import_path.strip())
    if not import_path.exists() or not import_path.is_dir():
        raise HTTPException(status_code=400, detail="导入路径不存在或不是目录")

    # 1. 尝试识别账号名
    # 优先从路径名识别 (例如 .../wxid_xxxx)
    from ..wechat_decrypt import _derive_account_name_from_path
    account_name = _derive_account_name_from_path(import_path)
    
    # 2. 验证关键数据库文件
    # 必须包含 contact.db 和 session.db 才能在列表中正常显示
    required_dbs = ["contact.db", "session.db"]
    for db_name in required_dbs:
        if not _is_valid_sqlite(import_path / db_name):
            # 兼容性检查：如果不在根目录，可能在 db_storage 子目录？
            # 但用户说“和现在完全保存的目录一致”，所以应该在根目录。
            raise HTTPException(status_code=400, detail=f"导入目录中未找到有效的 {db_name}，请确保是已解密的扁平化目录")

    # 3. 准备输出目录
    output_base = get_output_databases_dir()
    account_output_dir = output_base / account_name
    account_output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"正在从 {import_path} 导入账号 {account_name} ...")

    # 4. 导入 .db 文件
    imported_files = []
    for item in import_path.iterdir():
        if item.is_file() and item.suffix == ".db":
            target = account_output_dir / item.name
            try:
                # 优先尝试硬链接以节省空间
                if target.exists():
                    target.unlink()
                os.link(item, target)
                imported_files.append(item.name)
            except Exception as e:
                logger.warning(f"硬链接失败，尝试复制: {item.name}, error: {e}")
                try:
                    shutil.copy2(item, target)
                    imported_files.append(item.name)
                except Exception as e2:
                    logger.error(f"复制失败: {item.name}, error: {e2}")

    # 5. 导入 resource 目录
    resource_src = import_path / "resource"
    if resource_src.exists() and resource_src.is_dir():
        resource_dst = account_output_dir / "resource"
        try:
            if resource_dst.exists():
                if resource_dst.is_symlink() or resource_dst.is_file():
                    resource_dst.unlink()
                else:
                    shutil.rmtree(resource_dst)
            
            # 对目录尝试符号链接（Windows 下可能需要权限）
            try:
                os.symlink(resource_src, resource_dst, target_is_directory=True)
                logger.info("已创建 resource 目录的符号链接")
            except Exception:
                # 符号链接失败则尝试硬链接或复制（对于资源目录，复制比较慢，建议用户手动移动）
                logger.warning("符号链接失败，尝试复制 resource 目录（这可能需要较长时间）")
                shutil.copytree(resource_src, resource_dst, dirs_exist_ok=True)
        except Exception as e:
            logger.error(f"导入 resource 目录失败: {e}")

    # 6. 保存来源信息
    try:
        (account_output_dir / "_source.json").write_text(
            json.dumps(
                {"db_storage_path": str(import_path), "import_mode": "manual_import", "imported_at": __import__('datetime').datetime.now().isoformat()},
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
        "imported_files": imported_files,
        "has_resource": resource_src.exists(),
        "message": f"成功导入账号 {account_name}，共 {len(imported_files)} 个数据库"
    }
