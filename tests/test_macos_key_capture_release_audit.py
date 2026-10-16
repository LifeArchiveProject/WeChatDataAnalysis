from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "audit_macos_key_capture_release.py"
_SPEC = importlib.util.spec_from_file_location("audit_macos_key_capture_release", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_AUDIT = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_AUDIT)


def test_release_audit_rejects_personal_paths_and_runtime_secrets(tmp_path: Path) -> None:
    app = tmp_path / "Example.app"
    app.mkdir()
    (app / "binary").write_bytes(b"built from /Users/example/private/source.py")
    (app / "wechat-passphrase.json").write_text("{}", encoding="utf-8")

    violations = _AUDIT.audit_directory(app)

    assert any("用户主目录绝对路径" in item for item in violations)
    assert any("私密文件" in item for item in violations)


def test_release_audit_accepts_clean_app_and_rejects_database_in_zip(tmp_path: Path) -> None:
    app = tmp_path / "Clean.app"
    app.mkdir()
    (app / "binary").write_bytes(b"portable executable content")
    assert _AUDIT.audit_directory(app) == []

    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("Clean.app/Contents/MacOS/binary", b"clean")
        output.writestr("Clean.app/user/message_0.db", b"private")
    assert any("私密文件" in item for item in _AUDIT.audit_zip(archive))


def test_release_audit_scans_zip_entry_contents(tmp_path: Path) -> None:
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(
            "Example.app/Contents/Resources/build.txt",
            b"built from /Users/example/private/source.py",
        )

    assert any("用户主目录绝对路径" in item for item in _AUDIT.audit_zip(archive))
