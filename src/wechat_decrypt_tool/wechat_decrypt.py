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
import struct
import time
from pathlib import Path
from typing import Any

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .app_paths import get_output_databases_dir
from .database_filters import should_skip_source_database
from .sqlite_diagnostics import collect_sqlite_diagnostics, sqlite_diagnostics_status

# 注意：不再支持默认密钥，所有密钥必须通过参数传入

# SQLite文件头
SQLITE_HEADER = b"SQLite format 3\x00"
PAGE_SIZE = 4096
KEY_SIZE = 32
SALT_SIZE = 16
IV_SIZE = 16
HMAC_SIZE = 64
# WeChat 4.x SQLCipher/WCDB pages reserve IV + HMAC at the tail.
# When exporting to plain SQLite, do not keep encrypted IV/HMAC bytes in output pages.
RESERVE_SIZE = IV_SIZE + HMAC_SIZE


def _derive_mac_key(enc_key: bytes, salt: bytes) -> bytes:
    """Derive SQLCipher/WCDB page HMAC key."""
    mac_salt = bytes(b ^ 0x3A for b in salt)
    return hashlib.pbkdf2_hmac("sha512", enc_key, mac_salt, 2, dklen=KEY_SIZE)


def _derive_sqlcipher_enc_key(key_material: bytes, salt: bytes) -> bytes:
    """Derive AES enc_key from SQLCipher passphrase/base key."""
    return hashlib.pbkdf2_hmac("sha512", key_material, salt, 256000, dklen=KEY_SIZE)


def _compute_page_hmac(mac_key: bytes, page: bytes, page_num: int) -> bytes:
    offset = SALT_SIZE if page_num == 1 else 0
    data_end = PAGE_SIZE - RESERVE_SIZE + IV_SIZE
    mac = hmac.new(mac_key, digestmod=hashlib.sha512)
    mac.update(page[offset:data_end])
    mac.update(page_num.to_bytes(4, "little"))
    return mac.digest()


def _compute_page_hmac_variant(
    mac_key: bytes,
    page: bytes,
    page_num: int,
    *,
    endian: str = "little",
    include_iv: bool = True,
) -> bytes:
    """用于诊断的 HMAC 变体计算，不参与实际解密决策。"""
    offset = SALT_SIZE if page_num == 1 else 0
    data_end = PAGE_SIZE - RESERVE_SIZE + (IV_SIZE if include_iv else 0)
    mac = hmac.new(mac_key, digestmod=hashlib.sha512)
    mac.update(page[offset:data_end])
    mac.update(page_num.to_bytes(4, endian))
    return mac.digest()


def _hash_prefix(data: bytes, *, length: int = 16) -> str:
    """返回 SHA256 前缀，避免日志输出明文数据。"""
    try:
        return hashlib.sha256(bytes(data or b"")).hexdigest()[: max(int(length), 8)]
    except Exception:
        return ""


def _hex_prefix(data: bytes, *, length: int = 32) -> str:
    try:
        return bytes(data or b"")[: max(int(length), 0)].hex()
    except Exception:
        return ""


def _safe_file_snapshot(path: str | Path) -> dict[str, Any]:
    """采集源/输出文件与 WAL 旁路文件信息，用于定位解密时文件是否变化。"""
    p = Path(path)
    out: dict[str, Any] = {"path": str(p), "exists": False}
    try:
        st = p.stat()
        out.update(
            {
                "exists": True,
                "size": int(st.st_size),
                "mtime_ns": int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))),
            }
        )
    except Exception as exc:
        out["stat_error"] = f"{type(exc).__name__}: {' '.join(str(exc).split())[:180]}"

    siblings: dict[str, Any] = {}
    for suffix in ("-wal", "-shm", "-journal"):
        sp = Path(str(p) + suffix)
        try:
            st = sp.stat()
            siblings[suffix] = {
                "exists": True,
                "size": int(st.st_size),
                "mtime_ns": int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))),
            }
        except FileNotFoundError:
            siblings[suffix] = {"exists": False}
        except Exception as exc:
            siblings[suffix] = {
                "exists": False,
                "stat_error": f"{type(exc).__name__}: {' '.join(str(exc).split())[:180]}",
            }
    out["siblings"] = siblings
    return out


def _read_plain_sqlite_header_debug(path: str | Path) -> dict[str, Any]:
    """解析明文 SQLite 头部关键字段，帮助定位输出库结构问题。"""
    p = Path(path)
    out: dict[str, Any] = {"path": str(p)}
    try:
        with p.open("rb") as f:
            header = f.read(100)
        out["header_len"] = len(header)
        out["header_ok"] = header.startswith(SQLITE_HEADER)
        out["header_hex"] = header[:32].hex()
        if len(header) >= 100:
            raw_page_size = struct.unpack(">H", header[16:18])[0]
            out.update(
                {
                    "page_size_header": 65536 if raw_page_size == 1 else int(raw_page_size),
                    "write_version": int(header[18]),
                    "read_version": int(header[19]),
                    "reserved_space": int(header[20]),
                    "max_payload_fraction": int(header[21]),
                    "min_payload_fraction": int(header[22]),
                    "leaf_payload_fraction": int(header[23]),
                    "file_change_counter": int.from_bytes(header[24:28], "big"),
                    "db_size_pages_header": int.from_bytes(header[28:32], "big"),
                    "freelist_trunk_page": int.from_bytes(header[32:36], "big"),
                    "freelist_pages": int.from_bytes(header[36:40], "big"),
                    "schema_cookie": int.from_bytes(header[40:44], "big"),
                    "schema_format": int.from_bytes(header[44:48], "big"),
                    "text_encoding": int.from_bytes(header[56:60], "big"),
                }
            )
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {' '.join(str(exc).split())[:180]}"
    return out


def _plain_page_btree_debug(page_plain: bytes, page_num: int) -> dict[str, Any]:
    """解析明文页 B-tree 页头摘要，不输出任何业务明文。"""
    out: dict[str, Any] = {"page": int(page_num), "plain_sha256": _hash_prefix(page_plain, length=24)}
    try:
        hdr = 100 if int(page_num) == 1 else 0
        if len(page_plain) >= hdr + 12:
            page_type = int(page_plain[hdr])
            out["btree_header_offset"] = int(hdr)
            out["btree_page_type"] = page_type
            out["btree_page_type_name"] = {
                2: "interior_index",
                5: "interior_table",
                10: "leaf_index",
                13: "leaf_table",
            }.get(page_type, "unknown")
            out["first_freeblock"] = int.from_bytes(page_plain[hdr + 1 : hdr + 3], "big")
            out["cell_count"] = int.from_bytes(page_plain[hdr + 3 : hdr + 5], "big")
            out["cell_content_area"] = int.from_bytes(page_plain[hdr + 5 : hdr + 7], "big")
            out["fragmented_free_bytes"] = int(page_plain[hdr + 7])
            if page_type in (2, 5):
                out["right_most_pointer"] = int.from_bytes(page_plain[hdr + 8 : hdr + 12], "big")
    except Exception as exc:
        out["btree_parse_error"] = f"{type(exc).__name__}: {' '.join(str(exc).split())[:160]}"
    return out


def _build_page_anomaly_debug(
    enc_key: bytes,
    mac_key: bytes,
    page: bytes,
    page_num: int,
    *,
    stored_hmac: bytes | None = None,
    expected_hmac: bytes | None = None,
    reason: str = "hmac",
) -> dict[str, Any]:
    """构造异常页诊断信息，默认只记录哈希/页头摘要。"""
    page = bytes(page or b"")
    stored = stored_hmac if stored_hmac is not None else page[PAGE_SIZE - HMAC_SIZE : PAGE_SIZE]
    expected = expected_hmac if expected_hmac is not None else _compute_page_hmac(mac_key, page, page_num)
    iv = page[PAGE_SIZE - RESERVE_SIZE : PAGE_SIZE - RESERVE_SIZE + IV_SIZE]
    encrypted_payload = page[SALT_SIZE if page_num == 1 else 0 : PAGE_SIZE - RESERVE_SIZE]
    out: dict[str, Any] = {
        "reason": str(reason),
        "page": int(page_num),
        "byte_start": int((int(page_num) - 1) * PAGE_SIZE),
        "byte_end_exclusive": int(int(page_num) * PAGE_SIZE),
        "page_size": int(len(page)),
        "page_sha256": _hash_prefix(page, length=24),
        "encrypted_payload_sha256": _hash_prefix(encrypted_payload, length=24),
        "iv_hex": _hex_prefix(iv, length=16),
        "stored_hmac_prefix": _hex_prefix(stored, length=16),
        "expected_hmac_prefix": _hex_prefix(expected, length=16),
        "hmac_match_current": bool(hmac.compare_digest(stored, expected)),
    }

    variants: dict[str, bool] = {}
    for candidate_page in (page_num - 1, page_num, page_num + 1):
        if candidate_page <= 0:
            continue
        for endian in ("little", "big"):
            for include_iv in (True, False):
                key = f"page={candidate_page};endian={endian};include_iv={int(include_iv)}"
                try:
                    variants[key] = bool(
                        hmac.compare_digest(
                            stored,
                            _compute_page_hmac_variant(
                                mac_key,
                                page,
                                int(candidate_page),
                                endian=endian,
                                include_iv=include_iv,
                            ),
                        )
                    )
                except Exception:
                    variants[key] = False
    out["hmac_variant_matches"] = [k for k, v in variants.items() if v]

    try:
        plain_page = _decrypt_page(enc_key, page, int(page_num))
        out["aes_decrypt_ok"] = True
        out["plain"] = _plain_page_btree_debug(plain_page, int(page_num))
    except Exception as exc:
        out["aes_decrypt_ok"] = False
        out["aes_error"] = f"{type(exc).__name__}: {' '.join(str(exc).split())[:180]}"

    return out


def _resolve_page1_key_material(key_material: bytes, page1: bytes) -> tuple[bytes, bytes, str] | None:
    """Detect whether input key is raw enc_key or SQLCipher passphrase by page-1 HMAC."""
    if len(page1) < PAGE_SIZE:
        return None

    salt = page1[:SALT_SIZE]
    stored_page1_hmac = page1[PAGE_SIZE - HMAC_SIZE: PAGE_SIZE]
    candidates = [
        ("raw_enc_key", key_material, _derive_mac_key(key_material, salt)),
    ]

    derived_key = _derive_sqlcipher_enc_key(key_material, salt)
    candidates.append(("sqlcipher_passphrase", derived_key, _derive_mac_key(derived_key, salt)))

    for mode, enc_key, mac_key in candidates:
        if hmac.compare_digest(stored_page1_hmac, _compute_page_hmac(mac_key, page1, 1)):
            return enc_key, mac_key, mode

    return None


def _decrypt_page(enc_key: bytes, page: bytes, page_num: int) -> bytes:
    iv = page[PAGE_SIZE - RESERVE_SIZE: PAGE_SIZE - RESERVE_SIZE + IV_SIZE]
    offset = SALT_SIZE if page_num == 1 else 0
    encrypted_page = page[offset: PAGE_SIZE - RESERVE_SIZE]

    cipher = Cipher(
        algorithms.AES(enc_key),
        modes.CBC(iv),
        backend=default_backend(),
    )
    decryptor = cipher.decryptor()
    decrypted_page = decryptor.update(encrypted_page) + decryptor.finalize()

    # Plain SQLite pages do not carry SQLCipher/WCDB IV/HMAC reserve bytes.
    # Keep page size stable by zero-filling the reserve tail.
    if page_num == 1:
        return SQLITE_HEADER + decrypted_page + (b"\x00" * RESERVE_SIZE)
    return decrypted_page + (b"\x00" * RESERVE_SIZE)


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
    from .logging_config import get_logger

    logger = get_logger(__name__)
    storage_path = Path(str(db_storage_path or "").strip())
    logger.info("[decrypt.scan] start db_storage_path=%s", str(storage_path))
    if not storage_path.exists():
        logger.warning("[decrypt.scan] path_not_exists db_storage_path=%s", str(storage_path))
        return {
            "status": "error",
            "message": f"指定的数据库路径不存在: {db_storage_path}",
            "account_databases": {},
            "account_sources": {},
            "detected_accounts": [],
        }

    db_roots = _resolve_db_storage_roots(storage_path)
    logger.info(
        "[decrypt.scan] resolved_roots %s",
        json.dumps([str(x) for x in db_roots], ensure_ascii=False),
    )
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

    logger.info(
        "[decrypt.scan] databases_found %s",
        json.dumps(
            {
                "account": account_name,
                "db_storage_path": str(db_root),
                "wxid_dir": str(db_root.parent),
                "count": len(databases),
                "files": [
                    {
                        "name": str(item.get("name") or ""),
                        "relative": str(Path(str(item.get("path") or "")).relative_to(db_root))
                        if str(item.get("path") or "").startswith(str(db_root))
                        else str(item.get("path") or ""),
                    }
                    for item in databases[:80]
                ],
                "truncated": max(0, len(databases) - 80),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
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
            "hmac_warning_pages": 0,
            "hmac_warning_samples": [],
            "hmac_debug_samples": [],
            "aes_debug_samples": [],
            "source_snapshot_before": {},
            "source_snapshot_after": {},
            "source_changed_during_read": False,
            "read_ms": 0,
            "key_mode": "",
            "input_layout": {},
            "expected_output_size": 0,
            "output_header_debug": {},
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

        def _append_hmac_warning_page(page_num: int) -> None:
            # 非首页 HMAC 异常不再直接丢弃页面：部分微信 4.x 大库在 1GiB 边界会出现
            # 单页 HMAC 不匹配，但页面本身仍可正常解密。丢页会导致后续页号整体错位。
            result["hmac_warning_pages"] = int(result.get("hmac_warning_pages") or 0) + 1
            if len(result["hmac_warning_samples"]) >= 8:
                return
            result["hmac_warning_samples"].append({"page": int(page_num), "reason": "hmac"})

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
                result["output_header_debug"] = _read_plain_sqlite_header_debug(output_file)

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
                "hmac_warning_pages": result["hmac_warning_pages"],
                "hmac_warning_samples": result["hmac_warning_samples"],
                "hmac_debug_samples": result["hmac_debug_samples"],
                "aes_debug_samples": result["aes_debug_samples"],
                "source_snapshot_before": result["source_snapshot_before"],
                "source_snapshot_after": result["source_snapshot_after"],
                "source_changed_during_read": result["source_changed_during_read"],
                "read_ms": result["read_ms"],
                "key_mode": result["key_mode"],
                "input_layout": result["input_layout"],
                "expected_output_size": result["expected_output_size"],
                "output_header_debug": result["output_header_debug"],
                "diagnostic_status": result["diagnostic_status"],
                "diagnostics": result["diagnostics"],
                "error": result["error"],
            }
            log_fn = logger.info
            if (
                (not result["success"])
                or int(result["failed_pages"] or 0) > 0
                or int(result.get("hmac_warning_pages") or 0) > 0
                or str(result["diagnostic_status"] or "") != "ok"
            ):
                log_fn = logger.warning
            log_fn("[decrypt.diagnostic] %s", json.dumps(payload, ensure_ascii=False, sort_keys=True))
            self.last_result = result
            return bool(result["success"])

        logger.info(f"开始解密数据库: {db_path}")
        
        try:
            source_snapshot_before = _safe_file_snapshot(db_path)
            result["source_snapshot_before"] = source_snapshot_before
            logger.info(
                "[decrypt.pipeline] source_snapshot_before %s",
                json.dumps(
                    {
                        "db_name": result["db_name"],
                        "snapshot": source_snapshot_before,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )

            read_t0 = time.perf_counter()
            with open(db_path, 'rb') as f:
                encrypted_data = f.read()
            result["read_ms"] = round((time.perf_counter() - read_t0) * 1000.0, 1)

            source_snapshot_after = _safe_file_snapshot(db_path)
            result["source_snapshot_after"] = source_snapshot_after
            before_size = int(source_snapshot_before.get("size") or 0)
            after_size = int(source_snapshot_after.get("size") or 0)
            before_mtime = int(source_snapshot_before.get("mtime_ns") or 0)
            after_mtime = int(source_snapshot_after.get("mtime_ns") or 0)
            source_changed = bool(before_size != after_size or before_mtime != after_mtime)
            result["source_changed_during_read"] = source_changed
            logger.info(
                "[decrypt.pipeline] source_snapshot_after %s",
                json.dumps(
                    {
                        "db_name": result["db_name"],
                        "snapshot": source_snapshot_after,
                        "read_ms": result["read_ms"],
                        "source_changed_during_read": source_changed,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
            if source_changed:
                logger.warning(
                    "[decrypt.pipeline] source_changed_during_read db=%s before_size=%s after_size=%s before_mtime_ns=%s after_mtime_ns=%s",
                    result["db_name"],
                    before_size,
                    after_size,
                    before_mtime,
                    after_mtime,
                )

            logger.info(f"读取文件大小: {len(encrypted_data)} bytes")
            result["input_size"] = int(len(encrypted_data))
            result["input_layout"] = {
                "page_size": PAGE_SIZE,
                "reserve_size": RESERVE_SIZE,
                "iv_size": IV_SIZE,
                "hmac_size": HMAC_SIZE,
                "input_size": int(len(encrypted_data)),
                "input_size_mod_page": int(len(encrypted_data) % PAGE_SIZE),
                "total_pages_floor": int(len(encrypted_data) // PAGE_SIZE),
                "total_pages_ceil": int((len(encrypted_data) + PAGE_SIZE - 1) // PAGE_SIZE),
                "starts_with_sqlite_header": bool(encrypted_data.startswith(SQLITE_HEADER)),
                "first16_hex": encrypted_data[:16].hex(),
            }
            logger.info(
                "[decrypt.pipeline] input_layout %s",
                json.dumps(
                    {
                        "db_name": result["db_name"],
                        "input_layout": result["input_layout"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )

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
            
            page1 = encrypted_data[:PAGE_SIZE]
            resolved_key_material = _resolve_page1_key_material(self.key_bytes, page1)
            if resolved_key_material is None:
                _append_failed_page(1, "hmac")
                result["total_pages"] = int(len(encrypted_data) // PAGE_SIZE)
                result["failed_pages"] = 1
                logger.warning("Page 1 HMAC verification failed; key does not match database: %s", db_path)
                return _finalize(False, "key_mismatch")

            enc_key, mac_key, key_mode = resolved_key_material
            result["key_mode"] = key_mode
            logger.info("Page 1 HMAC verification passed: mode=%s path=%s", key_mode, db_path)
            logger.info(
                "[decrypt.pipeline] key_material_resolved %s",
                json.dumps(
                    {
                        "db_name": result["db_name"],
                        "key_mode": key_mode,
                        "salt_sha256": _hash_prefix(page1[:SALT_SIZE], length=24),
                        "page1_stored_hmac_prefix": _hex_prefix(page1[PAGE_SIZE - HMAC_SIZE : PAGE_SIZE], length=16),
                        "page1_expected_hmac_prefix": _hex_prefix(_compute_page_hmac(mac_key, page1, 1), length=16),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )

            decrypted_data = bytearray()
            total_pages = (len(encrypted_data) + PAGE_SIZE - 1) // PAGE_SIZE
            successful_pages = 0
            failed_pages = 0
            result["total_pages"] = int(total_pages)
            result["expected_output_size"] = int(total_pages * PAGE_SIZE)
            logger.info(
                "[decrypt.pipeline] page_loop_start db=%s total_pages=%s expected_output_size=%s",
                result["db_name"],
                int(total_pages),
                int(result["expected_output_size"]),
            )

            for cur_page in range(total_pages):
                page_num = cur_page + 1
                start = cur_page * PAGE_SIZE
                page = encrypted_data[start:start + PAGE_SIZE]
                if not page:
                    break
                if len(page) < PAGE_SIZE:
                    logger.warning(
                        "Page %s is short: %s bytes; padding to %s bytes",
                        page_num,
                        len(page),
                        PAGE_SIZE,
                    )
                    page = page + (b"\x00" * (PAGE_SIZE - len(page)))

                stored_hmac = page[PAGE_SIZE - HMAC_SIZE: PAGE_SIZE]
                expected_hmac = _compute_page_hmac(mac_key, page, page_num)
                if not hmac.compare_digest(stored_hmac, expected_hmac):
                    logger.warning("Page %s HMAC verification failed; decrypting page anyway", page_num)
                    _append_hmac_warning_page(page_num)
                    anomaly_debug = _build_page_anomaly_debug(
                        enc_key,
                        mac_key,
                        page,
                        page_num,
                        stored_hmac=stored_hmac,
                        expected_hmac=expected_hmac,
                        reason="hmac",
                    )
                    if len(result["hmac_debug_samples"]) < 8:
                        result["hmac_debug_samples"].append(anomaly_debug)
                    logger.warning(
                        "[decrypt.page_anomaly] %s",
                        json.dumps(
                            {
                                "db_name": result["db_name"],
                                "anomaly": anomaly_debug,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    )

                try:
                    decrypted_data.extend(_decrypt_page(enc_key, page, page_num))
                    successful_pages += 1
                except Exception as e:
                    logger.error("Page %s AES decryption failed: %s", page_num, e)
                    failed_pages += 1
                    _append_failed_page(page_num, "aes", str(e))
                    aes_debug = _build_page_anomaly_debug(
                        enc_key,
                        mac_key,
                        page,
                        page_num,
                        stored_hmac=stored_hmac,
                        expected_hmac=expected_hmac,
                        reason="aes",
                    )
                    if len(result["aes_debug_samples"]) < 8:
                        result["aes_debug_samples"].append(aes_debug)
                    logger.error(
                        "[decrypt.page_anomaly] %s",
                        json.dumps(
                            {
                                "db_name": result["db_name"],
                                "anomaly": aes_debug,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    )
                    # 保留页占位，避免后续页整体错位导致 SQLite 必然损坏。
                    decrypted_data.extend(b"\x00" * PAGE_SIZE)
                    continue

                if total_pages >= 100000 and page_num % 50000 == 0:
                    logger.info(
                        "[decrypt.pipeline] page_loop_progress db=%s page=%s/%s successful_pages=%s failed_pages=%s hmac_warning_pages=%s output_bytes=%s",
                        result["db_name"],
                        int(page_num),
                        int(total_pages),
                        int(successful_pages),
                        int(failed_pages),
                        int(result.get("hmac_warning_pages") or 0),
                        int(len(decrypted_data)),
                    )

            result["successful_pages"] = int(successful_pages)
            result["failed_pages"] = int(failed_pages)

            # 写入解密后的文件
            with open(output_path, 'wb') as f:
                f.write(decrypted_data)

            logger.info(f"解密文件大小: {len(decrypted_data)} bytes")
            if int(len(decrypted_data)) != int(result["expected_output_size"]):
                logger.warning(
                    "[decrypt.pipeline] output_size_mismatch db=%s output_size=%s expected_output_size=%s delta=%s",
                    result["db_name"],
                    int(len(decrypted_data)),
                    int(result["expected_output_size"]),
                    int(len(decrypted_data)) - int(result["expected_output_size"]),
                )
            if failed_pages > 0:
                logger.warning(
                    "解密输出包含页失败: db=%s total_pages=%s failed_pages=%s failure_reasons=%s samples=%s",
                    result["db_name"],
                    int(total_pages),
                    int(failed_pages),
                    json.dumps(result["failure_reasons"], ensure_ascii=False, sort_keys=True),
                    json.dumps(result["failed_page_samples"], ensure_ascii=False),
                )
            if int(result.get("hmac_warning_pages") or 0) > 0:
                logger.warning(
                    "解密输出包含HMAC告警页但已保留页内容: db=%s total_pages=%s hmac_warning_pages=%s samples=%s",
                    result["db_name"],
                    int(total_pages),
                    int(result.get("hmac_warning_pages") or 0),
                    json.dumps(result["hmac_warning_samples"], ensure_ascii=False),
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
                or int(db_diagnostic.get("hmac_warning_pages") or 0) > 0
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
            "source_db_storage_path": str(source_db_storage_path),
            "source_wxid_dir": str(wxid_dir),
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
