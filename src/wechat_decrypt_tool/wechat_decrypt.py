#!/usr/bin/env python3
"""
微信4.x数据库解密工具
基于SQLCipher 4.0加密机制，支持批量解密微信数据库文件

使用方法:
python wechat_decrypt.py

密钥: 请通过参数传入您的解密密钥
"""

import os
import hashlib
import hmac
from pathlib import Path
from datetime import datetime
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

# 默认密钥已移除，请通过参数传入
WECHAT_KEY = None

# SQLite文件头
SQLITE_HEADER = b"SQLite format 3\x00"

def setup_logging():
    """设置日志配置"""
    import logging
    
    # 创建日志目录
    now = datetime.now()
    log_dir = Path("output/logs") / str(now.year) / f"{now.month:02d}" / f"{now.day:02d}"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 设置日志文件名
    date_str = now.strftime("%d")
    log_file = log_dir / f"{date_str}_decrypt.log"
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    logging.info(f"日志系统初始化完成，日志文件: {log_file}")
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
        import logging
        
        logging.info(f"开始解密数据库: {db_path}")
        
        try:
            with open(db_path, 'rb') as f:
                encrypted_data = f.read()
            
            logging.info(f"读取文件大小: {len(encrypted_data)} bytes")
            
            if len(encrypted_data) < 4096:
                logging.warning(f"文件太小，跳过解密: {db_path}")
                return False
            
            # 检查是否已经是解密的数据库
            if encrypted_data.startswith(SQLITE_HEADER):
                logging.info(f"文件已是SQLite格式，直接复制: {db_path}")
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
                    logging.warning(f"页面 {page_num} 大小不足: {len(page)} bytes")
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
                    logging.warning(f"页面 {page_num} HMAC验证失败")
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
                    logging.error(f"页面 {page_num} AES解密失败: {e}")
                    failed_pages += 1
                    continue
            
            logging.info(f"解密完成: 成功 {successful_pages} 页, 失败 {failed_pages} 页")
            
            # 写入解密后的文件
            with open(output_path, 'wb') as f:
                f.write(decrypted_data)
            
            logging.info(f"解密文件大小: {len(decrypted_data)} bytes")
            return True
            
        except Exception as e:
            logging.error(f"解密失败: {db_path}, 错误: {e}")
            return False

def decrypt_wechat_databases(db_storage_path: str = None, key: str = None) -> dict:
    """
    微信数据库解密API函数

    参数:
        db_storage_path: 数据库存储路径，如 ......\\{微信id}\\db_storage
                        如果为None，将自动搜索数据库文件
        key: 解密密钥，如果为None，将使用默认密钥

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
    import logging

    # 初始化日志系统
    setup_logging()

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

    logging.info("=" * 60)
    logging.info("微信4.x数据库解密工具 - API模式")
    logging.info("=" * 60)

    # 创建输出目录
    output_dir = Path("output/databases")
    output_dir.mkdir(parents=True, exist_ok=True)
    logging.info(f"输出目录: {output_dir.absolute()}")

    # 查找数据库文件
    if db_storage_path:
        # 使用指定路径查找数据库
        database_paths = []
        storage_path = Path(db_storage_path)
        if storage_path.exists():
            for db_file in storage_path.glob("*.db"):
                if db_file.is_file() and db_file.name != 'key_info.db':
                    database_paths.append(str(db_file))
            logging.info(f"在指定路径找到 {len(database_paths)} 个数据库文件")
        else:
            return {
                "status": "error",
                "message": f"指定的数据库路径不存在: {db_storage_path}",
                "total_databases": 0,
                "successful_count": 0,
                "failed_count": 0,
                "output_directory": str(output_dir.absolute()),
                "processed_files": [],
                "failed_files": []
            }
    else:
        # 使用检测函数获取数据库列表
        try:
            from .wechat_detection import detect_wechat_installation
            wechat_info = detect_wechat_installation()
            if wechat_info and wechat_info.get('databases'):
                database_paths = [db['path'] for db in wechat_info['databases']]
                logging.info(f"通过检测函数找到 {len(database_paths)} 个数据库文件")
            else:
                database_paths = []
                logging.warning("检测函数未找到数据库文件")
        except Exception as e:
            logging.error(f"检测函数调用失败: {e}")
            database_paths = []

    if not database_paths:
        return {
            "status": "error",
            "message": "未找到微信数据库文件！请确保微信已安装并有数据，或提供正确的db_storage路径",
            "total_databases": 0,
            "successful_count": 0,
            "failed_count": 0,
            "output_directory": str(output_dir.absolute()),
            "processed_files": [],
            "failed_files": []
        }

    # 创建解密器
    try:
        decryptor = WeChatDatabaseDecryptor(decrypt_key)
        logging.info("解密器初始化成功")
    except ValueError as e:
        return {
            "status": "error",
            "message": f"密钥错误: {e}",
            "total_databases": len(database_paths),
            "successful_count": 0,
            "failed_count": 0,
            "output_directory": str(output_dir.absolute()),
            "processed_files": [],
            "failed_files": []
        }

    # 批量解密
    success_count = 0
    total_count = len(database_paths)
    processed_files = []
    failed_files = []

    for db_path in database_paths:
        # 生成输出文件名
        db_name = os.path.basename(db_path)
        output_path = output_dir / f"decrypted_{db_name}"

        # 解密数据库
        if decryptor.decrypt_database(db_path, str(output_path)):
            success_count += 1
            processed_files.append(str(output_path))
        else:
            failed_files.append(db_path)
            logging.error(f"解密失败: {db_path}")

    # 返回结果
    result = {
        "status": "success" if success_count > 0 else "error",
        "message": f"解密完成: 成功 {success_count}/{total_count}",
        "total_databases": total_count,
        "successful_count": success_count,
        "failed_count": total_count - success_count,
        "output_directory": str(output_dir.absolute()),
        "processed_files": processed_files,
        "failed_files": failed_files
    }

    logging.info("=" * 60)
    logging.info("解密任务完成!")
    logging.info(f"成功: {success_count}/{total_count}")
    logging.info(f"失败: {total_count - success_count}/{total_count}")
    logging.info(f"输出目录: {output_dir.absolute()}")
    logging.info("=" * 60)

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
