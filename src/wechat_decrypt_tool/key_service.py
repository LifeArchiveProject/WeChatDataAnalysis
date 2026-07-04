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
from .dll_key_scan import extract_xor_keys_from_dll
from .key_store import upsert_account_keys_in_store
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
        from . import key_v4 as key_v4_module
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
            target_account_variants = _image_key_account_match_variants(target_account_wxid)
            for k in local_keys:
                local_wxid = str(k.get("wxid") or "").strip().lower()
                local_account_variants = _image_key_account_match_variants(local_wxid)
                if local_account_variants and (local_account_variants & target_account_variants):
                    logger.info(
                        "[image_key] 本地算法账号匹配成功：target_wxid=%s target_variants=%s local_variants=%s payload=%s",
                        target_account_wxid,
                        sorted(target_account_variants),
                        sorted(local_account_variants),
                        _summarize_key_payload(k),
                    )
                    if local_wxid != target_account_wxid:
                        aliases = []
                        for alias in [local_wxid, str(account or "").strip()]:
                            if alias and alias not in aliases:
                                aliases.append(alias)
                        upsert_account_keys_in_store(
                            account=target_account_wxid,
                            image_xor_key=k['xor_key'],
                            image_aes_key=k['aes_key'],
                            aliases=aliases,
                        )
                    else:
                        upsert_account_keys_in_store(
                            account=str(k.get("wxid") or "").strip(),
                            image_xor_key=k['xor_key'],
                            image_aes_key=k['aes_key']
                        )
                    k = dict(k)
                    k.setdefault("matched_wxid", target_account_wxid)
                    k.setdefault("match_variants", sorted(local_account_variants | target_account_variants))
                    return k
            logger.info(
                "[image_key] 本地算法未匹配到目标账号：target_wxid=%s target_variants=%s local_wxids=%s",
                target_account_wxid,
                sorted(target_account_variants),
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
