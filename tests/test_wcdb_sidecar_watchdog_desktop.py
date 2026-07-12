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


if __name__ == "__main__":
    unittest.main()
