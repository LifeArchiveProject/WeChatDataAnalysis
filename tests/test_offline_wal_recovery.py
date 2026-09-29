"""Real SQLite pages and encrypted fixtures for issue #166 (no mocked diagnostics)."""
import hashlib
from contextlib import closing
import hmac
import sqlite3
import struct
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

import wechat_decrypt_tool.wechat_decrypt as decrypt
from wechat_decrypt_tool.sqlite_wal import merge_wal_snapshot
from wechat_decrypt_tool.routers.decrypt import _db_key_persistence_rejection

KEY = bytes(range(32))
SALT = bytes(range(16))
INDEX = 'SessionUnreadListTable_1_NameId_CreateTime'


def checksum(data, state=(0, 0), endian='<'):
    values = struct.unpack(endian + 'I' * (len(data) // 4), data)
    a, b = state
    for i in range(0, len(values), 2):
        a = (a + values[i] + b) % 2**32
        b = (b + values[i + 1] + a) % 2**32
    return a, b


def wal_bytes(frames, endian='<'):
    header = struct.pack('>IIIIII', 0x377f0682 if endian == '<' else 0x377f0683,
                         3007000, 4096, 0, 123, 456)
    state = checksum(header, endian=endian)
    output = header + struct.pack('>II', *state)
    for pgno, size, page in frames:
        fields = struct.pack('>IIII', pgno, size, 123, 456)
        state = checksum(fields[:8] + page, state, endian)
        output += fields + struct.pack('>II', *state) + page
    return output


def plain_database(path):
    with closing(sqlite3.connect(path)) as c:
        c.execute('PRAGMA page_size=4096')
        c.execute('VACUUM')
    # Reserve SQLCipher's 80-byte IV/MAC region before creating any records.
    raw = bytearray(path.read_bytes())
    raw[20] = 80
    raw[105:107] = (4096 - 80).to_bytes(2, 'big')
    path.write_bytes(raw)
    c = sqlite3.connect(path)
    c.execute('CREATE TABLE records(id INTEGER PRIMARY KEY, name TEXT, time INT)')
    c.execute(f'CREATE INDEX {INDEX} ON records(name,time)')
    c.execute("INSERT INTO records VALUES(1,'before',1)")
    c.commit()
    return c


@pytest.fixture(scope='module')
def keys():
    enc = decrypt._derive_sqlcipher_enc_key(KEY, SALT)
    mac = decrypt._derive_mac_key(enc, SALT)
    return enc, mac


def encrypt_page(page, pgno, keys):
    enc, mac = keys
    iv = bytes(range(16, 32))
    prefix = SALT if pgno == 1 else b''
    start = 16 if pgno == 1 else 0
    cipher = Cipher(algorithms.AES(enc), modes.CBC(iv)).encryptor()
    data = prefix + cipher.update(page[start:4016]) + cipher.finalize() + iv
    digest = hmac.new(mac, data[start:] + pgno.to_bytes(4, 'little'), hashlib.sha512).digest()
    return data + digest


def encrypt_database(data, keys):
    return b''.join(encrypt_page(data[i:i+4096], i//4096+1, keys) for i in range(0, len(data), 4096))


def run_decrypt(src, dst):
    worker = decrypt.WeChatDatabaseDecryptor(KEY.hex())
    ok = worker.decrypt_database(str(src), str(dst))
    return ok, worker.last_result


@pytest.mark.parametrize('encrypted', [False, True])
def test_real_sqlite_wal_commits_are_exported(tmp_path, keys, encrypted):
    src, out = tmp_path/'source.db', tmp_path/'output.db'
    c = plain_database(src)
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA wal_autocheckpoint=0')
    c.execute("UPDATE records SET name='first commit'")
    c.commit()
    c.execute("UPDATE records SET name='latest commit'")
    c.execute("INSERT INTO records VALUES(2,'second row',2)")
    c.commit()
    main, wal = src.read_bytes(), Path(str(src)+'-wal').read_bytes()
    c.close()
    if encrypted:
        frames = []
        for offset in range(32, len(wal), 4120):
            pgno, size = struct.unpack('>II', wal[offset:offset+8])
            frames.append((pgno, size, encrypt_page(wal[offset+24:offset+4120], pgno, keys)))
        wal = wal_bytes(frames)
        main = encrypt_database(main, keys)
    src.write_bytes(main)
    Path(str(src)+'-wal').write_bytes(wal)
    ok, result = run_decrypt(src, out)
    assert ok, result
    assert result['wal']['committed_frames'] > 0
    assert result['key_authenticated'] is encrypted
    assert out.read_bytes()[18:20] == b'\x01\x01'
    with closing(sqlite3.connect(out)) as conn:
        assert conn.execute('SELECT name FROM records ORDER BY id').fetchall() == [('latest commit',), ('second row',)]
        assert conn.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
    assert src.read_bytes() == main
    assert Path(str(src)+'-wal').read_bytes() == wal


def broken_index(tmp_path):
    path = tmp_path/'fixture.db'
    c = plain_database(path)
    before = path.read_bytes()
    index_page = c.execute("SELECT rootpage FROM sqlite_master WHERE type='index'").fetchone()[0]
    c.execute("INSERT INTO records VALUES(2,'new',2)")
    c.commit()
    c.close()
    after = path.read_bytes()
    mixed = bytearray(after)
    offset = (index_page-1)*4096
    mixed[offset:offset+4096] = before[offset:offset+4096]
    return bytes(mixed), after, index_page


@pytest.mark.parametrize('with_wal', [False, True])
def test_issue166_authenticated_index_mismatch_recovers(tmp_path, keys, with_wal):
    mixed, good, pgno = broken_index(tmp_path)
    src, out = tmp_path/'session.db', tmp_path/'out.db'
    encrypted = encrypt_database(mixed, keys)
    src.write_bytes(encrypted)
    if with_wal:
        page = good[(pgno-1)*4096:pgno*4096]
        Path(str(src)+'-wal').write_bytes(wal_bytes([(pgno,len(good)//4096,encrypt_page(page,pgno,keys))]))
    ok, result = run_decrypt(src, out)
    assert ok, result
    assert result['failed_pages'] == result['hmac_warning_pages'] == 0
    assert result['key_authenticated']
    if with_wal:
        assert not result['index_repair']  # WAL fixed it, no REINDEX required.
    else:
        assert result['index_repair']['success']
        assert result['index_repair']['indexes'] == [INDEX]
    with closing(sqlite3.connect(out)) as c:
        assert c.execute('SELECT COUNT(*) FROM records').fetchone() == (2,)
        assert c.execute('PRAGMA integrity_check').fetchone() == ('ok',)
    assert src.read_bytes() == encrypted


@pytest.mark.parametrize('endian', ['<', '>'])
def test_commit_boundaries_recycled_tail_and_truncation(endian):
    a, b, c, d = [bytes([n])*4096 for n in range(4)]
    wal = wal_bytes([(2,2,b), (3,3,c), (2,2,d), (2,0,a)], endian)
    actual, info = merge_wal_snapshot(a+a+a, wal+b'\0'*4120, 4096)
    assert actual == a+d
    assert info['committed_frames'] == 3
    assert info['ignored_tail_bytes'] == 8240


@pytest.mark.parametrize('damage', ['header', 'frame', 'page_size', 'version', 'short', 'growth'])
def test_invalid_wal_is_not_silently_ignored(damage):
    data = b'0'*4096
    wal = bytearray(wal_bytes([(1,1,data)]))
    if damage == 'header': wal[24] ^= 1
    if damage == 'frame': wal[-1] ^= 1
    if damage == 'page_size': wal[8:12] = (8192).to_bytes(4,'big')
    if damage == 'version': wal[4:8] = (0).to_bytes(4,'big')
    if damage == 'short': wal = wal[:16]
    if damage == 'growth': wal = wal_bytes([(1,0xfffffffe,data)])
    with pytest.raises(ValueError): merge_wal_snapshot(data, bytes(wal), 4096)


def test_uncommitted_and_partial_frames_do_not_change_snapshot():
    a, b = b'a'*4096, b'b'*4096
    actual, info = merge_wal_snapshot(a, wal_bytes([(1,1,b), (1,0,a)])[:-100], 4096)
    assert actual == b
    assert info['ignored_tail_bytes'] == 4020
    assert merge_wal_snapshot(a, wal_bytes([(1,0,b)]),4096)[0] == a


def test_valid_wal_checksum_does_not_bypass_page_hmac(tmp_path, keys):
    src, out = tmp_path/'session.db', tmp_path/'out.db'
    conn = plain_database(src); conn.close()
    data = encrypt_database(src.read_bytes(), keys); src.write_bytes(data)
    bad = bytearray(data[4096:8192]); bad[-1] ^= 1
    Path(str(src)+'-wal').write_bytes(wal_bytes([(2,3,bytes(bad))]))
    out.write_bytes(b'previous good output')
    ok, result = run_decrypt(src, out)
    assert not ok and 'HMAC' in result['error']
    assert out.read_bytes() == b'previous good output'
    assert not list(tmp_path.glob('.decrypt-*'))


def test_changing_wal_is_rejected(tmp_path, monkeypatch):
    src = tmp_path/'source.db'; conn = plain_database(src); conn.close()
    original = decrypt._safe_file_snapshot
    calls = 0
    def snapshot(path):
        nonlocal calls
        result = original(path); calls += 1
        if calls == 2: result['siblings']['-wal'] = {'exists': True, 'size': 1}
        return result
    monkeypatch.setattr(decrypt, '_safe_file_snapshot', snapshot)
    ok, result = run_decrypt(src,tmp_path/'out.db')
    assert not ok and result['source_changed_during_read']
    assert not (tmp_path/'out.db').exists()


def test_key_authentication_is_independent_of_output_integrity():
    diagnostics = {name:{'db_name':name, 'key_authenticated':True,
        'key_mode':'sqlcipher_passphrase', 'success':False, 'diagnostic_status':'quick_check_failed'}
        for name in ['session.db','message_0.db']}
    assert _db_key_persistence_rejection({'db_diagnostics':diagnostics}) == ''
    diagnostics['session.db']['key_authenticated'] = False
    assert 'session' in _db_key_persistence_rejection({'db_diagnostics':diagnostics})


def test_table_corruption_is_not_repaired_or_published(tmp_path, keys):
    src = tmp_path/'session.db'; c = plain_database(src); c.close()
    data = bytearray(src.read_bytes()); data[4096] = 0xff
    src.write_bytes(encrypt_database(data,keys))
    ok, result = run_decrypt(src,tmp_path/'out.db')
    assert not ok
    assert not result['index_repair'].get('attempted')
    assert not (tmp_path/'out.db').exists()


def test_partial_output_still_saves_cross_database_authenticated_key(monkeypatch):
    import wechat_decrypt_tool.routers.decrypt as router
    import wechat_decrypt_tool.wcdb_realtime as realtime
    saved = []
    monkeypatch.setattr(router, 'upsert_account_keys_in_store', lambda *a, **kw: saved.append((a,kw)))
    monkeypatch.setattr(realtime.WCDB_REALTIME, 'disconnect', lambda account: None)
    diags = {name: {'db_name':name, 'key_mode':'sqlcipher_passphrase', 'key_authenticated':True,
                   'success':name != 'session.db', 'diagnostic_status':'quick_check_failed' if name == 'session.db' else 'ok'}
             for name in ['session.db','message_0.db']}
    assert router._persist_db_keys({'test_account':{'success':1,'db_diagnostics':diags}},KEY.hex()) == (True,[])
    assert len(saved) == 1
    diags['session.db']['key_authenticated'] = False
    assert router._persist_db_keys({'test_account':{'success':1,'db_diagnostics':diags}},KEY.hex()) == (False,['test_account'])
    assert len(saved) == 1


def test_failed_publication_keeps_previous_output(tmp_path, monkeypatch):
    src, out = tmp_path/'source.db', tmp_path/'output.db'
    c = plain_database(src); c.close()
    out.write_bytes(b'previous good output')
    def fail(*args): raise PermissionError('output busy')
    monkeypatch.setattr(decrypt.os,'replace',fail)
    ok, result = run_decrypt(src,out)
    assert not ok and 'output busy' in result['error']
    assert out.read_bytes() == b'previous good output'
    assert not list(tmp_path.glob('.decrypt-*'))


@pytest.mark.parametrize('alias', ['same_path', 'hardlink', 'symlink'])
def test_source_is_never_overwritten(tmp_path, alias):
    src = tmp_path/'source.db'; c = plain_database(src); c.close()
    original = src.read_bytes(); out = tmp_path/'out.db'
    if alias == 'hardlink': out.hardlink_to(src)
    elif alias == 'symlink':
        try:
            out.symlink_to(src)
        except OSError:
            pytest.skip('Creating symlinks is unavailable on this platform')
    else: out = src
    ok, result = run_decrypt(src,out)
    assert not ok and '源数据库' in result['error']
    assert src.read_bytes() == original


def test_growth_after_truncation_cannot_reuse_discarded_pages():
    a,b,c = b'a'*4096,b'b'*4096,b'c'*4096
    with pytest.raises(ValueError, match='扩展页'):
        merge_wal_snapshot(a+b+c,wal_bytes([(1,1,a),(3,3,c)]),4096)
    result, info = merge_wal_snapshot(a+b+c,wal_bytes([(1,1,a),(2,0,c),(3,3,b)]),4096)
    assert result == a+c+b


def test_old_output_wal_cannot_override_new_output(tmp_path):
    src, out = tmp_path/'source.db',tmp_path/'out.db'
    c = plain_database(src); c.close()
    out.write_bytes(b'previous good output')
    Path(str(out)+'-wal').write_bytes(b'existing log')
    ok, result = run_decrypt(src,out)
    assert not ok and '输出数据库' in result['error']
    assert out.read_bytes() == b'previous good output'
    assert Path(str(out)+'-wal').read_bytes() == b'existing log'


def test_real_sqlite_wal_growth_and_vacuum(tmp_path):
    src, out = tmp_path/'source.db',tmp_path/'out.db'
    c = plain_database(src)
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA wal_autocheckpoint=0')
    c.executemany('INSERT INTO records VALUES(?,?,?)', [(i, 'x'*1000, i) for i in range(2, 100)])
    c.commit()
    expected = c.execute('SELECT COUNT(*) FROM records').fetchone()
    ok, result = run_decrypt(src,out)
    assert ok, result
    with closing(sqlite3.connect(out)) as reader:
        assert reader.execute('SELECT COUNT(*) FROM records').fetchone() == expected
        assert reader.execute('PRAGMA integrity_check').fetchone() == ('ok',)
    c.execute('DELETE FROM records WHERE id > 2'); c.commit()
    c.execute('VACUUM')
    ok, result = run_decrypt(src,out)
    assert ok, result
    with closing(sqlite3.connect(out)) as reader:
        assert reader.execute('SELECT COUNT(*) FROM records').fetchone() == (2,)
        assert reader.execute('PRAGMA integrity_check').fetchone() == ('ok',)
    c.close()
