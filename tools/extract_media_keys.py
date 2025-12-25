#!/usr/bin/env python3
"""
已废弃：本项目不再提供任何密钥提取流程。

请使用 wx_key 获取数据库/图片密钥：
https://github.com/ycccccccy/wx_key

获取到图片密钥后，可在前端「图片密钥」步骤填写并保存，
或调用后端接口保存：

  POST /api/media/keys
  body: { "xor_key": "0xA5", "aes_key": "xxxxxxxxxxxxxxxx" }
"""

from __future__ import annotations

import sys


def main():
    print("[DEPRECATED] 本项目不再提供密钥提取流程。")
    print("请使用 wx_key 获取密钥：https://github.com/ycccccccy/wx_key")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
