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

WECHAT_EXECUTABLE_NAMES = ("Weixin.exe", "WeChat.exe")


def _summarize_aes_key(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) <= 8:
        return raw
    return f"{raw[:4]}...{raw[-4:]}(len={len(raw)})"


def _summarize_key_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = payload or {}
    return {
        "wxid": str(payload.get("wxid") or "").strip(),
        "xor_key": str(payload.get("xor_key") or "").strip(),
        "aes_key": _summarize_aes_key(payload.get("aes_key")),
    }


def _resolve_wxid_dir_for_image_key(
        account: Optional[str] = None,
        *,
        wxid_dir: Optional[str] = None,
        db_storage_path: Optional[str] = None,
) -> Path:
    explicit_wxid_dir = str(wxid_dir or "").strip()
    if explicit_wxid_dir:
        candidate = Path(explicit_wxid_dir).expanduser()
        if candidate.exists() and candidate.is_dir():
            logger.info("[image_key] 使用显式 wxid_dir: %s", str(candidate))
            return candidate
        raise FileNotFoundError(f"指定的 wxid_dir 不存在或不是目录: {candidate}")

    explicit_db_storage_path = str(db_storage_path or "").strip()
    if explicit_db_storage_path:
        db_storage_dir = Path(explicit_db_storage_path).expanduser()
        if db_storage_dir.exists() and db_storage_dir.is_dir():
            if db_storage_dir.name.lower() == "db_storage":
                candidate = db_storage_dir.parent
                if candidate.exists() and candidate.is_dir():
                    logger.info(
                        "[image_key] 通过 db_storage_path 反推出 wxid_dir: db_storage_path=%s wxid_dir=%s",
                        str(db_storage_dir),
                        str(candidate),
                    )
                    return candidate
            nested_db_storage = db_storage_dir / "db_storage"
            if nested_db_storage.exists() and nested_db_storage.is_dir():
                logger.info(
                    "[image_key] db_storage_path 指向 wxid_dir，自动使用其子目录: wxid_dir=%s",
                    str(db_storage_dir),
                )
                return db_storage_dir
        logger.info(
            "[image_key] 提供的 db_storage_path 无法解析 wxid_dir: %s",
            explicit_db_storage_path,
        )

    if account:
        try:
            account_dir = _resolve_account_dir(account)
            wx_id_dir = _resolve_account_wxid_dir(account_dir)
            if wx_id_dir:
                logger.info(
                    "[image_key] 通过已解密账号目录解析 wxid_dir: account=%s account_dir=%s wxid_dir=%s",
                    str(account).strip(),
                    str(account_dir),
                    str(wx_id_dir),
                )
                return wx_id_dir
        except Exception as e:
            logger.info(
                "[image_key] 无法通过已解密账号目录解析 wxid_dir: account=%s error=%s",
                str(account).strip(),
                str(e),
            )

    raise FileNotFoundError("无法定位该账号的 wxid_dir，请传入有效的 db_storage_path 或先完成数据库解密")


def _normalize_user_path(value: Any) -> str:
    raw = str(value or "").strip().strip('"').strip("'")
    if not raw:
        return ""
    try:
        return os.path.normpath(os.path.expandvars(raw))
    except Exception:
        return raw


def _read_wechat_version_from_exe(exe_path: str) -> str:
    normalized = _normalize_user_path(exe_path)
    if not normalized:
        return ""
    try:
        import win32api

        version_info = win32api.GetFileVersionInfo(normalized, "\\")
        return (
            f"{version_info['FileVersionMS'] >> 16}."
            f"{version_info['FileVersionMS'] & 0xFFFF}."
            f"{version_info['FileVersionLS'] >> 16}."
            f"{version_info['FileVersionLS'] & 0xFFFF}"
        )
    except Exception:
        return ""


def _resolve_manual_wechat_exe_path(wechat_install_path: Optional[str] = None) -> str:
    normalized = _normalize_user_path(wechat_install_path)
    if not normalized:
        return ""

    candidate = Path(normalized).expanduser()
    executable_names = {name.lower() for name in WECHAT_EXECUTABLE_NAMES}
    if candidate.is_file():
        if candidate.name.lower() not in executable_names:
            raise RuntimeError("手动路径必须指向微信安装目录，或直接指向 Weixin.exe / WeChat.exe")
        return str(candidate)

    if candidate.is_dir():
        for exe_name in WECHAT_EXECUTABLE_NAMES:
            exe_path = candidate / exe_name
            if exe_path.is_file():
                return str(exe_path)
        raise RuntimeError("手动指定的微信安装目录中未找到 Weixin.exe 或 WeChat.exe")

    raise RuntimeError(f"手动指定的微信安装目录不存在: {candidate}")


# ======================  以下是hook逻辑  ======================================

class WeChatKeyFetcher:
    def __init__(self):
        self.process_names = {name.lower() for name in WECHAT_EXECUTABLE_NAMES}
        self.timeout_seconds = 60

    def _is_wechat_process(self, name: Any) -> bool:
        return str(name or "").strip().lower() in self.process_names

    def kill_wechat(self):
        """检测并查杀微信进程"""
        killed = False
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if self._is_wechat_process(proc.info['name']):
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
            normalized_exe_path = _normalize_user_path(exe_path)
            process = subprocess.Popen(normalized_exe_path)
            time.sleep(2)
            candidates = []

            for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
                try:
                    p_name = proc.info.get('name')
                    if p_name and p_name.lower() in self.process_names:
                        cmdline_list = proc.info.get('cmdline') or []
                        cmdline_str = " ".join(cmdline_list).lower()

                        if any(target.lower() in cmdline_str for target in WECHAT_EXECUTABLE_NAMES):
                            candidates.append({
                                "pid": proc.info['pid'],
                                "cmd_len": len(cmdline_str)
                            })
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

            if candidates:
                # 选择命令行最短的一个作为主进程
                main_proc = min(candidates, key=lambda x: x['cmd_len'])
                target_pid = main_proc["pid"]
                return target_pid

            return process.pid

        except Exception as e:
            logger.error(f"启动微信失败: {e}")
            raise RuntimeError(f"无法启动微信: {e}")

    def fetch_db_key(self, wechat_install_path: Optional[str] = None) -> dict:
        """调用 wx_key 仅获取数据库密钥 (Hook 模式)"""
        if wx_key is None:
            raise RuntimeError("wx_key 模块未安装或加载失败")

        manual_path = _normalize_user_path(wechat_install_path)
        if manual_path:
            exe_path = _resolve_manual_wechat_exe_path(manual_path)
            version = _read_wechat_version_from_exe(exe_path)
            logger.info(
                "[db_key] 使用手动指定的微信安装路径: input=%s exe_path=%s version=%s",
                manual_path,
                exe_path,
                version or "unknown",
            )
        else:
            install_info = detect_wechat_installation()
            exe_path = _normalize_user_path(install_info.get('wechat_exe_path'))
            version = str(install_info.get('wechat_version') or "").strip()

        if not exe_path:
            raise RuntimeError("无法自动定位微信安装路径，请手动填写微信安装目录")
        if not Path(exe_path).is_file():
            raise RuntimeError(f"微信可执行文件不存在: {exe_path}")

        logger.info(f"Detect WeChat: {version or 'unknown'} at {exe_path}")

        self.kill_wechat()
        pid = self.launch_wechat(exe_path)
        logger.info(f"WeChat launched, PID: {pid}")

        # 仅传入 PID，触发数据库密钥自动 Hook
        if not wx_key.initialize_hook(pid):
            err = wx_key.get_last_error_msg()
            raise RuntimeError(f"数据库 Hook 初始化失败: {err}")

        start_time = time.time()
        found_db_key = None

        try:
            while True:
                if time.time() - start_time > self.timeout_seconds:
                    raise TimeoutError("获取数据库密钥超时 (60s)，请确保在弹出的微信中完成登录。")

                key_data = wx_key.poll_key_data()
                if key_data and 'key' in key_data:
                    found_db_key = key_data['key']
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

        return {
            "db_key": found_db_key
        }


def get_db_key_workflow(wechat_install_path: Optional[str] = None):
    fetcher = WeChatKeyFetcher()
    return fetcher.fetch_db_key(wechat_install_path=wechat_install_path)


# ==============================   以下是图片密钥逻辑  =====================================

def get_wechat_internal_global_config(wx_dir: Path, file_name1) -> bytes:
    xwechat_files_root = wx_dir.parent
    target_path = os.path.join(xwechat_files_root, "all_users", "config", file_name1)
    if not os.path.exists(target_path):
        raise FileNotFoundError(f"找不到配置文件: {target_path}，请确认微信数据目录结构是否完整")
    return Path(target_path).read_bytes()


def try_get_local_image_keys() -> List[Dict[str, Any]]:
    """尝试通过本地算法提取图片密钥 (无需 Hook)"""
    if wx_key is None or not hasattr(wx_key, 'get_image_key'):
        logger.info("[image_key] 本地算法不可用：wx_key.get_image_key 缺失")
        return []

    try:
        res_json = wx_key.get_image_key()
        if not res_json:
            logger.info("[image_key] 本地算法返回空结果")
            return []

        data = json.loads(res_json)
        accounts = data.get('accounts', [])
        results = []
        for acc in accounts:
            wxid = acc.get('wxid')
            keys = acc.get('keys', [])
            for k in keys:
                xor_key = k.get('xorKey')
                aes_key = k.get('aesKey')
                if xor_key is not None:
                    results.append({
                        "wxid": wxid,
                        "xor_key": f"0x{int(xor_key):02X}",
                        "aes_key": aes_key
                    })
        logger.info(
            "[image_key] 本地算法完成：accounts=%s results=%s",
            len(accounts),
            [_summarize_key_payload(item) for item in results],
        )
        return results
    except Exception as e:
        logger.error(f"本地提取图片密钥失败: {e}")
        return []


async def get_image_key_integrated_workflow(
        account: Optional[str] = None,
        *,
        wxid_dir: Optional[str] = None,
        db_storage_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    集成图片密钥获取流程：
    1. 优先尝试本地算法提取
    2. 如果本地提取失败或未匹配到指定账号，尝试远程 API 解析
    """
    # 1. 尝试本地提取
    local_keys = try_get_local_image_keys()

    target_account_wxid = None
    if account or wxid_dir or db_storage_path:
        try:
            resolved_wxid_dir = _resolve_wxid_dir_for_image_key(
                account,
                wxid_dir=wxid_dir,
                db_storage_path=db_storage_path,
            )
            target_account_wxid = resolved_wxid_dir.name
        except Exception:
            target_account_wxid = account
    target_account_wxid = str(target_account_wxid or "").strip().lower()
    logger.info(
        "[image_key] 开始集成流程：request_account=%s target_wxid=%s local_key_count=%s db_storage_path=%s wxid_dir=%s",
        str(account or "").strip(),
        target_account_wxid,
        len(local_keys),
        str(db_storage_path or "").strip(),
        str(wxid_dir or "").strip(),
    )

    if local_keys:
        # 如果指定了账号，尝试在本地结果中找匹配的
        if target_account_wxid:
            for k in local_keys:
                local_wxid = str(k.get("wxid") or "").strip().lower()
                if local_wxid and local_wxid == target_account_wxid:
                    logger.info(
                        "[image_key] 本地算法精确匹配成功：target_wxid=%s payload=%s",
                        target_account_wxid,
                        _summarize_key_payload(k),
                    )
                    upsert_account_keys_in_store(
                        account=str(k.get("wxid") or "").strip(),
                        image_xor_key=k['xor_key'],
                        image_aes_key=k['aes_key']
                    )
                    return k
            logger.info(
                "[image_key] 本地算法未匹配到目标账号：target_wxid=%s local_wxids=%s",
                target_account_wxid,
                [str(item.get("wxid") or "").strip() for item in local_keys],
            )
        else:
            # 如果没指定账号，返回第一个发现的并存入 store (如果有的话)
            k = local_keys[0]
            logger.info(
                "[image_key] 未指定账号，返回本地首个结果：payload=%s",
                _summarize_key_payload(k),
            )
            upsert_account_keys_in_store(
                account=k['wxid'],
                image_xor_key=k['xor_key'],
                image_aes_key=k['aes_key']
            )
            return k

    # 2. 本地提取失败或不匹配，尝试远程解析
    logger.info("[image_key] 本地算法未命中，尝试远程 API 解析")
    return await fetch_and_save_remote_keys(
        account,
        wxid_dir=wxid_dir,
        db_storage_path=db_storage_path,
    )


async def fetch_and_save_remote_keys(
        account: Optional[str] = None,
        *,
        wxid_dir: Optional[str] = None,
        db_storage_path: Optional[str] = None,
) -> Dict[str, Any]:
    wx_id_dir = _resolve_wxid_dir_for_image_key(
        account,
        wxid_dir=wxid_dir,
        db_storage_path=db_storage_path,
    )
    wxid = wx_id_dir.name

    url = "https://view.free.c3o.re/api/key"
    data = {"weixinIDFolder": wxid}

    logger.info(
        "[image_key] 准备请求远程密钥：request_account=%s resolved_account=%s wxid_dir=%s db_storage_path=%s",
        str(account or "").strip(),
        wxid,
        str(wx_id_dir),
        str(db_storage_path or "").strip(),
    )

    try:
        blob1_bytes = get_wechat_internal_global_config(wx_id_dir, file_name1="global_config")
        blob2_bytes = get_wechat_internal_global_config(wx_id_dir, file_name1="global_config.crc")
    except Exception as e:
        raise RuntimeError(f"读取微信内部文件失败: {e}")
    logger.info(
        "[image_key] 远程请求输入文件已读取：wxid=%s global_config_bytes=%s crc_bytes=%s",
        wxid,
        len(blob1_bytes),
        len(blob2_bytes),
    )

    files = {
        'fileBytes': ('file', blob1_bytes, 'application/octet-stream'),
        'crcBytes': ('file.crc', blob2_bytes, 'application/octet-stream'),
    }

    async with httpx.AsyncClient(timeout=30) as client:
        logger.info("[image_key] 向云端 API 发送请求：url=%s wxid=%s", url, wxid)
        response = await client.post(url, data=data, files=files)

    if response.status_code != 200:
        raise RuntimeError(f"云端服务器错误: {response.status_code} - {response.text[:100]}")

    config = response.json()
    if not config:
        raise RuntimeError("云端解析失败: 返回数据为空")
    logger.info(
        "[image_key] 收到远程响应：status_code=%s keys=%s nick_name=%s",
        response.status_code,
        {
            "xor_key": str(config.get("xorKey", config.get("xor_key", ""))),
            "aes_key": _summarize_aes_key(config.get("aesKey", config.get("aes_key", ""))),
        },
        str(config.get("nickName", config.get("nick_name", ""))),
    )

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
    logger.info(
        "[image_key] 远程密钥已保存：account=%s xor_key=%s aes_key=%s",
        wxid,
        xor_hex_str,
        _summarize_aes_key(aes_val),
    )

    return {
        "wxid": wxid,
        "xor_key": xor_hex_str,
        "aes_key": aes_val,
        "nick_name": config.get("nickName", config.get("nick_name", ""))
    }
