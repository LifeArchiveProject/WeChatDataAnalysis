"""数据库密钥与图片密钥文件在 POSIX 上只允许属主读写。"""

import json
import os
import stat
from pathlib import Path

import pytest

from wechat_decrypt_tool import key_store, media_helpers


pytestmark = pytest.mark.skipif(os.name == "nt", reason="Windows 没有 POSIX 权限位")

DB_KEY = "ab" * 32
MEDIA_KEYS = {"xor": 0xA5, "aes": "1234567890abcdef"}


def mode(path):
    return stat.S_IMODE(Path(path).stat().st_mode)


def seed(path, permissions=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"{}")
    path.chmod(permissions)


def save_db_key():
    return key_store.upsert_account_keys_in_store("wxid_demo", db_key=DB_KEY, raise_on_write_error=True)


def save_media_keys(account_dir):
    media_helpers._save_media_keys(account_dir, MEDIA_KEYS["xor"], MEDIA_KEYS["aes"].encode("ascii"))


@pytest.fixture(autouse=True)
def default_umask():
    previous = os.umask(0o022)
    try:
        yield
    finally:
        os.umask(previous)


@pytest.fixture
def store_path(tmp_path, monkeypatch):
    path = tmp_path / "output" / "account_keys.json"
    monkeypatch.setattr(key_store, "_KEY_STORE_PATH", path)
    return path


@pytest.fixture
def modes_at_write(monkeypatch):
    """记录密钥内容写入那一刻文件已有的权限；文件还不存在时记 None。"""
    seen = []
    write_text = Path.write_text

    def recording_write_text(self, *args, **kwargs):
        seen.append((self.name, mode(self) if self.exists() else None))
        return write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", recording_write_text)
    return seen


def test_account_keys_store_is_created_owner_only(store_path):
    save_db_key()

    assert mode(store_path) == 0o600


def test_account_keys_store_overwrite_narrows_existing_mode(store_path):
    seed(store_path)

    save_db_key()

    assert mode(store_path) == 0o600
    assert json.loads(store_path.read_text(encoding="utf-8"))["wxid_demo"]["db_key"] == DB_KEY


@pytest.mark.parametrize("stale_temp_file", [False, True], ids=["new", "stale-0644-temp-file"])
def test_account_keys_are_only_written_to_an_owner_only_file(store_path, modes_at_write, stale_temp_file):
    if stale_temp_file:
        # 上次异常退出留下的临时文件权限更宽，也必须在写入密钥前收紧。
        seed(store_path.with_name("account_keys.json.tmp"))

    save_db_key()

    assert modes_at_write == [("account_keys.json.tmp", 0o600)]
    assert mode(store_path) == 0o600


def test_media_keys_file_is_created_owner_only(tmp_path):
    save_media_keys(tmp_path)

    assert mode(tmp_path / "_media_keys.json") == 0o600


def test_media_keys_overwrite_narrows_existing_mode(tmp_path):
    path = tmp_path / "_media_keys.json"
    seed(path)

    save_media_keys(tmp_path)

    assert mode(path) == 0o600
    assert json.loads(path.read_text(encoding="utf-8")) == MEDIA_KEYS


@pytest.mark.parametrize("existing", [False, True], ids=["new", "existing-0644"])
def test_media_keys_are_only_written_to_an_owner_only_file(tmp_path, modes_at_write, existing):
    if existing:
        seed(tmp_path / "_media_keys.json")

    save_media_keys(tmp_path)

    assert modes_at_write == [("_media_keys.json", 0o600)]


def test_keys_are_still_saved_when_chmod_is_refused(store_path, tmp_path, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise PermissionError("chmod refused")

    monkeypatch.setattr(os, "chmod", refuse)

    save_db_key()
    save_media_keys(tmp_path)

    assert json.loads(store_path.read_text(encoding="utf-8"))["wxid_demo"]["db_key"] == DB_KEY
    assert json.loads((tmp_path / "_media_keys.json").read_text(encoding="utf-8")) == MEDIA_KEYS
