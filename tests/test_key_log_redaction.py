import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class _SuccessfulPool:
    def __init__(self, recovered_key: bytes):
        self.recovered_key = recovered_key
        self.terminated = False

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        return False

    def imap_unordered(self, _worker, tasks, chunksize):
        assert chunksize == 16
        assert len(list(tasks)) == 1
        return iter((self.recovered_key,))

    def terminate(self):
        self.terminated = True


def test_v4_key_success_stdout_does_not_include_recovered_key():
    from wechat_decrypt_tool import key_v4

    recovered_key = bytes.fromhex(
        "0123456789abcdeffedcba9876543210"
        "112233445566778899aabbccddeeff00"
    )
    pool = _SuccessfulPool(recovered_key)
    stdout = io.StringIO()

    with (
        mock.patch.object(key_v4.multiprocessing, "cpu_count", return_value=2),
        mock.patch.object(key_v4.multiprocessing, "Pool", return_value=pool),
        redirect_stdout(stdout),
    ):
        result = key_v4.verify_keys([recovered_key], b"unused")

    rendered = stdout.getvalue()
    recovered_hex = recovered_key.hex()
    assert result == recovered_hex
    assert pool.terminated is True
    assert "Key found" in rendered
    assert "length=32 bytes" in rendered
    assert "value redacted" in rendered
    assert recovered_hex not in rendered
    assert recovered_hex[:8] not in rendered
    assert recovered_hex[-8:] not in rendered


def test_all_v4_entrypoints_redact_success_output():
    for relative_path in ("key_v4.py", "src/wechat_decrypt_tool/key_v4.py"):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert 'print(f"[+] Key found: {bytes.hex(r)}")' not in source
        assert 'print(f"[+] Successfully recovered key: {key}")' not in source
        assert source.count("value redacted") == 2


def test_backend_image_key_log_metadata_contains_no_key_values_or_fragments():
    from wechat_decrypt_tool.key_service import _key_payload_log_metadata
    from wechat_decrypt_tool.routers.keys import _image_key_log_metadata
    from wechat_decrypt_tool.routers.media import _media_key_log_metadata

    xor_key = "0xA5"
    aes_key = "S3cr3tAesKey9876"
    metadata_values = [
        _key_payload_log_metadata({
            "wxid": "wxid_example",
            "xorKey": xor_key,
            "aesKey": aes_key,
        }),
        _image_key_log_metadata(xor_key, aes_key),
        _media_key_log_metadata(xor_key=xor_key, aes_key=aes_key),
    ]

    assert metadata_values[0]["wxid"] == "wxid_example"
    for metadata in metadata_values:
        assert metadata["has_xor"] is True
        assert metadata["has_aes"] is True
        assert metadata["xor_length"] == len(xor_key)
        assert metadata["aes_length"] == len(aes_key)
        rendered = repr(metadata)
        assert xor_key not in rendered
        assert aes_key not in rendered
        assert aes_key[:4] not in rendered
        assert aes_key[-4:] not in rendered


def test_decrypt_renderer_key_debug_summary_is_metadata_only():
    source = (ROOT / "frontend/pages/decrypt.vue").read_text(encoding="utf-8")
    start = source.index("const summarizeKeyStateForLog")
    end = source.index("const formatLogError", start)
    summary_source = source[start:end]

    assert "summarizeAesForLog" not in source
    assert ".slice(0, 4)" not in summary_source
    assert ".slice(-4)" not in summary_source
    assert "xor_key:" not in summary_source
    assert "aes_key:" not in summary_source
    assert "has_xor: !!normalizedXor" in summary_source
    assert "has_aes: !!normalizedAes" in summary_source
    assert "xor_length: normalizedXor.length" in summary_source
    assert "aes_length: normalizedAes.length" in summary_source
