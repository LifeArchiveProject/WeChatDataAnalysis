"""Recover a stable SQLite/SQLCipher WAL snapshot without touching source files.

Format: https://sqlite.org/fileformat2.html#walformat. SQLCipher computes WAL
checksums over the encrypted page payload, before writing the frame to disk.
"""
from __future__ import annotations

import struct
from collections.abc import Callable


def _checksum(data: bytes, endian: str, state: tuple[int, int] = (0, 0)) -> tuple[int, int]:
    a, b = state
    for x, y in struct.iter_unpack(endian + 'II', data):
        a = (a + x + b) & 0xffffffff
        b = (b + y + a) & 0xffffffff
    return a, b


def merge_wal_snapshot(
    database: bytes,
    wal: bytes,
    page_size: int,
    *,
    verify_page: Callable[[bytes, int], bool] | None = None,
) -> tuple[bytes, dict]:
    """Apply only checksum-valid committed frames, respecting database truncation.

    A salt mismatch marks the recycled tail of a WAL. Complete frames with a
    bad checksum are rejected rather than silently exporting an older snapshot.
    Incomplete/uncommitted trailing frames never become part of the output.
    """
    info = {'wal_bytes': len(wal), 'committed_frames': 0, 'applied_pages': 0,
            'ignored_tail_bytes': 0, 'database_pages': len(database) // page_size}
    if not wal:
        return database, info
    if len(wal) < 32:
        raise ValueError('WAL 文件头不完整，请退出微信后重试')
    magic, version, wal_page_size = struct.unpack('>III', wal[:12])
    if magic not in (0x377f0682, 0x377f0683) or version != 3007000:
        raise ValueError('WAL 文件头或版本无效')
    if wal_page_size != page_size or len(database) % page_size:
        raise ValueError('WAL 与数据库页大小不匹配，或主数据库页不完整')
    endian = '<' if magic == 0x377f0682 else '>'
    state = _checksum(wal[:24], endian)
    if state != struct.unpack('>II', wal[24:32]):
        raise ValueError('WAL 文件头校验失败')
    salt = wal[16:24]
    frame_size = 24 + page_size
    pending: dict[int, bytes] = {}
    committed: dict[int, bytes] = {}
    base_pages = len(database) // page_size
    size = base_pages
    commit_end = 32
    for offset in range(32, len(wal) - frame_size + 1, frame_size):
        header = wal[offset:offset + 24]
        if header[8:16] != salt:
            break  # old frames left after WAL reset / preallocated zero tail
        pgno, db_size = struct.unpack('>II', header[:8])
        if pgno == 0 or pgno > 0xfffffffe:
            raise ValueError('WAL 页号无效')
        page = wal[offset + 24:offset + frame_size]
        state = _checksum(page, endian, _checksum(header[:8], endian, state))
        if state != struct.unpack('>II', header[16:24]):
            raise ValueError('WAL 帧校验失败，请重新获取稳定的数据库副本')
        pending[pgno] = page
        if db_size:
            committed.update(pending)
            pending.clear()
            committed = {n: p for n, p in committed.items() if n <= db_size}
            base_pages = min(base_pages, db_size)
            # Check before allocating: malformed sizes must not cause huge allocations.
            extension = sum(n > base_pages for n in committed)
            if db_size - base_pages != extension:
                raise ValueError('WAL 提交缺少数据库扩展页')
            size = db_size
            commit_end = offset + frame_size
            info['committed_frames'] = (commit_end - 32) // frame_size
    info.update(applied_pages=len(committed), ignored_tail_bytes=len(wal) - commit_end,
                database_pages=size)
    if not info['committed_frames']:
        return database, info
    output = bytearray(database[:base_pages * page_size])
    output.extend(b'\0' * (size * page_size - len(output)))
    for pgno, page in committed.items():
        if verify_page is not None and not verify_page(page, pgno):
            raise ValueError(f'WAL 第 {pgno} 页 HMAC 校验失败')
        output[(pgno - 1) * page_size:pgno * page_size] = page
    return bytes(output), info
