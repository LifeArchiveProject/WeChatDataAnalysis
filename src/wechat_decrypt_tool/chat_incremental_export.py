from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


STATE_FILE_NAME = ".wechat-chat-export.json"
SCHEMA_VERSION = 1
ARTIFACT_TYPE = "wechat-chat-incremental-folder"
PENDING_MEDIA_STATES = {
    "unclassified",
    "recoverable_local",
    "recoverable_remote",
    "retryable",
    "source_unavailable",
    "decrypt_blocked",
    "unsupported",
}


class ChatIncrementalError(ValueError):
    """聊天增量目录无法安全继续更新。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = str(code or "incremental_error")


def _safe_component(value: Any, *, fallback: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    if not text:
        text = fallback
    return text[:96].rstrip(" .") or fallback


def normalize_relative_path(value: Any) -> str:
    text = str(value or "").replace("\\", "/").lstrip("/")
    parts = [part for part in text.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        return ""
    return "/".join(parts)


def _require_managed_path(value: Any) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    normalized = normalize_relative_path(raw)
    if (
        not normalized
        or raw.startswith("/")
        or raw != normalized
        or ":" in normalized.split("/", 1)[0]
        or "\x00" in raw
    ):
        raise ChatIncrementalError("incremental_unsafe_path", "增量基线包含不安全的文件路径。")
    return normalized


def _validate_baseline_paths(value: dict[str, Any]) -> None:
    files = value.get("files") if isinstance(value.get("files"), dict) else {}
    for path, metadata in files.items():
        _require_managed_path(path)
        if not isinstance(metadata, dict):
            raise ChatIncrementalError("incremental_baseline_invalid", "增量基线文件摘要损坏，请选择新目录。")
        digest = str(metadata.get("sha256") or "")
        try:
            size = int(metadata.get("size"))
        except Exception as exc:
            raise ChatIncrementalError("incremental_baseline_invalid", "增量基线文件摘要损坏，请选择新目录。") from exc
        if size < 0 or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ChatIncrementalError("incremental_baseline_invalid", "增量基线文件摘要损坏，请选择新目录。")
    conversations = value.get("conversations") if isinstance(value.get("conversations"), dict) else {}
    for state in conversations.values():
        if not isinstance(state, dict):
            raise ChatIncrementalError("incremental_baseline_invalid", "增量基线会话信息损坏，请选择新目录。")
        directory = _require_managed_path(state.get("directory"))
        if not directory.startswith("conversations/"):
            raise ChatIncrementalError("incremental_unsafe_path", "增量基线包含不安全的会话目录。")
        managed_files = state.get("managedFiles") or []
        if not isinstance(managed_files, list):
            raise ChatIncrementalError("incremental_baseline_invalid", "增量基线会话信息损坏，请选择新目录。")
        for path in managed_files:
            _require_managed_path(path)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def build_config(
    *,
    export_format: str,
    start_time: Optional[int],
    end_time: Optional[int],
    message_types: list[str],
    include_media: bool,
    media_kinds: list[str],
    download_remote_media: bool,
    html_page_size: int,
    privacy_mode: bool,
    transcribe_voice: bool,
) -> dict[str, Any]:
    return {
        "format": str(export_format or "").strip().lower(),
        "startTime": int(start_time) if start_time is not None else None,
        "endTime": int(end_time) if end_time is not None else None,
        "messageTypes": sorted({str(item or "").strip() for item in message_types if str(item or "").strip()}),
        "includeMedia": bool(include_media),
        "mediaKinds": sorted({str(item or "").strip() for item in media_kinds if str(item or "").strip()}),
        "downloadRemoteMedia": bool(download_remote_media),
        "htmlPageSize": int(html_page_size) if str(export_format or "").lower() == "html" else None,
        "privacyMode": bool(privacy_mode),
        "transcribeVoice": bool(transcribe_voice),
    }


def config_fingerprint(config: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(config)).hexdigest()


def conversation_key(*, salt: str, username: str) -> str:
    payload = f"{str(salt or '')}\0{str(username or '')}".encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()


def account_fingerprint(account: str) -> str:
    return hashlib.sha256(str(account or "").encode("utf-8", errors="replace")).hexdigest()


def privacy_account_token(account: str) -> str:
    """生成与浏览器端一致的短标识，避免隐私目录名包含账号明文。"""

    value = 0x811C9DC5
    raw = str(account or "").encode("utf-16-le", errors="surrogatepass")
    for index in range(0, len(raw), 2):
        unit = raw[index] | (raw[index + 1] << 8)
        value ^= unit
        value = (value * 0x01000193) & 0xFFFFFFFF
    return f"{value:08x}"


def allocate_conversation_directory(
    *,
    old_state: dict[str, Any],
    key: str,
    display_name: str,
    privacy_mode: bool,
) -> str:
    conversations = old_state.get("conversations") if isinstance(old_state.get("conversations"), dict) else {}
    old = conversations.get(key) if isinstance(conversations.get(key), dict) else {}
    existing = normalize_relative_path(old.get("directory"))
    if existing and existing.startswith("conversations/"):
        return existing
    stem = "conversation" if privacy_mode else _safe_component(display_name, fallback="conversation")
    return f"conversations/{stem}_{key[:10]}"


def normalize_pending_media(
    values: Any,
    *,
    default_state: str = "unclassified",
    default_reason: str = "",
) -> list[dict[str, Any]]:
    """按媒体唯一标识合并待补项，同时保留受影响消息引用数。"""

    state_default = str(default_state or "unclassified").strip()
    if state_default not in PENDING_MEDIA_STATES:
        state_default = "unclassified"
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in values if isinstance(values, list) else []:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or "").strip().lower()
        ident = str(raw.get("id") or "").strip()
        if not kind or not ident:
            continue
        key = (kind, ident)
        try:
            occurrences = max(1, int(raw.get("occurrenceCount") or 1))
        except Exception:
            occurrences = 1
        state = str(raw.get("state") or state_default).strip()
        if state not in PENDING_MEDIA_STATES:
            state = state_default
        repairable = bool(raw.get("repairable")) or state in {"recoverable_local", "recoverable_remote"}
        reason_code = str(raw.get("reasonCode") or default_reason or "").strip()
        existing = grouped.get(key)
        if existing is None:
            existing = {
                "kind": kind,
                "id": ident,
                "occurrenceCount": occurrences,
                "state": state,
                "reasonCode": reason_code,
                "repairable": repairable,
            }
            message_id = str(raw.get("messageId") or "").strip()
            if message_id:
                existing["messageId"] = message_id
            grouped[key] = existing
            continue
        existing["occurrenceCount"] = int(existing.get("occurrenceCount") or 0) + occurrences
        # 只要任一来源已确认可恢复，就不能被另一个旧的不可用记录覆盖。
        if repairable and not bool(existing.get("repairable")):
            existing["state"] = state
            existing["reasonCode"] = reason_code
            existing["repairable"] = True
    return [grouped[key] for key in sorted(grouped)]


def summarize_pending_media(conversations: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """汇总唯一缺失媒体和消息引用数，避免把重复表情误报成多个文件。"""

    unique: dict[tuple[str, str], dict[str, Any]] = {}
    by_kind: dict[str, dict[str, int]] = {}
    for state in conversations.values():
        if not isinstance(state, dict):
            continue
        for item in normalize_pending_media(state.get("pendingMedia") or []):
            if bool(item.get("repairable")):
                continue
            kind = str(item.get("kind") or "")
            ident = str(item.get("id") or "")
            key = (kind, ident)
            references = max(1, int(item.get("occurrenceCount") or 1))
            bucket = by_kind.setdefault(kind, {"uniqueCount": 0, "referenceCount": 0})
            bucket["referenceCount"] += references
            if key not in unique:
                unique[key] = dict(item)
                bucket["uniqueCount"] += 1
            else:
                unique[key]["occurrenceCount"] = int(unique[key].get("occurrenceCount") or 0) + references
    return {
        "uniqueCount": len(unique),
        "referenceCount": sum(int(item.get("occurrenceCount") or 0) for item in unique.values()),
        "byKind": by_kind,
    }


@dataclass
class ChatFolderContext:
    account: str
    folder_name: str
    config: dict[str, Any]
    config_hash: str
    privacy_mode: bool
    desktop_output: bool
    exports_root: Path
    target_root: Optional[Path]
    old_state: dict[str, Any]
    salt: str
    missing_files: set[str] = field(default_factory=set)
    reset_baseline: bool = False
    selected_keys: set[str] = field(default_factory=set)
    current_conversations: dict[str, dict[str, Any]] = field(default_factory=dict)
    repair_candidates: list[dict[str, Any]] = field(default_factory=list)
    history_synced: list[dict[str, Any]] = field(default_factory=list)
    unresolved_media_conversations: list[dict[str, Any]] = field(default_factory=list)
    unresolved_missing_owner_keys: set[str] = field(default_factory=set)
    metadata_changed: bool = False

    @property
    def export_runtime_id(self) -> str:
        return str(self.old_state.get("runtimeId") or hashlib.sha256(self.salt.encode("utf-8")).hexdigest()[:12])


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ChatIncrementalError("incremental_baseline_invalid", "增量基线损坏，请选择新目录。") from exc
    if not isinstance(value, dict):
        raise ChatIncrementalError("incremental_baseline_invalid", "增量基线损坏，请选择新目录。")
    return value


def _baseline_is_owned(value: dict[str, Any]) -> bool:
    return (
        int(value.get("schemaVersion") or 0) == SCHEMA_VERSION
        and str(value.get("artifactType") or "") == ARTIFACT_TYPE
        and isinstance(value.get("conversations"), dict)
        and isinstance(value.get("files"), dict)
    )


def _directory_has_user_files(path: Path) -> bool:
    try:
        return path.is_dir() and any(path.iterdir())
    except Exception:
        # 无法检查时按非空处理，避免在未知目录中覆盖用户文件。
        return True


def prepare_folder_context(
    *,
    account: str,
    exports_root: Path,
    requested_folder_name: str,
    config: dict[str, Any],
    privacy_mode: bool,
    desktop_output: bool,
    supplied_baseline: Optional[dict[str, Any]],
    missing_files: list[str],
    reset_baseline: bool,
) -> ChatFolderContext:
    folder_name = _safe_component(
        requested_folder_name or f"微信聊天记录_{account}",
        fallback="微信聊天记录",
    )
    if privacy_mode:
        folder_name = f"微信聊天记录_隐私_{privacy_account_token(account)}"
    exports_root = Path(exports_root).resolve()
    nested_root = (exports_root / folder_name).resolve()
    direct_state_path = exports_root / STATE_FILE_NAME
    direct_state: dict[str, Any] = {}
    if desktop_output and direct_state_path.is_file():
        direct_state = _read_json_file(direct_state_path)

    direct_matches = bool(
        exports_root.name == folder_name
        or (
            direct_state
            and str(direct_state.get("artifactType") or "") == ARTIFACT_TYPE
            and (
                str(direct_state.get("account") or "") == str(account or "")
                or str(direct_state.get("accountFingerprint") or "") == account_fingerprint(account)
            )
        )
    )
    target_root = exports_root if desktop_output and direct_matches else (nested_root if desktop_output else None)

    old_state: dict[str, Any] = {}
    if desktop_output and target_root is not None:
        disk_state_path = target_root / STATE_FILE_NAME
        if disk_state_path.is_file():
            old_state = direct_state if disk_state_path == direct_state_path and direct_state else _read_json_file(disk_state_path)
    elif isinstance(supplied_baseline, dict):
        old_state = dict(supplied_baseline)

    owned = bool(old_state and _baseline_is_owned(old_state))
    if old_state and not owned:
        raise ChatIncrementalError("incremental_baseline_invalid", "增量基线损坏或不属于聊天导出，请选择新目录。")
    if owned:
        _validate_baseline_paths(old_state)

    desired_hash = config_fingerprint(config)
    if owned:
        baseline_account = str(old_state.get("account") or "")
        baseline_account_fingerprint = str(old_state.get("accountFingerprint") or "")
        account_matches = (
            baseline_account == str(account or "")
            if baseline_account
            else baseline_account_fingerprint == account_fingerprint(account)
        )
        if not account_matches:
            raise ChatIncrementalError("incremental_account_mismatch", "该增量目录属于其他微信账号，请选择新目录。")
        if str(old_state.get("configFingerprint") or "") != desired_hash and not reset_baseline:
            raise ChatIncrementalError(
                "incremental_config_mismatch",
                "导出格式或筛选配置与该增量目录不一致，请选择新目录或重置后完整重建。",
            )

    if reset_baseline:
        if old_state and not owned:
            raise ChatIncrementalError("incremental_baseline_invalid", "无法安全重置损坏的增量目录，请选择空目录。")
        if not owned and desktop_output and target_root is not None and _directory_has_user_files(target_root):
            raise ChatIncrementalError(
                "incremental_directory_not_empty",
                "无法重置来源不明的非空目录，请选择新目录。",
            )
        old_state = {} if not owned else old_state
    elif not old_state and desktop_output and target_root is not None and _directory_has_user_files(target_root):
        raise ChatIncrementalError(
            "incremental_directory_not_empty",
            "所选目录非空且没有可识别的聊天增量基线，请选择其父目录或一个空目录。",
        )

    salt = str(old_state.get("conversationSalt") or uuid.uuid4().hex)
    missing = {_require_managed_path(raw) for raw in missing_files}
    if owned and desktop_output and target_root is not None:
        managed_files = old_state.get("files") if isinstance(old_state.get("files"), dict) else {}
        for raw_path, metadata in managed_files.items():
            path = _require_managed_path(raw_path)
            destination = (target_root / Path(*path.split("/"))).resolve()
            if target_root not in destination.parents or not destination.is_file():
                missing.add(path)
                continue
            try:
                expected_size = int((metadata or {}).get("size"))
            except Exception:
                expected_size = -1
            if expected_size >= 0 and destination.stat().st_size != expected_size:
                missing.add(path)
    return ChatFolderContext(
        account=str(account or ""),
        folder_name=str(old_state.get("folderName") or folder_name),
        config=dict(config),
        config_hash=desired_hash,
        privacy_mode=bool(privacy_mode),
        desktop_output=bool(desktop_output),
        exports_root=exports_root,
        target_root=target_root,
        old_state=old_state,
        salt=salt,
        missing_files=missing,
        reset_baseline=bool(reset_baseline),
    )


def missing_conversation_keys(
    context: ChatFolderContext,
    *,
    preferred_keys: Optional[set[str]] = None,
) -> set[str]:
    """把全部缺失受管理文件反向映射到需要重建的会话。"""

    missing = set(context.missing_files)
    if not missing:
        return set()

    conversations = (
        context.old_state.get("conversations")
        if isinstance(context.old_state.get("conversations"), dict)
        else {}
    )
    files = (
        context.old_state.get("files")
        if isinstance(context.old_state.get("files"), dict)
        else {}
    )
    result: set[str] = set()
    preferred = {str(key or "") for key in (preferred_keys or set())}

    for raw_key, raw_state in conversations.items():
        if not isinstance(raw_state, dict):
            continue
        key = str(raw_key or "")
        managed = {
            normalize_relative_path(path)
            for path in (raw_state.get("managedFiles") or [])
        }
        directory = normalize_relative_path(raw_state.get("directory"))
        if managed & missing or any(
            directory and (path == directory or path.startswith(directory + "/"))
            for path in missing
        ):
            result.add(key)

    known_keys = {str(key or "") for key in conversations}
    for path in missing:
        if not _is_owned_resource_path(path):
            continue
        metadata = files.get(path) if isinstance(files.get(path), dict) else {}
        owners = {
            str(owner or "")
            for owner in (metadata.get("owners") or [])
            if str(owner or "") in known_keys
        }
        if owners:
            # 共享资源只需一个所有者重新物化；优先复用已经需要重建或本次已选择的会话。
            candidates = owners & result
            if not candidates:
                candidates = owners & preferred
            result.add(sorted(candidates or owners)[0])
        else:
            # 老基线若没有资源归属信息，保守重建全部会话，避免缺失媒体永久无法补回。
            result.update(known_keys)
    return result


def _safe_archive_infos(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    result: dict[str, zipfile.ZipInfo] = {}
    for info in archive.infolist():
        if info.is_dir():
            continue
        path = normalize_relative_path(info.filename)
        if path:
            result[path] = info
    return result


def _file_meta(payload: bytes, *, owners: Optional[list[str]] = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size": len(payload),
    }
    if owners:
        result["owners"] = sorted(set(owners))
    return result


def _resource_search_payload(payload: bytes, path: str) -> bytes:
    """Excel 文件本身是 ZIP，需要展开 XML 后才能识别其中的资源引用。"""

    if not str(path or "").lower().endswith(".xlsx"):
        return payload
    try:
        with zipfile.ZipFile(io.BytesIO(payload), "r") as workbook:
            return b"\n".join(
                workbook.read(info)
                for info in workbook.infolist()
                if not info.is_dir() and info.filename.lower().endswith((".xml", ".rels"))
            )
    except Exception:
        return payload


def _is_owned_resource_path(path: str) -> bool:
    return str(path or "").startswith(("media/", "avatars/"))


def _is_conversation_path(path: str) -> bool:
    return str(path or "").startswith("conversations/")


def _conversation_owner(path: str, conversations: dict[str, dict[str, Any]]) -> str:
    for key, state in conversations.items():
        directory = normalize_relative_path(state.get("directory"))
        if directory and (path == directory or path.startswith(directory + "/")):
            return key
    return ""


def _write_staged_file(staging_dir: Path, relative: str, payload: bytes) -> Path:
    destination = (staging_dir / Path(*relative.split("/"))).resolve()
    if staging_dir not in destination.parents:
        raise ChatIncrementalError("incremental_unsafe_path", "增量文件路径不安全。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return destination


def materialize_folder_archive(
    *,
    job: Any,
    archive_path: Path,
    context: ChatFolderContext,
) -> Path:
    staging_dir = Path(
        tempfile.mkdtemp(
            prefix=f".chat-folder-{job.export_id}-",
            dir=str(context.exports_root),
        )
    ).resolve()
    job.staging_dir = staging_dir

    old_files = context.old_state.get("files") if isinstance(context.old_state.get("files"), dict) else {}
    old_conversations = context.old_state.get("conversations") if isinstance(context.old_state.get("conversations"), dict) else {}
    conversations: dict[str, dict[str, Any]] = {} if context.reset_baseline else {
        str(key): dict(value)
        for key, value in old_conversations.items()
        if isinstance(value, dict)
    }
    conversations.update({str(key): dict(value) for key, value in context.current_conversations.items()})

    current_files: dict[str, Any] = {} if context.reset_baseline else {
        str(path): dict(meta)
        for path, meta in old_files.items()
        if normalize_relative_path(path) == str(path) and isinstance(meta, dict)
    }
    selected_old_managed: set[str] = set()
    rendered_keys = {
        key for key, state in context.current_conversations.items() if bool(state.get("rendered"))
    }
    append_keys = {
        key for key, state in context.current_conversations.items()
        if bool(state.get("rendered")) and bool(state.get("appendOnly"))
    }
    replaced_keys = rendered_keys - append_keys
    for key in replaced_keys:
        old = old_conversations.get(key) if isinstance(old_conversations.get(key), dict) else {}
        selected_old_managed.update(
            path
            for raw in (old.get("managedFiles") or [])
            if (path := normalize_relative_path(raw))
        )
    for path in selected_old_managed:
        current_files.pop(path, None)

    # 先撤销本轮重建会话对旧共享资源的引用；稍后再按新产物重新建立归属。
    for path, meta in list(current_files.items()):
        if not _is_owned_resource_path(path) or not isinstance(meta.get("owners"), list):
            continue
        meta["owners"] = sorted({str(owner) for owner in meta.get("owners") or []} - replaced_keys)

    quiet_noop = bool(
        context.old_state
        and not context.reset_baseline
        and not rendered_keys
        and not context.repair_candidates
        and not context.history_synced
        and not context.missing_files
        and not context.metadata_changed
    )
    preserve_dynamic_indexes = bool(
        context.old_state
        and not context.reset_baseline
        and not rendered_keys
        and not context.missing_files
    )
    staged_entries: list[dict[str, Any]] = []
    staged_payloads: dict[str, bytes] = {}
    new_managed: dict[str, set[str]] = {
        key: {
            path
            for raw in (
                (old_conversations.get(key) or {}).get("managedFiles")
                if isinstance(old_conversations.get(key), dict)
                else []
            ) or []
            if (path := normalize_relative_path(raw))
        }
        if key in append_keys
        else set()
        for key in rendered_keys
    }
    with zipfile.ZipFile(archive_path, "r") as archive:
        infos = _safe_archive_infos(archive)
        owner_search_payloads: dict[str, list[bytes]] = {key: [] for key in rendered_keys}
        for path, info in infos.items():
            if not _is_conversation_path(path):
                continue
            owner = _conversation_owner(path, context.current_conversations)
            if not owner or owner not in rendered_keys:
                continue
            payload = archive.read(info)
            owner_search_payloads.setdefault(owner, []).append(_resource_search_payload(payload, path))

        for path, info in infos.items():
            if path in {"manifest.json", "report.json"} or path.startswith("_integrity/"):
                continue
            owner = _conversation_owner(path, context.current_conversations)
            if _is_conversation_path(path):
                if not owner or owner not in rendered_keys:
                    continue
                new_managed.setdefault(owner, set()).add(path)
            payload = archive.read(info)
            if _is_owned_resource_path(path):
                path_bytes = path.encode("utf-8", errors="replace")
                referenced_by = {
                    key
                    for key, search_payloads in owner_search_payloads.items()
                    if any(path_bytes in search_payload for search_payload in search_payloads)
                }
                explicit_owners = (getattr(job, "options", {}) or {}).get("_folderResourceOwners") or {}
                for username in explicit_owners.get(path, []) if isinstance(explicit_owners, dict) else []:
                    key = conversation_key(salt=context.salt, username=str(username or ""))
                    if key in rendered_keys:
                        referenced_by.add(key)
                previous_current = current_files.get(path) if isinstance(current_files.get(path), dict) else {}
                owners = sorted(
                    {
                        str(value)
                        for value in (previous_current.get("owners") or [])
                        if str(value or "")
                    }
                    | referenced_by
                )
            else:
                owners = [owner] if owner else []
            meta = _file_meta(payload, owners=owners)
            previous = old_files.get(path) if isinstance(old_files.get(path), dict) else {}
            current_files[path] = meta
            missing = path in context.missing_files
            if preserve_dynamic_indexes and not missing and path in {"index.html", "index.xlsx"} and path in old_files:
                current_files[path] = dict(previous)
                continue
            if (
                not context.reset_baseline
                and not missing
                and str(previous.get("sha256") or "") == meta["sha256"]
                and int(previous.get("size") or -1) == meta["size"]
                and (
                    context.target_root is None
                    or (context.target_root / Path(*path.split("/"))).is_file()
                )
            ):
                continue
            staged_payloads[path] = payload

    # 只有旧基线明确记录过归属的资源，才会在最后一个会话解除引用后被清理。
    for path, meta in list(current_files.items()):
        previous = old_files.get(path) if isinstance(old_files.get(path), dict) else {}
        if (
            _is_owned_resource_path(path)
            and isinstance(previous.get("owners"), list)
            and not list(meta.get("owners") or [])
        ):
            current_files.pop(path, None)
            staged_payloads.pop(path, None)

    for key in rendered_keys:
        state = conversations.get(key) or {}
        state["managedFiles"] = sorted(new_managed.get(key) or [])
        conversations[key] = state

    generated_at = datetime.now().isoformat(timespec="seconds")
    unresolved_media = summarize_pending_media(conversations)
    unresolved_conversations: list[dict[str, Any]] = []
    for raw in context.unresolved_media_conversations:
        key = str(raw.get("conversationKey") or "")
        state = conversations.get(key) if isinstance(conversations.get(key), dict) else {}
        pending = [
            item
            for item in normalize_pending_media(state.get("pendingMedia") or [])
            if not bool(item.get("repairable"))
        ]
        if not pending:
            continue
        unresolved_conversations.append(
            {
                **dict(raw),
                "uniqueCount": len(pending),
                "referenceCount": sum(
                    max(1, int(item.get("occurrenceCount") or 1)) for item in pending
                ),
            }
        )
    manifest = {
        "schemaVersion": 1,
        "artifactType": ARTIFACT_TYPE,
        "account": "hidden" if context.privacy_mode else context.account,
        "format": context.config.get("format"),
        "folderName": context.folder_name,
        "updatedAt": generated_at,
        "stats": {
            "conversations": len(conversations),
            "repairPending": len(context.repair_candidates),
            "unresolvedMedia": int(unresolved_media.get("uniqueCount") or 0),
            "unresolvedMediaReferences": int(unresolved_media.get("referenceCount") or 0),
        },
    }
    persisted_repairs = [dict(item) for item in context.repair_candidates]
    persisted_history = [dict(item) for item in context.history_synced]
    if context.privacy_mode:
        for item in [*persisted_repairs, *persisted_history]:
            item["username"] = ""
            item["displayName"] = ""
    report = {
        "schemaVersion": 1,
        "updatedAt": manifest["updatedAt"],
        "repairCandidates": persisted_repairs,
        "historyChangesSynced": persisted_history,
        "unresolvedMedia": unresolved_media,
    }
    for path, payload in {
        "manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        "report.json": json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"),
    }.items():
        if quiet_noop and path in old_files:
            current_files[path] = dict(old_files[path])
            continue
        meta = _file_meta(payload)
        previous = old_files.get(path) if isinstance(old_files.get(path), dict) else {}
        current_files[path] = meta
        if (
            context.reset_baseline
            or str(previous.get("sha256") or "") != meta["sha256"]
            or int(previous.get("size") or -1) != meta["size"]
            or context.target_root is None
            or not (context.target_root / path).is_file()
        ):
            staged_payloads[path] = payload

    old_managed = set(old_files)
    stale = sorted(
        path
        for path in old_managed - set(current_files)
        if normalize_relative_path(path) == path
    )
    # 全局运行时升级也属于真实变更，必须最后更新基线，避免下次重复迁移。
    quiet_noop = quiet_noop and not staged_payloads and not stale

    for path, payload in sorted(staged_payloads.items()):
        staged_path = _write_staged_file(staging_dir, path, payload)
        file_id = uuid.uuid4().hex
        job.staged_files[file_id] = staged_path
        meta = current_files[path]
        staged_entries.append(
            {
                "fileId": file_id,
                "path": path,
                "size": int(meta.get("size") or 0),
                "sha256": str(meta.get("sha256") or ""),
            }
        )

    persisted_conversations: dict[str, dict[str, Any]] = {}
    for key, value in conversations.items():
        cleaned = {
            field_name: field_value
            for field_name, field_value in value.items()
            if field_name not in {"rendered", "appendOnly", "newMessageCount"}
        }
        persisted_conversations[key] = cleaned

    state = {
        "schemaVersion": SCHEMA_VERSION,
        "artifactType": ARTIFACT_TYPE,
        "account": "" if context.privacy_mode else context.account,
        "accountFingerprint": account_fingerprint(context.account),
        "folderName": context.folder_name,
        "runtimeId": context.export_runtime_id,
        "conversationSalt": context.salt,
        "config": context.config,
        "configFingerprint": context.config_hash,
        "updatedAt": (
            str(context.old_state.get("updatedAt") or generated_at)
            if quiet_noop
            else generated_at
        ),
        "conversations": persisted_conversations,
        "files": current_files,
    }
    state_bytes = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    state_path = _write_staged_file(staging_dir, STATE_FILE_NAME, state_bytes)
    state_file_id = uuid.uuid4().hex
    job.staged_files[state_file_id] = state_path

    updated_count = len(rendered_keys)
    reused_count = max(0, len(context.selected_keys) - updated_count)
    appended = sum(max(0, int(item.get("newMessageCount") or 0)) for item in context.current_conversations.values())
    recovered_count = sum(1 for entry in staged_entries if str(entry.get("path") or "") in context.missing_files)
    job.incremental = {
        "messagesAdded": appended,
        "conversationsUpdated": updated_count,
        "conversationsReused": reused_count,
        "conversationsRepairPending": len(context.repair_candidates),
        "historyChangesSynced": len(context.history_synced),
        "filesChanged": len(staged_entries),
        "filesReused": max(0, len(current_files) - len(staged_entries)),
        "filesRemoved": len(stale),
        "filesRecovered": recovered_count,
    }
    job.repair_candidates = list(context.repair_candidates)
    job.unresolved_media = {
        **unresolved_media,
        "conversations": unresolved_conversations,
    }
    job.change_manifest = {
        "folderName": context.folder_name,
        "files": staged_entries,
        "stale": stale,
        "state": {
            "fileId": state_file_id,
            "path": STATE_FILE_NAME,
            "size": len(state_bytes),
            "sha256": hashlib.sha256(state_bytes).hexdigest(),
            "unchanged": quiet_noop,
        },
        "stats": dict(job.incremental),
    }

    if not context.desktop_output:
        return staging_dir

    target_root = context.target_root
    if target_root is None:
        raise ChatIncrementalError("incremental_target_missing", "增量目录不可用。")
    target_root.mkdir(parents=True, exist_ok=True)
    for entry in staged_entries:
        source = job.staged_files[str(entry["fileId"])]
        relative = normalize_relative_path(entry["path"])
        destination = (target_root / Path(*relative.split("/"))).resolve()
        if target_root not in destination.parents:
            raise ChatIncrementalError("incremental_unsafe_path", "增量文件路径不安全。")
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, destination)

    # 只清理由旧基线明确管理、且本轮已经失效的文件。
    for relative in stale:
        destination = (target_root / Path(*relative.split("/"))).resolve()
        if target_root not in destination.parents or not destination.is_file():
            continue
        destination.unlink(missing_ok=True)

    state_destination = target_root / STATE_FILE_NAME
    if not quiet_noop or not state_destination.is_file():
        os.replace(state_path, state_destination)
    job.folder_path = target_root
    job.staged_files = {}
    shutil.rmtree(staging_dir, ignore_errors=True)
    job.staging_dir = None
    return target_root


__all__ = [
    "ARTIFACT_TYPE",
    "ChatFolderContext",
    "ChatIncrementalError",
    "SCHEMA_VERSION",
    "STATE_FILE_NAME",
    "account_fingerprint",
    "allocate_conversation_directory",
    "build_config",
    "config_fingerprint",
    "conversation_key",
    "materialize_folder_archive",
    "missing_conversation_keys",
    "normalize_pending_media",
    "normalize_relative_path",
    "prepare_folder_context",
    "privacy_account_token",
    "summarize_pending_media",
]
