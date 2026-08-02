from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _reset_test_file_logging() -> None:
    loggers = [logging.getLogger()]
    loggers.extend(
        logger
        for logger in logging.Logger.manager.loggerDict.values()
        if isinstance(logger, logging.Logger)
    )
    closed: set[int] = set()
    for logger in loggers:
        for handler in list(logger.handlers):
            if not isinstance(handler, logging.FileHandler):
                continue
            logger.removeHandler(handler)
            if id(handler) in closed:
                continue
            closed.add(id(handler))
            handler.close()

    try:
        from wechat_decrypt_tool.logging_config import WeChatLogger

        WeChatLogger._initialized = False
    except ImportError:
        pass


def _suppress_implicit_test_file_logging() -> None:
    _reset_test_file_logging()
    from wechat_decrypt_tool.logging_config import WeChatLogger

    WeChatLogger._initialized = True


@pytest.fixture(autouse=True)
def _native_core_source_entrypoint_context(monkeypatch: pytest.MonkeyPatch):
    """Mirror the source entrypoint contract for tests that call services directly."""

    monkeypatch.setenv("WECHAT_TOOL_NATIVE_CORE_MODE", "required")
    monkeypatch.setenv("WECHAT_TOOL_NATIVE_CORE_ALLOW_DEVELOPMENT_BUILD", "1")
    _suppress_implicit_test_file_logging()
    yield

    from wechat_decrypt_tool import native_core_broker, native_core_dev_lease
    from wechat_decrypt_tool.native_core_client import close_native_core_client

    native_core_broker.stop_native_core_broker(_force=True)
    close_native_core_client()
    native_core_dev_lease._cleanup()
    _reset_test_file_logging()
