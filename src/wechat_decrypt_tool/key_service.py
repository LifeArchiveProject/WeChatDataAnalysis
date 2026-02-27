# import sys
# import requests

try:
    import wx_key
except ImportError:
    print('[!] 环境中未安装wx_key依赖，可能无法自动获取数据库密钥')
    wx_key = None
    # sys.exit(1)

import time
import psutil
import subprocess
import hashlib
import os
import json
import re
import random
import logging
import asyncio
import httpx
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from packaging import version as pkg_version  # 建议使用 packaging 库处理版本比较
from .wechat_detection import detect_wechat_installation
from .key_store import upsert_account_keys_in_store
from .media_helpers import _resolve_account_dir, _resolve_account_wxid_dir

logger = logging.getLogger(__name__)


# ======================  以下是hook逻辑  ======================================

@dataclass
class HookConfig:
    min_version: str
    pattern: str
    mask: str
    offset: int
    md5_pattern: str = ""
    md5_mask: str = ""
    md5_offset: int = 0

class WeChatKeyFetcher:
    def __init__(self):
        self.process_name = "Weixin.exe"
        self.timeout_seconds = 60

    @staticmethod
    def _hex_array_to_str(hex_array: List[int]) -> str:
        return " ".join([f"{b:02X}" for b in hex_array])

    def _get_hook_config(self, version_str: str) -> Optional[HookConfig]:
        try:
            v_curr = pkg_version.parse(version_str)
        except Exception as e:
            logger.error(f"版本号解析失败: {version_str} || {e}")
            return None


        if v_curr > pkg_version.parse("4.1.6.14"):
            return HookConfig(
                min_version=">4.1.6.14",
                pattern=self._hex_array_to_str([
                    0x24, 0x50, 0x48, 0xC7, 0x45, 0x00, 0xFE, 0xFF, 0xFF, 0xFF,
                    0x44, 0x89, 0xCF, 0x44, 0x89, 0xC3, 0x49, 0x89, 0xD6, 0x48,
                    0x89, 0xCE, 0x48, 0x89
                ]),
                mask="xxxxxxxxxxxxxxxxxxxxxxxx",
                offset=-3,
                md5_pattern="48 8D 4D 00 48 89 4D B0 48 89 45 B8 48 8D 7D 00 48 8D 55 B0 48 89 F9",
                md5_mask="xxx?xxxxxxxxxxx?xxxxxxx",
                md5_offset=4
            )

        if pkg_version.parse("4.1.4") <= v_curr <= pkg_version.parse("4.1.6.14"):
            return HookConfig(
                min_version="4.1.4-4.1.6.14",
                pattern=self._hex_array_to_str([
                    0x24, 0x08, 0x48, 0x89, 0x6c, 0x24, 0x10, 0x48, 0x89, 0x74,
                    0x00, 0x18, 0x48, 0x89, 0x7c, 0x00, 0x20, 0x41, 0x56, 0x48,
                    0x83, 0xec, 0x50, 0x41
                ]),
                mask="xxxxxxxxxx?xxxx?xxxxxxxx",
                offset=-3,
                md5_pattern="48 8D 4D 00 48 89 4D B0 48 89 45 B8 48 8D 7D 00 48 8D 55 B0 48 89 F9",
                md5_mask="xxx?xxxxxxxxxxx?xxxxxxx",
                md5_offset=4
            )

        if v_curr < pkg_version.parse("4.1.4"):
            """图片密钥可能是错的，版本过低没有测试"""
            return HookConfig(
                min_version="<4.1.4",
                pattern=self._hex_array_to_str([
                    0x24, 0x50, 0x48, 0xc7, 0x45, 0x00, 0xfe, 0xff, 0xff, 0xff,
                    0x44, 0x89, 0xcf, 0x44, 0x89, 0xc3, 0x49, 0x89, 0xd6, 0x48,
                    0x89, 0xce, 0x48, 0x89
                ]),
                mask="xxxxxxxxxxxxxxxxxxxxxxxx",
                offset=-15,  # -0xf
                md5_pattern="48 8D 4D 00 48 89 4D B0 48 89 45 B8 48 8D 7D 00 48 8D 55 B0 48 89 F9",
                md5_mask="xxx?xxxxxxxxxxx?xxxxxxx",
                md5_offset=4
            )

        return None

    def kill_wechat(self):
        """检测并查杀微信进程"""
        killed = False
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] == self.process_name:
                    logger.info(f"Killing WeChat process: {proc.info['pid']}")
                    proc.terminate()
                    killed = True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        if killed:
            time.sleep(1)  # 等待完全退出

    def launch_wechat(self, exe_path: str) -> int:
        """启动微信并返回 PID"""
        try:

            process = subprocess.Popen(exe_path)

            time.sleep(2)
            candidates = []
            for proc in psutil.process_iter(['pid', 'name', 'create_time']):
                if proc.info['name'] == self.process_name:
                    candidates.append(proc)

            if candidates:

                candidates.sort(key=lambda x: x.info['create_time'], reverse=True)
                target_pid = candidates[0].info['pid']
                return target_pid

            return process.pid

        except Exception as e:
            logger.error(f"启动微信失败: {e}")
            raise RuntimeError(f"无法启动微信: {e}")

    def fetch_key(self) -> dict:
        """调用 wx_key 获取双密钥"""
        if wx_key is None:
            raise RuntimeError("wx_key 模块未安装或加载失败")

        install_info = detect_wechat_installation()
        exe_path = install_info.get('wechat_exe_path')
        version = install_info.get('wechat_version')

        if not exe_path or not version:
            raise RuntimeError("无法自动定位微信安装路径或版本")

        logger.info(f"Detect WeChat: {version} at {exe_path}")

        config = self._get_hook_config(version)
        if not config:
            raise RuntimeError(f"原生获取失败：当前微信版本 ({version}) 过低，为保证稳定性，仅支持 4.1.5 及以上版本使用原生获取。")

        self.kill_wechat()
        pid = self.launch_wechat(exe_path)
        logger.info(f"WeChat launched, PID: {pid}")

        if not wx_key.initialize_hook(pid, "", config.pattern, config.mask, config.offset,
                                      config.md5_pattern, config.md5_mask, config.md5_offset):
            err = wx_key.get_last_error_msg()
            raise RuntimeError(f"Hook初始化失败: {err}")

        start_time = time.time()
        found_db_key = None
        found_md5_data = None

        try:
            while True:
                if time.time() - start_time > self.timeout_seconds:
                    raise TimeoutError("获取密钥超时 (60s)，请确保在弹出的微信中完成登录。")

                key_data = wx_key.poll_key_data()
                if key_data:
                    if 'key' in key_data:
                        found_db_key = key_data['key']
                    if 'md5' in key_data:
                        found_md5_data = key_data['md5']

                if found_db_key and found_md5_data:
                    break

                while True:
                    msg, level = wx_key.get_status_message()
                    if msg is None:
                        break
                    if level == 2:
                        logger.error(f"[Hook Error] {msg}")

                time.sleep(0.1)
        finally:
            logger.info("Cleaning up hook...")
            wx_key.cleanup_hook()

        aes_key = None  # gemini !!! ???
        xor_key = None

        if found_md5_data and "|" in found_md5_data:
            aes_key, xor_key_dec = found_md5_data.split("|")
            xor_key = f"0x{int(xor_key_dec):02X}"

        return {
            "db_key": found_db_key,
            "aes_key": aes_key,
            "xor_key": xor_key
        }

def get_db_key_workflow():
    fetcher = WeChatKeyFetcher()
    return fetcher.fetch_key()


# ==============================   以下是图片密钥逻辑  =====================================

def get_wechat_internal_global_config(wx_dir: Path, file_name1) -> bytes:
    xwechat_files_root = wx_dir.parent
    target_path = os.path.join(xwechat_files_root, "all_users", "config", file_name1)
    if not os.path.exists(target_path):
        raise FileNotFoundError(f"找不到配置文件: {target_path}，请确认微信数据目录结构是否完整")
    return Path(target_path).read_bytes()



async def fetch_and_save_remote_keys(account: Optional[str] = None) -> Dict[str, Any]:
    account_dir = _resolve_account_dir(account)
    wx_id_dir = _resolve_account_wxid_dir(account_dir)
    wxid = wx_id_dir.name

    url = "https://view.free.c3o.re/api/key"
    data = {"weixinIDFolder": wxid}

    logger.info(f"正在为账号 {wxid} 获取云端备选图片密钥...")

    try:
        blob1_bytes = get_wechat_internal_global_config(wx_id_dir, file_name1="global_config")
        blob2_bytes = get_wechat_internal_global_config(wx_id_dir, file_name1="global_config.crc")
    except Exception as e:
        raise RuntimeError(f"读取微信内部文件失败: {e}")

    files = {
        'fileBytes': ('file', blob1_bytes, 'application/octet-stream'),
        'crcBytes': ('file.crc', blob2_bytes, 'application/octet-stream'),
    }

    async with httpx.AsyncClient(timeout=30) as client:
        logger.info("向云端 API 发送请求...")
        response = await client.post(url, data=data, files=files)

    if response.status_code != 200:
        raise RuntimeError(f"云端服务器错误: {response.status_code} - {response.text[:100]}")

    config = response.json()
    if not config:
        raise RuntimeError("云端解析失败: 返回数据为空")

    # 新 API 的字段兼容处理
    xor_raw = str(config.get("xorKey", config.get("xor_key", "")))
    aes_val = str(config.get("aesKey", config.get("aes_key", "")))

    try:
        if xor_raw.startswith("0x"):
            xor_int = int(xor_raw, 16)
        else:
            xor_int = int(xor_raw)
        xor_hex_str = f"0x{xor_int:02X}"
    except:
        xor_hex_str = xor_raw

    upsert_account_keys_in_store(
        account=wxid,
        image_xor_key=xor_hex_str,
        image_aes_key=aes_val
    )

    return {
        "wxid": wxid,
        "xor_key": xor_hex_str,
        "aes_key": aes_val,
        "nick_name": config.get("nickName", config.get("nick_name", ""))
    }