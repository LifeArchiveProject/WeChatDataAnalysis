#!/usr/bin/env python3
"""调试消息类型返回值"""

import os
import requests

PORT = os.environ.get("WECHAT_TOOL_PORT", "10392")
resp = requests.get(f'http://localhost:{PORT}/api/chat/messages', params={
    'account': 'wxid_v4mbduwqtzpt22',
    'username': 'wxid_qmzc7q0xfm0j22',
    'limit': 100
})
data = resp.json()
messages = data.get('messages', [])

# 找出不同类型的消息
types_found = {}
for m in messages:
    rt = m.get('renderType', 'text')
    if rt not in types_found:
        types_found[rt] = m

print('找到的消息类型:')
for rt, m in types_found.items():
    content = str(m.get('content') or '')[:50]
    print(f"  {rt}: type={m.get('type')}, content={content}")
    if rt == 'emoji':
        print(f"    emojiMd5={m.get('emojiMd5')}")
        print(f"    emojiUrl={m.get('emojiUrl')}")
    if rt == 'image':
        print(f"    imageMd5={m.get('imageMd5')}")
        print(f"    imageUrl={str(m.get('imageUrl') or '')[:80]}")
