"""Exercise the real shell wrapper without LLDB, WeChat, or authorization."""

import os
from pathlib import Path
import select
import shlex
import signal
import subprocess
import sys
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.macos_db_key_capture import _build_lldb_capture_command


@unittest.skipUnless(os.name == "posix" and Path("/bin/bash").is_file(), "requires POSIX bash")
class TestLLDBCommandLifecycle(unittest.TestCase):
    def command(self, stub: str, timeout: int = 3) -> list[str]:
        args = shlex.split(_build_lldb_capture_command(Path("/dev/null"), timeout))
        self.assertEqual(args[:2], ["/bin/bash", "-c"])
        launcher = "/usr/bin/env TERM=dumb /usr/bin/lldb"
        self.assertEqual(args[2].count(launcher), 1)
        args[2] = args[2].replace(launcher, stub)
        self.assertNotIn("/usr/bin/lldb", args[2])
        self.assertNotIn("osascript", args[2])
        self.assertIn("/bin/cat /dev/null;", args[2])
        # Report only this test's private directory and child IDs. This also
        # gives signal tests a readiness barrier before interrupting the shell.
        marker = "watchdog_pid=$!\n"
        self.assertEqual(args[2].count(marker), 1)
        args[2] = args[2].replace(
            marker,
            marker + 'printf "WEDATA_TEST_SCOPE %s %s %s %s\\n" '
            '"$capture_dir" "$producer_pid" "$lldb_pid" "$watchdog_pid"\n',
        )
        return args

    def run_wrapper(self, stub: str, interrupt: int | None = None) -> tuple[str, int, float]:
        started = time.monotonic()
        process = subprocess.Popen(
            self.command(stub), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True,
        )
        try:
            self.assertTrue(select.select([process.stdout], [], [], 2)[0], "wrapper did not start")
            scope = process.stdout.readline().strip().split()
            self.assertEqual(scope[0], "WEDATA_TEST_SCOPE")
            capture_dir = Path(scope[1])
            self.assertEqual(capture_dir.parent.resolve(), Path("/tmp").resolve())
            self.assertTrue(capture_dir.name.startswith("wedata-lldb."))
            if interrupt is not None:
                # Allow the watchdog to enter its timer wait, not just fork.
                time.sleep(0.1)
                process.send_signal(interrupt)
            stdout, _stderr = process.communicate(timeout=6)
            elapsed = time.monotonic() - started
            self.assertFalse(capture_dir.exists(), "private FIFO directory was not cleaned")
            for raw_pid in scope[2:]:
                with self.assertRaises(ProcessLookupError, msg=f"child {raw_pid} was not reaped"):
                    os.kill(int(raw_pid), 0)
            with self.assertRaises(ProcessLookupError, msg="wrapper left a descendant in its private process group"):
                os.killpg(process.pid, 0)
            return stdout, process.returncode, elapsed
        finally:
            # A failed regression must not leave its synthetic sleep children.
            # The group belongs solely to Popen(start_new_session=True) above.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate(timeout=6)

    def test_success_returns_without_waiting_for_watchdog(self) -> None:
        stdout, returncode, elapsed = self.run_wrapper("/bin/sleep 0.2")
        self.assertEqual(returncode, 0)
        self.assertIn("WEDATA_LLDB_EXIT=0", stdout)
        self.assertLess(elapsed, 2.0, "successful capture waited for the 3-second watchdog")

    def test_debugger_failure_returns_without_waiting_for_watchdog(self) -> None:
        stdout, returncode, elapsed = self.run_wrapper("/bin/sh -c 'exit 24'")
        self.assertEqual(returncode, 0)
        self.assertIn("WEDATA_LLDB_EXIT=24", stdout)
        self.assertLess(elapsed, 2.0, "failed capture waited for the 3-second watchdog")

    def test_watchdog_still_terminates_a_long_running_debugger(self) -> None:
        stdout, returncode, elapsed = self.run_wrapper("/bin/sleep 10")
        self.assertEqual(returncode, 0)
        self.assertIn("WEDATA_LLDB_EXIT=143", stdout)
        self.assertGreaterEqual(elapsed, 2.6, "watchdog fired before its configured deadline")
        self.assertLess(elapsed, 4.5, "watchdog did not terminate the synthetic debugger")

    def test_signals_clean_children_and_return_promptly(self) -> None:
        for interrupt in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            with self.subTest(signal=interrupt):
                _stdout, returncode, elapsed = self.run_wrapper("/bin/sleep 10", interrupt)
                self.assertEqual(returncode, 128 + interrupt)
                self.assertLess(elapsed, 2.0, "interrupted capture left a timer holding output open")


if __name__ == "__main__":
    unittest.main()
