import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestWcdbSidecarWatchdogDesktop(unittest.TestCase):
    def test_desktop_monitors_and_recycles_an_unresponsive_sidecar(self) -> None:
        source = (ROOT / "desktop" / "src" / "main.cjs").read_text(encoding="utf-8")

        self.assertIn("function startWcdbSidecarHealthMonitor", source)
        self.assertIn("function stopWcdbSidecarHealthMonitor", source)
        self.assertIn("function probeWcdbSidecarHealth", source)
        self.assertIn("/health", source)
        self.assertIn("wcdbSidecarHealthFailures", source)
        self.assertIn("proc.kill()", source)
        self.assertIn("scheduleWcdbRuntimeRestart", source)

    def test_output_migration_and_backend_maintenance_block_sidecar_restart(self) -> None:
        source = (ROOT / "desktop" / "src" / "main.cjs").read_text(encoding="utf-8")

        self.assertIn("function waitForWcdbRuntimeRestartToSettle", source)
        self.assertGreaterEqual(source.count("outputDirChangeInProgress ||"), 3)
        self.assertGreaterEqual(source.count("backendPortChangeInProgress ||"), 3)
        self.assertGreaterEqual(source.count("accountDataChangeInProgress ||"), 2)
        self.assertIn("await waitForWcdbRuntimeRestartToSettle();", source)
        self.assertIn("wcdbSidecarProc.killed", source)


if __name__ == "__main__":
    unittest.main()
