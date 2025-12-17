#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
导出微信数据库分析结果为 JSON：
- 基于 analyze_wechat_databases.WeChatDatabaseAnalyzer
- 联合 wechat_db_config.json（含 ohmywechat 常见类型与启发式）补全字段含义
- 生成汇总 JSON 与按库拆分的 JSON 文件

用法:
  python tools/export_database_schema_json.py \
      --databases-path output/databases \
      --output-dir output/schema_json \
      --config wechat_db_config.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
import sys

# 项目根目录
ROOT = Path(__file__).resolve().parents[1]
# 确保能导入项目根目录下的 analyze_wechat_databases.py
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def export_analysis(databases_path: Path, output_dir: Path, config_file: Path) -> int:
    # 延迟导入分析器
    from analyze_wechat_databases import WeChatDatabaseAnalyzer

    output_dir.mkdir(parents=True, exist_ok=True)

    analyzer = WeChatDatabaseAnalyzer(databases_path=str(databases_path), config_file=str(config_file))
    results = analyzer.analyze_all_databases()  # dict[db_name] = db_info

    meta = {
        "generated_time": datetime.now().isoformat(),
        "source": "analyze_wechat_databases.py",
        "config_used": str(config_file),
        "databases_root": str(databases_path),
        "note": "字段含义来自 wechat_db_config.json 与启发式推断（结合 ohmywechat 常见类型）",
    }

    combined: Dict[str, Any] = {"_metadata": meta, "databases": {}}

    count_dbs = 0
    for db_name, db_info in results.items():
        count_dbs += 1
        db_out: Dict[str, Any] = {
            "database_name": db_info.get("database_name", db_name),
            "database_path": db_info.get("database_path"),
            "database_size": db_info.get("database_size"),
            "description": db_info.get("description"),
            "table_count": db_info.get("table_count"),
            "tables": {},
        }

        tables = db_info.get("tables", {})
        for table_name, table in tables.items():
            # 列增强：补充 meaning
            cols_out = []
            for col in table.get("columns", []):
                name = col.get("name")
                meaning = analyzer.get_field_meaning(name, table_name) if name else ""
                cols_out.append({
                    "name": name,
                    "type": col.get("type"),
                    "notnull": col.get("notnull"),
                    "default": col.get("dflt_value"),
                    "pk": col.get("pk"),
                    "meaning": meaning,
                })

            tbl_out = {
                "row_count": table.get("row_count", 0),
                "columns": cols_out,
                "indexes": table.get("indexes", []),
                "foreign_keys": table.get("foreign_keys", []),
                "create_sql": table.get("create_sql"),
                "sample_data": table.get("sample_data", []),
                # 相似组标记（如 Msg_* 合并）
                "is_representative": table.get("is_representative", False),
                "similar_group": table.get("similar_group", {}),
            }

            db_out["tables"][table_name] = tbl_out

        # 写入单库 JSON
        single_path = output_dir / f"{db_name}.schema.json"
        with single_path.open("w", encoding="utf-8") as f:
            json.dump(db_out, f, ensure_ascii=False, indent=2)

        combined["databases"][db_name] = db_out

        print(f"[OK] 写出数据库JSON: {single_path.name}")

    # 汇总文件
    combined_path = output_dir / "all_databases.schema.json"
    with combined_path.open("w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    print(f"[OK] 汇总JSON: {combined_path} （数据库数: {count_dbs}）")
    return count_dbs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--databases-path", default=str(ROOT / "output" / "databases"),
                        help="解密后的数据库根目录（按账号分目录）")
    parser.add_argument("--output-dir", default=str(ROOT / "output" / "schema_json"),
                        help="JSON 输出目录")
    parser.add_argument("--config", default=str(ROOT / "wechat_db_config.json"),
                        help="字段含义配置 JSON（由 tools/generate_wechat_db_config.py 生成）")
    args = parser.parse_args()

    db_root = Path(args.databases_path)
    out_dir = Path(args.output_dir)
    cfg = Path(args.config)

    if not cfg.exists():
        raise FileNotFoundError(f"未找到配置文件: {cfg}，请先运行 tools/generate_wechat_db_config.py")

    if not db_root.exists():
        print(f"[WARN] 数据库目录不存在: {db_root}，仍将生成空汇总文件。")

    count = export_analysis(db_root, out_dir, cfg)
    if count == 0:
        print("[INFO] 未检测到可分析数据库（可先运行解密流程或确认路径）")


if __name__ == "__main__":
    main()