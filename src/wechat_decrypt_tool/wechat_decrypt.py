#!/usr/bin/env python3
"""
微信4.x数据库解密工具
基于SQLCipher 4.0加密机制，支持批量解密微信数据库文件

使用方法:
python wechat_decrypt.py

密钥: 请通过参数传入您的解密密钥
"""

import hashlib
import hmac
import os
import json
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .app_paths import get_output_databases_dir
from .database_filters import should_skip_source_database
from .sqlite_diagnostics import collect_sqlite_diagnostics, sqlite_diagnostics_status

# 注意：不再支持默认密钥，所有密钥必须通过参数传入

# SQLite文件头
SQLITE_HEADER = b"SQLite format 3\x00"


def _normalize_account_name(name: str) -> str:
    value = str(name or "").strip()
    if not value:
        return "unknown_account"

    if value.startswith("wxid_"):
        parts = value.split("_")
        if len(parts) >= 3:
            trimmed = "_".join(parts[:-1]).strip()
            if trimmed:
                return trimmed

    return value


def _derive_account_name_from_path(path: Path) -> str:
    try:
        target = path.resolve()
    except Exception:
        target = path

    for part in target.parts:
        part_str = str(part or "").strip()
        if part_str.startswith("wxid_"):
            return _normalize_account_name(part_str)

    for part in reversed(target.parts):
        part_str = str(part or "").strip()
        if not part_str or part_str.lower() == "db_storage" or len(part_str) <= 3:
            continue
        return _normalize_account_name(part_str)

    return "unknown_account"


def _build_decrypt_failure_message(result: dict) -> str:
    failed_pages = int(result.get("failed_pages") or 0)
    successful_pages = int(result.get("successful_pages") or 0)
    diagnostic_status = str(result.get("diagnostic_status") or "").strip()
    diagnostics = dict(result.get("diagnostics") or {})

    detail = (
        diagnostics.get("quick_check_error")
        or diagnostics.get("connect_error")
        or diagnostics.get("table_list_error")
        or diagnostics.get("page_count_error")
        or diagnostics.get("quick_check")
        or diagnostic_status
    )
    detail_text = " ".join(str(detail or "").split()).strip()

    if failed_pages > 0 and successful_pages == 0:
        if detail_text:
            return f"数据库校验未通过，密钥可能不匹配当前账号: {detail_text}"
        return "数据库校验未通过，密钥可能不匹配当前账号"

    if diagnostic_status and diagnostic_status != "ok":
        if detail_text:
            return f"解密输出不是有效的 SQLite 数据库: {detail_text}"
        return "解密输出不是有效的 SQLite 数据库"

    if failed_pages > 0:
        return "解密输出包含页失败，结果不完整"

    return ""


def build_decrypt_summary_message(*, success_count: int, total_databases: int, diagnostic_warning_count: int) -> str:
    success_count = int(success_count or 0)
    total_databases = int(total_databases or 0)
    diagnostic_warning_count = int(diagnostic_warning_count or 0)

    if total_databases <= 0:
        return "未找到可解密的数据库"

    if success_count <= 0:
        if diagnostic_warning_count > 0:
            return "解密失败：数据库校验未通过，密钥可能不匹配当前账号。"
        return "解密失败：未能成功解密任何数据库。"

    if success_count < total_databases:
        if diagnostic_warning_count > 0:
            return f"解密部分成功：成功 {success_count}/{total_databases}，其余数据库校验未通过。"
        return f"解密部分成功：成功 {success_count}/{total_databases}。"

    return f"解密完成: 成功 {success_count}/{total_databases}"


def _resolve_db_storage_roots(storage_path: Path) -> list[Path]:
    try:
        target = storage_path.resolve()
    except Exception:
        target = storage_path

    if not target.exists():
        return []

    current = target if target.is_dir() else target.parent
    probe = current
    while True:
        if probe.name.lower() == "db_storage":
            return [probe]
        parent = probe.parent
        if parent == probe:
            break
        probe = parent

    roots: list[Path] = []
    try:
        for root, dirs, _files in os.walk(current):
            root_path = Path(root)
            if root_path.name.lower() != "db_storage":
                continue
            roots.append(root_path)
            dirs[:] = []
    except Exception:
        return []

    uniq: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(root)
    uniq.sort(key=lambda p: str(p).lower())
    return uniq


def scan_account_databases_from_path(db_storage_path: str) -> dict:
    storage_path = Path(str(db_storage_path or "").strip())
    if not storage_path.exists():
        return {
            "status": "error",
            "message": f"指定的数据库路径不存在: {db_storage_path}",
            "account_databases": {},
            "account_sources": {},
            "detected_accounts": [],
        }

    db_roots = _resolve_db_storage_roots(storage_path)
    if not db_roots:
        return {
            "status": "error",
            "message": "未找到微信数据库文件！请确保路径指向具体账号的 db_storage 目录。",
            "account_databases": {},
            "account_sources": {},
            "detected_accounts": [],
        }

    detected_accounts = [
        {
            "account": _derive_account_name_from_path(root),
            "db_storage_path": str(root),
            "wxid_dir": str(root.parent),
        }
        for root in db_roots
    ]

    if len(db_roots) > 1:
        account_names = ", ".join(
            [str(item.get("account") or item.get("db_storage_path") or "").strip() for item in detected_accounts]
        )
        return {
            "status": "error",
            "message": (
                "检测到多个账号目录，请选择具体账号的 db_storage 目录后再解密，"
                f"不要直接选择上级目录。当前检测到: {account_names}"
            ),
            "account_databases": {},
            "account_sources": {},
            "detected_accounts": detected_accounts,
        }

    db_root = db_roots[0]
    account_name = _derive_account_name_from_path(db_root)
    databases: list[dict] = []
    for root, _dirs, files in os.walk(db_root):
        for file_name in files:
            if not file_name.endswith(".db"):
                continue
            if should_skip_source_database(file_name):
                continue
            db_path = os.path.join(root, file_name)
            databases.append(
                {
                    "path": db_path,
                    "name": file_name,
                    "account": account_name,
                }
            )

    if not databases:
        return {
            "status": "error",
            "message": "未找到微信数据库文件！请检查 db_storage_path 是否正确",
            "account_databases": {},
            "account_sources": {},
            "detected_accounts": detected_accounts,
        }

    return {
        "status": "success",
        "message": "",
        "account_databases": {account_name: databases},
        "account_sources": {
            account_name: {
                "db_storage_path": str(db_root),
                "wxid_dir": str(db_root.parent),
            }
        },
        "detected_accounts": detected_accounts,
    }

def setup_logging():
    """设置日志配置 - 已弃用，使用统一的日志配置"""
    from .logging_config import setup_logging as unified_setup_logging

    # 使用统一的日志配置
    log_file = unified_setup_logging()
    log_dir = log_file.parent

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"解密模块日志系统初始化完成，日志文件: {log_file}")
    return log_dir



class WeChatDatabaseDecryptor:
    """微信4.x数据库解密器"""

    def __init__(self, key_hex: str):
        """初始化解密器

        参数:
            key_hex: 64位十六进制密钥
        """
        if len(key_hex) != 64:
            raise ValueError("密钥必须是64位十六进制字符串")
        
        try:
            self.key_bytes = bytes.fromhex(key_hex)
        except ValueError:
            raise ValueError("密钥必须是有效的十六进制字符串")
        self.last_result: dict = {}
    
    def decrypt_database(self, db_path: str, output_path: str) -> bool:
        """解密微信4.x版本数据库

        使用SQLCipher 4.0参数:
        - PBKDF2-SHA512, 256000轮迭代
        - AES-256-CBC加密
        - HMAC-SHA512验证
        - 页面大小4096字节
        """
        from .logging_config import get_logger
        logger = get_logger(__name__)

        result = {
            "db_path": str(db_path),
            "db_name": Path(str(db_path)).name,
            "output_path": str(output_path),
            "success": False,
            "copied_as_sqlite": False,
            "input_size": 0,
            "output_size": 0,
            "total_pages": 0,
            "successful_pages": 0,
            "failed_pages": 0,
            "failed_page_samples": [],
            "failure_reasons": {},
            "diagnostics": {},
            "diagnostic_status": "not_run",
            "error": "",
        }
        self.last_result = result

        def _append_failed_page(page_num: int, reason: str, error: str = "") -> None:
            result["failure_reasons"][reason] = int(result["failure_reasons"].get(reason) or 0) + 1
            if len(result["failed_page_samples"]) >= 8:
                return
            item = {"page": int(page_num), "reason": str(reason)}
            err = " ".join(str(error or "").split()).strip()
            if err:
                item["error"] = err[:200]
            result["failed_page_samples"].append(item)

        def _finalize(success: bool, error: str = "") -> bool:
            normalized_success = bool(success)
            result["success"] = normalized_success
            if error:
                result["error"] = " ".join(str(error).split()).strip()

            output_file = Path(str(output_path))
            if output_file.exists():
                try:
                    result["output_size"] = int(output_file.stat().st_size)
                except Exception:
                    pass

                diagnostics = collect_sqlite_diagnostics(output_file, quick_check=True)
                result["diagnostics"] = diagnostics
                result["diagnostic_status"] = sqlite_diagnostics_status(diagnostics)

            if normalized_success:
                failure_message = _build_decrypt_failure_message(result)
                if failure_message:
                    normalized_success = False
                    result["success"] = False
                    if not result["error"]:
                        result["error"] = failure_message
                    if output_file.exists():
                        try:
                            output_file.unlink()
                        except Exception as exc:
                            logger.warning("删除无效解密输出失败: %s, 错误: %s", output_file, exc)

            payload = {
                "db_name": result["db_name"],
                "db_path": result["db_path"],
                "output_path": result["output_path"],
                "success": result["success"],
                "copied_as_sqlite": result["copied_as_sqlite"],
                "input_size": result["input_size"],
                "output_size": result["output_size"],
                "total_pages": result["total_pages"],
                "successful_pages": result["successful_pages"],
                "failed_pages": result["failed_pages"],
                "failure_reasons": result["failure_reasons"],
                "failed_page_samples": result["failed_page_samples"],
                "diagnostic_status": result["diagnostic_status"],
                "diagnostics": result["diagnostics"],
                "error": result["error"],
            }
            log_fn = logger.info
            if (
                (not result["success"])
                or int(result["failed_pages"] or 0) > 0
                or str(result["diagnostic_status"] or "") != "ok"
            ):
                log_fn = logger.warning
            log_fn("[decrypt.diagnostic] %s", json.dumps(payload, ensure_ascii=False, sort_keys=True))
            self.last_result = result
            return bool(result["success"])

        logger.info(f"开始解密数据库: {db_path}")
        
        try:
            with open(db_path, 'rb') as f:
                encrypted_data = f.read()
            
            logger.info(f"读取文件大小: {len(encrypted_data)} bytes")
            result["input_size"] = int(len(encrypted_data))

            if len(encrypted_data) < 4096:
                logger.warning(f"文件太小，跳过解密: {db_path}")
                return _finalize(False, "file_too_small")

            # 检查是否已经是解密的数据库
            if encrypted_data.startswith(SQLITE_HEADER):
                logger.info(f"文件已是SQLite格式，直接复制: {db_path}")
                with open(output_path, 'wb') as f:
                    f.write(encrypted_data)
                result["copied_as_sqlite"] = True
                return _finalize(True)
            
            # 提取salt (前16字节)
            salt = encrypted_data[:16]
            
            # 计算mac_salt (salt XOR 0x3a)
            mac_salt = bytes(b ^ 0x3a for b in salt)
            
            # 使用PBKDF2-SHA512派生密钥
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA512(),
                length=32,
                salt=salt,
                iterations=256000,
                backend=default_backend()
            )
            derived_key = kdf.derive(self.key_bytes)
            
            # 派生MAC密钥
            mac_kdf = PBKDF2HMAC(
                algorithm=hashes.SHA512(),
                length=32,
                salt=mac_salt,
                iterations=2,
                backend=default_backend()
            )
            mac_key = mac_kdf.derive(derived_key)
            
            # 解密数据
            decrypted_data = bytearray()
            decrypted_data.extend(SQLITE_HEADER)
            
            page_size = 4096
            iv_size = 16
            hmac_size = 64  # SHA512的HMAC是64字节
            
            # 计算保留区域大小 (对齐到AES块大小)
            reserve_size = iv_size + hmac_size
            if reserve_size % 16 != 0:
                reserve_size = ((reserve_size // 16) + 1) * 16
            
            total_pages = len(encrypted_data) // page_size
            successful_pages = 0
            failed_pages = 0
            result["total_pages"] = int(total_pages)
            
            # 逐页解密
            for cur_page in range(total_pages):
                start = cur_page * page_size
                end = start + page_size
                page = encrypted_data[start:end]
                
                page_num = cur_page + 1  # 页面编号从1开始
                
                if len(page) < page_size:
                    logger.warning(f"页面 {page_num} 大小不足: {len(page)} bytes")
                    break
                
                # 确定偏移量：第一页(cur_page == 0)需要跳过salt
                offset = 16 if cur_page == 0 else 0  # SALT_SIZE = 16
                
                # 提取存储的HMAC
                hmac_start = page_size - reserve_size + iv_size
                hmac_end = hmac_start + hmac_size
                stored_hmac = page[hmac_start:hmac_end]
                
                # 按照wechat-dump-rs的方式验证HMAC
                data_end = page_size - reserve_size + iv_size
                hmac_data = page[offset:data_end]
                
                # 分步计算HMAC：先更新数据，再更新页面编号
                mac = hmac.new(mac_key, digestmod=hashlib.sha512)
                mac.update(hmac_data)  # 包含加密数据+IV
                mac.update(page_num.to_bytes(4, 'little'))  # 页面编号(小端序)
                expected_hmac = mac.digest()
                
                if stored_hmac != expected_hmac:
                    logger.warning(f"页面 {page_num} HMAC验证失败")
                    failed_pages += 1
                    _append_failed_page(page_num, "hmac")
                    continue
                
                # 提取IV和加密数据用于AES解密
                iv = page[page_size - reserve_size:page_size - reserve_size + iv_size]
                encrypted_page = page[offset:page_size - reserve_size]
                
                # AES-CBC解密
                try:
                    cipher = Cipher(
                        algorithms.AES(derived_key),
                        modes.CBC(iv),
                        backend=default_backend()
                    )
                    decryptor = cipher.decryptor()
                    decrypted_page = decryptor.update(encrypted_page) + decryptor.finalize()
                    
                    # 按照wechat-dump-rs的方式重组页面数据
                    decrypted_data.extend(decrypted_page)
                    decrypted_data.extend(page[page_size - reserve_size:])  # 保留区域
                    
                    successful_pages += 1
                
                except Exception as e:
                    logger.error(f"页面 {page_num} AES解密失败: {e}")
                    failed_pages += 1
                    _append_failed_page(page_num, "aes", str(e))
                    continue

            logger.info(f"解密完成: 成功 {successful_pages} 页, 失败 {failed_pages} 页")
            result["successful_pages"] = int(successful_pages)
            result["failed_pages"] = int(failed_pages)

            # 写入解密后的文件
            with open(output_path, 'wb') as f:
                f.write(decrypted_data)

            logger.info(f"解密文件大小: {len(decrypted_data)} bytes")
            if failed_pages > 0:
                logger.warning(
                    "解密输出包含页失败: db=%s total_pages=%s failed_pages=%s failure_reasons=%s samples=%s",
                    result["db_name"],
                    int(total_pages),
                    int(failed_pages),
                    json.dumps(result["failure_reasons"], ensure_ascii=False, sort_keys=True),
                    json.dumps(result["failed_page_samples"], ensure_ascii=False),
                )
            return _finalize(True)

        except Exception as e:
            logger.error(f"解密失败: {db_path}, 错误: {e}")
            return _finalize(False, str(e))

def decrypt_wechat_databases(db_storage_path: str = None, key: str = None) -> dict:
    """
    微信数据库解密API函数

    参数:
        db_storage_path: 数据库存储路径，如 ......\\{微信id}\\db_storage
                        如果为None，将自动搜索数据库文件
        key: 解密密钥（必需参数），64位十六进制字符串

    返回值:
        dict: 解密结果统计信息
        {
            "status": "success" | "error",
            "message": "描述信息",
            "total_databases": 总数据库数量,
            "successful_count": 成功解密数量,
            "failed_count": 失败数量,
            "output_directory": "输出目录路径",
            "processed_files": ["解密成功的文件列表"],
            "failed_files": ["解密失败的文件列表"]
        }
    """
    from .logging_config import get_logger

    # 获取日志器
    logger = get_logger(__name__)

    # 验证密钥是否提供
    if not key:
        return {
            "status": "error",
            "message": "解密密钥是必需的参数",
            "total_databases": 0,
            "successful_count": 0,
            "failed_count": 0,
            "output_directory": "",
            "processed_files": [],
            "failed_files": []
        }

    decrypt_key = key

    logger.info("=" * 60)
    logger.info("微信4.x数据库解密工具 - API模式")
    logger.info("=" * 60)

    # 创建基础输出目录
    base_output_dir = get_output_databases_dir()
    base_output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"基础输出目录: {base_output_dir.absolute()}")

    # 查找数据库文件并按账号组织
    account_databases = {}  # {account_name: [db_info, ...]}
    account_sources = {}
    detected_accounts = []

    if db_storage_path:
        scan_result = scan_account_databases_from_path(db_storage_path)
        detected_accounts = scan_result.get("detected_accounts", [])
        if scan_result["status"] == "error":
            return {
                "status": "error",
                "message": scan_result["message"],
                "total_databases": 0,
                "successful_count": 0,
                "failed_count": 0,
                "output_directory": str(base_output_dir.absolute()),
                "processed_files": [],
                "failed_files": [],
                "detected_accounts": scan_result.get("detected_accounts", []),
            }
        account_databases = scan_result.get("account_databases", {})
        account_sources = scan_result.get("account_sources", {})
        for account_name, databases in account_databases.items():
            logger.info(f"在指定路径找到账号 {account_name} 的 {len(databases)} 个数据库文件")
    else:
        # 不再支持自动检测，要求用户提供具体的db_storage_path
        return {
            "status": "error",
            "message": "请提供具体的db_storage_path参数。由于一个密钥只能对应一个账户，不支持自动检测多账户。",
            "total_databases": 0,
            "successful_count": 0,
            "failed_count": 0,
            "output_directory": str(base_output_dir.absolute()),
            "processed_files": [],
            "failed_files": []
        }

    if not account_databases:
        return {
            "status": "error",
            "message": "未找到微信数据库文件！请确保微信已安装并有数据，或提供正确的db_storage路径",
            "total_databases": 0,
            "successful_count": 0,
            "failed_count": 0,
            "output_directory": str(base_output_dir.absolute()),
            "processed_files": [],
            "failed_files": []
        }

    # 计算总数据库数量
    total_databases = sum(len(dbs) for dbs in account_databases.values())

    # 创建解密器
    try:
        decryptor = WeChatDatabaseDecryptor(decrypt_key)
        logger.info("解密器初始化成功")
    except ValueError as e:
        return {
            "status": "error",
            "message": f"密钥错误: {e}",
            "total_databases": total_databases,
            "successful_count": 0,
            "failed_count": 0,
            "output_directory": str(base_output_dir.absolute()),
            "processed_files": [],
            "failed_files": []
        }

    # 按账号批量解密
    success_count = 0
    processed_files = []
    failed_files = []
    account_results = {}
    diagnostic_warning_count = 0

    for account_name, databases in account_databases.items():
        logger.info(f"开始解密账号 {account_name} 的 {len(databases)} 个数据库")

        # 为每个账号创建专门的输出目录
        account_output_dir = base_output_dir / account_name
        account_output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"账号 {account_name} 输出目录: {account_output_dir}")

        try:
            source_info = account_sources.get(account_name, {})
            source_db_storage_path = str(source_info.get("db_storage_path") or db_storage_path or "")
            wxid_dir = str(source_info.get("wxid_dir") or "")
            (account_output_dir / "_source.json").write_text(
                json.dumps(
                    {
                        "db_storage_path": source_db_storage_path,
                        "wxid_dir": wxid_dir,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

        account_success = 0
        account_processed = []
        account_failed = []
        account_db_diagnostics = {}
        account_diagnostic_warning_count = 0

        for db_info in databases:
            db_path = db_info['path']
            db_name = db_info['name']

            # 生成输出文件名（保持原始文件名，不添加前缀）
            output_path = account_output_dir / db_name

            # 解密数据库
            logger.info(f"解密 {account_name}/{db_name}")
            ok = decryptor.decrypt_database(db_path, str(output_path))
            db_diagnostic = dict(getattr(decryptor, "last_result", {}) or {})
            if not db_diagnostic:
                db_diagnostic = {
                    "db_path": str(db_path),
                    "db_name": str(db_name),
                    "output_path": str(output_path),
                    "success": bool(ok),
                }
            db_diagnostic["account"] = str(account_name)
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
                logger.info(f"解密成功: {account_name}/{db_name}")
            else:
                account_failed.append(db_path)
                failed_files.append(db_path)
                logger.error(f"解密失败: {account_name}/{db_name}")

        # 记录账号解密结果
        account_results[account_name] = {
            "total": len(databases),
            "success": account_success,
            "failed": len(databases) - account_success,
            "output_dir": str(account_output_dir),
            "processed_files": account_processed,
            "failed_files": account_failed,
            "db_diagnostics": account_db_diagnostics,
            "diagnostic_warning_count": int(account_diagnostic_warning_count),
        }
        diagnostic_warning_count += int(account_diagnostic_warning_count)

        # 构建“会话最后一条消息”缓存表：把耗时挪到解密阶段，后续会话列表直接查表
        if os.environ.get("WECHAT_TOOL_BUILD_SESSION_LAST_MESSAGE", "1") != "0":
            try:
                from .session_last_message import build_session_last_message_table

                account_results[account_name]["session_last_message"] = build_session_last_message_table(
                    account_output_dir,
                    rebuild=True,
                    include_hidden=True,
                    include_official=True,
                )
            except Exception as e:
                logger.warning(f"构建会话最后一条消息缓存表失败: {account_name}: {e}")
                account_results[account_name]["session_last_message"] = {
                    "status": "error",
                    "message": str(e),
                }

        logger.info(f"账号 {account_name} 解密完成: 成功 {account_success}/{len(databases)}")

    # 返回结果
    result = {
        "status": "success" if success_count > 0 else "error",
        "message": build_decrypt_summary_message(
            success_count=success_count,
            total_databases=total_databases,
            diagnostic_warning_count=diagnostic_warning_count,
        ),
        "total_databases": total_databases,
        "successful_count": success_count,
        "failed_count": total_databases - success_count,
        "output_directory": str(base_output_dir.absolute()),
        "processed_files": processed_files,
        "failed_files": failed_files,
        "account_results": account_results,  # 新增：按账号的详细结果
        "detected_accounts": detected_accounts,
        "diagnostic_warning_count": int(diagnostic_warning_count),
    }

    logger.info("=" * 60)
    logger.info("解密任务完成!")
    logger.info(f"成功: {success_count}/{total_databases}")
    logger.info(f"失败: {total_databases - success_count}/{total_databases}")
    logger.info(f"输出目录: {base_output_dir.absolute()}")
    logger.info("=" * 60)

    return result


def main():
    """主函数 - 保持向后兼容"""
    result = decrypt_wechat_databases()
    if result["status"] == "error":
        print(f"错误: {result['message']}")
    else:
        print(f"解密完成: {result['message']}")
        print(f"输出目录: {result['output_directory']}")

if __name__ == "__main__":
    main()
