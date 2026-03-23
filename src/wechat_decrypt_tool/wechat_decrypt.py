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
import shutil
import tempfile
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .app_paths import get_output_databases_dir

# 注意：不再支持默认密钥，所有密钥必须通过参数传入

# SQLite文件头
SQLITE_HEADER = b"SQLite format 3\x00"
PAGE_SIZE = 4096
KEY_SIZE = 32
SALT_SIZE = 16
IV_SIZE = 16
HMAC_SIZE = 64
RESERVE_SIZE = 80
KEY_MISMATCH_GUIDANCE = (
    "请在当前设备登录该账号后重新获取密钥；"
    "如果聊天记录是从另一台设备复制过来的，当前设备通常无法获取原设备对应的密钥。"
)


def _derive_mac_key(raw_key: bytes, salt: bytes) -> bytes:
    mac_salt = bytes(b ^ 0x3A for b in salt)
    return hashlib.pbkdf2_hmac("sha512", raw_key, mac_salt, 2, dklen=KEY_SIZE)


def _derive_sqlcipher_enc_key(key_material: bytes, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha512", key_material, salt, 256000, dklen=KEY_SIZE)


def _resolve_page1_key_material(key_material: bytes, page1: bytes) -> tuple[bytes, bytes, str] | None:
    salt = page1[:SALT_SIZE]
    stored_page1_hmac = page1[PAGE_SIZE - HMAC_SIZE : PAGE_SIZE]

    candidates = [
        ("raw_enc_key", key_material, _derive_mac_key(key_material, salt)),
    ]

    derived_key = _derive_sqlcipher_enc_key(key_material, salt)
    candidates.append(("sqlcipher_passphrase", derived_key, _derive_mac_key(derived_key, salt)))

    for mode, enc_key, mac_key in candidates:
        expected_page1_hmac = _compute_page_hmac(mac_key, page1, 1)
        if stored_page1_hmac == expected_page1_hmac:
            return enc_key, mac_key, mode

    return None


def _compute_page_hmac(mac_key: bytes, page: bytes, page_num: int) -> bytes:
    offset = SALT_SIZE if page_num == 1 else 0
    data_end = PAGE_SIZE - RESERVE_SIZE + IV_SIZE
    mac = hmac.new(mac_key, digestmod=hashlib.sha512)
    mac.update(page[offset:data_end])
    mac.update(page_num.to_bytes(4, "little"))
    return mac.digest()


def _decrypt_page(raw_key: bytes, page: bytes, page_num: int) -> bytes:
    iv = page[PAGE_SIZE - RESERVE_SIZE : PAGE_SIZE - RESERVE_SIZE + IV_SIZE]
    offset = SALT_SIZE if page_num == 1 else 0
    encrypted = page[offset : PAGE_SIZE - RESERVE_SIZE]

    cipher = Cipher(
        algorithms.AES(raw_key),
        modes.CBC(iv),
        backend=default_backend(),
    )
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(encrypted) + decryptor.finalize()

    if page_num == 1:
        return SQLITE_HEADER + decrypted + (b"\x00" * RESERVE_SIZE)
    return decrypted + (b"\x00" * RESERVE_SIZE)


def _failure_matches_key_mismatch(detail: dict | None) -> bool:
    if not isinstance(detail, dict):
        return False
    code = str(detail.get("code") or "").strip().lower()
    reason = str(detail.get("reason") or "").strip()
    if code == "key_mismatch":
        return True
    return ("密钥" in reason and "不匹配" in reason) or ("当前数据库密钥不正确" in reason)


def build_decrypt_result_message(
    total_databases: int,
    success_count: int,
    failed_count: int,
    failure_details: list[dict] | None = None,
) -> str:
    total = max(int(total_databases or 0), 0)
    success = max(int(success_count or 0), 0)
    failed = max(int(failed_count or 0), 0)
    details = list(failure_details or [])

    if total == 0:
        return "未找到可解密的数据库文件"

    if failed == 0:
        return f"解密完成: 成功 {success}/{total}"

    key_mismatch_count = sum(1 for item in details if _failure_matches_key_mismatch(item))

    if success == 0 and failed == total:
        if key_mismatch_count == failed:
            return (
                f"解密失败：当前数据库密钥不正确，或该密钥不属于当前账号/当前设备（0/{total} 成功）。"
                + KEY_MISMATCH_GUIDANCE
            )
        return f"解密失败：0/{total} 个数据库解密成功，请检查密钥、账号与数据库路径是否匹配。"

    if key_mismatch_count > 0:
        return (
            f"解密完成：成功 {success}/{total}，失败 {failed}/{total}。"
            "失败文件中包含密钥不匹配的数据库，请确认使用的是当前账号在当前设备上的密钥。"
        )

    return f"解密完成：成功 {success}/{total}，失败 {failed}/{total}。"


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
            if file_name in ["key_info.db"]:
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
        self.last_error_code = ""
        self.last_error_message = ""

    def _set_last_error(self, code: str, message: str) -> None:
        self.last_error_code = str(code or "").strip()
        self.last_error_message = str(message or "").strip()

    def _clear_last_error(self) -> None:
        self.last_error_code = ""
        self.last_error_message = ""
    
    def decrypt_database(self, db_path: str, output_path: str) -> bool:
        """解密微信4.x版本数据库

        兼容两种输入形态：
        - raw enc_key（部分内存扫描/工具直接返回）
        - SQLCipher 口令/基础 key（需先用数据库 salt 做一轮 PBKDF2）
        """
        from .logging_config import get_logger
        logger = get_logger(__name__)

        logger.info(f"开始解密数据库: {db_path}")

        tmp_output_path = ""
        self._clear_last_error()
        try:
            file_size = os.path.getsize(db_path)
            logger.info(f"读取文件大小: {file_size} bytes")

            if file_size < PAGE_SIZE:
                message = f"数据库文件过小，无法解密: {db_path}"
                self._set_last_error("file_too_small", message)
                logger.warning(message)
                return False

            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)

            with open(db_path, "rb") as source:
                page1 = source.read(PAGE_SIZE)

            if len(page1) < PAGE_SIZE:
                message = f"数据库首页大小不足，无法解密: {db_path}"
                self._set_last_error("page_too_small", message)
                logger.warning(message)
                return False

            # 检查是否已经是解密的数据库
            if page1.startswith(SQLITE_HEADER):
                logger.info(f"文件已是SQLite格式，直接复制: {db_path}")
                fd, tmp_output_path = tempfile.mkstemp(
                    prefix=f".{Path(output_path).name}.",
                    suffix=".tmp",
                    dir=str(output_dir),
                )
                os.close(fd)
                with open(db_path, "rb") as src, open(tmp_output_path, "wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
                os.replace(tmp_output_path, output_path)
                tmp_output_path = ""
                return True

            resolved_key_material = _resolve_page1_key_material(self.key_bytes, page1)
            if resolved_key_material is None:
                message = f"当前数据库密钥不正确，或该密钥不属于当前账号/当前设备: {db_path}"
                self._set_last_error("key_mismatch", message)
                logger.error(f"页面 1 HMAC验证失败，密钥与数据库不匹配: {db_path}")
                return False
            enc_key, mac_key, key_mode = resolved_key_material
            logger.info(f"页面 1 HMAC验证通过: mode={key_mode} path={db_path}")

            total_pages = (file_size + PAGE_SIZE - 1) // PAGE_SIZE
            successful_pages = 0
            fd, tmp_output_path = tempfile.mkstemp(
                prefix=f".{Path(output_path).name}.",
                suffix=".tmp",
                dir=str(output_dir),
            )
            os.close(fd)

            with open(db_path, "rb") as source, open(tmp_output_path, "wb") as target:
                for page_num in range(1, total_pages + 1):
                    page = source.read(PAGE_SIZE)
                    if not page:
                        break
                    if len(page) < PAGE_SIZE:
                        logger.warning(f"页面 {page_num} 大小不足: {len(page)} bytes，自动补齐到 {PAGE_SIZE} bytes")
                        page = page + (b"\x00" * (PAGE_SIZE - len(page)))

                    stored_hmac = page[PAGE_SIZE - HMAC_SIZE : PAGE_SIZE]
                    expected_hmac = _compute_page_hmac(mac_key, page, page_num)
                    if stored_hmac != expected_hmac:
                        message = f"数据库校验失败，文件可能损坏或密钥不匹配: {db_path}"
                        self._set_last_error("page_hmac_mismatch", message)
                        logger.error(f"页面 {page_num} HMAC验证失败，终止解密: {db_path}")
                        return False

                    target.write(_decrypt_page(enc_key, page, page_num))
                    successful_pages += 1

            logger.info(f"解密完成: 成功 {successful_pages} 页, 失败 0 页")
            os.replace(tmp_output_path, output_path)
            tmp_output_path = ""
            logger.info(f"解密文件大小: {os.path.getsize(output_path)} bytes")
            self._clear_last_error()
            return True

        except Exception as e:
            self._set_last_error("exception", f"解密过程中发生异常: {e}")
            logger.error(f"解密失败: {db_path}, 错误: {e}")
            return False
        finally:
            if tmp_output_path:
                try:
                    os.remove(tmp_output_path)
                except OSError:
                    pass

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
    failure_details = []
    account_results = {}

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
        account_failure_details = []

        for db_info in databases:
            db_path = db_info['path']
            db_name = db_info['name']

            # 生成输出文件名（保持原始文件名，不添加前缀）
            output_path = account_output_dir / db_name

            # 解密数据库
            logger.info(f"解密 {account_name}/{db_name}")
            if decryptor.decrypt_database(db_path, str(output_path)):
                account_success += 1
                success_count += 1
                account_processed.append(str(output_path))
                processed_files.append(str(output_path))
                logger.info(f"解密成功: {account_name}/{db_name}")
            else:
                account_failed.append(db_path)
                failed_files.append(db_path)
                failure_detail = {
                    "account": account_name,
                    "file": db_path,
                    "name": db_name,
                    "code": str(decryptor.last_error_code or "").strip(),
                    "reason": str(decryptor.last_error_message or "").strip() or "解密失败",
                }
                account_failure_details.append(failure_detail)
                failure_details.append(failure_detail)
                logger.error(f"解密失败: {account_name}/{db_name} reason={failure_detail['reason']}")

        # 记录账号解密结果
        account_results[account_name] = {
            "total": len(databases),
            "success": account_success,
            "failed": len(databases) - account_success,
            "output_dir": str(account_output_dir),
            "processed_files": account_processed,
            "failed_files": account_failed,
            "failure_details": account_failure_details,
        }

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
    failed_count = total_databases - success_count
    message = build_decrypt_result_message(
        total_databases=total_databases,
        success_count=success_count,
        failed_count=failed_count,
        failure_details=failure_details,
    )
    result = {
        "status": "success" if success_count > 0 else "error",
        "message": message,
        "total_databases": total_databases,
        "successful_count": success_count,
        "failed_count": failed_count,
        "output_directory": str(base_output_dir.absolute()),
        "processed_files": processed_files,
        "failed_files": failed_files,
        "failure_details": failure_details,
        "account_results": account_results,  # 新增：按账号的详细结果
        "detected_accounts": detected_accounts,
    }

    logger.info("=" * 60)
    logger.info("解密任务完成!")
    logger.info(f"成功: {success_count}/{total_databases}")
    logger.info(f"失败: {failed_count}/{total_databases}")
    logger.info(f"输出目录: {base_output_dir.absolute()}")
    logger.info(f"结果说明: {message}")
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
