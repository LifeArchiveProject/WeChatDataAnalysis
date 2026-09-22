#!/usr/bin/env python3
"""生成完全虚构、且真实经过 WCDB 加密的演示账号，用于开发、测试与截图。

与 ``tools/seed_ai_acceptance.py`` 的区别：后者生成的是**明文** SQLite，只覆盖
AI 验收场景；本脚本生成的是**逐页 AES-CBC + 逐页 HMAC 的微信 4.x 加密库**，
因此可以驱动完整的「密钥 -> 解密 -> 解析 -> 展示」链路，也不需要任何真实微信数据。

用途
----
- 贡献者在没有真实微信环境时跑通解密与读取流程；
- 截图、文档、演示视频使用可公开的虚构数据；
- 回归测试需要「真实加密格式 + 真实表结构」的样本。

所有姓名、群名、正文都带「示例」标记；域名统一 example.com；电话 13800000000。

用法::

    python tools/seed_demo_database.py                                    # 输出到 output/demo
    python tools/seed_demo_database.py --check                            # 解密器自校验
    python tools/seed_demo_database.py --output /tmp/demo-account         # 指定输出目录

默认输出到 ``output/demo``，该目录已被 ``/output/`` 规则忽略；脚本只写
``--output`` 指定的目录，不读取也不修改任何真实微信目录。
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sqlite3
import struct
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wechat_decrypt_tool.wechat_decrypt import (  # noqa: E402
    HMAC_SIZE,
    IV_SIZE,
    KEY_SIZE,
    PAGE_SIZE,
    RESERVE_SIZE,
    SALT_SIZE,
    _derive_mac_key,
    _derive_sqlcipher_enc_key,
)

DEMO_ACCOUNT = "wxid_demo_2026"
DEMO_DISPLAY_NAME = "示例账号"
# 固定密钥：公开样本库不需要保密，固定值让同一提交产出可复现的库结构。
DEMO_KEY = hashlib.sha256(b"wechat-data-analysis-demo-key").hexdigest()
DEMO_ALIAS = "demo_user"

EXAMPLE_URL = "https://example.com"

# 群聊房间号固定为示例值，避免与任何真实群聊撞号。
DEMO_GROUP = "10000000001@chatroom"


def _derive_keys(key_hex: str, salt: bytes) -> tuple[bytes, bytes]:
    key_material = bytes.fromhex(key_hex)
    enc_key = _derive_sqlcipher_enc_key(key_material, salt)
    mac_key = _derive_mac_key(enc_key, salt)
    return enc_key, mac_key


def encrypt_wcdb(plain: bytes, key_hex: str) -> bytes:
    """把明文 SQLite 整库加密为微信 4.x 页面格式（``wechat_decrypt`` 的逆过程）。

    每页布局：``[salt(仅第 1 页)] + ciphertext + iv + hmac``，其中密文长度为
    ``PAGE_SIZE - RESERVE_SIZE - salt_offset``；HMAC 覆盖密文与 IV，再拼小端页码。
    """
    if len(plain) % PAGE_SIZE != 0:
        raise ValueError("待加密数据库必须严格按 4096 字节分页")

    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    salt = os.urandom(SALT_SIZE)
    enc_key, mac_key = _derive_keys(key_hex, salt)

    out = bytearray()
    for page_num in range(1, len(plain) // PAGE_SIZE + 1):
        start = (page_num - 1) * PAGE_SIZE
        chunk = plain[start : start + PAGE_SIZE]
        offset = SALT_SIZE if page_num == 1 else 0
        payload = chunk[offset : PAGE_SIZE - RESERVE_SIZE]
        iv = os.urandom(IV_SIZE)
        cipher = Cipher(
            algorithms.AES(enc_key), modes.CBC(iv), backend=default_backend()
        )
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(payload) + encryptor.finalize()
        digest = hmac.new(mac_key, digestmod=hashlib.sha512)
        digest.update(ciphertext)
        digest.update(iv)
        digest.update(page_num.to_bytes(4, "little"))
        page = (salt if page_num == 1 else b"") + ciphertext + iv + digest.digest()
        if len(page) != PAGE_SIZE:
            raise AssertionError(f"第 {page_num} 页长度异常: {len(page)}")
        out += page
    return bytes(out)


def _patch_reserved_space(path: Path) -> None:
    """把明文库改成每页预留 80 字节（与解密还原后的页面布局一致）。

    ``PRAGMA user_version`` 只写文件头、不产生任何 cell，因此页尾预留区保持空闲；
    随后必须把 page1 btree 头的「cell 内容区起始」从 4096 改成 4096-80，否则
    SQLite 会按原页头判定空闲空间，报 ``database disk image is malformed``。
    """
    with path.open("r+b") as handle:
        handle.seek(20)
        handle.write(bytes([RESERVE_SIZE]))
        handle.seek(100 + 5)
        handle.write(struct.pack(">H", PAGE_SIZE - RESERVE_SIZE))


def create_plain_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    bootstrap = sqlite3.connect(path)
    bootstrap.execute("PRAGMA user_version=1")
    bootstrap.commit()
    bootstrap.close()
    _patch_reserved_space(path)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=DELETE")
    return conn


def _timestamp(days_ago: float, hour: int, minute: int) -> int:
    base = time.time() - days_ago * 86400
    local = time.localtime(base)
    return int(
        time.mktime(
            (local.tm_year, local.tm_mon, local.tm_mday, hour, minute, 0, 0, 0, -1)
        )
    )


def _message(
    local_id: int,
    sender_rowid: int,
    local_type: int,
    created_at: int,
    content: str,
    compress_flag: int = 0,
) -> tuple:
    server_id = 880000000 + local_id * 13
    return (
        local_id,
        server_id,
        local_type,
        sender_rowid,
        created_at,
        content,
        b"",
        b"",
        compress_flag,
    )


def build_message_database(path: Path) -> None:
    conn = create_plain_database(path)
    cur = conn.cursor()

    # 真实微信的 Name2Id 不包含账号本人；本人由「出现在全部单聊表中的
    # real_sender_id」判定，因此这里保持同样的结构，聊天列表才不会多出一条。
    name2id = [
        (2, "wxid_demo_zhangwei"),
        (3, "wxid_demo_liting"),
        (4, "wxid_demo_wangfang"),
        (5, "wxid_demo_liuyang"),
        (6, DEMO_GROUP),
    ]
    cur.execute("CREATE TABLE Name2Id (user_name TEXT)")
    cur.executemany("INSERT INTO Name2Id (rowid, user_name) VALUES (?, ?)", name2id)

    chats: dict[str, list[tuple]] = {}

    # --- 群聊：覆盖文字、链接卡片、系统消息、表情、引用 ---
    rows: list[tuple] = []
    ts = _timestamp(2, 9, 15)
    rows.append(_message(1, 4, 1, ts, "各位早上好，今天十点对齐一下示例项目的排期"))
    rows.append(_message(2, 2, 1, ts + 180, "收到，上周的示例数据我已经整理好了"))
    rows.append(_message(3, 3, 1, ts + 240, "示例模块的联调环境已经部署到测试服"))
    rows.append(_message(4, 1, 1, ts + 400, "辛苦大家，会议链接稍后发到群里"))
    rows.append(
        _message(
            5,
            5,
            49,
            ts + 420,
            "<msg><appmsg><title>示例项目排期表（9 月）</title>"
            "<des>包含里程碑与分工的示例文档</des><type>5</type>"
            f"<url>{EXAMPLE_URL}/docs/demo-plan</url></appmsg></msg>",
        )
    )
    rows.append(
        _message(6, 1, 10000, ts + 500, "示例-李婷 邀请 示例-王芳 加入了群聊")
    )
    rows.append(_message(7, 4, 1, ts + 700, "欢迎新同事，示例团队欢迎你"))
    rows.append(
        _message(
            8,
            2,
            49,
            ts + 900,
            "<msg><appmsg><title>示例接口文档 v2</title>"
            "<des>更新了示例接口的返回结构</des><type>57</type>"
            f"<url>{EXAMPLE_URL}/docs/demo-api</url>"
            "<refermsg><type>1</type><svrid>8800000014</svrid>"
            f"<fromusr>{DEMO_GROUP}</fromusr><chatusr>wxid_demo_liuyang</chatusr>"
            "<displayname>示例-刘洋</displayname>"
            "<content>示例接口的返回结构谁能同步一下？</content></refermsg></appmsg></msg>",
        )
    )
    rows.append(_message(9, 3, 47, ts + 960, "[示例表情]"))
    rows.append(_message(10, 1, 1, _timestamp(0, 9, 41), "上午的示例评审结论我整理好了，下午发出来"))
    rows.append(_message(11, 5, 1, _timestamp(0, 9, 45), "收到，示例版本的发布时间定在周五"))
    chats[DEMO_GROUP] = rows

    # --- 单聊：日常闲聊 ---
    rows = []
    ts = _timestamp(1, 20, 10)
    rows.append(_message(1, 2, 1, ts, "周末的示例聚会你来吗？"))
    rows.append(_message(2, 1, 1, ts + 120, "来，示例场地我已经订好了"))
    rows.append(_message(3, 2, 1, ts + 200, "那我把示例名单统计一下"))
    rows.append(
        _message(
            4,
            2,
            49,
            ts + 300,
            "<msg><appmsg><title>示例餐厅订座确认</title>"
            "<des>周六 18:00，8 人桌</des><type>5</type>"
            f"<url>{EXAMPLE_URL}/booking/demo123</url></appmsg></msg>",
        )
    )
    rows.append(_message(5, 1, 1, _timestamp(0, 8, 30), "早，通勤路上听了你推荐的示例播客，不错"))
    rows.append(_message(6, 2, 1, _timestamp(0, 8, 42), "示例播客是我最近的下饭神器"))
    chats["wxid_demo_zhangwei"] = rows

    # --- 单聊：出行计划（含转账卡片）---
    rows = []
    ts = _timestamp(3, 15, 20)
    rows.append(_message(1, 3, 1, ts, "示例城市这周末天气不错，适合去拍外景"))
    rows.append(_message(2, 1, 1, ts + 200, "好，示例相机的电池我充上"))
    rows.append(
        _message(
            3,
            3,
            49,
            ts + 600,
            "<msg><appmsg><title>示例民宿预订</title>"
            "<des>两晚套房，含示例早餐</des><type>5</type>"
            f"<url>{EXAMPLE_URL}/stay/demo-room</url></appmsg></msg>",
        )
    )
    rows.append(
        _message(
            4,
            1,
            49,
            ts + 800,
            "<msg><appmsg><title>微信转账</title><type>2000</type>"
            "<wcpayinfo><feedesc>¥288.00</feedesc>"
            "<paysubtype>1</paysubtype></wcpayinfo></appmsg></msg>",
        )
    )
    rows.append(_message(5, 3, 1, ts + 900, "示例民宿的定金我收到了，周五出发"))
    chats["wxid_demo_liting"] = rows

    # --- 单聊：工作对接（含语音消息占位）---
    rows = []
    ts = _timestamp(0, 9, 2)
    rows.append(_message(1, 4, 1, ts, "示例报告初稿在附件里，麻烦帮忙看看第二部分"))
    rows.append(_message(2, 1, 1, ts + 300, "收到，我十一点前把批注发你"))
    rows.append(_message(3, 4, 34, ts + 600, ""))
    rows.append(_message(4, 4, 1, ts + 700, "语音里说的示例口径以文档为准"))
    chats["wxid_demo_wangfang"] = rows

    # --- 单聊：发布检查 ---
    rows = []
    ts = _timestamp(1, 16, 40)
    rows.append(_message(1, 5, 1, ts, "示例环境的冒烟测试我跑完了，全部通过"))
    rows.append(_message(2, 1, 1, ts + 400, "效率很高，示例包我来打"))
    rows.append(_message(3, 5, 1, ts + 800, "好，打完包我在群里同步"))
    chats["wxid_demo_liuyang"] = rows

    for talker, chat_rows in chats.items():
        table = "Msg_" + hashlib.md5(talker.encode("utf-8")).hexdigest()
        cur.execute(
            f"""CREATE TABLE [{table}] (
                local_id INTEGER, server_id INTEGER, local_type INTEGER,
                real_sender_id INTEGER, create_time INTEGER,
                message_content BLOB, source BLOB, packed_info_data BLOB,
                WCDB_CT_message_content INTEGER)"""
        )
        cur.executemany(
            f"INSERT INTO [{table}] VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", chat_rows
        )

    conn.commit()
    status = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if status != "ok":
        raise AssertionError(f"message 库完整性检查失败: {status}")
    conn.close()


def build_contact_database(path: Path) -> None:
    conn = create_plain_database(path)
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE Contact (
            user_name TEXT, nick_name TEXT, remark TEXT, alias TEXT,
            description TEXT, local_type INTEGER)"""
    )
    rows = [
        (DEMO_ACCOUNT, DEMO_DISPLAY_NAME, "", DEMO_ALIAS, "示例账号自我介绍", 1),
        ("wxid_demo_zhangwei", "示例-张伟", "示例-张伟", "demo_zw", "示例好友：产品同事", 1),
        ("wxid_demo_liting", "示例-李婷", "示例-李婷", "demo_lt", "示例好友：摄影搭子", 1),
        ("wxid_demo_wangfang", "示例-王芳", "示例-王芳", "demo_wf", "示例好友：报告对接", 1),
        ("wxid_demo_liuyang", "示例-刘洋", "示例-刘洋", "demo_ly", "示例好友：测试同事", 1),
        (DEMO_GROUP, "示例-产品讨论群", "", "", "示例群聊", 2),
    ]
    cur.executemany("INSERT INTO Contact VALUES (?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    status = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if status != "ok":
        raise AssertionError(f"contact 库完整性检查失败: {status}")
    conn.close()


def _write_encrypted(plain_db: Path, target: Path) -> None:
    plain = plain_db.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encrypt_wcdb(plain, DEMO_KEY))


def seed(output: Path) -> dict[str, Path]:
    account_root = output / "databases" / DEMO_ACCOUNT
    message_dir = account_root / "db_storage" / "message"
    contact_dir = account_root / "db_storage" / "contact"

    work_dir = output / "_plain"
    work_dir.mkdir(parents=True, exist_ok=True)
    plain_message = work_dir / "message_0.plain.db"
    plain_contact = work_dir / "contact.plain.db"

    build_message_database(plain_message)
    build_contact_database(plain_contact)
    _write_encrypted(plain_message, message_dir / "message_0.db")
    _write_encrypted(plain_contact, contact_dir / "contact.db")

    keys_path = output / "demo_keys.json"
    keys_path.write_text(
        json.dumps(
            {
                DEMO_ACCOUNT: {
                    "key": DEMO_KEY,
                    "display_name": DEMO_DISPLAY_NAME,
                    "alias": DEMO_ALIAS,
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "account_root": account_root,
        "message_db": message_dir / "message_0.db",
        "contact_db": contact_dir / "contact.db",
        "keys": keys_path,
    }


def _self_check(paths: dict[str, Path]) -> None:
    """用项目自身的扫描与解密链路验证样本可被真实读取。"""
    from wechat_decrypt_tool.wechat_decrypt import (
        decrypt_wechat_databases,
        scan_account_databases_from_path,
    )

    db_storage = paths["account_root"] / "db_storage"
    scanned = scan_account_databases_from_path(str(db_storage))
    if not scanned:
        raise AssertionError("扫描演示账号时没有发现任何数据库")

    result = decrypt_wechat_databases(str(db_storage), DEMO_KEY)
    if result.get("status") != "success" or not result.get("successful_count"):
        raise AssertionError(f"演示账号解密失败: {result}")

    total = result.get("total_databases")
    success = result.get("successful_count")
    if result.get("failed_count"):
        raise AssertionError(f"演示账号存在解密失败的库: {result.get('failed_files')}")

    # 解密产物必须真的是可读 SQLite，且包含我们写入的表。
    output_dir = Path(str(result.get("output_directory") or ""))
    for label, expected_table in (("message", "Name2Id"), ("contact", "Contact")):
        candidates = sorted(output_dir.rglob(f"{label}*.db")) + sorted(
            output_dir.rglob(f"{label}.db")
        )
        if not candidates:
            raise AssertionError(f"解密输出中找不到 {label} 库: {output_dir}")
        conn = sqlite3.connect(candidates[0])
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        finally:
            conn.close()
        if integrity != "ok":
            raise AssertionError(f"{label} 解密后完整性检查失败: {integrity}")
        if expected_table not in tables:
            raise AssertionError(f"{label} 解密后缺少表 {expected_table}: {tables}")

    print(f"自校验通过：扫描到 {len(scanned)} 个数据库，成功解密 {success}/{total} 个")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成虚构的微信 4.x 加密演示账号")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "output" / "demo",
        help="输出目录（默认 output/demo，已随 /output/ 一起被忽略）",
    )
    parser.add_argument(
        "--check", action="store_true", help="生成后用项目解密器自校验"
    )
    args = parser.parse_args()

    output = args.output.resolve()
    paths = seed(output)

    print(f"演示账号: {DEMO_ACCOUNT}（显示名 {DEMO_DISPLAY_NAME}）")
    print(f"账号目录: {paths['account_root']}")
    print(f"消息库:   {paths['message_db']}")
    print(f"联系人库: {paths['contact_db']}")
    print(f"密钥文件: {paths['keys']}")
    print(f"演示密钥: {DEMO_KEY}")

    if args.check:
        _self_check(paths)
    return 0


if __name__ == "__main__":
    sys.exit(main())
