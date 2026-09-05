from __future__ import annotations

import json
import os
import plistlib
import shutil
import sys
from pathlib import Path
from typing import Any


DEFAULT_WECHAT_APP = Path("/Applications/WeChat.app")
DEFAULT_DATA_RELATIVE = Path(
    "Library/Containers/com.tencent.xinWeChat/Data/Documents/app_data/xwechat_files"
)
DEFAULT_DATA_RELATIVES = (
    DEFAULT_DATA_RELATIVE,
    Path("Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files"),
    Path("Documents/xwechat_files"),
    Path("Documents/WeChat Files"),
)
APP_SUPPORT_RELATIVE = Path("Library/Application Support/WeDataKeyExtractor")
DATABASE_PRIORITY = (
    "msg0.db",
    "msg.db",
    "message_0.db",
    "message_1.db",
    "session.db",
    "contact.db",
    "favorite.db",
    "sns.db",
    "general.db",
    "media_0.db",
    "head_image.db",
)
KNOWN_DATABASE_RELATIVES = (
    Path("msg0.db"),
    Path("msg.db"),
    Path("message_0.db"),
    Path("message/message_0.db"),
    Path("message/message_1.db"),
    Path("session.db"),
    Path("session/session.db"),
    Path("contact.db"),
    Path("contact/contact.db"),
    Path("sns.db"),
    Path("sns/sns.db"),
    Path("general.db"),
    Path("general/general.db"),
)


def app_support_root(home: str | Path | None = None) -> Path:
    base = Path(home).expanduser() if home is not None else Path.home()
    return base / APP_SUPPORT_RELATIVE


def default_work_root(home: str | Path | None = None) -> Path:
    """Use this app's per-user support directory on every machine."""

    base = Path(home).expanduser() if home is not None else Path.home()
    return app_support_root(base) / "work"


def default_backup_root(work_root: str | Path) -> Path:
    return Path(work_root).expanduser() / "wechat-app-backups"


def _candidate_rank(path: Path) -> tuple[int, str]:
    name = path.name.lower()
    try:
        priority = DATABASE_PRIORITY.index(name)
    except ValueError:
        priority = len(DATABASE_PRIORITY)
    return priority, path.as_posix().lower()


def _usable_database(path: Path) -> bool:
    try:
        return path.is_file() and path.suffix.lower() == ".db" and path.stat().st_size >= 4096
    except OSError:
        return False


def resolve_probe_database(selected_path: str | Path) -> Path:
    selected = Path(selected_path).expanduser()
    if _usable_database(selected):
        return selected
    if not selected.is_dir():
        raise FileNotFoundError(f"数据库路径不存在: {selected}")

    known = [selected / relative for relative in KNOWN_DATABASE_RELATIVES]
    known = sorted((path for path in known if _usable_database(path)), key=_candidate_rank)
    if known:
        return known[0]

    candidates = sorted(
        (path for path in selected.rglob("*.db") if _usable_database(path)),
        key=_candidate_rank,
    )
    if not candidates:
        raise FileNotFoundError(f"目录中没有可用于校验的微信数据库: {selected}")
    return candidates[0]


def discover_default_probe_databases(home: str | Path | None = None) -> list[Path]:
    base = Path(home).expanduser() if home is not None else Path.home()
    found: list[Path] = []
    seen: set[str] = set()
    seen_accounts: set[str] = set()
    for relative_root in DEFAULT_DATA_RELATIVES:
        data_root = base / relative_root
        if not data_root.is_dir():
            continue
        account_candidates = [
            *data_root.glob("wxid_*"),
        ]
        if data_root.name.lower().startswith("wxid_"):
            account_candidates.append(data_root)
        for account_dir in sorted(account_candidates, key=lambda item: item.as_posix().lower()):
            account_key = account_dir.name.lower()
            if account_key in seen_accounts:
                continue
            storage = account_dir / "db_storage"
            if not storage.is_dir():
                continue
            try:
                database = resolve_probe_database(storage)
                normalized = str(database.resolve())
            except (FileNotFoundError, PermissionError, OSError):
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            seen_accounts.add(account_key)
            found.append(database)
    return found


def account_label(database: str | Path) -> str:
    path = Path(database)
    for parent in path.parents:
        if parent.name.lower().startswith("wxid_"):
            return parent.name
    return path.parent.name or path.name


def _active_layout_counterpart(selected_path: str | Path) -> Path | None:
    """Return the v4 app_data path corresponding to a legacy database path."""

    selected = Path(selected_path).expanduser()
    parts = selected.parts
    for index in range(len(parts) - 1):
        if parts[index] != "Documents" or parts[index + 1] != "xwechat_files":
            continue
        return Path(*parts[: index + 1], "app_data", *parts[index + 1 :])
    return None


def _wechat_uses_app_data_layout(wechat_app: str | Path | None) -> bool:
    if not wechat_app:
        return False
    info_plist = Path(wechat_app).expanduser() / "Contents" / "Info.plist"
    try:
        with info_plist.open("rb") as handle:
            payload = plistlib.load(handle)
        version = str(payload.get("CFBundleShortVersionString") or "")
        major = int(version.split(".", 1)[0])
    except (OSError, ValueError, TypeError, plistlib.InvalidFileException):
        return False
    return major >= 4


def prefer_active_probe_database(
    selected_path: str | Path,
    *,
    home: str | Path | None = None,
    wechat_app: str | Path | None = None,
) -> Path:
    """Replace a stale legacy-layout database with the active account copy."""

    # WeChat 4 always writes under Documents/app_data/xwechat_files.  When an
    # updated standalone build temporarily lacks Full Disk Access, pathlib may
    # report that tree as absent even though it is the live database.  Derive
    # the v4 path from a visible legacy duplicate before touching either file;
    # environment inspection will then report the permission error instead of
    # silently validating against an obsolete salt.
    active_counterpart = _active_layout_counterpart(selected_path)
    if active_counterpart is not None and _wechat_uses_app_data_layout(wechat_app):
        return active_counterpart

    selected = resolve_probe_database(selected_path)
    selected_parts = selected.parts
    if any(
        selected_parts[index : index + 3] == ("Documents", "app_data", "xwechat_files")
        for index in range(max(0, len(selected_parts) - 2))
    ):
        return selected
    account = account_label(selected).lower()
    for candidate in discover_default_probe_databases(home=home):
        if account_label(candidate).lower() != account:
            continue
        try:
            if candidate.resolve() == selected.resolve():
                return selected
        except OSError:
            return selected
        # DEFAULT_DATA_RELATIVES is ordered with app_data first and discovery
        # keeps only the first usable database for each wxid.  Reaching this
        # branch means the stored preference points at an older duplicate.
        return candidate
    return selected


def mask_database_key(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return "尚未提取"
    if len(normalized) <= 16:
        return "••••••••"
    return f"{normalized[:8]}……{normalized[-8:]}"


def validate_database_key(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError("提取结果不是有效的 32 字节十六进制数据库密钥")
    return normalized


def merge_fresh_capture_result(
    capture: dict[str, Any],
    captured_key: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Keep capture provenance while returning the newly validated key."""

    key = validate_database_key((captured_key or capture).get("db_key"))
    return {
        **capture,
        "db_key": key,
        "validated": True,
        "fresh_capture": True,
    }


def preferences_path(home: str | Path | None = None) -> Path:
    return app_support_root(home) / "preferences.json"


def load_preferences(home: str | Path | None = None) -> dict[str, str]:
    path = preferences_path(home)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "wechat_app": str(payload.get("wechat_app") or DEFAULT_WECHAT_APP),
        "database_path": str(payload.get("database_path") or ""),
        "work_root": str(payload.get("work_root") or default_work_root(home)),
    }


def save_preferences(payload: dict[str, Any], home: str | Path | None = None) -> Path:
    path = preferences_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(
            {
                "wechat_app": str(payload.get("wechat_app") or DEFAULT_WECHAT_APP),
                "database_path": str(payload.get("database_path") or ""),
                "work_root": str(payload.get("work_root") or default_work_root(home)),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    os.chmod(path, 0o600)
    return path


def inspect_environment(
    wechat_app: str | Path,
    database_path: str | Path,
    work_root: str | Path,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "platform_ok": sys.platform == "darwin",
        "lldb_ok": shutil.which("lldb") is not None,
        "wechat_ok": False,
        "wechat_official": False,
        "database_ok": False,
        "database_plaintext": False,
        "work_root_ok": False,
        "database": "",
        "errors": [],
    }
    if not result["platform_ok"]:
        result["errors"].append("该工具只支持 macOS")
    if not result["lldb_ok"]:
        result["errors"].append("未找到 LLDB，请先运行 xcode-select --install")

    try:
        from wechat_decrypt_tool.macos_db_key_capture import (
            _is_tencent_official_signature,
            inspect_wechat_signature,
            normalize_wechat_app_path,
        )

        normalized_app = normalize_wechat_app_path(wechat_app)
        result["wechat_ok"] = True
        result["wechat_official"] = _is_tencent_official_signature(
            inspect_wechat_signature(normalized_app)
        )
        if not result["wechat_official"]:
            result["errors"].append("微信当前不是腾讯原签名，需先恢复原版微信")
    except Exception as exc:
        result["errors"].append(str(exc))

    try:
        database = prefer_active_probe_database(database_path, wechat_app=wechat_app)
        with database.open("rb") as handle:
            page = handle.read(4096)
        result["database"] = str(database)
        result["database_plaintext"] = page.startswith(b"SQLite format 3")
        result["database_ok"] = len(page) >= 4096 and not result["database_plaintext"]
        if result["database_plaintext"]:
            result["errors"].append("所选数据库已经是明文 SQLite，无需提取密钥")
        elif not result["database_ok"]:
            result["errors"].append("所选文件不是完整的加密微信数据库")
    except Exception as exc:
        result["errors"].append(str(exc))

    try:
        work = Path(work_root).expanduser()
        work.mkdir(parents=True, exist_ok=True)
        probe = work / f".wedata-key-extractor-write-test-{os.getpid()}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        result["work_root_ok"] = True
    except Exception as exc:
        result["errors"].append(f"工作目录不可写: {exc}")
    return result


def discover_cached_key(database_path: str | Path) -> dict[str, Any]:
    from wechat_decrypt_tool.macos_db_key_discovery import discover_macos_db_key

    database = prefer_active_probe_database(database_path)
    return discover_macos_db_key(database)


def prepare_capture(wechat_app: str | Path, work_root: str | Path) -> dict[str, Any]:
    from wechat_decrypt_tool.macos_inplace_capture import prepare_in_place_capture

    return prepare_in_place_capture(
        wechat_app,
        backup_root=default_backup_root(work_root),
        defer_launch=True,
    )


def confirm_manual_launch(wechat_app: str | Path, work_root: str | Path, transaction_id: str) -> dict[str, Any]:
    from wechat_decrypt_tool.macos_inplace_capture import confirm_manual_in_place_launch

    return confirm_manual_in_place_launch(wechat_app, backup_root=default_backup_root(work_root),
                                         transaction_id=transaction_id)


def preflight_capture(wechat_app: str | Path, work_root: str | Path) -> dict[str, Any]:
    from wechat_decrypt_tool.macos_db_key_capture import preflight_prepared_macos_passphrase

    return preflight_prepared_macos_passphrase(
        wechat_app,
        backup_root=default_backup_root(work_root),
    )


def finish_capture(
    wechat_app: str | Path,
    database_path: str | Path,
    work_root: str | Path,
    *,
    timeout: int = 180,
) -> dict[str, Any]:
    from wechat_decrypt_tool.macos_db_key_capture import (
        MacOSDBKeyCaptureFailure,
        capture_prepared_macos_passphrase,
        save_passphrase,
    )
    from wechat_decrypt_tool.wechat_decrypt import validate_realtime_database_key

    database = prefer_active_probe_database(database_path, wechat_app=wechat_app)
    capture = capture_prepared_macos_passphrase(
        wechat_app,
        backup_root=default_backup_root(work_root),
        probe_db_path=database,
        timeout=timeout,
        save_result=False,
    )
    fresh = merge_fresh_capture_result(capture)
    db_storage = next(
        (parent for parent in database.parents if parent.name.lower() == "db_storage"),
        None,
    )
    if db_storage is None:
        raise MacOSDBKeyCaptureFailure(
            "capture_account_database_missing",
            "无法从所选数据库定位账号 db_storage，已拒绝保存捕获值。",
        )
    validation = validate_realtime_database_key(db_storage, fresh["db_key"])
    if validation.get("valid") is not True:
        missing = ",".join(validation.get("required_roles") or ["message", "session"])
        raise MacOSDBKeyCaptureFailure(
            "capture_account_key_mismatch",
            f"捕获值未通过账号消息库与会话库完整校验（{missing}），已拒绝保存。",
        )
    fresh["cache_path"] = str(save_passphrase(fresh["db_key"]))
    fresh["account_roles_validated"] = True
    return fresh


def capture_monitor_ready() -> bool:
    """Whether the native login monitor is armed for the current run."""

    from wechat_decrypt_tool.macos_inplace_capture import native_capture_monitor_ready

    return native_capture_monitor_ready()


def cancel_capture(wechat_app: str | Path, work_root: str | Path) -> dict[str, Any]:
    from wechat_decrypt_tool.macos_db_key_capture import cleanup_macos_passphrase_capture

    return cleanup_macos_passphrase_capture(
        wechat_app,
        backup_root=default_backup_root(work_root),
    )


def capture_is_pending() -> bool:
    from wechat_decrypt_tool.macos_inplace_capture import has_pending_in_place_capture

    return has_pending_in_place_capture()


def capture_status(wechat_app: str | Path | None = None) -> dict[str, Any]:
    """Expose only safe recovery state; recheck an external app before retry UI."""
    from wechat_decrypt_tool.macos_inplace_capture import get_in_place_capture_status

    status = dict(get_in_place_capture_status())
    if status.get("pending") and status.get("stage") in {"external_install_conflict", "recovery_blocked"}:
        from wechat_decrypt_tool.macos_db_key_capture import (
            _is_tencent_official_signature, inspect_wechat_signature, normalize_wechat_app_path,
        )
        try:
            app = normalize_wechat_app_path(wechat_app or DEFAULT_WECHAT_APP)
            official = _is_tencent_official_signature(inspect_wechat_signature(app))
        except Exception:
            official = False
        # This is only an affordance, not restoration authorization: prepare
        # reacquires the installation lock and verifies the live bundle again.
        status["restart_allowed"] = official
        status["stage"] = "external_install_conflict" if official else "recovery_blocked"
    return status
