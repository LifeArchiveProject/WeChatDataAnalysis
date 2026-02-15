#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
导出微信数据库字段配置为一份 Markdown 文档（单文件）：

- 输入：wechat_db_config.json（由 tools/generate_wechat_db_config.py 生成）
- 输出：Markdown（包含：数据库 → 表/表组 → 字段与含义）

说明：
- 本脚本只基于“配置文件中的结构与字段含义”生成文档，不会读取真实数据内容；
- 会对类似 Msg_<md5> 这类用户相关的哈希表名做脱敏显示。
- 会将“同结构但表名仅数字不同”的重复表自动折叠为一个表组（常见于 FTS 分片/内部表）。

用法示例：
  python tools/export_database_schema_markdown.py \
      --config wechat_db_config.json \
      --output docs/wechat_database_schema.md
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


_HASH_TABLE_RE = re.compile(r"^([A-Za-z0-9]+)_([0-9a-fA-F]{16,})$")


def _md_escape_cell(v: Any) -> str:
    """Escape Markdown table cell content."""
    if v is None:
        return "-"
    s = str(v)
    # Keep it one-line for tables.
    s = s.replace("\r", " ").replace("\n", " ").strip()
    # Escape pipe
    s = s.replace("|", r"\|")
    return s if s else "-"


def _mask_hash_table_name(name: str) -> str:
    """
    Mask user-specific hash suffix table names:
      Msg_00140f... -> Msg_<hash>
    """
    m = _HASH_TABLE_RE.match(name)
    if not m:
        return name
    return f"{m.group(1)}_<hash>"


def _db_sort_key(db_name: str) -> tuple[int, int, str]:
    """
    Roughly sort DBs by importance for readers.
    """
    # Core
    if db_name == "contact":
        return (10, 0, db_name)
    if db_name == "session":
        return (20, 0, db_name)
    m = re.match(r"^message_(\d+)$", db_name)
    if m:
        return (30, int(m.group(1)), db_name)
    if re.match(r"^biz_message_(\d+)$", db_name):
        n = int(re.match(r"^biz_message_(\d+)$", db_name).group(1))  # type: ignore[union-attr]
        return (31, n, db_name)
    if db_name == "message_resource":
        return (40, 0, db_name)
    if db_name == "media_0":
        return (41, 0, db_name)
    if db_name == "hardlink":
        return (42, 0, db_name)
    if db_name == "head_image":
        return (43, 0, db_name)

    # Social / content
    if db_name == "sns":
        return (50, 0, db_name)
    if db_name == "favorite":
        return (60, 0, db_name)
    if db_name == "emoticon":
        return (70, 0, db_name)

    # System / misc
    if db_name in {"general", "unspportmsg"}:
        return (80, 0, db_name)

    # Search / index
    if db_name in {"chat_search_index", "message_fts"} or db_name.endswith("_fts"):
        return (90, 0, db_name)

    # Others
    return (100, 0, db_name)


def _render_message_type_map(message_types: dict[str, Any]) -> str:
    # In Windows WeChat v4, `local_type` is commonly a 64-bit integer:
    #   raw = (sub_type << 32) | type
    # Some configs may still store explicit (type, sub_type) pairs; handle both.
    items: list[tuple[int, int, int, str]] = []
    for k, v in message_types.items():
        if k in {"_instructions", "examples"}:
            continue
        if not isinstance(k, str) or "," not in k:
            continue
        a, b = k.split(",", 1)
        try:
            a_i = int(a)
            b_i = int(b)
        except Exception:
            continue
        desc = str(v)

        if b_i != 0:
            msg_type = a_i
            msg_sub = b_i
            raw = (msg_sub << 32) | (msg_type & 0xFFFFFFFF)
        else:
            raw = a_i
            msg_type = raw & 0xFFFFFFFF
            msg_sub = (raw >> 32) & 0xFFFFFFFF

        items.append((raw, msg_type, msg_sub, desc))

    if not items:
        return ""

    # Sort by decoded (type, sub_type), then raw value.
    items.sort(key=lambda x: (x[1], x[2], x[0]))

    out = "## 消息类型（local_type）速查\n\n"
    out += "说明：Windows 微信 v4 的 `local_type` 常见为 64 位整型：`raw = (sub_type<<32) | type`。\n\n"
    out += "| local_type(raw) | type(low32) | sub_type(high32) | 含义 |\n|---:|---:|---:|---|\n"
    for raw, t, st, desc in items:
        out += f"| {raw} | {t} | {st} | {_md_escape_cell(desc)} |\n"
    return out + "\n"


def _table_schema_signature(table: dict[str, Any]) -> tuple[str, str, tuple[tuple[str, str, str, str], ...]]:
    """
    Build a stable signature for a table schema in config.

    Used to fold tables which are structurally identical but only differ in name
    (e.g. message_fts_v4_aux_0..3).
    """
    t_type = str(table.get("type", "table"))
    desc = str(table.get("description", ""))
    fields = table.get("fields") or {}

    items: list[tuple[str, str, str, str]] = []
    if isinstance(fields, dict):
        for field_name, fm in fields.items():
            if not isinstance(fm, dict):
                fm = {}
            items.append(
                (
                    str(field_name),
                    str(fm.get("type", "")),
                    str(fm.get("meaning", "")),
                    str(fm.get("notes", "")),
                )
            )
    items.sort(key=lambda x: x[0])
    return (t_type, desc, tuple(items))


def _name_family_key(name: str) -> str:
    """Normalize a table name into a family key by replacing digit runs with {n}."""
    return re.sub(r"\d+", "{n}", name)


def _make_group_pattern(table_names: list[str]) -> str:
    """
    Make a readable pattern for a group of similar table names:

    - Only varying numeric segments become `{n}`
    - Constant numeric segments are kept as-is

    Example:
      message_fts_v4_0/message_fts_v4_1 -> message_fts_v4_{n}
      ImgFts0V0/ImgFts1V0 -> ImgFts{n}V0
    """
    if not table_names:
        return ""

    tokenized = [re.split(r"(\d+)", n) for n in table_names]
    base = tokenized[0]

    # Ensure token structures match; otherwise fall back to a simple normalization.
    for t in tokenized[1:]:
        if len(t) != len(base):
            return _name_family_key(table_names[0])
        for i in range(0, len(base), 2):
            if t[i] != base[i]:
                return _name_family_key(table_names[0])

    out_parts: list[str] = []
    for i, part in enumerate(base):
        if i % 2 == 0:
            out_parts.append(part)
            continue
        nums = {t[i] for t in tokenized if i < len(t)}
        out_parts.append(part if len(nums) == 1 else "{n}")
    return "".join(out_parts)


def _fold_same_schema_tables_for_display(
    tables: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """
    Fold duplicated tables that share the same schema/signature but only differ in name.

    This is common in FTS shards, e.g.:
      message_fts_v4_aux_0..3
      message_fts_v4_0..3 and their internal *_content/*_data/*_idx tables
      ImgFts0V0..3 and their internal tables

    Returns a list of (display_name, table_dict) items sorted by the original table name order.
    """
    if not tables:
        return []

    # (family_key, schema_sig) -> [table_name, ...]
    groups: dict[tuple[str, tuple[str, str, tuple[tuple[str, str, str, str], ...]]], list[str]] = {}
    for table_name, table in tables.items():
        if not isinstance(table, dict):
            continue
        if str(table.get("type", "table")) == "similar_group":
            continue
        family = _name_family_key(str(table_name))
        sig = _table_schema_signature(table)
        groups.setdefault((family, sig), []).append(str(table_name))

    consumed: set[str] = set()
    items: list[tuple[str, str, dict[str, Any]]] = []  # (sort_key, display_name, table)
    used_display_names: set[str] = set()

    # Create auto "similar_group" entries for groups > 1.
    for (_, _), names in sorted(groups.items(), key=lambda x: x[0][0]):
        if len(names) <= 1:
            continue
        names_sorted = sorted(names)
        rep = names_sorted[0]
        rep_table = tables.get(rep)
        if not isinstance(rep_table, dict):
            continue
        pattern = _make_group_pattern(names_sorted)
        if not pattern:
            pattern = _name_family_key(rep)

        display_name = pattern
        if display_name in used_display_names:
            # Rare: same name pattern but different schema signatures. Disambiguate.
            n = 2
            while f"{pattern} (var{n})" in used_display_names:
                n += 1
            display_name = f"{pattern} (var{n})"

        group_entry = dict(rep_table)
        group_entry.update(
            {
                "type": "similar_group",
                "pattern": pattern,
                "table_count": len(names_sorted),
                "representative_table": rep,
                "table_names": names_sorted,
            }
        )
        items.append((rep, display_name, group_entry))
        used_display_names.add(display_name)
        consumed.update(names_sorted)

    # Keep non-grouped tables (and existing similar_group) as-is.
    for table_name, table in tables.items():
        if not isinstance(table, dict):
            continue
        if str(table_name) in consumed:
            continue
        items.append((str(table_name), str(table_name), table))

    items.sort(key=lambda x: (x[0], x[1]))
    return [(display_name, table) for _, display_name, table in items]


def export_markdown(config_path: Path, output_path: Path) -> None:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    meta = cfg.get("_metadata") or {}
    databases: dict[str, Any] = cfg.get("databases") or {}

    # message_{n}.db are typically shards with identical schema. Keep only the last shard for detailed sections.
    message_shards: list[tuple[int, str]] = []
    for name in databases.keys():
        m = re.match(r"^message_(\d+)$", str(name))
        if not m:
            continue
        try:
            message_shards.append((int(m.group(1)), str(name)))
        except Exception:
            continue
    message_shards.sort(key=lambda x: x[0])
    rep_message_db: str | None = message_shards[-1][1] if message_shards else None
    all_message_db_names = [n for _, n in message_shards]

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    gen_time = meta.get("generated_time") or now

    lines: list[str] = []
    lines.append("# Windows 微信数据库结构文档（自动生成）")
    lines.append("")
    lines.append(f"> 生成时间：{_md_escape_cell(gen_time)}")
    lines.append(f"> 本次导出：{now}")
    lines.append(f"> 配置来源：`{config_path.as_posix()}`（由 `tools/generate_wechat_db_config.py` 生成）")
    lines.append("")
    lines.append("参考资料：")
    lines.append("- `万字长文带你了解Windows微信.md`（目录结构/部分表结构与含义）")
    lines.append("- 本项目前端页面与后端解析逻辑（字段命名与用途）")
    lines.append("")
    lines.append("注意：")
    lines.append("- 本文档尽量覆盖“库/表/字段”，字段含义部分来自启发式与公开资料，可能存在不准确之处。")
    lines.append("- 为避免泄露个人数据，类似 `Msg_<md5>` 的哈希表名会脱敏显示。")
    lines.append("- 部分 FTS 虚表可能依赖微信自定义 tokenizer（如 `MMFtsTokenizer`），普通 sqlite 环境下查询会报错；本文档字段来自建表 SQL/模板解析。")
    lines.append("")

    # Overview
    lines.append("## 数据库总览")
    lines.append("")
    lines.append("| 数据库 | 描述 | 表数量 |")
    lines.append("|---|---|---:|")

    for db_name in sorted(databases.keys(), key=_db_sort_key):
        db = databases.get(db_name) or {}
        if not isinstance(db, dict):
            continue
        desc = db.get("description", "")
        tables = db.get("tables") or {}
        lines.append(
            f"| `{db_name}.db` | {_md_escape_cell(desc)} | {len(tables) if isinstance(tables, dict) else 0} |"
        )
    lines.append("")

    lines.append("## 本项目（前端）功能与数据库大致对应")
    lines.append("")
    lines.append("- 联系人/群聊：`contact.db`（contact/chat_room/chatroom_member/label 等）")
    lines.append("- 会话列表/未读：`session.db`（通常为 SessionTable/ChatInfo 等）")
    lines.append("- 聊天记录：`message_*.db`（`Msg_*` 表组 + `Name2Id` 映射等）")
    lines.append("- 消息资源/媒体：`message_resource.db` / `hardlink.db` / `media_0.db` / `head_image.db`")
    lines.append("- 朋友圈：`sns.db`")
    lines.append("- 收藏：`favorite.db`")
    lines.append("- 表情包：`emoticon.db`")
    lines.append("- 搜索：`chat_search_index.db` / `message_fts.db` / `*_fts.db`（不同版本/实现可能不同）")
    lines.append("")

    # Per DB
    for db_name in sorted(databases.keys(), key=_db_sort_key):
        # Skip duplicated details for message shards; only keep the last shard as representative.
        if rep_message_db and re.match(r"^message_\d+$", str(db_name)) and str(db_name) != rep_message_db:
            continue

        db = databases.get(db_name) or {}
        if not isinstance(db, dict):
            continue

        desc = db.get("description", "")
        tables = db.get("tables") or {}
        if not isinstance(tables, dict):
            tables = {}

        display_table_items = _fold_same_schema_tables_for_display(tables)
        display_table_count = len(display_table_items)

        lines.append(f"## {db_name}.db")
        lines.append("")
        lines.append(f"- 描述：{_md_escape_cell(desc)}")
        if display_table_count != len(tables):
            lines.append(f"- 表数量：{len(tables)}（同结构表折叠后展示 {display_table_count}）")
        else:
            lines.append(f"- 表数量：{len(tables)}")
        lines.append("")

        # Extra note for message shards
        if re.match(r"^message_\d+$", db_name):
            if rep_message_db and db_name == rep_message_db and len(all_message_db_names) > 1:
                others = [n for n in all_message_db_names if n != rep_message_db]
                # Keep it short; avoid blowing up the doc with too many names if there are lots of shards.
                if len(others) <= 10:
                    lines.append(f"本节仅展示最后一个分片 `{rep_message_db}.db` 的结构；其它分片结构通常一致：{', '.join([f'`{n}.db`' for n in others])}。")
                else:
                    lines.append(
                        f"本节仅展示最后一个分片 `{rep_message_db}.db` 的结构；其它分片（{len(others)} 个）结构通常一致。"
                    )
            lines.append("说明：")
            lines.append("- `Msg_*` 表组通常对应“每个联系人/会话一个表”，常见命名为 `Msg_{md5(wxid)}`。")
            lines.append("- 可通过对 wxid 做 md5 计算定位具体会话表；或结合 `Name2Id`/`name2id` 映射表进行解析。")
            lines.append("")
            lines.append("示例（Python）：")
            lines.append("")
            lines.append("```python")
            lines.append("import hashlib")
            lines.append("")
            lines.append("wxid = \"wxid_xxx\"")
            lines.append("md5_hex = hashlib.md5(wxid.encode(\"utf-8\")).hexdigest()")
            lines.append("table = f\"Msg_{md5_hex}\"")
            lines.append("print(table)")
            lines.append("```")
            lines.append("")

        # Tables
        for table_name, table in display_table_items:
            if not isinstance(table, dict):
                continue

            t_type = table.get("type", "table")
            t_desc = table.get("description", "")

            # Table header
            display_table_name = _mask_hash_table_name(table_name)
            lines.append(f"### {display_table_name}")
            lines.append("")
            if t_desc:
                lines.append(f"- 描述：{_md_escape_cell(t_desc)}")
            if t_type == "similar_group":
                pat = table.get("pattern") or display_table_name
                rep = table.get("representative_table")
                table_count = table.get("table_count")
                lines.append(f"- 类型：相似表组（pattern: `{_md_escape_cell(pat)}`）")
                if table_count is not None:
                    lines.append(f"- 表数量：{_md_escape_cell(table_count)}")
                if rep:
                    rep_s = str(rep)
                    rep_masked = _mask_hash_table_name(rep_s)
                    rep_note = "（已脱敏）" if rep_masked != rep_s else ""
                    lines.append(f"- 代表表：`{_md_escape_cell(rep_masked)}`{rep_note}")

                members = table.get("table_names") or table.get("tables")
                if isinstance(members, list) and members:
                    member_names = [str(x) for x in members]
                    member_names = [_mask_hash_table_name(n) for n in member_names]
                    if len(member_names) <= 20:
                        show = member_names
                        suffix = ""
                    else:
                        show = member_names[:10] + ["..."] + member_names[-5:]
                        suffix = f"（共 {len(member_names)} 个）"
                    parts = [f"`{_md_escape_cell(n)}`" if n != "..." else "..." for n in show]
                    lines.append(f"- 包含表：{', '.join(parts)}{suffix}")
            lines.append("")

            fields = table.get("fields") or {}
            if not isinstance(fields, dict) or not fields:
                lines.append("_无字段信息_\n")
                continue

            lines.append("| 字段 | 类型 | 含义 | 备注 |")
            lines.append("|---|---|---|---|")
            for field_name in sorted(fields.keys()):
                fm = fields.get(field_name) or {}
                if not isinstance(fm, dict):
                    fm = {}
                f_type = fm.get("type", "")
                meaning = fm.get("meaning", "")
                notes = fm.get("notes", "")
                lines.append(
                    f"| `{_md_escape_cell(field_name)}` | `{_md_escape_cell(f_type)}` | {_md_escape_cell(meaning)} | {_md_escape_cell(notes)} |"
                )
            lines.append("")

    # Appendices
    message_types = cfg.get("message_types") or {}
    if isinstance(message_types, dict) and message_types:
        mt = _render_message_type_map(message_types)
        if mt:
            lines.append(mt)

    friend_types = cfg.get("friend_types") or {}
    if isinstance(friend_types, dict) and friend_types:
        # friend_types in config usually uses string keys
        items: list[tuple[int, str]] = []
        for k, v in friend_types.items():
            if k in {"_instructions", "examples"}:
                continue
            try:
                items.append((int(str(k)), str(v)))
            except Exception:
                continue
        items.sort(key=lambda x: x[0])

        if items:
            lines.append("## 联系人类型（friend_type）速查\n")
            lines.append("| 值 | 含义 |\n|---:|---|\n")
            for code, desc in items:
                lines.append(f"| {code} | {_md_escape_cell(desc)} |")
            lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="导出微信数据库字段配置为 Markdown 文档（单文件）")
    parser.add_argument(
        "--config",
        default=str(ROOT / "wechat_db_config.json"),
        help="wechat_db_config.json 路径（由 tools/generate_wechat_db_config.py 生成）",
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "docs" / "wechat_database_schema.md"),
        help="Markdown 输出路径",
    )
    args = parser.parse_args()

    cfg = Path(args.config)
    if not cfg.exists():
        raise FileNotFoundError(f"未找到配置文件: {cfg}，请先运行 tools/generate_wechat_db_config.py")

    out = Path(args.output)
    export_markdown(cfg, out)
    print(f"[OK] 写出 Markdown: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
