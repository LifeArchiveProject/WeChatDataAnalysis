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
    pattern: str  # 用 00 不要用 ?  !!!!  否则C++内存会炸
    mask: str
    offset: int


class WeChatKeyFetcher:
    def __init__(self):
        self.process_name = "Weixin.exe"
        self.timeout_seconds = 60

    @staticmethod
    def _hex_array_to_str(hex_array: List[int]) -> str:
        return " ".join([f"{b:02X}" for b in hex_array])

    def _get_hook_config(self, version_str: str) -> Optional[HookConfig]:
        """搬运自wx_key代码，未来用ida脚本直接获取即可"""
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
                offset=-3
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
                offset=-3
            )

        if v_curr < pkg_version.parse("4.1.4"):
            return HookConfig(
                min_version="<4.1.4",
                pattern=self._hex_array_to_str([
                    0x24, 0x50, 0x48, 0xc7, 0x45, 0x00, 0xfe, 0xff, 0xff, 0xff,
                    0x44, 0x89, 0xcf, 0x44, 0x89, 0xc3, 0x49, 0x89, 0xd6, 0x48,
                    0x89, 0xce, 0x48, 0x89
                ]),
                mask="xxxxxxxxxxxxxxxxxxxxxxxx",
                offset=-15  # -0xf
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

    def fetch_key(self) -> str:
        """没有wx_key模块无法自动获取密钥"""
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
            raise RuntimeError(f"不支持的微信版本: {version}")

        self.kill_wechat()

        pid = self.launch_wechat(exe_path)
        logger.info(f"WeChat launched, PID: {pid}")

        logger.info(f"Initializing Hook with pattern: {config.pattern[:20]}... Offset: {config.offset}")

        if not wx_key.initialize_hook(pid, "", config.pattern, config.mask, config.offset):
            err = wx_key.get_last_error_msg()
            raise RuntimeError(f"Hook初始化失败: {err}")

        start_time = time.time()


        try:
            while True:
                if time.time() - start_time > self.timeout_seconds:
                    raise TimeoutError("获取密钥超时 (60s)")

                key = wx_key.poll_key_data()
                if key:
                    found_key = key
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

        if found_key:
            return found_key
        else:
            raise RuntimeError("未知错误，未获取到密钥")

def get_db_key_workflow():
    fetcher = WeChatKeyFetcher()
    return fetcher.fetch_key()


# ==============================   以下是图片密钥逻辑  =====================================


# 远程 API 配置
REMOTE_URL = "https://view.free.c3o.re/dashboard"
BASE_URL = "https://view.free.c3o.re"  # 用于拼接js

# NEXT_ACTION_ID = "7c8f99280c70626ccf5960cc4a68f368197e15f8e9"  # 不可以硬编码


async def fetch_js_and_scan(client: httpx.AsyncClient, js_path: str) -> Optional[str]:
    """
    异步下载单个 JS 文件并匹配 Action ID
    """
    full_url = f"{BASE_URL}{js_path}" if js_path.startswith("/") else js_path
    try:
        response = await client.get(full_url)
        if response.status_code != 200:
            return None

        content = response.text

        action_id_pattern = re.compile(r'createServerReference.*?["\']([a-f0-9]{42})["\'].*?["\']getUserConfigFromBytes["\']')

        match = action_id_pattern.search(content)
        if match:
            found_id = match.group(1)
            return found_id

    except Exception as e:
        logger.error(f"Error fetching {js_path}: {e}")
    return None


async def _get_next_action_id_async() -> str:
    async with httpx.AsyncClient(timeout=10.0) as client:

        resp = await client.get(REMOTE_URL)
        html = resp.text

        js_file_pattern = re.compile(r'src="(/_next/static/chunks/[^"]+\.js)"')
        js_files = set(js_file_pattern.findall(html))

        if not js_files:
            raise Exception("未找到任何 Next.js chunk 文件，可能页面结构已变动。")

        tasks = [fetch_js_and_scan(client, js_path) for js_path in js_files]

        results = await asyncio.gather(*tasks)

        for res in results:
            if res:
                return res

        raise Exception("遍历了所有 JS 文件，但未找到匹配的 createServerReference ID。")


def get_wechat_internal_global_config(wx_dir: Path, file_name1) -> bytes:
    """
    读微信目录下的主配置文件
    """
    xwechat_files_root = wx_dir.parent

    target_path = os.path.join(xwechat_files_root, "all_users", "config", file_name1)

    if not os.path.exists(target_path):
        logger.error(f"未找到微信内部 global_config: {target_path}")
        raise FileNotFoundError(f"找不到文件: {target_path}，请确认微信数据目录结构是否完整")

    return Path(target_path).read_bytes()



async def fetch_and_save_remote_keys(account: Optional[str] = None) -> Dict[str, Any]:
    account_dir = _resolve_account_dir(account)
    wx_id_dir = _resolve_account_wxid_dir(account_dir)
    wxid = wx_id_dir.name

    logger.info("尝试获取next_action_id")
    try:
        next_action_id = await _get_next_action_id_async()
        logger.info(f"获取next_action_id成功: {next_action_id}")
    except Exception as e:
        raise RuntimeError(f"获取next_action_id失败：{e}")


    logger.info(f"正在为账号 {wxid} 获取密钥...")

    try:
        blob1_bytes = get_wechat_internal_global_config(wx_id_dir, file_name1= "global_config") # 估计这是唯一有效的数据！！
        logger.info(f"获取微信内部配置成功，大小: {len(blob1_bytes)} bytes")
    except Exception as e:
        raise RuntimeError(f"读取微信内部文件失败: {e}")

    try:
        blob2_bytes = get_wechat_internal_global_config(wx_id_dir, file_name1= "global_config.crc")
        logger.info(f"获取微信内部配置成功，大小: {len(blob2_bytes)} bytes")
    except Exception as e:
        raise RuntimeError(f"读取微信内部文件失败: {e}")

    blob3_bytes = b""

    headers = {
        "Accept": "text/x-component",
        "Next-Action": next_action_id,
        "Next-Router-State-Tree": "%5B%22%22%2C%7B%22children%22%3A%5B%22dashboard%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D",
        "Origin": "https://view.free.c3o.re",
        "Referer": "https://view.free.c3o.re/dashboard",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    files = {
        '1': ('blob', blob1_bytes, 'application/octet-stream'),
        '2': ('blob', blob2_bytes, 'application/octet-stream'),
        '3': ('blob', blob3_bytes, 'application/octet-stream'),
        '0': (None, json.dumps([wxid, "$A1", "$A2", "$A3", 0],separators=(",",":")).encode('utf-8')),
    }


    async with httpx.AsyncClient(timeout=30) as client:
        logger.info("向远程服务器发送请求...")
        response = await client.post(REMOTE_URL, headers=headers, files=files)

    if response.status_code != 200:
        raise RuntimeError(f"远程服务器错误: {response.status_code} - {response.text[:100]}")


    result_data = {}
    lines = response.text.split('\n')

    found_config = False
    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith('1:'):
            try:
                json_part = line[2:]  # 去掉 "1:"
                data_obj = json.loads(json_part)

                if "config" in data_obj:
                    config = data_obj["config"]
                    result_data = {
                        "xor_key": config.get("xor_key", ""),
                        "aes_key": config.get("aes_key", ""),
                        "nick_name": config.get("nick_name", ""),
                        "avatar_url": config.get("avatar_url", "")
                    }
                    found_config = True
                    break
            except Exception as e:
                logger.warning(f"解析响应行失败: {e}")
                continue

    if not found_config or not result_data.get("aes_key"):
        logger.error(f"响应中未找到密钥信息。Full Response: {response.text[:500]}")
        raise RuntimeError("解析失败: 服务器未返回 config 数据")

    # 6. 处理并保存密钥
    xor_raw = str(result_data["xor_key"])
    aes_val = str(result_data["aes_key"])

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
        "nick_name": result_data["nick_name"]
    }

