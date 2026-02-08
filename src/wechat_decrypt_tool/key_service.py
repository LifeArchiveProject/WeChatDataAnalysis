# import sys

try:
    import wx_key
except ImportError:
    print('[!] 环境中未安装wx_key依赖，可能无法自动获取数据库密钥')
    wx_key = None
    # sys.exit(1)

import time
import psutil
import subprocess
import logging
from typing import Optional, List
from dataclasses import dataclass
from packaging import version as pkg_version  # 建议使用 packaging 库处理版本比较
from .wechat_detection import detect_wechat_installation

logger = logging.getLogger(__name__)


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
