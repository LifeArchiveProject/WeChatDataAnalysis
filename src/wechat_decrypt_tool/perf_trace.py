from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable


def create_perf_trace(logger: Any, category: str, **base_fields: Any) -> tuple[str, Callable[[str], None]]:
    trace_id = f"{category}-{int(time.time() * 1000)}-{threading.get_ident()}"
    started_at = time.perf_counter()
    last_at = started_at

    def log(phase: str, **fields: Any) -> None:
        nonlocal last_at
        now = time.perf_counter()
        payload = {
            **base_fields,
            **fields,
            "elapsedMs": round((now - started_at) * 1000.0, 1),
            "deltaMs": round((now - last_at) * 1000.0, 1),
        }
        last_at = now
        try:
            payload_text = json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:
            payload_text = str(payload)
        logger.info("[%s] %s %s %s", trace_id, category, phase, payload_text)

    return trace_id, log
