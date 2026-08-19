"""Parse WeChat's optional official voice-transcript protobuf payload."""

from __future__ import annotations

from typing import Any


_MAX_PAYLOAD_BYTES = 1 << 20
_MAX_FIELD_BYTES = 1 << 20
_MAX_TRANSCRIPT_BYTES = 1 << 16
_MAX_FIELDS = 64


def _read_varint(data: bytes, offset: int, end: int) -> tuple[int, int] | None:
    value = 0
    for index in range(10):
        if offset >= end:
            return None
        byte = data[offset]
        offset += 1
        if index == 9 and byte > 0x01:
            return None
        value |= (byte & 0x7F) << (7 * index)
        if not (byte & 0x80):
            return value, offset
    return None


def _skip_field(data: bytes, offset: int, end: int, wire_type: int, *, limit: int) -> int | None:
    if wire_type == 0:
        parsed = _read_varint(data, offset, end)
        return parsed[1] if parsed else None
    if wire_type == 1:
        return offset + 8 if offset + 8 <= end else None
    if wire_type == 2:
        parsed = _read_varint(data, offset, end)
        if parsed is None:
            return None
        length, offset = parsed
        if length > limit or length > end - offset:
            return None
        return offset + length
    if wire_type == 5:
        return offset + 4 if offset + 4 <= end else None
    # Groups are not expected in this payload and are deliberately rejected.
    return None


def _parse_transcript_message(data: bytes) -> str:
    offset = 0
    end = len(data)
    result = ""
    field_count = 0
    while offset < end:
        field_count += 1
        if field_count > _MAX_FIELDS:
            return ""
        key = _read_varint(data, offset, end)
        if key is None:
            return ""
        field_key, offset = key
        field_number = field_key >> 3
        wire_type = field_key & 0x07
        if field_number <= 0:
            return ""
        if wire_type == 2:
            parsed = _read_varint(data, offset, end)
            if parsed is None:
                return ""
            length, offset = parsed
            if length > _MAX_FIELD_BYTES or length > end - offset:
                return ""
            value = data[offset : offset + length]
            offset += length
            if field_number == 2:
                if length > _MAX_TRANSCRIPT_BYTES:
                    return ""
                try:
                    result = value.decode("utf-8").strip()
                except UnicodeDecodeError:
                    return ""
        else:
            offset = _skip_field(data, offset, end, wire_type, limit=_MAX_FIELD_BYTES) or -1
            if offset < 0:
                return ""
    return result


def extract_wechat_transcript(value: Any) -> str:
    """Return the official transcript in ``packed_info_data`` or ``""``.

    The accepted shape is a protobuf top-level field 5 (length-delimited)
    containing a submessage field 2 (length-delimited UTF-8 text). Malformed,
    truncated, oversized, or invalidly encoded input is intentionally ignored.
    """

    try:
        if isinstance(value, str):
            text = value.strip()
            if not text or len(text) % 2:
                return ""
            data = bytes.fromhex(text)
        elif isinstance(value, (bytes, bytearray, memoryview)):
            data = bytes(value)
        else:
            return ""
    except (TypeError, ValueError):
        return ""

    if not data or len(data) > _MAX_PAYLOAD_BYTES:
        return ""

    offset = 0
    end = len(data)
    result = ""
    field_count = 0
    while offset < end:
        field_count += 1
        if field_count > _MAX_FIELDS:
            return ""
        key = _read_varint(data, offset, end)
        if key is None:
            return ""
        field_key, offset = key
        field_number = field_key >> 3
        wire_type = field_key & 0x07
        if field_number <= 0:
            return ""
        if wire_type == 2:
            parsed = _read_varint(data, offset, end)
            if parsed is None:
                return ""
            length, offset = parsed
            if length > _MAX_FIELD_BYTES or length > end - offset:
                return ""
            payload = data[offset : offset + length]
            offset += length
            if field_number == 5:
                result = _parse_transcript_message(payload)
                if not result:
                    # An explicitly present but malformed/empty candidate is
                    # not allowed to mask a later valid field, but malformed
                    # nested data must still fail the whole payload.
                    if payload:
                        nested_offset = 0
                        nested_field_count = 0
                        while nested_offset < len(payload):
                            nested_field_count += 1
                            if nested_field_count > _MAX_FIELDS:
                                return ""
                            nested_key = _read_varint(payload, nested_offset, len(payload))
                            if nested_key is None:
                                return ""
                            nested_field, nested_offset = nested_key
                            nested_offset = _skip_field(
                                payload,
                                nested_offset,
                                len(payload),
                                nested_field & 0x07,
                                limit=_MAX_FIELD_BYTES,
                            ) or -1
                            if nested_offset < 0:
                                return ""
        else:
            offset = _skip_field(data, offset, end, wire_type, limit=_MAX_FIELD_BYTES) or -1
            if offset < 0:
                return ""
    return result


__all__ = ["extract_wechat_transcript"]
