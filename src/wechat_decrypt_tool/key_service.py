# import sys
# import requests

from .platform_support import MAC_DB_KEY_GUIDANCE, is_macos, is_windows

try:
    import wx_key
except ImportError:
    if is_windows():
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
import importlib
import httpx
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from packaging import version as pkg_version  # 建议使用 packaging 库处理版本比较
from .wechat_detection import detect_wechat_installation, parse_global_config
from .dll_key_scan import extract_xor_keys_from_dll
from .image_key_resolver import (
    ImageKeyResolution,
    TemplateScanResult,
    clean_wxid,
    derive_image_keys,
    resolve_local_image_key,
    scan_v2_templates,
    verify_key_pair,
)
from .image_key_memory_scan import scan_image_key_from_memory
from .key_store import (
    get_account_keys_from_store,
    normalize_key_store_path,
    upsert_account_keys_in_store,
)
from .media_helpers import _resolve_account_dir, _resolve_account_wxid_dir

logger = logging.getLogger(__name__)

WECHAT_EXECUTABLE_NAMES = ("Weixin.exe", "WeChat.exe")
KEY_SIZE = 32
V4_DB_NAME_PRIORITY = (
    "msg0.db",
    "msg.db",
    "micromsg.db",
    "favorite.db",
    "mediamsg0.db",
    "media_msg0.db",
    "sns.db",
)


def _key_payload_log_metadata(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = payload or {}
    xor_key = str(payload.get("xor_key", payload.get("xorKey", "")) or "").strip()
    aes_key = str(payload.get("aes_key", payload.get("aesKey", "")) or "").strip()
    return {
        "wxid": str(payload.get("wxid") or "").strip(),
        "has_xor": bool(xor_key),
        "has_aes": bool(aes_key),
        "xor_length": len(xor_key),
        "aes_length": len(aes_key),
    }


def _image_key_account_match_variants(value: Any) -> set[str]:
    """Return account names that should be considered equivalent for image key matching.

    Windows WeChat 4.x stores account data under a folder such as
    ``wxid_o6wp2aat9mu312_8d63`` while wx_key may report the account as
    ``wxid_o6wp2aat9mu312``.  The trailing four-hex folder suffix is not part
    of the logical account id, so both names must match.  Do not strip
    arbitrary suffixes: names like ``wxid_demo_extra`` may be a distinct
    account in tests or legacy data.
    """
    raw = str(value or "").strip().lower()
    if not raw:
        return set()

    variants = {raw}
    suffix_match = re.match(r"^(wxid_[^_\s]+)_[0-9a-f]{4}$", raw, flags=re.IGNORECASE)
    if suffix_match:
        variants.add(suffix_match.group(1).lower())
    return variants


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


def _resolve_wechat_dll_path(wechat_install_path: Optional[str] = None) -> Path:
    def _dll_candidates_from_dir(install_dir: Path) -> list[Path]:
        patterns = (
            "Weixin.dll",
            "WeChat.dll",
            "*/Weixin.dll",
            "*/WeChat.dll",
            "install/*/Weixin.dll",
            "install/*/WeChat.dll",
        )
        out: list[Path] = []
        seen: set[str] = set()
        for pattern in patterns:
            try:
                for item in install_dir.glob(pattern):
                    if not item.is_file():
                        continue
                    key = str(item.resolve()).lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(item)
            except Exception:
                continue
        out.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)
        return out

    normalized = _normalize_user_path(wechat_install_path)
    if normalized:
        candidate = Path(normalized).expanduser()
        if candidate.is_file():
            install_dir = candidate.parent
        else:
            install_dir = candidate
        dll_candidates = _dll_candidates_from_dir(install_dir)
        if dll_candidates:
            return dll_candidates[0]
        raise FileNotFoundError(f"微信安装目录中未找到 Weixin.dll / WeChat.dll: {install_dir}")

    install_info = detect_wechat_installation()
    exe_path = _normalize_user_path(install_info.get("wechat_exe_path"))
    if exe_path:
        exe_dir = Path(exe_path).parent
        dll_candidates = _dll_candidates_from_dir(exe_dir)
        if dll_candidates:
            return dll_candidates[0]

    raise FileNotFoundError("未能定位微信 DLL，请先提供微信安装目录或确保微信进程已正确检测")


def _normalize_db_key(value: Any) -> str:
    if value is None:
        raise RuntimeError("V4 内存扫描未返回数据库密钥")

    if isinstance(value, (bytes, bytearray)):
        raw_bytes = bytes(value)
        # 两种常见形态：32 字节原始 key / 64 字符 ASCII hex
        if len(raw_bytes) == 32:
            key = raw_bytes.hex()
        else:
            try:
                key = raw_bytes.decode("utf-8", errors="ignore").strip()
            except Exception:
                key = raw_bytes.hex()
    else:
        key = str(value).strip()

    key = key.lower()
    if key.startswith("0x"):
        key = key[2:]

    if not re.fullmatch(r"[0-9a-f]{64}", key):
        raise RuntimeError(f"V4 内存扫描返回了非 64 位十六进制密钥（type={type(value).__name__}, len={len(key)}）")
    return key


def _normalize_internal_db_key(value: Any) -> bytes:
    """把 scan.py 里扫出来的 32 字节 DLL key 规范化成 bytes。"""
    if value is None:
        return b""

    if isinstance(value, (bytes, bytearray)):
        raw_bytes = bytes(value)
        if len(raw_bytes) == KEY_SIZE:
            return raw_bytes
        try:
            value = raw_bytes.decode("utf-8", errors="ignore")
        except Exception:
            value = raw_bytes.hex()

    raw = str(value or "").strip()
    if not raw:
        return b""

    if raw.startswith("{") and raw.endswith("}"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                for candidate_key in ("internal_db_key", "internal_db_key_hex", "dll_key", "key", "key_hex"):
                    candidate = str(parsed.get(candidate_key) or "").strip()
                    if candidate:
                        raw = candidate
                        break
        except Exception:
            pass

    raw = raw.lower().replace("0x", "")
    cleaned = re.sub(r"[^0-9a-f]", "", raw)
    if not cleaned:
        return b""
    if len(cleaned) != KEY_SIZE * 2:
        raise RuntimeError(
            f"internal_db_key 格式无效：需要 32 字节（64 位十六进制），当前长度={len(cleaned)}"
        )
    try:
        return bytes.fromhex(cleaned)
    except Exception as e:
        raise RuntimeError("internal_db_key 格式无效：无法解析为十六进制") from e


def _load_internal_db_key_candidates(wechat_install_path: Optional[str] = None) -> list[bytes]:
    """自动扫描 Weixin.dll，提取 scan.py 需要的 internal_db_key 候选。"""
    dll_path = _resolve_wechat_dll_path(wechat_install_path)
    logger.info("[db_key_v4] 准备扫描 DLL key: dll_path=%s", str(dll_path))

    candidates = extract_xor_keys_from_dll(dll_path)
    keys: list[bytes] = []
    for item in candidates:
        hex_value = str(item.get("key_hex") or "").strip()
        if not hex_value:
            continue
        try:
            key_bytes = bytes.fromhex(re.sub(r"[^0-9a-fA-F]", "", hex_value))
        except Exception:
            continue
        if len(key_bytes) == KEY_SIZE and key_bytes not in keys:
            keys.append(key_bytes)

    logger.info("[db_key_v4] DLL key 扫描完成: dll_path=%s candidate_count=%s", str(dll_path), len(keys))
    return keys


def _xor_hex_key_with_internal_db_key(db_key: Any, internal_db_key: bytes) -> str:
    normalized_key = _normalize_db_key(db_key)
    key_bytes = bytes.fromhex(normalized_key)
    if len(key_bytes) != len(internal_db_key):
        raise RuntimeError(
            f"internal_db_key 长度不匹配：db_key={len(key_bytes)} bytes internal_db_key={len(internal_db_key)} bytes"
        )
    return bytes(a ^ b for a, b in zip(key_bytes, internal_db_key)).hex()


def _sort_key_for_v4_probe(path: Path) -> tuple[int, int, str]:
    name = path.name.lower()
    try:
        priority = V4_DB_NAME_PRIORITY.index(name)
    except ValueError:
        priority = len(V4_DB_NAME_PRIORITY)
    depth = len(path.parts)
    return priority, depth, str(path).lower()


def _resolve_v4_probe_db_file(db_storage_path: Optional[str]) -> Path:
    """从用户填写的 db_storage_path 中选一个用于 key_v4 校验的加密 DB。"""
    raw_path = _normalize_user_path(db_storage_path)
    if not raw_path:
        raise RuntimeError("未提供 db_storage_path，无法使用 V4 内存扫描模式")

    candidate = Path(raw_path).expanduser()
    min_size = 4096
    if candidate.is_file():
        if candidate.suffix.lower() != ".db":
            raise RuntimeError(f"V4 模式需要 .db 文件或 db_storage 目录: {candidate}")
        if candidate.stat().st_size < min_size:
            raise RuntimeError(f"数据库文件过小，无法用于密钥校验: {candidate}")
        return candidate

    if not candidate.exists() or not candidate.is_dir():
        raise RuntimeError(f"db_storage_path 不存在或不是目录: {candidate}")

    db_candidates: list[Path] = []
    try:
        from .wechat_decrypt import scan_account_databases_from_path

        scan_result = scan_account_databases_from_path(str(candidate))
        if scan_result.get("status") == "success":
            for databases in (scan_result.get("account_databases") or {}).values():
                for item in databases or []:
                    db_path = Path(str(item.get("path") or ""))
                    if db_path.is_file() and db_path.stat().st_size >= min_size:
                        db_candidates.append(db_path)
        else:
            logger.info("[db_key_v4] 数据库扫描未命中: %s", scan_result.get("message") or "")
    except Exception as e:
        logger.info("[db_key_v4] 数据库扫描异常，将尝试直接枚举: %s", e)

    # 兜底：允许传入具体 wxid 目录，或 scan 对新目录结构暂时不认识时仍可尝试。
    if not db_candidates:
        for db_path in candidate.rglob("*.db"):
            try:
                if db_path.name.lower() == "key_info.db":
                    continue
                if db_path.is_file() and db_path.stat().st_size >= min_size:
                    db_candidates.append(db_path)
            except Exception:
                continue

    if not db_candidates:
        raise RuntimeError(f"未在路径中找到可用于 V4 校验的数据库文件: {candidate}")

    db_candidates = sorted(set(db_candidates), key=_sort_key_for_v4_probe)
    return db_candidates[0]


def _get_db_key_with_v4(
        db_storage_path: Optional[str],
        internal_db_key: Optional[str] = None,
        *,
        wechat_install_path: Optional[str] = None,
) -> Dict[str, Any]:
    probe_db_path = _resolve_v4_probe_db_file(db_storage_path)
    normalized_internal_db_key = _normalize_internal_db_key(internal_db_key)
    logger.info(
        "[db_key_v4] 开始 V4 内存扫描: probe_db=%s manual_internal_db_key_present=%s manual_internal_db_key_len=%s",
        str(probe_db_path),
        bool(normalized_internal_db_key),
        len(normalized_internal_db_key) if normalized_internal_db_key else 0,
    )

    scan_candidate_count = 0
    candidate_plan: list[tuple[bytes, str]] = []
    if normalized_internal_db_key:
        candidate_plan.append((normalized_internal_db_key, "manual"))
    else:
        logger.info("[db_key_v4] 未提供手动 DLL key，先自动扫描微信 DLL 辅助 key")
        try:
            scan_candidates = _load_internal_db_key_candidates(wechat_install_path)
        except Exception as e:
            raise RuntimeError(f"V4 预处理失败：自动扫描微信 DLL 辅助 key 失败：{e}") from e

        scan_candidate_count = len(scan_candidates)
        if not scan_candidates:
            raise RuntimeError("V4 预处理失败：未从微信 DLL 中扫描到可用的辅助 key")

        candidate_plan.extend((candidate, "scan.py") for candidate in scan_candidates)

    try:
        key_v4_module = importlib.import_module(".key_v4", __package__)
    except Exception as e:
        raise RuntimeError(f"包内 key_v4.py 加载失败: {e}") from e

    if not hasattr(key_v4_module, "recover_key"):
        raise RuntimeError("包内 key_v4.py 缺少 recover_key 函数")

    try:
        import pymem as _pymem
    except Exception as e:
        raise RuntimeError("pymem 模块未安装，无法执行 V4 内存扫描") from e

    errors: list[str] = []
    pid = None
    process_name_used = ""
    for process_name in WECHAT_EXECUTABLE_NAMES:
        try:
            pm = _pymem.Pymem(process_name)
            pid = pm.process_id
            process_name_used = process_name
            break
        except Exception as e:
            errors.append(f"{process_name}: {e}")

    if not pid:
        raise RuntimeError("未找到运行中的微信进程：" + "; ".join(errors))

    logger.info(
        "[db_key_v4] 调用单文件扫描器: module=%s process=%s pid=%s probe_db=%s",
        getattr(key_v4_module, "__file__", "key_v4"),
        process_name_used,
        pid,
        str(probe_db_path),
    )

    last_errors: list[str] = []
    recovered_key = ""
    used_internal_db_key_source = ""

    def _try_recover(candidate_internal_db_key: bytes, source: str) -> str:
        if hasattr(key_v4_module, "finish_flag"):
            try:
                key_v4_module.finish_flag = False
            except Exception:
                pass
        if candidate_internal_db_key:
            current_raw_key = key_v4_module.recover_key(pid, str(probe_db_path), candidate_internal_db_key)
        else:
            current_raw_key = key_v4_module.recover_key(pid, str(probe_db_path))
        logger.info(
            "[db_key_v4] 单文件扫描器返回结果: type=%s has_value=%s candidate_internal_db_key_len=%s source=%s",
            type(current_raw_key).__name__,
            bool(current_raw_key),
            len(candidate_internal_db_key),
            source or "raw",
        )
        current_key = _normalize_db_key(current_raw_key)
        if candidate_internal_db_key:
            current_key = _xor_hex_key_with_internal_db_key(current_key, candidate_internal_db_key)
            logger.info("[db_key_v4] 已应用 internal_db_key 对候选 key 解掩码")
        else:
            logger.info("[db_key_v4] 未使用 internal_db_key，直接验证原始候选 key")
        return current_key

    tried: list[str] = []
    for candidate_internal_db_key, source in candidate_plan:
        try:
            tried.append(f"{source}:len={len(candidate_internal_db_key)}")
            recovered_key = _try_recover(candidate_internal_db_key, source)
            used_internal_db_key_source = source if candidate_internal_db_key else ""
            break
        except Exception as e:
            last_errors.append(str(e))
            recovered_key = ""
            continue

    if not recovered_key:
        raise RuntimeError("V4 内存扫描失败：" + ("; ".join(last_errors) if last_errors else "未找到有效密钥"))

    logger.info("[db_key_v4] V4 内存扫描成功: probe_db=%s", str(probe_db_path))
    return {
        "db_key": recovered_key,
        "method": "key_v4",
        "db_key_probe_path": str(probe_db_path),
        "internal_db_key_source": used_internal_db_key_source,
        "internal_db_key_candidate_count": scan_candidate_count,
    }


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


def get_db_key_workflow(
        wechat_install_path: Optional[str] = None,
        *,
        db_storage_path: Optional[str] = None,
        internal_db_key: Optional[str] = None,
        key_mode: str = "auto",
):
    if is_macos():
        raise RuntimeError(MAC_DB_KEY_GUIDANCE)
    if not is_windows():
        raise RuntimeError("当前平台不支持自动获取数据库密钥，请使用同类工具获取后手动填写。")

    mode = str(key_mode or "auto").strip().lower()
    if mode in {"v4", "key_v4", "memory", "memory_scan"}:
        return _get_db_key_with_v4(
            db_storage_path,
            internal_db_key=internal_db_key,
            wechat_install_path=wechat_install_path,
        )

    if mode == "hook":
        fetcher = WeChatKeyFetcher()
        result = fetcher.fetch_db_key(wechat_install_path=wechat_install_path)
        result["method"] = "hook"
        return result

    if mode != "auto":
        raise RuntimeError(f"未知密钥获取模式: {key_mode}")

    v4_error = ""
    try:
        return _get_db_key_with_v4(
            db_storage_path,
            internal_db_key=internal_db_key,
            wechat_install_path=wechat_install_path,
        )
    except Exception as e:
        v4_error = str(e)
        logger.warning("[db_key] V4 内存扫描失败，准备回退 Hook: %s", v4_error)

    fetcher = WeChatKeyFetcher()
    try:
        result = fetcher.fetch_db_key(wechat_install_path=wechat_install_path)
    except TimeoutError as e:
        if v4_error:
            raise TimeoutError(f"V4 内存扫描失败: {v4_error}; Hook 获取超时: {e}") from e
        raise
    except Exception as e:
        if v4_error:
            raise RuntimeError(f"V4 内存扫描失败: {v4_error}; Hook 获取失败: {e}") from e
        raise

    result["method"] = "hook"
    if v4_error:
        result["fallback_from"] = "key_v4"
        result["key_v4_error"] = v4_error
    return result


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
            [_key_payload_log_metadata(item) for item in results],
        )
        return results
    except Exception as e:
        logger.error(f"本地提取图片密钥失败: {e}")
        return []


def _parse_image_xor_key(value: Any) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if 0 <= value <= 0xFF else None

    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.lower().startswith("0x"):
            parsed = int(raw[2:], 16)
        elif re.fullmatch(r"\d+", raw):
            parsed = int(raw, 10)
        else:
            parsed = int(raw, 16)
    except (TypeError, ValueError):
        return None
    return parsed if 0 <= parsed <= 0xFF else None


def _normalize_complete_image_key_payload(payload: Dict[str, Any]) -> Optional[tuple[int, str]]:
    xor_key = _parse_image_xor_key(
        payload.get("xor_key", payload.get("xorKey", payload.get("image_xor_key")))
    )
    aes_key = str(
        payload.get("aes_key", payload.get("aesKey", payload.get("image_aes_key", ""))) or ""
    ).strip()
    if xor_key is None or len(aes_key) < 16:
        return None
    aes_key = aes_key[:16]
    try:
        if len(aes_key.encode("ascii")) != 16:
            return None
    except UnicodeEncodeError:
        return None
    return xor_key, aes_key


def _get_image_key_kvcomm_dirs(account_dir: Optional[Path] = None) -> tuple[Path, ...]:
    override = str(os.environ.get("WECHAT_IMAGE_KVCOMM_DIR") or "").strip()
    if override:
        return (Path(override).expanduser(),)

    if is_macos():
        container_data = Path.home() / "Library" / "Containers" / "com.tencent.xinWeChat" / "Data"
        candidates = [
            container_data / "Documents" / "app_data" / "net" / "kvcomm",
            container_data
            / "Library"
            / "Application Support"
            / "com.tencent.xinWeChat"
            / "xwechat"
            / "net"
            / "kvcomm",
            container_data
            / "Library"
            / "Application Support"
            / "com.tencent.xinWeChat"
            / "net"
            / "kvcomm",
            container_data / "Documents" / "xwechat" / "net" / "kvcomm",
        ]

        if account_dir is not None:
            account_path = Path(account_dir).expanduser()
            for parent in (account_path, *account_path.parents):
                if parent.name.casefold() == "xwechat_files":
                    candidates.append(parent.parent / "app_data" / "net" / "kvcomm")
                    break

            cursor = account_path
            for _ in range(6):
                candidates.append(cursor / "net" / "kvcomm")
                if cursor.parent == cursor:
                    break
                cursor = cursor.parent
    else:
        appdata = str(os.environ.get("APPDATA") or "").strip()
        appdata_root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        candidates = [appdata_root / "Tencent" / "xwechat" / "net" / "kvcomm"]

    deduplicated: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = normalize_key_store_path(str(candidate))
        if normalized in seen:
            continue
        seen.add(normalized)
        deduplicated.append(candidate)

    existing = tuple(candidate for candidate in deduplicated if candidate.is_dir())
    if existing:
        return existing
    return tuple(deduplicated[:1])


def _get_image_key_kvcomm_dir(account_dir: Optional[Path] = None) -> Path:
    return _get_image_key_kvcomm_dirs(account_dir)[0]


def _resolve_local_image_key_from_kvcomm_candidates(
        *,
        account_dir: Path,
        target_wxid: str,
        account: Optional[str],
        local_native_wxids: list[str],
        template_scan: Optional[TemplateScanResult],
) -> Optional[ImageKeyResolution]:
    for kvcomm_dir in _get_image_key_kvcomm_dirs(account_dir):
        logger.info("[image_key] 尝试本地 kvcomm 目录: %s", kvcomm_dir)
        resolution = resolve_local_image_key(
            kvcomm_dir=kvcomm_dir,
            account_dir=account_dir,
            target_wxid=target_wxid,
            account=account,
            local_native_wxids=local_native_wxids,
            template_scan=template_scan,
        )
        if resolution is not None:
            return resolution
    return None


def _image_key_aliases(canonical_account: str, *values: Any) -> list[str]:
    aliases: list[str] = []
    seen = {str(canonical_account or "").strip().lower()}
    for value in values:
        alias = str(value or "").strip()
        normalized = alias.lower()
        if not alias or normalized in seen:
            continue
        seen.add(normalized)
        aliases.append(alias)
    return aliases


def _is_trusted_image_key_alias(
    alias: Any,
    *,
    canonical_account: str,
    matched_wxid: str,
    source_wxid_dir: Path,
) -> bool:
    alias_text = str(alias or "").strip()
    if not alias_text:
        return False
    alias_variants = _image_key_account_match_variants(alias_text)
    if alias_variants & _image_key_account_match_variants(canonical_account):
        return True
    if alias_variants & _image_key_account_match_variants(matched_wxid):
        return True
    try:
        account_dir = _resolve_account_dir(alias_text)
        resolved_source = _resolve_account_wxid_dir(account_dir)
    except Exception:
        return False
    return (
        resolved_source is not None
        and normalize_key_store_path(str(resolved_source))
        == normalize_key_store_path(str(source_wxid_dir))
    )


def _load_verified_image_key_cache(
        canonical_account: str,
        request_account: Optional[str],
        source_wxid_dir: Path,
) -> Optional[Dict[str, Any]]:
    candidates = [canonical_account, str(request_account or "").strip()]
    for value in list(candidates):
        candidates.extend(sorted(_image_key_account_match_variants(value)))

    seen: set[str] = set()
    expected_source = normalize_key_store_path(str(source_wxid_dir))
    for candidate in candidates:
        candidate = str(candidate or "").strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        saved = get_account_keys_from_store(candidate)
        if not isinstance(saved, dict) or saved.get("image_key_verified") is not True:
            continue
        if normalize_key_store_path(saved.get("image_key_source_wxid_dir")) != expected_source:
            continue
        normalized = _normalize_complete_image_key_payload(saved)
        if normalized is None:
            continue
        xor_key, aes_key = normalized
        return {
            "wxid": canonical_account,
            "matched_wxid": str(saved.get("image_key_derived_wxid") or canonical_account),
            "xor_key": f"0x{xor_key:02X}",
            "aes_key": aes_key,
            "source": "verified_cache",
            "cached_source": str(saved.get("image_key_source") or ""),
            "verified": True,
            "code": saved.get("image_key_code"),
        }
    return None


def _verified_image_key_cache_matches_templates(
    cached: Dict[str, Any],
    template_scan: TemplateScanResult,
) -> bool:
    if not template_scan.templates:
        return True
    normalized = _normalize_complete_image_key_payload(cached)
    if normalized is None:
        return False
    xor_key, aes_key = normalized

    if str(cached.get("cached_source") or "").strip() == "weflow_local_verified":
        try:
            code = int(cached.get("code"))
            derived = derive_image_keys(code, str(cached.get("matched_wxid") or ""))
        except (TypeError, ValueError):
            return False
        if derived.xor_key != xor_key or derived.aes_key != aes_key:
            return False
        return verify_key_pair(
            xor_key,
            aes_key,
            template_scan,
            require_xor_match=False,
        )

    return verify_key_pair(
        xor_key,
        aes_key,
        template_scan,
        require_xor_match=True,
    )


def _persist_verified_image_keys(
        *,
        canonical_account: str,
        request_account: Optional[str],
        source_wxid_dir: Path,
        matched_wxid: str,
        xor_key: int,
        aes_key: str,
        source: str,
        code: Optional[int] = None,
        trust_matched_alias: bool = True,
) -> None:
    normalized = _normalize_complete_image_key_payload({"xor_key": xor_key, "aes_key": aes_key})
    if normalized is None:
        raise RuntimeError("拒绝保存不完整的图片密钥")
    normalized_xor, normalized_aes = normalized
    alias_values: list[str] = []
    if _is_trusted_image_key_alias(
        request_account,
        canonical_account=canonical_account,
        matched_wxid=matched_wxid,
        source_wxid_dir=source_wxid_dir,
    ):
        alias_values.append(str(request_account or "").strip())
    if trust_matched_alias:
        alias_values.append(matched_wxid)
    upsert_account_keys_in_store(
        account=canonical_account,
        image_xor_key=f"0x{normalized_xor:02X}",
        image_aes_key=normalized_aes,
        aliases=_image_key_aliases(canonical_account, *alias_values),
        image_key_verified=True,
        image_key_source=source,
        image_key_source_wxid_dir=str(source_wxid_dir),
        image_key_derived_wxid=matched_wxid,
        image_key_code=code,
    )


def _verified_image_key_result(
        *,
        canonical_account: str,
        matched_wxid: str,
        xor_key: int,
        aes_key: str,
        source: str,
        code: Optional[int] = None,
        template_path: Optional[Path] = None,
) -> Dict[str, Any]:
    return {
        "wxid": canonical_account,
        "matched_wxid": matched_wxid,
        "xor_key": f"0x{xor_key:02X}",
        "aes_key": aes_key,
        "source": source,
        "verified": True,
        "code": code,
        "template_path": str(template_path) if template_path else "",
    }


async def get_image_key_integrated_workflow(
        account: Optional[str] = None,
        *,
        wxid_dir: Optional[str] = None,
        db_storage_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve image keys locally with real V2 validation before remote fallback."""
    resolved_wxid_dir: Optional[Path] = None
    try:
        resolved_wxid_dir = _resolve_wxid_dir_for_image_key(
            account,
            wxid_dir=wxid_dir,
            db_storage_path=db_storage_path,
        )
    except Exception as error:
        logger.info("[image_key] 无法预先解析目标账号目录，将保留远端兜底: %s", str(error))

    canonical_account = (
        resolved_wxid_dir.name if resolved_wxid_dir is not None else str(account or "").strip()
    )
    template_scan: Optional[TemplateScanResult] = None
    if resolved_wxid_dir is not None:
        template_scan = await asyncio.to_thread(scan_v2_templates, resolved_wxid_dir)
        logger.info(
            "[image_key] V2 模板扫描完成: account=%s templates=%s files_scanned=%s inferred_xor_present=%s fallback=%s",
            canonical_account,
            len(template_scan.templates),
            template_scan.files_scanned,
            template_scan.inferred_xor_key is not None,
            template_scan.used_fallback,
        )
        cached = _load_verified_image_key_cache(canonical_account, account, resolved_wxid_dir)
        if cached is not None and _verified_image_key_cache_matches_templates(cached, template_scan):
            logger.info(
                "[image_key] 命中已验真缓存: account=%s source=%s",
                canonical_account,
                cached.get("cached_source"),
            )
            return cached
        if cached is not None:
            logger.info(
                "[image_key] 已验真缓存未通过最新 V2 模板复验，将重新解析: account=%s source=%s",
                canonical_account,
                cached.get("cached_source"),
            )

    local_keys: List[Dict[str, Any]] = []
    local_native_wxids: list[str] = []
    trusted_native_aliases = set(_image_key_account_match_variants(canonical_account))
    trusted_native_aliases.update(_image_key_account_match_variants(account))
    if resolved_wxid_dir is not None:
        global_info = await asyncio.to_thread(parse_global_config, str(resolved_wxid_dir.parent))
        if isinstance(global_info, dict) and str(global_info.get("wxid") or "").strip():
            global_wxid = str(global_info["wxid"]).strip()
            local_native_wxids.append(global_wxid)
            trusted_native_aliases.update(_image_key_account_match_variants(global_wxid))
        try:
            siblings = await asyncio.to_thread(lambda: list(resolved_wxid_dir.parent.iterdir()))
            local_native_wxids.extend(
                item.name for item in siblings[:128]
                if item.is_dir() and item.name.lower() != "all_users"
            )
        except OSError:
            pass

        try:
            resolution: Optional[ImageKeyResolution] = await asyncio.to_thread(
                _resolve_local_image_key_from_kvcomm_candidates,
                account_dir=resolved_wxid_dir,
                target_wxid=canonical_account,
                account=account,
                local_native_wxids=local_native_wxids,
                template_scan=template_scan,
            )
        except Exception as error:
            logger.warning("[image_key] WeFlow 本地派生失败: %s", str(error))
            resolution = None

        if resolution is None and template_scan.templates:
            local_keys = await asyncio.to_thread(try_get_local_image_keys)
            known_wxids = {
                clean_wxid(value).casefold()
                for value in local_native_wxids
                if clean_wxid(value)
            }
            additional_native_wxids: list[str] = []
            for item in local_keys:
                native_wxid = str(item.get("wxid") or "").strip()
                cleaned_native_wxid = clean_wxid(native_wxid)
                if not cleaned_native_wxid or cleaned_native_wxid.casefold() in known_wxids:
                    continue
                known_wxids.add(cleaned_native_wxid.casefold())
                additional_native_wxids.append(native_wxid)

            if additional_native_wxids:
                local_native_wxids.extend(additional_native_wxids)
                try:
                    resolution = await asyncio.to_thread(
                        _resolve_local_image_key_from_kvcomm_candidates,
                        account_dir=resolved_wxid_dir,
                        target_wxid=canonical_account,
                        account=account,
                        local_native_wxids=local_native_wxids,
                        template_scan=template_scan,
                    )
                except Exception as error:
                    logger.warning("[image_key] 使用原生 wxid 补充派生失败: %s", str(error))
                    resolution = None

        if resolution is not None and resolution.verified is True:
            _persist_verified_image_keys(
                canonical_account=canonical_account,
                request_account=account,
                source_wxid_dir=resolved_wxid_dir,
                matched_wxid=resolution.wxid,
                xor_key=resolution.xor_key,
                aes_key=resolution.aes_key,
                source="weflow_local_verified",
                code=resolution.code,
            )
            logger.info(
                "[image_key] WeFlow 本地派生验真成功: account=%s matched_wxid=%s key_pair_verified=true",
                canonical_account,
                resolution.wxid,
            )
            return _verified_image_key_result(
                canonical_account=canonical_account,
                matched_wxid=resolution.wxid,
                xor_key=resolution.xor_key,
                aes_key=resolution.aes_key,
                source="weflow_local_verified",
                code=resolution.code,
                template_path=resolution.template_path,
            )

        if template_scan.templates:
            for candidate in local_keys:
                normalized = _normalize_complete_image_key_payload(candidate)
                if normalized is None:
                    continue
                xor_key, aes_key = normalized
                if not verify_key_pair(
                    xor_key,
                    aes_key,
                    template_scan,
                    require_xor_match=True,
                ):
                    continue
                matched_wxid = str(candidate.get("wxid") or canonical_account).strip()
                _persist_verified_image_keys(
                    canonical_account=canonical_account,
                    request_account=account,
                    source_wxid_dir=resolved_wxid_dir,
                    matched_wxid=matched_wxid,
                    xor_key=xor_key,
                    aes_key=aes_key,
                    source="native_v2_verified",
                    trust_matched_alias=bool(
                        _image_key_account_match_variants(matched_wxid) & trusted_native_aliases
                    ),
                )
                logger.info(
                    "[image_key] 原生候选通过 V2 验真: account=%s matched_wxid=%s key_pair_verified=true",
                    canonical_account,
                    matched_wxid,
                )
                return _verified_image_key_result(
                    canonical_account=canonical_account,
                    matched_wxid=matched_wxid,
                    xor_key=xor_key,
                    aes_key=aes_key,
                    source="native_v2_verified",
                )

    logger.info("[image_key] 本地验真未命中，最后尝试远程 API 解析")
    remote_result = await fetch_and_save_remote_keys(
        account,
        wxid_dir=wxid_dir,
        db_storage_path=db_storage_path,
        persist=False,
    )
    normalized_remote = _normalize_complete_image_key_payload(remote_result)
    if normalized_remote is None:
        raise RuntimeError("远程 API 返回了不完整或格式无效的图片密钥")
    remote_xor, remote_aes = normalized_remote

    if resolved_wxid_dir is not None and template_scan is not None and template_scan.templates:
        if not verify_key_pair(
            remote_xor,
            remote_aes,
            template_scan,
            require_xor_match=True,
        ):
            raise RuntimeError("远程 API 返回的图片密钥未通过本地 V2 图片验真")
        matched_wxid = str(remote_result.get("wxid") or canonical_account).strip()
        _persist_verified_image_keys(
            canonical_account=canonical_account,
            request_account=account,
            source_wxid_dir=resolved_wxid_dir,
            matched_wxid=matched_wxid,
            xor_key=remote_xor,
            aes_key=remote_aes,
            source="remote_v2_verified",
        )
        return _verified_image_key_result(
            canonical_account=canonical_account,
            matched_wxid=matched_wxid,
            xor_key=remote_xor,
            aes_key=remote_aes,
            source="remote_v2_verified",
        )

    result = dict(remote_result)
    result.update({
        "xor_key": f"0x{remote_xor:02X}",
        "aes_key": remote_aes,
        "source": "remote_api",
        "verified": False,
    })
    return result


async def get_image_key_memory_workflow(
        account: Optional[str] = None,
        *,
        wxid_dir: Optional[str] = None,
        db_storage_path: Optional[str] = None,
        timeout: float = 60,
) -> Dict[str, Any]:
    """Scan WeChat process memory and persist only a V2-verified image key pair."""
    resolved_wxid_dir = _resolve_wxid_dir_for_image_key(
        account,
        wxid_dir=wxid_dir,
        db_storage_path=db_storage_path,
    )
    canonical_account = resolved_wxid_dir.name
    logger.info(
        "[image_key] 开始显式内存扫描: account=%s wxid_dir=%s timeout=%ss",
        canonical_account,
        str(resolved_wxid_dir),
        timeout,
    )

    timeout_seconds = max(0.0, float(timeout))
    try:
        resolution = await asyncio.wait_for(
            asyncio.to_thread(
                scan_image_key_from_memory,
                resolved_wxid_dir,
                timeout_seconds,
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        resolution = None
    if resolution is None or resolution.verified is not True:
        raise RuntimeError(
            f"{int(timeout_seconds)} 秒内未在微信进程内存中找到可通过 V2 图片验真的 AES 密钥"
        )

    _persist_verified_image_keys(
        canonical_account=canonical_account,
        request_account=account,
        source_wxid_dir=resolved_wxid_dir,
        matched_wxid=canonical_account,
        xor_key=resolution.xor_key,
        aes_key=resolution.aes_key,
        source="memory_v2_verified",
    )
    logger.info(
        "[image_key] 内存候选通过 V2 验真: account=%s pid=%s encoding=%s key_pair_verified=true",
        canonical_account,
        resolution.pid,
        resolution.encoding,
    )

    result = _verified_image_key_result(
        canonical_account=canonical_account,
        matched_wxid=canonical_account,
        xor_key=resolution.xor_key,
        aes_key=resolution.aes_key,
        source="memory_v2_verified",
        template_path=resolution.template_path,
    )
    result.update({"pid": resolution.pid, "encoding": resolution.encoding})
    return result


async def fetch_and_save_remote_keys(
        account: Optional[str] = None,
        *,
        wxid_dir: Optional[str] = None,
        db_storage_path: Optional[str] = None,
        persist: bool = True,
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
        _key_payload_log_metadata(config),
        str(config.get("nickName", config.get("nick_name", ""))),
    )

    normalized = _normalize_complete_image_key_payload({
        "xor_key": config.get("xorKey", config.get("xor_key")),
        "aes_key": config.get("aesKey", config.get("aes_key")),
    })
    if normalized is None:
        raise RuntimeError("云端解析失败: 返回的 XOR/AES 密钥不完整或格式无效")
    xor_int, aes_val = normalized
    xor_hex_str = f"0x{xor_int:02X}"

    if persist:
        upsert_account_keys_in_store(
            account=wxid,
            image_xor_key=xor_hex_str,
            image_aes_key=aes_val,
            image_key_verified=False,
            image_key_source="remote_api",
        )
        logger.info(
            "[image_key] 远程候选已按未验真状态保存：account=%s keys=%s",
            wxid,
            _key_payload_log_metadata({"xor_key": xor_hex_str, "aes_key": aes_val}),
        )

    return {
        "wxid": wxid,
        "xor_key": xor_hex_str,
        "aes_key": aes_val,
        "nick_name": config.get("nickName", config.get("nick_name", "")),
        "source": "remote_api",
        "verified": False,
    }
