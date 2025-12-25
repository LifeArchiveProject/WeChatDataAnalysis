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

# 注意：不再支持默认密钥，所有密钥必须通过参数传入

# SQLite文件头
SQLITE_HEADER = b"SQLite format 3\x00"

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

        logger.info(f"开始解密数据库: {db_path}")
        
        try:
            with open(db_path, 'rb') as f:
                encrypted_data = f.read()
            
            logger.info(f"读取文件大小: {len(encrypted_data)} bytes")

            if len(encrypted_data) < 4096:
                logger.warning(f"文件太小，跳过解密: {db_path}")
                return False

            # 检查是否已经是解密的数据库
            if encrypted_data.startswith(SQLITE_HEADER):
                logger.info(f"文件已是SQLite格式，直接复制: {db_path}")
                with open(output_path, 'wb') as f:
                    f.write(encrypted_data)
                return True
            
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
                    continue

            logger.info(f"解密完成: 成功 {successful_pages} 页, 失败 {failed_pages} 页")

            # 写入解密后的文件
            with open(output_path, 'wb') as f:
                f.write(decrypted_data)

            logger.info(f"解密文件大小: {len(decrypted_data)} bytes")
            return True

        except Exception as e:
            logger.error(f"解密失败: {db_path}, 错误: {e}")
            return False

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
    base_output_dir = Path("output/databases")
    base_output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"基础输出目录: {base_output_dir.absolute()}")

    # 查找数据库文件并按账号组织
    account_databases = {}  # {account_name: [db_info, ...]}

    if db_storage_path:
        # 使用指定路径查找数据库
        storage_path = Path(db_storage_path)

        if storage_path.exists():
            # 尝试从路径中提取账号名
            account_name = "unknown_account"
            path_parts = storage_path.parts

            # 常见的微信账号格式模式
            account_patterns = ['wxid_']

            for part in path_parts:
                # 检查是否匹配已知的账号格式
                for pattern in account_patterns:
                    if part.startswith(pattern):
                        # 提取主要部分，去掉后面的随机后缀
                        # 例如：wxid_v4mbduwqtzpt22_1e7a -> wxid_v4mbduwqtzpt22
                        parts = part.split('_')
                        if len(parts) >= 3:  # wxid_主要部分_随机后缀
                            account_name = '_'.join(parts[:-1])  # 去掉最后一个随机部分
                        else:
                            account_name = part  # 如果格式不符合预期，保留原名
                        break
                if account_name != "unknown_account":
                    break

            # 如果没有匹配到已知格式，使用包含数据库的目录名
            if account_name == "unknown_account":
                # 查找包含db_storage的父目录作为账号名
                for part in reversed(path_parts):
                    if part != "db_storage" and len(part) > 3:
                        account_name = part
                        break

            databases = []
            # 使用递归查找，与自动检测逻辑一致
            for root, dirs, files in os.walk(storage_path):
                # 只处理db_storage目录下的数据库文件
                if "db_storage" not in str(root):
                    continue
                for file_name in files:
                    if not file_name.endswith(".db"):
                        continue
                    # 排除不需要解密的数据库
                    if file_name in ["key_info.db"]:
                        continue
                    db_path = os.path.join(root, file_name)
                    databases.append({
                        'path': db_path,
                        'name': file_name,
                        'account': account_name
                    })

            if databases:
                account_databases[account_name] = databases
                logger.info(f"在指定路径找到账号 {account_name} 的 {len(databases)} 个数据库文件")
        else:
            return {
                "status": "error",
                "message": f"指定的数据库路径不存在: {db_storage_path}",
                "total_databases": 0,
                "successful_count": 0,
                "failed_count": 0,
                "output_directory": str(base_output_dir.absolute()),
                "processed_files": [],
                "failed_files": []
            }
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

    for account_name, databases in account_databases.items():
        logger.info(f"开始解密账号 {account_name} 的 {len(databases)} 个数据库")

        # 为每个账号创建专门的输出目录
        account_output_dir = base_output_dir / account_name
        account_output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"账号 {account_name} 输出目录: {account_output_dir}")

        try:
            source_db_storage_path = str(db_storage_path or "")
            wxid_dir = ""
            if db_storage_path:
                sp = Path(db_storage_path)
                if sp.name.lower() == "db_storage":
                    wxid_dir = str(sp.parent)
                else:
                    wxid_dir = str(sp)
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
                logger.error(f"解密失败: {account_name}/{db_name}")

        # 记录账号解密结果
        account_results[account_name] = {
            "total": len(databases),
            "success": account_success,
            "failed": len(databases) - account_success,
            "output_dir": str(account_output_dir),
            "processed_files": account_processed,
            "failed_files": account_failed
        }

        # 构建“会话最后一条消息”索引：把耗时挪到解密阶段，一劳永逸
        if os.environ.get("WECHAT_TOOL_BUILD_SESSION_PREVIEW", "1") != "0":
            try:
                from .session_preview_index import build_session_preview_index

                account_results[account_name]["session_preview_index"] = build_session_preview_index(
                    account_output_dir,
                    rebuild=True,
                    include_hidden=True,
                    include_official=True,
                )
            except Exception as e:
                logger.warning(f"构建会话预览索引失败: {account_name}: {e}")
                account_results[account_name]["session_preview_index"] = {
                    "status": "error",
                    "message": str(e),
                }

        logger.info(f"账号 {account_name} 解密完成: 成功 {account_success}/{len(databases)}")

    # 返回结果
    result = {
        "status": "success" if success_count > 0 else "error",
        "message": f"解密完成: 成功 {success_count}/{total_databases}",
        "total_databases": total_databases,
        "successful_count": success_count,
        "failed_count": total_databases - success_count,
        "output_directory": str(base_output_dir.absolute()),
        "processed_files": processed_files,
        "failed_files": failed_files,
        "account_results": account_results  # 新增：按账号的详细结果
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
