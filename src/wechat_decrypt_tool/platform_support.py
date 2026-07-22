from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Any


MAC_DB_KEY_GUIDANCE = (
    "macOS 版不提供数据库密钥提取。请使用支持 macOS 的同类本地工具获取您本人账号的数据库密钥，"
    "然后回到本应用手动填写；填写后数据库解密、实时消息和分析功能仍可使用。"
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

    candidates.append(_native_root() / relative_path)

    if getattr(sys, "frozen", False):
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


def mac_wcdb_api_path(architecture: str | None = None) -> Path:
    arch = str(architecture or platform.machine() or "").strip().lower()
    arch_dir = "arm64" if arch in {"arm64", "aarch64"} else "x64"
    return _first_existing_native_resource(
        Path("macos") / arch_dir / "libwcdb_api.dylib",
        explicit=str(os.environ.get("WECHAT_TOOL_WCDB_API_DLL_PATH", "") or "").strip(),
    )


def runtime_capabilities() -> dict[str, Any]:
    system = current_platform()
    architecture = (platform.machine() or "unknown").lower()
    apple_silicon = system == "macos" and architecture in {"arm64", "aarch64"}
    helper = mac_image_scan_helper_path() if system == "macos" else None
    image_scan_library = mac_image_scan_library_path() if system == "macos" else None
    wcdb_api = mac_wcdb_api_path(architecture) if system == "macos" else None
    image_scan_ready = bool(
        helper
        and image_scan_library
        and helper.is_file()
        and image_scan_library.is_file()
        and helper.parent.resolve() == image_scan_library.parent.resolve()
    )
    realtime_ready = bool(apple_silicon and wcdb_api and wcdb_api.is_file())
    return {
        "platform": system,
        "platform_release": platform.release(),
        "architecture": architecture,
        "apple_silicon": apple_silicon,
        "database_key_extraction": system == "windows",
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
        "database_key_guidance": MAC_DB_KEY_GUIDANCE if system == "macos" else "",
        "suggested_key_tools": (
            [
                {
                    "name": "WeFlow",
                    "url": "https://github.com/hicccc77/WeFlow",
                    "purpose": "获取 macOS 微信数据库密钥",
                }
            ]
            if system == "macos"
            else []
        ),
    }


__all__ = [
    "MAC_DB_KEY_GUIDANCE",
    "current_platform",
    "is_macos",
    "is_windows",
    "mac_image_scan_helper_path",
    "mac_image_scan_library_path",
    "mac_wcdb_api_path",
    "runtime_capabilities",
]
