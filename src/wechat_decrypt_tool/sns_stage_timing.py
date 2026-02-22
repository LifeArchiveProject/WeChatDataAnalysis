import re
from collections.abc import MutableMapping


def add_sns_stage_timing_headers(
    headers: MutableMapping[str, str],
    *,
    source: str,
    hit_type: str = "",
    x_enc: str = "",
) -> None:
    """Inject `Server-Timing` + `Timing-Allow-Origin` for SNS media stage inspection.

    The frontend can't read `<img>` response headers, but browsers expose `Server-Timing` metrics
    via `performance.getEntriesByName(...).serverTiming` when `Timing-Allow-Origin` allows it.

    This helper is intentionally side-effect free beyond mutating `headers`.
    """

    src = str(source or "").strip()
    if not src:
        return

    ht = str(hit_type or "").strip()
    xe = str(x_enc or "").strip()

    if "Timing-Allow-Origin" not in headers:
        headers["Timing-Allow-Origin"] = "*"

    def _esc(v: str) -> str:
        return v.replace("\\", "\\\\").replace('"', '\\"')

    def _token(v: str) -> str:
        raw = str(v or "").strip()
        if not raw:
            return ""
        raw = raw.replace(" ", "_")
        safe = re.sub(r"[^0-9A-Za-z_.-]+", "_", raw).strip("_")
        if not safe:
            return ""
        return safe[:64]

    parts: list[str] = []
    src_tok = _token(src) or "unknown"
    parts.append(f'sns_source_{src_tok};dur=0;desc="{_esc(src)}"')
    if ht:
        ht_tok = _token(ht)
        if ht_tok:
            parts.append(f'sns_hit_{ht_tok};dur=0;desc="{_esc(ht)}"')
    if xe:
        xe_tok = _token(xe)
        if xe_tok:
            parts.append(f'sns_xenc_{xe_tok};dur=0;desc="{_esc(xe)}"')

    existing = str(headers.get("Server-Timing") or "").strip()
    # Some responses may already have upstream `Server-Timing` metrics. Always append ours so
    # the frontend can consistently read `sns_source_*` via ResourceTiming.serverTiming.
    if existing and re.search(r"(^|,\\s*)sns_source(_|;)", existing):
        return

    combined = ", ".join(parts)
    headers["Server-Timing"] = f"{existing}, {combined}" if existing else combined

