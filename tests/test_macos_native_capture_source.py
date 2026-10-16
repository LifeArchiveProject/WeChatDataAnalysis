from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/wechat_decrypt_tool/native/macos/source/wcdb_native_capture.c"


def test_validated_capture_terminates_disposable_process_before_returning() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("if (candidate_matches_page1(candidate))")
    end = source.index("    return continue_thread_at_x16(thread);", start)
    block = source[start:end]

    assert "kill(g_ctx.target_pid, SIGKILL)" in block
    assert "task_resume" not in block
    assert "continue_thread_at_x16" not in block


def test_monitor_reports_ready_only_after_breakpoint_installation() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    capture = source.index("static int run_capture")
    restore_debug = source.index("(void)restore_hardware_breakpoints();", capture)
    restore_port = source.index("restore_exception_ports(g_ctx.task);", restore_debug)
    resume = source.index("if (task_resume(g_ctx.task) != KERN_SUCCESS)", restore_port)
    assert restore_debug < restore_port < resume


def test_helper_source_contains_no_environment_specific_paths() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert "/Users/" not in source
    assert "/Volumes/" not in source
    assert "wxid_" not in source
