from __future__ import annotations

import os
import unittest
from unittest.mock import Mock

import psutil

from wechat_decrypt_tool.desktop_parent_watchdog import (
    DESKTOP_PARENT_PID_ENV,
    start_desktop_parent_watchdog_from_env,
)


class DesktopParentWatchdogTests(unittest.TestCase):
    def test_absent_parent_does_not_start_watchdog(self) -> None:
        self.assertIsNone(start_desktop_parent_watchdog_from_env(env={}))

    def test_invalid_parent_is_rejected(self) -> None:
        for value in ("bad", "0", "-1", str(os.getpid())):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                start_desktop_parent_watchdog_from_env(
                    env={DESKTOP_PARENT_PID_ENV: value}
                )

    def test_parent_exit_terminates_backend(self) -> None:
        parent = Mock()
        parent.wait.return_value = 0
        exits: list[int] = []
        thread = start_desktop_parent_watchdog_from_env(
            env={DESKTOP_PARENT_PID_ENV: "4242"},
            process_factory=lambda pid: parent if pid == 4242 else None,
            exit_process=exits.append,
        )

        self.assertIsNotNone(thread)
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        parent.wait.assert_called_once_with()
        self.assertEqual(exits, [0])

    def test_watchdog_failure_exits_nonzero(self) -> None:
        parent = Mock()
        parent.wait.side_effect = psutil.AccessDenied(pid=4242)
        exits: list[int] = []
        thread = start_desktop_parent_watchdog_from_env(
            env={DESKTOP_PARENT_PID_ENV: "4242"},
            process_factory=lambda _pid: parent,
            exit_process=exits.append,
        )

        self.assertIsNotNone(thread)
        thread.join(timeout=2)
        self.assertEqual(exits, [70])


if __name__ == "__main__":
    unittest.main()
