#!/usr/bin/env python3
"""
生成微信数据库字段配置模板
基于实际数据库结构生成JSON模板，供人工填写字段含义
"""

import sqlite3
import json
import argparse
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict
import re

class ConfigTemplateGenerator:
    """配置模板生成器"""
    
    def __init__(self, databases_path: str = "output/databases"):
        """初始化生成器
        
        Args:
            databases_path: 数据库文件路径
        """
        self.databases_path = Path(databases_path)
        self.template_structure = {}
        
    def connect_database(self, db_path: Path) -> sqlite3.Connection:
        """连接SQLite数据库"""
        try:
            conn = sqlite3.connect(str(db_path))
            return conn
        except Exception as e:
            print(f"连接数据库失败 {db_path}: {e}")
            return None
    
    def detect_similar_table_patterns(self, table_names: List[str]) -> Dict[str, List[str]]:
        """检测相似的表名模式（与主脚本逻辑一致）"""
        patterns = defaultdict(list)
        
        for table_name in table_names:
            # 检测 前缀_后缀 模式，其中后缀是32位或更长的哈希字符串
            if '_' in table_name:
                parts = table_name.split('_', 1)  # 只分割第一个下划线
                if len(parts) == 2:
                    prefix, suffix = parts
                    # 检查后缀是否像哈希值（长度>=16的十六进制字符串）
                    if len(suffix) >= 16 and all(c in '0123456789abcdefABCDEF' for c in suffix):
                        patterns[prefix].append(table_name)
        
        # 只返回有多个表的模式
        return {prefix: tables for prefix, tables in patterns.items() if len(tables) > 1}
    
    def compare_table_structures(self, conn: sqlite3.Connection, table_names: List[str]) -> Dict[str, Any]:
        """比较多个表的结构是否相同（与主脚本逻辑一致）"""
        if not table_names:
            return {'are_identical': False, 'representative_table': None}
        
        try:
            cursor = conn.cursor()
            structures = {}
            
            # 获取每个表的结构
            for table_name in table_names:
                try:
                    cursor.execute(f"PRAGMA table_info({table_name})")
                    columns = cursor.fetchall()
                    
                    # 标准化字段信息用于比较
                    structure = []
                    for col in columns:
                        structure.append({
                            'name': col[1],
                            'type': col[2].upper(),  # 统一大小写
                            'notnull': col[3],
                            'pk': col[5]
                        })
                    
                    structures[table_name] = structure
                except Exception as e:
                    print(f"获取表结构失败 {table_name}: {e}")
                    continue
            
            if not structures:
                return {'are_identical': False, 'representative_table': None}
            
            # 比较所有表结构
            first_table = list(structures.keys())[0]
            first_structure = structures[first_table]
            
            are_identical = True
            
            for table_name, structure in structures.items():
                if table_name == first_table:
                    continue
                
                if len(structure) != len(first_structure):
                    are_identical = False
                    break
                
                for i, (field1, field2) in enumerate(zip(first_structure, structure)):
                    if field1 != field2:
                        are_identical = False
                        break
                
                if not are_identical:
                    break
            
            return {
                'are_identical': are_identical,
                'representative_table': first_table,
                'structure': first_structure,
                'table_count': len(structures),
                'table_names': list(structures.keys())
            }
            
        except Exception as e:
            print(f"比较表结构失败: {e}")
            return {'are_identical': False, 'representative_table': None}
    
    def analyze_database_structure(self, db_path: Path) -> Dict[str, Any]:
        """分析单个数据库结构"""
        db_name = db_path.stem
        print(f"分析数据库结构: {db_name}")
        
        conn = self.connect_database(db_path)
        if not conn:
            return {}
        
        try:
            cursor = conn.cursor()

            def parse_columns_from_create_sql(create_sql: str) -> list[tuple[str, str]]:
                """
                从建表 SQL 中尽力解析列名（用于 FTS5/缺失 tokenizer 扩展导致 PRAGMA 失败的情况）。
                返回 (name, type)；类型缺失时默认 TEXT。
                """
                out: list[tuple[str, str]] = []
                if not create_sql:
                    return out
                try:
                    start = create_sql.find("(")
                    end = create_sql.rfind(")")
                    if start == -1 or end == -1 or end <= start:
                        return out
                    inner = create_sql[start + 1:end]

                    parts: list[str] = []
                    buf = ""
                    depth = 0
                    for ch in inner:
                        if ch == "(":
                            depth += 1
                        elif ch == ")":
                            depth -= 1
                        if ch == "," and depth == 0:
                            parts.append(buf.strip())
                            buf = ""
                        else:
                            buf += ch
                    if buf.strip():
                        parts.append(buf.strip())

                    for part in parts:
                        token = part.strip()
                        if not token:
                            continue
                        low = token.lower()
                        # 跳过约束/外键等
                        if low.startswith(("constraint", "primary", "unique", "foreign", "check")):
                            continue
                        # fts5 选项（tokenize/prefix/content/content_rowid 等）
                        if "=" in token:
                            key = token.split("=", 1)[0].strip().lower()
                            if key in ("tokenize", "prefix", "content", "content_rowid", "compress", "uncompress"):
                                continue
                        tokens = token.split()
                        if not tokens:
                            continue
                        name = tokens[0].strip("`\"[]")
                        typ = tokens[1].upper() if len(tokens) > 1 and "=" not in tokens[1] else "TEXT"
                        out.append((name, typ))
                except Exception:
                    return out
                return out

            def get_table_columns(table_name: str) -> list[tuple[str, str]]:
                # 先尝试 PRAGMA
                try:
                    cursor.execute(f"PRAGMA table_info({table_name})")
                    columns = cursor.fetchall()
                    if columns:
                        return [(col[1], col[2]) for col in columns]
                except Exception:
                    pass

                # 兜底：从 sqlite_master.sql 解析
                try:
                    cursor.execute(
                        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                        (table_name,),
                    )
                    row = cursor.fetchone()
                    create_sql = row[0] if row and len(row) > 0 else ""
                    return parse_columns_from_create_sql(create_sql or "")
                except Exception:
                    return []
            
            # 获取所有表名
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            table_names = [table[0] for table in tables]
            
            # 检测相似表并分组
            similar_patterns = self.detect_similar_table_patterns(table_names)
            processed_tables = set()
            db_structure = {}
            
            # 处理相似表组
            for prefix, pattern_tables in similar_patterns.items():
                print(f"  检测到相似表模式 {prefix}_*: {len(pattern_tables)} 个表")
                
                # 比较表结构
                comparison = self.compare_table_structures(conn, pattern_tables)
                
                if comparison['are_identical']:
                    print(f"    → 表结构完全相同，使用代表表: {comparison['representative_table']}")
                    # 使用模式名作为键，记录代表表的字段
                    representative_table = comparison['representative_table']
                    table_key = f"{prefix}_*"  # 使用模式名
                    
                    # 获取代表表的字段信息
                    columns = get_table_columns(representative_table)
                    
                    fields = {}
                    for field_name, field_type in columns:
                        fields[field_name] = {
                            "type": field_type,
                            "meaning": "",  # 留空供用户填写
                            "notes": f"字段类型: {field_type}"
                        }
                    
                    db_structure[table_key] = {
                        "type": "similar_group",
                        "pattern": f"{prefix}_{{hash}}",
                        "table_count": comparison['table_count'],
                        "representative_table": representative_table,
                        "description": "",  # 留空供用户填写
                        "fields": fields
                    }
                    
                    # 标记这些表已被处理
                    processed_tables.update(pattern_tables)
                else:
                    print(f"    → 表结构不同，保持独立处理")
            
            # 处理剩余的独立表
            for table in tables:
                table_name = table[0]
                
                if table_name in processed_tables:
                    continue
                
                try:
                    # 获取表字段信息
                    columns = get_table_columns(table_name)
                    
                    fields = {}
                    for field_name, field_type in columns:
                        fields[field_name] = {
                            "type": field_type,
                            "meaning": "",  # 留空供用户填写
                            "notes": f"字段类型: {field_type}"
                        }
                    
                    db_structure[table_name] = {
                        "type": "table",
                        "description": "",  # 留空供用户填写
                        "fields": fields
                    }
                    
                except Exception as e:
                    print(f"    处理表 {table_name} 失败: {e}")
                    continue
            
            return db_structure
            
        except Exception as e:
            print(f"分析数据库失败 {db_name}: {e}")
            return {}
        finally:
            conn.close()
    
    def generate_template(
        self,
        output_file: str = "wechat_db_config_template.json",
        *,
        include_excluded: bool = False,
        include_message_shards: bool = False,
        exclude_db_stems: set[str] | None = None,
    ):
        """生成配置模板"""
        print("开始生成微信数据库配置模板...")
        
        # 定义要排除的数据库模式和描述
        excluded_patterns = {} if include_excluded else {
            r'biz_message_\d+\.db$': '公众号/企业微信聊天记录数据库（通常不参与个人聊天分析）',
            r'bizchat\.db$': '企业微信联系人/会话数据库（通常不参与个人聊天分析）',
            r'contact_fts\.db$': '联系人搜索索引数据库（FTS）',
            r'favorite_fts\.db$': '收藏搜索索引数据库（FTS）'
        }
        
        # 查找所有数据库文件
        all_db_files = []
        for account_dir in self.databases_path.iterdir():
            if account_dir.is_dir():
                for db_file in account_dir.glob("*.db"):
                    all_db_files.append(db_file)
        
        print(f"找到 {len(all_db_files)} 个数据库文件")
        
        # 过滤数据库文件
        db_files = []
        excluded_files = []
        
        for db_file in all_db_files:
            db_filename = db_file.name
            excluded_info = None
            
            for pattern, description in excluded_patterns.items():
                if re.match(pattern, db_filename):
                    excluded_files.append((db_file, description))
                    excluded_info = description
                    break
            
            if excluded_info is None:
                db_files.append(db_file)
        
        # 显示排除的数据库
        if excluded_files:
            print(f"\n排除以下数据库文件（{len(excluded_files)} 个）：")
            for excluded_file, description in excluded_files:
                print(f"  - {excluded_file.name} ({description})")
        
        # 显式排除指定 stem（不含 .db）
        if exclude_db_stems:
            before = len(db_files)
            db_files = [p for p in db_files if p.stem not in exclude_db_stems]
            after = len(db_files)
            if before != after:
                print(f"\n按 --exclude-db-stem 排除 {before - after} 个数据库: {sorted(exclude_db_stems)}")

        print(f"\n实际处理 {len(db_files)} 个数据库文件")
        
        # 过滤message数据库，只保留倒数第二个（与主脚本逻辑一致）
        if not include_message_shards:
            message_numbered_dbs = []
            message_other_dbs = []

            for db in db_files:
                if re.match(r'message_\d+$', db.stem):  # message_{数字}.db
                    message_numbered_dbs.append(db)
                elif db.stem.startswith('message_'):  # message_fts.db, message_resource.db等
                    message_other_dbs.append(db)

            if len(message_numbered_dbs) > 1:
                # 按数字编号排序（提取数字进行排序）
                message_numbered_dbs.sort(key=lambda x: int(re.search(r'message_(\d+)', x.stem).group(1)))
                # 选择倒数第二个（按编号排序）
                selected_message_db = message_numbered_dbs[-2]  # 倒数第二个
                print(f"检测到 {len(message_numbered_dbs)} 个message_{{数字}}.db数据库")
                print(f"选择倒数第二个: {selected_message_db.name}")

                # 从db_files中移除其他message_{数字}.db数据库，但保留message_fts.db等
                db_files = [db for db in db_files if not re.match(r'message_\d+$', db.stem)]
                db_files.append(selected_message_db)
        
        print(f"实际分析 {len(db_files)} 个数据库文件")
        
        # 生成模板结构
        template = {
            "_metadata": {
                "description": "微信数据库字段配置模板",
                "version": "1.0",
                "instructions": {
                    "zh": "请为每个字段的 'meaning' 填入准确的中文含义，'description' 填入数据库/表的功能描述",
                    "en": "Please fill in accurate Chinese meanings for each field's 'meaning' and functional descriptions for 'description'"
                },
                "database_count": len(db_files),
                "generated_time": __import__('datetime').datetime.now().isoformat()
            },
            "databases": {}
        }
        
        # 分析每个数据库
        for db_file in db_files:
            db_structure = self.analyze_database_structure(db_file)
            if db_structure:
                template["databases"][db_file.stem] = {
                    "description": "",  # 留空供用户填写
                    "file_size": db_file.stat().st_size,
                    "tables": db_structure
                }
        
        # 添加额外的配置项
        template["message_types"] = {
            "_instructions": "消息类型映射 - 格式: 'Type,SubType': '含义描述'",
            "examples": {
                "1,0": "文本消息",
                "3,0": "图片消息",
                "34,0": "语音消息"
            }
        }
        
        template["friend_types"] = {
            "_instructions": "好友类型映射 - 格式: 'TypeCode': '类型描述'",
            "examples": {
                "1": "好友",
                "2": "微信群",
                "3": "好友"
            }
        }
        
        # 写入模板文件
        output_path = Path(output_file)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(template, f, ensure_ascii=False, indent=2)
        
        print(f"\n配置模板生成完成: {output_file}")
        print(f"  - 数据库数量: {len(template['databases'])}")
        
        # 统计信息
        total_tables = 0
        total_fields = 0
        similar_groups = 0
        
        for db_name, db_info in template["databases"].items():
            db_tables = len(db_info["tables"])
            total_tables += db_tables
            
            for table_name, table_info in db_info["tables"].items():
                if table_info["type"] == "similar_group":
                    similar_groups += 1
                total_fields += len(table_info["fields"])
        
        print(f"  - 表数量: {total_tables}")
        print(f"  - 相似表组: {similar_groups}")
        print(f"  - 字段总数: {total_fields}")
        
        # 显示完成统计信息
        if excluded_files:
            print(f"\n生成完成统计：")
            print(f"  - 成功处理: {len(template['databases'])} 个数据库")
            print(f"  - 排除数据库: {len(excluded_files)} 个")
            print(f"  - 排除原因: 个人微信数据分析不需要企业微信和搜索索引数据")
        
        print(f"\n请编辑 {output_file} 文件，填入准确的字段含义和描述")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="微信数据库字段配置模板生成器")
    parser.add_argument("--databases-path", default="output/databases", help="解密后的数据库根目录（按账号分目录）")
    parser.add_argument("--output", default="wechat_db_config_template.json", help="输出 JSON 模板路径")
    parser.add_argument("--include-excluded", action="store_true", help="包含默认会被排除的数据库（如 bizchat/contact_fts/favorite_fts 等）")
    parser.add_argument("--include-message-shards", action="store_true", help="包含所有 message_{n}.db（否则仅保留倒数第二个作代表）")
    parser.add_argument("--exclude-db-stem", action="append", default=[], help="按 stem（不含 .db）排除数据库，可重复，例如: --exclude-db-stem digital_twin")
    args = parser.parse_args()

    print("微信数据库配置模板生成器")
    print("=" * 50)

    generator = ConfigTemplateGenerator(databases_path=args.databases_path)
    generator.generate_template(
        output_file=args.output,
        include_excluded=bool(args.include_excluded),
        include_message_shards=bool(args.include_message_shards),
        exclude_db_stems=set(args.exclude_db_stem or []),
    )

if __name__ == "__main__":
    main()
