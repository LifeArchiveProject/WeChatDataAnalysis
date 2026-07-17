from __future__ import annotations

from typing import Any


def normalize_data_source(value: Any, default: str = "auto") -> str:
    text = str(value or "").strip().lower()
    if not text or text == "default":
        return str(default or "auto").strip().lower() or "auto"
    if text in {"local", "sqlite"}:
        return "decrypted"
    if text in {"real-time", "wcdb"}:
        return "realtime"
    return text


def _source_name(value: Any, default: str) -> str:
    return normalize_data_source(value, default)


def humanize_wcdb_failure(reason: Any) -> str:
    raw = str(reason or "").strip()
    lowered = raw.lower()
    if not raw:
        return "WCDB 实时连接暂时不可用"
    if "missing db key" in lowered or "invalid db key" in lowered:
        return "当前账号缺少可用的数据库密钥"
    if "cannot resolve db_storage" in lowered:
        return "无法定位微信 db_storage 数据目录"
    if "session db not found" in lowered or "cannot find session db" in lowered:
        return "找不到微信实时数据库 session.db"
    if "sidecar" in lowered and ("unavailable" in lowered or "exited" in lowered):
        return "WCDB 辅助进程暂时不可用"
    if "timed out" in lowered or "timeout" in lowered:
        return "WCDB 实时连接超时"
    if "open_account" in lowered or "open account" in lowered:
        return "WCDB 无法打开当前账号的实时数据库"
    if "recently failed" in lowered:
        return "WCDB 实时连接刚刚失败"
    return raw[:240]


def build_source_fallback_meta(
    *,
    requested_source: Any,
    active_source: Any,
    reason: Any = "",
    retry_after_seconds: Any = 0,
) -> dict[str, Any]:
    requested = _source_name(requested_source, "auto")
    active = _source_name(active_source, "decrypted")
    raw_reason = str(reason or "").strip()
    try:
        retry_after = max(0, int(retry_after_seconds or 0))
    except Exception:
        retry_after = 0

    fallback_active = bool(
        active == "decrypted"
        and requested in {"auto", "realtime"}
        and raw_reason
    )
    message = ""
    if fallback_active:
        message = (
            f"实时更新暂时不可用：{humanize_wcdb_failure(raw_reason)}。"
            "当前显示已解密数据库快照，期间的新消息不会自动更新。"
        )
        if retry_after > 0:
            message += f" 约 {retry_after} 秒后可再次尝试实时连接。"

    return {
        "sourceRequested": requested,
        "sourceFallback": fallback_active,
        "sourceFallbackReason": raw_reason if fallback_active else "",
        "sourceFallbackMessage": message,
        "sourceFallbackRetryAfterSeconds": retry_after if fallback_active else 0,
    }
