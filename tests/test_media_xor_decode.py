"""单字节 XOR 解码改为查表后，结果必须与逐字节实现完全一致。"""

import struct

import pytest
from Crypto.Cipher import AES
from Crypto.Util import Padding

from wechat_decrypt_tool import media_helpers


PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) + b"\x00\x00\x00\x00IEND\xaeB`\x82"
BUFFERS = {
    "empty": b"",
    "one": b"\x5a",
    "short": b"wxgf\x00\xff",
    "all-bytes": bytes(range(256)),
    "long": bytes((i * 131 + 7) & 0xFF for i in range(70_001)),
}


def naive_xor(data, key):
    return bytes(b ^ key for b in data)


class NoIterBytes(bytes):
    """一旦被 Python 层逐字节迭代就失败，用来守住整文件解码不回退成解释器循环。"""

    def __iter__(self):
        raise AssertionError("逐字节 Python 循环")


@pytest.mark.parametrize("name", BUFFERS)
def test_xor_bytes_matches_naive_for_every_key(name):
    data = BUFFERS[name]
    # 逐字节的参照实现很慢：256 个 key 由短缓冲区（含全部 256 个字节值）覆盖，长缓冲区只抽几个。
    for key in (0x00, 0x01, 0x5A, 0xA5, 0xFF) if name == "long" else range(256):
        assert media_helpers._xor_bytes(data, key) == naive_xor(data, key)


@pytest.mark.parametrize("buffer_type", [bytearray, memoryview])
def test_xor_bytes_accepts_any_buffer_like_naive(buffer_type):
    data = BUFFERS["all-bytes"]

    decoded = media_helpers._xor_bytes(buffer_type(data), 0xA5)

    assert type(decoded) is bytes and decoded == naive_xor(buffer_type(data), 0xA5)


@pytest.mark.parametrize("key", [-1, 256])
def test_xor_bytes_rejects_out_of_range_key_like_naive(key):
    with pytest.raises(ValueError):
        naive_xor(b"\x00", key)
    with pytest.raises(ValueError):
        media_helpers._xor_bytes(b"\x00", key)


@pytest.mark.parametrize("name", BUFFERS)
def test_dat_v3_matches_naive(name):
    data = BUFFERS[name]
    for key in (0x00, 0x01, 0xA5, 0xFF):
        assert media_helpers._decrypt_wechat_dat_v3(data, key) == naive_xor(data, key)


@pytest.mark.parametrize("tail", [b"", b"\x01", BUFFERS["long"]], ids=["no-tail", "one", "long"])
def test_dat_v4_xor_tail_matches_naive(tail):
    aes_key = b"cfcd208495d565ef"
    head, raw, key = b"aes protected head", b"raw middle", 0xA5
    encrypted_head = AES.new(aes_key, AES.MODE_ECB).encrypt(Padding.pad(head, AES.block_size))
    data = (
        struct.pack("<6sLLx", b"\x07\x08V1\x08\x07", len(head), len(tail))
        + encrypted_head
        + raw
        + naive_xor(tail, key)
    )

    assert media_helpers._decrypt_wechat_dat_v4(data, key, aes_key) == head + raw + tail


@pytest.mark.parametrize("key", [0x00, 0x37, 0xA5, 0xFF])
def test_magic_guess_decodes_whole_payload(key):
    assert media_helpers._try_xor_decrypt_by_magic(naive_xor(PNG, key)) == (PNG, "image/png")


@pytest.mark.parametrize("key", [0x00, 0x37, 0xA5, 0xFF])
def test_magic_guess_bruteforce_strips_prefix(key):
    # 魔数不在固定偏移时走 256 个 key 的预览穷举，再剥掉前缀。
    data = naive_xor(b"junk!" + PNG, key)

    assert media_helpers._try_xor_decrypt_by_magic(data) == (PNG, "image/png")


def test_whole_buffer_decode_does_not_iterate_in_python():
    data = NoIterBytes(naive_xor(PNG, 0xA5))

    assert media_helpers._decrypt_wechat_dat_v3(data, 0xA5) == PNG
    assert media_helpers._try_xor_decrypt_by_magic(data) == (PNG, "image/png")
