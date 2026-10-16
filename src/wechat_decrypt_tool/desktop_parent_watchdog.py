from __future__ import annotations

import os
import threading
from collections.abc import Callable, Mapping
from typing import Protocol

import psutil

DESKTOP_PARENT_PID_ENV = "WECHAT_TOOL_DESKTOP_PARENT_PID"


class _WaitableProcess(Protocol):
    def wait(self, timeout: float | None = None) -> int | None: ...


def _wait_for_parent_exit(
    parent: _WaitableProcess,
    exit_process: Callable[[int], object],
) -> None:
    try:
        parent.wait()
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        pass
    except psutil.Error:
        exit_process(70)
        return
    exit_process(0)


def start_desktop_parent_watchdog_from_env(
    *,
    env: Mapping[str, str] | None = None,
    process_factory: Callable[[int], _WaitableProcess] | None = None,
    exit_process: Callable[[int], object] | None = None,
) -> threading.Thread | None:
    source = os.environ if env is None else env
    raw_pid = str(source.get(DESKTOP_PARENT_PID_ENV, "") or "").strip()
    if not raw_pid:
        return None
    try:
        parent_pid = int(raw_pid, 10)
    except ValueError as exc:
        raise RuntimeError("Desktop parent process ID is invalid.") from exc
    if parent_pid <= 1 or parent_pid == os.getpid():
        raise RuntimeError("Desktop parent process ID is invalid.")

    factory = psutil.Process if process_factory is None else process_factory
    callback = os._exit if exit_process is None else exit_process
    try:
        parent = factory(parent_pid)
    except psutil.NoSuchProcess:
        callback(0)
        return None

    thread = threading.Thread(
        target=_wait_for_parent_exit,
        args=(parent, callback),
        name="desktop-parent-watchdog",
        daemon=True,
    )
    thread.start()
    return thread
