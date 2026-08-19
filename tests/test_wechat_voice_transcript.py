from __future__ import annotations

from wechat_decrypt_tool.wechat_voice_transcript import extract_wechat_transcript


def _varint(value: int) -> bytes:
    out = bytearray()
    while value > 0x7F:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _payload(text: bytes = "微信官方转写".encode()) -> bytes:
    child = _varint((2 << 3) | 2) + _varint(len(text)) + text
    return _varint((5 << 3) | 2) + _varint(len(child)) + child


def test_extracts_utf8_transcript_from_supported_inputs() -> None:
    payload = _payload()
    assert extract_wechat_transcript(payload) == "微信官方转写"
    assert extract_wechat_transcript(bytearray(payload)) == "微信官方转写"
    assert extract_wechat_transcript(memoryview(payload)) == "微信官方转写"
    assert extract_wechat_transcript(payload.hex()) == "微信官方转写"


def test_malformed_or_invalid_payload_is_ignored() -> None:
    assert extract_wechat_transcript(b"") == ""
    assert extract_wechat_transcript(b"\x2a\x03\x12") == ""
    assert extract_wechat_transcript(_payload(b"\xff")) == ""
    assert extract_wechat_transcript(b"\x2a\x02\x12\x80") == ""


def test_overflow_varint_after_valid_prefix_rejects_whole_payload() -> None:
    assert extract_wechat_transcript(_payload() + b"\x80\x80\x80\x80\x80\x80\x80\x80\x80\x02") == ""
