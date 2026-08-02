import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestWcdbSidecarWatchdogDesktop(unittest.TestCase):
    def test_desktop_has_no_legacy_wcdb_sidecar_runtime(self) -> None:
        source = (ROOT / "desktop" / "src" / "main.cjs").read_text(encoding="utf-8")

        self.assertIn("function clearLegacyWcdbEnvironment", source)
        self.assertIn("clearLegacyWcdbEnvironment(env)", source)
        for environment_name in (
            "WECHAT_TOOL_WCDB_SIDECAR_URL",
            "WECHAT_TOOL_WCDB_SIDECAR_TOKEN",
            "WECHAT_TOOL_WCDB_API_DLL_PATH",
            "WECHAT_TOOL_WCDB_DLL_DIR",
            "WECHAT_TOOL_WCDB_RESOURCE_PATHS",
            "WECHAT_TOOL_KOFFI_DIR",
        ):
            self.assertIn(environment_name, source)

        for removed_symbol in (
            "wcdbSidecarProc",
            "wcdbSidecarPort",
            "wcdbSidecarHealthFailures",
            "startWcdbSidecar",
            "stopWcdbSidecar",
            "prepareWcdbSidecarPort",
            "probeWcdbSidecarHealth",
            "scheduleWcdbRuntimeRestart",
            "getWcdbDllPath",
            "getKoffiDir",
            "[wcdb-sidecar]",
        ):
            self.assertNotIn(removed_symbol, source)

    def test_output_migration_and_backend_maintenance_remain_serialized(self) -> None:
        source = (ROOT / "desktop" / "src" / "main.cjs").read_text(encoding="utf-8")

        self.assertGreaterEqual(source.count("outputDirChangeInProgress ||"), 3)
        self.assertGreaterEqual(source.count("if (backendPortChangeInProgress)"), 2)
        self.assertGreaterEqual(source.count("backendPortChangeInProgress ||"), 2)
        self.assertGreaterEqual(
            source.count("outputDirChangeInProgress || accountDataChangeInProgress"),
            2,
        )
        self.assertGreaterEqual(
            source.count("backendPortChangeInProgress || accountDataChangeInProgress"),
            2,
        )
        self.assertNotIn("waitForWcdbRuntimeRestartToSettle", source)
        self.assertNotIn("wcdbSidecarProc", source)


if __name__ == "__main__":
    unittest.main()
