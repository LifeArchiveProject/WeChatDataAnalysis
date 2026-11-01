"""Read-only synthetic Mach-O output and fake LLDB; no real debugger attach."""

import ast
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.macos_clone_capture import (
    WECHAT_PBKDF_STUB_POINTS,
    build_lldb_breakpoint_preflight_script,
    build_lldb_salt_capture_script,
    capture_salt_matched_passphrase,
    preflight_capture_breakpoints,
    resolve_lldb_pbkdf_stub_plan,
)
from wechat_decrypt_tool.macos_db_key_capture import MacOSDBKeyCaptureFailure

SYNTHETIC_UUID = "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE"
STUB_OFFSET = 0x1234
LOAD_COMMANDS = f"Load command 15\n     cmd LC_UUID\n cmdsize 24\n    uuid {SYNTHETIC_UUID}\n"
IMPORTS = f"Indirect symbols for (__TEXT,__stubs) 1 entries\naddress index name\n0x{STUB_OFFSET:x} 6 _CCKeyDerivationPBKDF\n"


class FakeAddress:
    def __init__(self, *, valid=True, executable=True, loaded=True):
        self.valid, self.executable, self.loaded = valid, executable, loaded

    def IsValid(self):
        return self.valid

    def GetSection(self):
        return types.SimpleNamespace(IsValid=lambda: True, GetPermissions=lambda: 4 if self.executable else 0, GetName=lambda: "__stubs")

    def GetLoadAddress(self, target):
        return 0x12345000 if self.loaded else -1


class FakeBreakpoint:
    def __init__(self, address, *, resolved=True):
        self.address, self.resolved = address, resolved

    def GetNumLocations(self):
        return 1

    def GetLocationAtIndex(self, index):
        return types.SimpleNamespace(IsResolved=lambda: self.resolved, GetAddress=lambda: self.address)

    def SetEnabled(self, enabled):
        pass

    def SetScriptCallbackFunction(self, name):
        pass

    def SetAutoContinue(self, enabled):
        pass


class TestMacOSLLDBBreakpointPlan(unittest.TestCase):
    def namespace(self, script):
        ast.parse(script)
        namespace = {"__name__": "synthetic_breakpoints"}
        fake_lldb = types.SimpleNamespace(LLDB_INVALID_ADDRESS=-1, ePermissionsExecutable=4, SBSection=lambda: types.SimpleNamespace(IsValid=lambda: False))
        with patch.dict(sys.modules, {"lldb": fake_lldb}):
            exec(compile(script, "<synthetic-lldb>", "exec"), namespace)
        return namespace

    def scripts(self, plan=None):
        plan = plan if plan is not None else {SYNTHETIC_UUID: STUB_OFFSET}
        return (
            build_lldb_breakpoint_preflight_script(Path("/synthetic/preflight.json"), pbkdf_stub_plan=plan),
            build_lldb_salt_capture_script(Path("/synthetic/result.json"), [b"x" * 16], probe_page1=b"x" * 4096, pbkdf_stub_plan=plan),
        )

    def target(self, *, address=None, uuid=SYNTHETIC_UUID, stub_resolved=True, name_resolved=False):
        address = address or FakeAddress()
        process = types.SimpleNamespace(GetProcessID=lambda: 123, Detach=Mock(return_value=types.SimpleNamespace(Success=lambda: True)))
        module = types.SimpleNamespace(
            GetUUIDString=lambda: uuid, ResolveFileAddress=Mock(return_value=address),
            GetFileSpec=lambda: types.SimpleNamespace(GetFilename=lambda: "wechat.dylib"),
        )
        target = types.SimpleNamespace(
            GetProcess=lambda: process,
            module_iter=lambda: iter([module]),
            BreakpointCreateByName=lambda name: FakeBreakpoint(address, resolved=name_resolved),
            BreakpointCreateBySBAddress=Mock(side_effect=lambda address: FakeBreakpoint(address, resolved=stub_resolved)),
        )
        return target, module, process

    def test_resolver_binds_unknown_build_to_arm64_uuid_and_exact_import_stub(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app = Path(temp_dir) / "Synthetic.app"
            dylib = app / "Contents/Resources/wechat.dylib"
            dylib.parent.mkdir(parents=True)
            dylib.write_bytes(b"synthetic Mach-O placeholder")
            with patch("wechat_decrypt_tool.macos_clone_capture._run", side_effect=[types.SimpleNamespace(stdout=LOAD_COMMANDS), types.SimpleNamespace(stdout=IMPORTS)]) as run:
                plan = resolve_lldb_pbkdf_stub_plan(app)
            self.assertEqual(plan[SYNTHETIC_UUID], STUB_OFFSET)
            self.assertEqual(run.call_count, 2)
            for call in run.call_args_list:
                self.assertEqual(call.args[0][:3], ["/usr/bin/otool", "-arch", "arm64"])
                self.assertEqual(call.args[0][-1], str(dylib))
            for script in self.scripts(plan):
                self.assertEqual(self.namespace(script)["PBKDF_STUB_POINTS"], plan)

    def test_missing_uuid_nonstub_import_or_failed_inspection_never_guesses_offset(self):
        cases = (
            [types.SimpleNamespace(stdout="cmd LC_VERSION_MIN_MACOSX\n version 27.0\n")],
            [types.SimpleNamespace(stdout=LOAD_COMMANDS * 2)],
            [types.SimpleNamespace(stdout=LOAD_COMMANDS), types.SimpleNamespace(stdout="Indirect symbols for (__DATA,__got)\n0x1234 6 _CCKeyDerivationPBKDF\n")],
            [MacOSDBKeyCaptureFailure("command_failed", "synthetic otool unavailable")],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            app = Path(temp_dir) / "Synthetic.app"
            dylib = app / "Contents/Resources/wechat.dylib"
            dylib.parent.mkdir(parents=True)
            dylib.write_bytes(b"synthetic")
            for outputs in cases:
                with self.subTest(output_count=len(outputs)), patch("wechat_decrypt_tool.macos_clone_capture._run", side_effect=outputs):
                    self.assertEqual(resolve_lldb_pbkdf_stub_plan(app), WECHAT_PBKDF_STUB_POINTS)

    def test_unknown_uuid_resolved_plan_arms_identical_executable_stub_in_both_stages(self):
        for stage, script in enumerate(self.scripts()):
            with self.subTest(stage=stage):
                namespace = self.namespace(script)
                target, module, process = self.target()
                writes = []
                namespace["_write_result"] = lambda payload: writes.append(payload) or True
                namespace["_write_ready"] = lambda payload: writes.append(payload) or True
                namespace["_setup"](types.SimpleNamespace(GetSelectedTarget=lambda: target), None, None, None)
                module.ResolveFileAddress.assert_called_once_with(STUB_OFFSET)
                self.assertEqual(writes[-1]["pbkdf_locations"], 1)
                if stage == 1:
                    self.assertEqual(writes[-1]["status"], "ready")
                    process.Detach.assert_not_called()

    def test_unresolved_nonexecutable_unloaded_or_wrong_uuid_never_becomes_ready(self):
        scenarios = (
            {"address": FakeAddress(valid=False)},
            {"address": FakeAddress(executable=False), "name_resolved": True},
            {"address": FakeAddress(loaded=False), "name_resolved": True},
            {"stub_resolved": False},
            {"uuid": "FFFFFFFF-BBBB-CCCC-DDDD-EEEEEEEEEEEE"},
        )
        class ScriptExit(Exception):
            pass
        for scenario in scenarios:
            for stage, script in enumerate(self.scripts()):
                with self.subTest(stage=stage, scenario=list(scenario)):
                    namespace = self.namespace(script)
                    target, module, process = self.target(**scenario)
                    writes = []
                    namespace["_write_result"] = lambda payload: writes.append(payload) or True
                    namespace["_write_ready"] = lambda payload: writes.append(payload) or True
                    debugger = types.SimpleNamespace(GetSelectedTarget=lambda: target)
                    if stage == 0:
                        namespace["_setup"](debugger, None, None, None)
                        self.assertEqual(writes[-1]["pbkdf_locations"], 0)
                    else:
                        with patch.object(namespace["os"], "_exit", side_effect=ScriptExit) as exit_script:
                            with self.assertRaises(ScriptExit):
                                namespace["_setup"](debugger, None, None, None)
                        exit_script.assert_called_once_with(24)
                        self.assertEqual(writes, [])
                        process.Detach.assert_called_once()

    def test_preflight_persists_the_same_resolver_plan_it_passes_to_lldb(self):
        plan = {**WECHAT_PBKDF_STUB_POINTS, SYNTHETIC_UUID: STUB_OFFSET}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            def fake_lldb(command, *, timeout):
                script_path = Path(command).parent / "preflight_callback.py"
                self.assertEqual(self.namespace(script_path.read_text())["PBKDF_STUB_POINTS"], plan)
                (root / "breakpoint-preflight.json").write_text(json.dumps({"pid": 123, "pbkdf_locations": 1, "key_return_locations": 0}))
                return ""
            with (
                patch("wechat_decrypt_tool.macos_clone_capture.platform.machine", return_value="arm64"),
                patch("wechat_decrypt_tool.macos_clone_capture.shutil.which", return_value="/fake/lldb"),
                patch("wechat_decrypt_tool.macos_clone_capture.resolve_lldb_pbkdf_stub_plan", return_value=plan),
                patch("wechat_decrypt_tool.macos_clone_capture._build_lldb_capture_command", side_effect=lambda path, timeout: str(path)),
                patch("wechat_decrypt_tool.macos_clone_capture._run_as_administrator", side_effect=fake_lldb),
            ):
                result = preflight_capture_breakpoints(pid=123, debug_root=root, wechat_app=root / "Synthetic.app")
            self.assertEqual(result["pbkdf_stub_plan"], plan)
            self.assertEqual(json.loads((root / "breakpoint-preflight.json").read_text())["pbkdf_stub_plan"], plan)

    def test_invalid_plan_is_rejected_before_it_can_become_debugger_code(self):
        for plan in ({"bad uuid": 4}, {SYNTHETIC_UUID: -4}, {SYNTHETIC_UUID: 3}, {SYNTHETIC_UUID: "4096"}):
            with self.subTest(value_type=type(next(iter(plan.values()))).__name__):
                with self.assertRaises(MacOSDBKeyCaptureFailure):
                    self.scripts(plan)

    def test_capture_wrapper_forwards_the_persisted_plan_without_resolving_again(self):
        plan = {**WECHAT_PBKDF_STUB_POINTS, SYNTHETIC_UUID: STUB_OFFSET}
        with tempfile.TemporaryDirectory() as temp_dir:
            probe = Path(temp_dir) / "synthetic.db"
            probe.write_bytes(b"x" * 4096)
            def fake_lldb(command, *, timeout):
                root = Path(command).parent
                self.assertEqual(self.namespace((root / "capture_callback.py").read_text())["PBKDF_STUB_POINTS"], plan)
                (root / "result.json").write_text(json.dumps({"passphrase": "ab" * 32, "salt": (b"x" * 16).hex()}))
                return ""
            with (
                patch("wechat_decrypt_tool.macos_clone_capture.platform.machine", return_value="arm64"),
                patch("wechat_decrypt_tool.macos_clone_capture.shutil.which", return_value="/fake/lldb"),
                patch("wechat_decrypt_tool.macos_clone_capture.resolve_lldb_pbkdf_stub_plan") as resolve,
                patch("wechat_decrypt_tool.macos_clone_capture._build_lldb_capture_command", side_effect=lambda path, timeout: str(path)),
                patch("wechat_decrypt_tool.macos_clone_capture._run_as_administrator", side_effect=fake_lldb),
            ):
                result = capture_salt_matched_passphrase(pid=123, expected_salts=[b"x" * 16], probe_db_path=probe, pbkdf_stub_plan=plan)
            self.assertEqual(result, "ab" * 32)
            resolve.assert_not_called()

    def test_failed_detach_never_publishes_success_or_raw_debugger_errors(self):
        namespace = self.namespace(self.scripts()[0])
        target, module, process = self.target()
        process.Detach.return_value = types.SimpleNamespace(Success=lambda: False, GetCString=lambda: "sensitive-debugger-details")
        writes = []
        namespace["_write_result"] = lambda payload: writes.append(payload) or True
        namespace["_setup"](types.SimpleNamespace(GetSelectedTarget=lambda: target), None, None, None)
        self.assertEqual(writes, [{"status": "error", "code": "capture_preflight_detach_failed"}])
        self.assertNotIn("sensitive-debugger-details", json.dumps(writes))

    def test_wrapper_rejects_failed_detach_even_with_resolved_locations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            def fake_lldb(command, *, timeout):
                (root / "breakpoint-preflight.json").write_text(json.dumps({
                    "status": "error", "code": "capture_preflight_detach_failed", "pbkdf_locations": 1,
                }))
                return "WEDATA_BREAKPOINT_PREFLIGHT_DETACH_FAILED"
            with (
                patch("wechat_decrypt_tool.macos_clone_capture.platform.machine", return_value="arm64"),
                patch("wechat_decrypt_tool.macos_clone_capture.shutil.which", return_value="/fake/lldb"),
                patch("wechat_decrypt_tool.macos_clone_capture._run_as_administrator", side_effect=fake_lldb),
            ):
                with self.assertRaises(MacOSDBKeyCaptureFailure) as failure:
                    preflight_capture_breakpoints(pid=123, debug_root=root)
            self.assertEqual(failure.exception.code, "capture_preflight_detach_failed")
            self.assertFalse((root / "breakpoint-preflight.json").exists())


if __name__ == "__main__":
    unittest.main()
