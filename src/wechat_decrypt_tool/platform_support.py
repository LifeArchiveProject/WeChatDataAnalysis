from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path
from typing import Any


MAC_DB_KEY_GUIDANCE = (
    "macOS 数据库密钥获取需要完整安装包中的本地受控组件，并在每次获取时完成联网安全校验。"
    "若组件缺失、已过期或校验失败，请更新到最新正式版本；您仍可手动填写已有的 64 位密钥。"
)


def current_platform() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    return str(sys.platform or "unknown")


def is_macos() -> bool:
    return current_platform() == "macos"


def is_windows() -> bool:
    return current_platform() == "windows"


def _native_root() -> Path:
    return Path(__file__).resolve().parent / "native"


def _bundled_native_candidates(relative_path: Path, *, explicit: str = "") -> list[Path]:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())

    if getattr(sys, "frozen", False):
        # PyInstaller may normalize Mach-O files collected inside its onefile
        # archive.  The sibling native directory is copied byte-for-byte into
        # the signed app bundle specifically to provide stable runtime paths.
        executable_dir = Path(sys.executable).resolve().parent
        candidates.extend(
            (
                executable_dir / "native" / relative_path,
                executable_dir / "wechat_decrypt_tool" / "native" / relative_path,
            )
        )

    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        root = Path(bundle_root)
        candidates.extend(
            (
                root / "native" / relative_path,
                root / "wechat_decrypt_tool" / "native" / relative_path,
            )
        )

    candidates.append(_native_root() / relative_path)
    return candidates


def _first_existing_native_resource(relative_path: Path, *, explicit: str = "") -> Path:
    candidates = _bundled_native_candidates(relative_path, explicit=explicit)

    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return candidates[0]


def mac_db_key_bundle_dir() -> Path:
    explicit = str(os.environ.get("WECHAT_TOOL_MACOS_DB_KEY_BUNDLE", "") or "").strip()
    if getattr(sys, "frozen", False):
        # A packaged backend must execute only the helper sealed into its own
        # application resources.  Honouring a process-environment path here
        # would let an alternate, self-described artifact bypass that boundary.
        explicit = ""
    candidates = _bundled_native_candidates(
        Path("macos") / "db-key" / "wda_xkey_helper",
        explicit=str(Path(explicit).expanduser() / "wda_xkey_helper") if explicit else "",
    )
    roots = [candidate.parent for candidate in candidates]
    for root in roots:
        try:
            if root.is_dir():
                return root.resolve()
        except OSError:
            continue
    return roots[0]


def mac_image_scan_helper_path() -> Path:
    return _first_existing_native_resource(
        Path("macos") / "universal" / "image_scan_helper",
        explicit=str(os.environ.get("WECHAT_TOOL_IMAGE_SCAN_HELPER", "") or "").strip(),
    )


def mac_image_scan_library_path() -> Path:
    return _first_existing_native_resource(
        Path("macos") / "universal" / "libwx_key.dylib",
        explicit=str(os.environ.get("WECHAT_TOOL_IMAGE_SCAN_LIBRARY", "") or "").strip(),
    )


def mac_native_core_paths() -> tuple[Path, Path, Path]:
    return (
        _first_existing_native_resource(
            Path("libwechatdb_client.dylib"),
            explicit=str(
                os.environ.get("WECHAT_TOOL_NATIVE_CORE_LIBRARY", "") or ""
            ).strip(),
        ),
        _first_existing_native_resource(
            Path("wechatdb_broker"),
            explicit=str(
                os.environ.get("WECHAT_TOOL_NATIVE_CORE_BROKER", "") or ""
            ).strip(),
        ),
        _first_existing_native_resource(Path("wechatdb_native_build.json")),
    )


def _native_core_resources_ready(paths: tuple[Path, Path, Path]) -> bool:
    client, broker, manifest_path = paths
    try:
        if not client.is_file() or not broker.is_file() or not manifest_path.is_file():
            return False
        if client.stat().st_size <= 0 or broker.stat().st_size <= 0:
            return False
        if manifest_path.stat().st_size <= 0 or manifest_path.stat().st_size > 16 * 1024:
            return False
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return bool(
        isinstance(manifest, dict)
        and manifest.get("schemaVersion") == 2
        and str(manifest.get("buildId") or "").strip()
        and isinstance(manifest.get("developmentBuild"), bool)
    )


def runtime_capabilities() -> dict[str, Any]:
    system = current_platform()
    architecture = (platform.machine() or "unknown").lower()
    apple_silicon = system == "macos" and architecture in {"arm64", "aarch64"}
    helper = mac_image_scan_helper_path() if system == "macos" else None
    image_scan_library = mac_image_scan_library_path() if system == "macos" else None
    native_core_paths = mac_native_core_paths() if system == "macos" else None
    image_scan_ready = bool(
        helper
        and image_scan_library
        and helper.is_file()
        and image_scan_library.is_file()
        and helper.parent.resolve() == image_scan_library.parent.resolve()
    )
    realtime_ready = bool(
        apple_silicon
        and native_core_paths
        and _native_core_resources_ready(native_core_paths)
    )
    mac_db_key_status: dict[str, Any] = {
        "available": False,
        "note": MAC_DB_KEY_GUIDANCE,
    }
    if system == "macos":
        try:
            from .macos_db_key_helper import inspect_macos_db_key_bundle

            mac_db_key_status = inspect_macos_db_key_bundle().as_capability()
        except Exception:
            mac_db_key_status = {
                "available": False,
                "note": "macOS 数据库密钥本地组件校验失败，请更新或重新安装正式版本。",
            }
    return {
        "platform": system,
        "platform_release": platform.release(),
        "architecture": architecture,
        "apple_silicon": apple_silicon,
        "database_key_extraction": system == "windows" or bool(mac_db_key_status["available"]),
        "database_key_manual_input": True,
        "database_decryption": True,
        "image_key_memory_scan": system == "windows" or image_scan_ready,
        "image_key_memory_scan_note": (
            "macOS 图片密钥扫描原生资源缺失或安装不完整，请重新安装完整发行包。"
            if system == "macos" and not image_scan_ready
            else ""
        ),
        "realtime_wcdb": system == "windows" or realtime_ready,
        "realtime_wcdb_note": (
            "macOS 实时 WCDB 当前仅支持 Apple Silicon。"
            if system == "macos" and not apple_silicon
            else "macOS 实时 WCDB 原生资源缺失，请重新安装完整发行包。"
            if system == "macos" and not realtime_ready
            else ""
        ),
        "wechat_process_media_hook": system == "windows",
        "account_archive_export": True,
        "account_archive_import": True,
        "account_archive_cross_platform": True,
        "database_key_guidance": (
            str(mac_db_key_status.get("note") or MAC_DB_KEY_GUIDANCE)
            if system == "macos"
            else ""
        ),
        "database_key_build_id": (
            str(mac_db_key_status.get("build_id") or "") if system == "macos" else ""
        ),
        "database_key_build_expires_at_unix": (
            mac_db_key_status.get("build_expires_at_unix") if system == "macos" else None
        ),
        "database_key_online_authorization_required": system == "macos",
        "suggested_key_tools": [],
    }


__all__ = [
    "MAC_DB_KEY_GUIDANCE",
    "current_platform",
    "is_macos",
    "is_windows",
    "mac_image_scan_helper_path",
    "mac_image_scan_library_path",
    "mac_db_key_bundle_dir",
    "mac_native_core_paths",
    "runtime_capabilities",
]
