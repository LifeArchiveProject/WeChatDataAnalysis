"""小程序和小游戏缩略图应解密为导出包内图片，不能把 CDN 标识当作网址。"""
import hashlib
import io
import json
import sqlite3
import zipfile

import pytest
from PIL import Image

import test_chat_export_message_types_semantics as fixtures

TOKEN = '305f020100044b304902010002049d2d866202033d11ff0204fcbe9b2402046ab09bab042437313832343830662d633664382d343565622d623533392d663330386362666335343065020405140803020100040d004c4dff000000000000000000'


@pytest.mark.parametrize('app_type', [33, 36])
@pytest.mark.parametrize('scenario', ['encrypted', 'token_file', 'other_chat', 'missing', 'invalid', 'disabled', 'privacy', 'http'])
def test_json_export_localizes_mini_program_thumbnail(tmp_path, monkeypatch, app_type, scenario):
    monkeypatch.setenv('WECHAT_TOOL_DATA_DIR', str(tmp_path))
    helper = fixtures.TestChatExportMessageTypesSemantics()
    account, username = 'wxid_test', 'wxid_friend'
    account_dir = helper._prepare_account(tmp_path, account=account, username=username)
    svc = helper._reload_export_modules()
    table = 'msg_' + hashlib.md5(username.encode()).hexdigest()
    thumbnail = 'https://example.invalid/preview.png' if scenario == 'http' else TOKEN
    xml = f'<msg><appmsg><type>{app_type}</type><title>测试小程序</title><url>https://example.invalid/app</url><appattach><cdnthumburl>{thumbnail}</cdnthumburl></appattach><weappinfo><username>gh_test@app</username></weappinfo></appmsg></msg>'
    with sqlite3.connect(account_dir / 'message_0.db') as db:
        db.execute(f'DELETE FROM {table}')
        db.execute(f'INSERT INTO {table} VALUES (?,?,?,?,?,?,?,?)', (7, 1007, 49+(app_type<<32), 1, 2, 1735689600, xml, None))
    buffer = io.BytesIO()
    Image.new('RGB', (8, 8), color='red').save(buffer, format='PNG')
    png = buffer.getvalue()
    media_username = 'wxid_other' if scenario == 'other_chat' else username
    filename = f'{TOKEN}.dat' if scenario == 'token_file' else '7_1735689600_t.dat'
    media = tmp_path / 'wxid_data' / account / 'msg/attach' / hashlib.md5(media_username.encode()).hexdigest() / '2025-01/Img' / filename
    media.parent.mkdir(parents=True, exist_ok=True)
    if scenario != 'missing':
        media.write_bytes(b'not-an-image' if scenario == 'invalid' else bytes(b ^ 0x66 for b in png))
    job = helper._create_job(svc.CHAT_EXPORT_MANAGER, account=account, username=username,
        message_types=['link'], include_media=scenario != 'disabled', media_kinds=['image'], privacy_mode=scenario == 'privacy')
    assert job.status == 'done', job.error
    with zipfile.ZipFile(job.zip_path) as archive:
        payload = json.loads(archive.read(next(p for p in archive.namelist() if p.endswith('/messages.json'))))
        message = payload['messages'][0]
        images = [p for p in archive.namelist() if p.startswith('media/images/')]
        if scenario in {'encrypted', 'token_file'}:
            assert message['linkType'] == 'mini_program'
            assert message['thumbUrl'] in images
            assert archive.read(message['thumbUrl']) == png
            assert message['offlineMedia'][0]['path'] == message['thumbUrl']
            assert job.progress.media_copied == 1
        else:
            assert not images
            assert not message.get('offlineMedia')
            if scenario == 'privacy':
                assert not message.get('thumbUrl')
            else:
                assert message['thumbUrl'] == thumbnail
            if scenario in {'missing', 'invalid', 'other_chat'}:
                assert job.progress.media_missing == 1
