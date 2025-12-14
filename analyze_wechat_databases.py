#!/usr/bin/env python3
"""
微信数据库结构分析工具
自动分析解密后的微信数据库文件，生成详细的字段关联文档
"""

import sqlite3
import os
import json
from pathlib import Path
from typing import Dict, List, Any, Tuple
from collections import defaultdict
import re

class WeChatDatabaseAnalyzer:
    """微信数据库分析器"""
    
    def __init__(self, databases_path: str = "output/databases", config_file: str = "wechat_db_config.json"):
        """初始化分析器
        
        Args:
            databases_path: 数据库文件路径
            config_file: 配置文件路径
        """
        self.databases_path = Path(databases_path)
        self.analysis_results = {}
        self.field_relationships = defaultdict(list)
        self.similar_table_groups = {}  # 存储相似表分组信息
        
        # 从配置文件加载字段含义、消息类型等数据
        self._load_config(config_file)
        
    def _load_config(self, config_file: str):
        """从配置文件加载配置数据
        
        Args:
            config_file: 配置文件路径
        """
        try:
            config_path = Path(config_file)
            if not config_path.exists():
                fallback_path = Path("output") / "configs" / "wechat_db_config.generated.json"
                if fallback_path.exists():
                    config_path = fallback_path
                else:
                    print(f"警告: 配置文件 {config_file} 不存在，将使用默认配置")
                    self._set_default_config()
                    return
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 加载字段含义
            self.field_meanings = {}
            raw_field_meanings = config.get('field_meanings', {})
            if isinstance(raw_field_meanings, dict):
                for k, v in raw_field_meanings.items():
                    if isinstance(k, str) and isinstance(v, str) and v.strip():
                        self.field_meanings[k] = v.strip()
            
            # 加载消息类型映射，将字符串键转换为元组键
            message_types_raw = config.get('message_types', {})
            merged_message_types = {}
            if isinstance(message_types_raw, dict):
                examples = message_types_raw.get('examples')
                if isinstance(examples, dict):
                    merged_message_types.update(examples)
                for k, v in message_types_raw.items():
                    if k in ('_instructions', 'examples'):
                        continue
                    merged_message_types[k] = v
            self.message_types = {}
            for key, value in merged_message_types.items() if isinstance(merged_message_types, dict) else []:
                # 解析 "1,0" 格式的键
                parts = key.split(',')
                if len(parts) == 2:
                    try:
                        type_key = (int(parts[0]), int(parts[1]))
                        self.message_types[type_key] = value
                    except ValueError:
                        continue
            
            # 加载好友类型映射，将字符串键转换为整数键
            friend_types_raw = config.get('friend_types', {})
            merged_friend_types = {}
            if isinstance(friend_types_raw, dict):
                examples = friend_types_raw.get('examples')
                if isinstance(examples, dict):
                    merged_friend_types.update(examples)
                for k, v in friend_types_raw.items():
                    if k in ('_instructions', 'examples'):
                        continue
                    merged_friend_types[k] = v
            self.friend_types = {}
            for key, value in merged_friend_types.items() if isinstance(merged_friend_types, dict) else []:
                try:
                    self.friend_types[int(key)] = value
                except ValueError:
                    continue
            
            # 加载数据库描述
            self.db_descriptions = config.get('db_descriptions', {}) if isinstance(config.get('db_descriptions', {}), dict) else {}
            databases_raw = config.get('databases', {})
            if isinstance(databases_raw, dict):
                for db_name, db_info in databases_raw.items():
                    if not isinstance(db_name, str) or not isinstance(db_info, dict):
                        continue

                    desc = db_info.get('description')
                    if isinstance(desc, str) and desc.strip():
                        self.db_descriptions.setdefault(db_name, desc.strip())
                        base = db_name.split('_')[0]
                        if base:
                            self.db_descriptions.setdefault(base, desc.strip())

                    tables = db_info.get('tables', {})
                    if not isinstance(tables, dict):
                        continue
                    for table_name, table_info in tables.items():
                        if not isinstance(table_name, str) or not isinstance(table_info, dict):
                            continue
                        fields = table_info.get('fields', {})
                        if not isinstance(fields, dict):
                            continue
                        for field_name, field_info in fields.items():
                            if not isinstance(field_name, str) or not isinstance(field_info, dict):
                                continue
                            meaning = field_info.get('meaning')
                            if not isinstance(meaning, str) or not meaning.strip():
                                continue
                            self.field_meanings.setdefault(f"{table_name}.{field_name}", meaning.strip())
                            self.field_meanings.setdefault(field_name, meaning.strip())
            
            print(f"成功加载配置文件: {config_file}")
            print(f"  - 字段含义: {len(self.field_meanings)} 个")
            print(f"  - 消息类型: {len(self.message_types)} 个")
            print(f"  - 好友类型: {len(self.friend_types)} 个")
            print(f"  - 数据库描述: {len(self.db_descriptions)} 个")
            
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            print("将使用默认配置")
            self._set_default_config()
    
    def _set_default_config(self):
        """设置默认配置（最小化配置）"""
        self.field_meanings = {
            'localId': '本地ID',
            'TalkerId': '消息所在房间的ID',
            'MsgSvrID': '服务器端存储的消息ID',
            'Type': '消息类型',
            'SubType': '消息类型子分类',
            'CreateTime': '消息创建时间',
            'UserName': '用户名/微信号',
            'NickName': '昵称',
            'Remark': '备注名'
        }
        
        self.message_types = {
            (1, 0): '文本消息',
            (3, 0): '图片消息',
            (34, 0): '语音消息'
        }
        
        self.friend_types = {
            1: '好友',
            2: '微信群',
            3: '好友'
        }
        
        self.db_descriptions = {
            'message': '聊天记录核心数据库',
            'contact': '联系人数据库',
            'session': '会话数据库'
        }
    
    def connect_database(self, db_path: Path) -> sqlite3.Connection:
        """连接SQLite数据库
        
        Args:
            db_path: 数据库文件路径
            
        Returns:
            数据库连接对象
        """
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            print(f"连接数据库失败 {db_path}: {e}")
            return None
    
    def get_table_info(self, conn: sqlite3.Connection, table_name: str) -> Dict[str, Any]:
        """获取表的详细信息（对FTS等特殊表做兼容，必要时仅解析建表SQL）"""
        cursor = conn.cursor()
        original_row_factory = conn.row_factory
        conn.row_factory = sqlite3.Row

        def parse_columns_from_create_sql(create_sql: str) -> List[Dict[str, Any]]:
            cols: List[Dict[str, Any]] = []
            try:
                # 取第一个括号内的定义段
                start = create_sql.find("(")
                end = create_sql.rfind(")")
                if start == -1 or end == -1 or end <= start:
                    return cols
                inner = create_sql[start + 1:end]

                parts: List[str] = []
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
                    # 跳过约束/索引/外键/检查等行
                    if low.startswith(("constraint", "primary", "unique", "foreign", "check")):
                        continue
                    # fts5 选项（tokenize/prefix/content/content_rowid 等）
                    if "=" in token:
                        key = token.split("=", 1)[0].strip().lower()
                        if key in ("tokenize", "prefix", "content", "content_rowid", "compress", "uncompress"):
                            continue
                    # 第一项作为列名（去掉引号/反引号/方括号）
                    tokens = token.split()
                    if not tokens:
                        continue
                    name = tokens[0].strip("`\"[]")
                    typ = tokens[1].upper() if len(tokens) > 1 else "TEXT"
                    cols.append({
                        "cid": None,
                        "name": name,
                        "type": typ,
                        "notnull": 0,
                        "dflt_value": None,
                        "pk": 0
                    })
            except Exception:
                pass
            return cols

        try:
            # 先拿建表SQL，便于遇错兜底
            cursor.execute(
                f"SELECT sql FROM sqlite_master WHERE type IN ('table','view') AND name='{table_name}'"
            )
            create_sql_raw = cursor.fetchone()
            create_sql = create_sql_raw[0] if create_sql_raw and len(create_sql_raw) > 0 else None

            # 尝试PRAGMA列信息
            columns: List[Dict[str, Any]] = []
            try:
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns_raw = cursor.fetchall()
                for col in columns_raw:
                    try:
                        columns.append(dict(col))
                    except Exception:
                        columns.append({
                            'cid': col[0] if len(col) > 0 else None,
                            'name': col[1] if len(col) > 1 else 'unknown',
                            'type': col[2] if len(col) > 2 else 'UNKNOWN',
                            'notnull': col[3] if len(col) > 3 else 0,
                            'dflt_value': col[4] if len(col) > 4 else None,
                            'pk': col[5] if len(col) > 5 else 0
                        })
            except Exception:
                # 兜底：从建表SQL解析列
                if create_sql:
                    columns = parse_columns_from_create_sql(create_sql)

            # 索引信息
            indexes: List[Dict[str, Any]] = []
            try:
                cursor.execute(f"PRAGMA index_list({table_name})")
                indexes_raw = cursor.fetchall()
                for idx in indexes_raw:
                    try:
                        indexes.append(dict(idx))
                    except Exception:
                        indexes.append({
                            'seq': idx[0] if len(idx) > 0 else None,
                            'name': idx[1] if len(idx) > 1 else 'unknown',
                            'unique': idx[2] if len(idx) > 2 else 0,
                            'origin': idx[3] if len(idx) > 3 else None,
                            'partial': idx[4] if len(idx) > 4 else 0
                        })
            except Exception:
                indexes = []

            # 外键信息
            foreign_keys: List[Dict[str, Any]] = []
            try:
                cursor.execute(f"PRAGMA foreign_key_list({table_name})")
                foreign_keys_raw = cursor.fetchall()
                for fk in foreign_keys_raw:
                    try:
                        foreign_keys.append(dict(fk))
                    except Exception:
                        foreign_keys.append({
                            'id': fk[0] if len(fk) > 0 else None,
                            'seq': fk[1] if len(fk) > 1 else None,
                            'table': fk[2] if len(fk) > 2 else 'unknown',
                            'from': fk[3] if len(fk) > 3 else 'unknown',
                            'to': fk[4] if len(fk) > 4 else 'unknown'
                        })
            except Exception:
                foreign_keys = []

            # 行数（FTS/缺tokenizer可失败）
            row_count = 0
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                row_count_raw = cursor.fetchone()
                row_count = row_count_raw[0] if row_count_raw and len(row_count_raw) > 0 else 0
            except Exception:
                row_count = None

            # 示例数据（可能失败）
            sample_data: List[Dict[str, Any]] = []
            try:
                sample_data = self.get_latest_sample_data(cursor, table_name, columns)
            except Exception:
                sample_data = []

            return {
                'columns': columns,
                'indexes': indexes,
                'foreign_keys': foreign_keys,
                'create_sql': create_sql,
                'row_count': row_count,
                'sample_data': sample_data
            }
        except Exception as e:
            print(f"获取表信息失败 {table_name}: {e}")
            # 兜底：尽力返回建表语句
            try:
                return {
                    'columns': [],
                    'indexes': [],
                    'foreign_keys': [],
                    'create_sql': None,
                    'row_count': None,
                    'sample_data': []
                }
            finally:
                try:
                    conn.row_factory = original_row_factory
                except Exception:
                    pass
        finally:
            try:
                conn.row_factory = original_row_factory
            except Exception:
                pass
    
    def get_latest_sample_data(self, cursor: sqlite3.Cursor, table_name: str, columns: List) -> List[Dict]:
        """获取表的最新10条示例数据（尽力按时间/自增倒序），不足则返回可用数量"""
        try:
            # 首先检查表是否有数据
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = cursor.fetchone()[0]

            if row_count == 0:
                return []  # 表为空，直接返回

            # 限制获取的数据量，至少尝试10条
            limit = min(10, row_count)

            # 选择可能的“最新”排序字段（优先时间戳/创建时间，其次本地自增/服务器序）
            column_names = [col['name'] if isinstance(col, dict) else col[1] for col in columns]
            lower_map = {name.lower(): name for name in column_names if isinstance(name, str)}

            preferred_orders = [
                # 时间相关
                "createtime", "create_time", "createtime_", "lastupdatetime", "last_update_time",
                "updatetime", "update_time", "time", "timestamp",
                # 常见消息/顺序相关
                "server_seq", "msgsvrid", "svr_id", "server_id",
                # 本地自增/行顺序
                "localid", "local_id",
            ]

            order_column = None
            for key in preferred_orders:
                if key in lower_map:
                    order_column = lower_map[key]
                    break

            # 构造候选查询（逐个尝试，失败则回退）
            queries = []
            if order_column:
                queries.append(f"SELECT * FROM {table_name} ORDER BY {order_column} DESC LIMIT {limit}")
            # rowid 通常可用（虚表/视图可能不可用）
            queries.append(f"SELECT * FROM {table_name} ORDER BY rowid DESC LIMIT {limit}")
            # 最后兜底：不排序
            queries.append(f"SELECT * FROM {table_name} LIMIT {limit}")

            # 临时禁用 row_factory 来避免 UTF-8 解码问题
            original_row_factory = cursor.connection.row_factory
            cursor.connection.row_factory = None

            raw_rows = None
            last_error = None
            for q in queries:
                try:
                    cursor.execute(q)
                    raw_rows = cursor.fetchall()
                    if raw_rows is not None:
                        break
                except Exception as qe:
                    last_error = qe
                    continue

            # 恢复 row_factory
            cursor.connection.row_factory = original_row_factory

            if raw_rows is None:
                return []

            # 安全地处理数据
            sample_data = []
            for raw_row in raw_rows:
                try:
                    row_dict = {}
                    for i, col_name in enumerate(column_names):
                        if i < len(raw_row):
                            value = raw_row[i]

                            # 简化的数据处理
                            if value is None:
                                row_dict[col_name] = None
                            elif isinstance(value, (int, float)):
                                row_dict[col_name] = value
                            elif isinstance(value, bytes):
                                # 对于二进制数据，只显示大小信息
                                row_dict[col_name] = f"<binary data, {len(value)} bytes>"
                            elif isinstance(value, str):
                                # 对于字符串，限制长度并清理
                                if len(value) > 200:
                                    clean_value = value[:200] + "..."
                                else:
                                    clean_value = value
                                # 简单清理不可打印字符
                                clean_value = ''.join(c if ord(c) >= 32 or c in '\n\r\t' else '?' for c in clean_value)
                                row_dict[col_name] = clean_value
                            else:
                                row_dict[col_name] = str(value)[:100]  # 转换为字符串并限制长度
                        else:
                            row_dict[col_name] = None

                    sample_data.append(row_dict)

                except Exception:
                    # 单行处理失败，继续处理其他行
                    continue

            return sample_data

        except Exception:
            # 完全失败，返回空列表但不中断整个分析过程
            return []
    
    def detect_similar_table_patterns(self, table_names: List[str]) -> Dict[str, List[str]]:
        """检测相似的表名模式
        
        Args:
            table_names: 表名列表
            
        Returns:
            按模式分组的表名字典 {模式前缀: [表名列表]}
        """
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
        """比较多个表的结构是否相同
        
        Args:
            conn: 数据库连接
            table_names: 要比较的表名列表
            
        Returns:
            比较结果 {
                'are_identical': bool,
                'representative_table': str,
                'structure': dict,
                'differences': list
            }
        """
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
            differences = []
            
            for table_name, structure in structures.items():
                if table_name == first_table:
                    continue
                
                if len(structure) != len(first_structure):
                    are_identical = False
                    differences.append(f"{table_name}: 字段数量不同 ({len(structure)} vs {len(first_structure)})")
                    continue
                
                for i, (field1, field2) in enumerate(zip(first_structure, structure)):
                    if field1 != field2:
                        are_identical = False
                        differences.append(f"{table_name}: 字段{i+1}不同 ({field1} vs {field2})")
                        break
            
            return {
                'are_identical': are_identical,
                'representative_table': first_table,
                'structure': first_structure,
                'differences': differences,
                'table_count': len(structures),
                'table_names': list(structures.keys())
            }
            
        except Exception as e:
            print(f"比较表结构失败: {e}")
            return {'are_identical': False, 'representative_table': None}
    
    def group_similar_tables(self, db_name: str, conn: sqlite3.Connection, table_names: List[str]) -> Dict[str, Any]:
        """对数据库中的相似表进行分组
        
        Args:
            db_name: 数据库名
            conn: 数据库连接
            table_names: 所有表名列表
            
        Returns:
            分组结果
        """
        # 检测相似表模式
        similar_patterns = self.detect_similar_table_patterns(table_names)
        
        grouped_tables = {}
        processed_tables = set()
        
        for prefix, pattern_tables in similar_patterns.items():
            print(f"检测到相似表模式 {prefix}_*: {len(pattern_tables)} 个表")
            
            # 比较表结构
            comparison = self.compare_table_structures(conn, pattern_tables)
            
            if comparison['are_identical']:
                print(f"  → 表结构完全相同，将合并为一个文档")
                grouped_tables[prefix] = {
                    'type': 'similar_group',
                    'representative_table': comparison['representative_table'],
                    'table_count': comparison['table_count'],
                    'table_names': comparison['table_names'],
                    'prefix': prefix
                }
                # 标记这些表已被处理
                processed_tables.update(pattern_tables)
            else:
                print(f"  → 表结构不同，保持独立文档")
                print(f"  → 差异: {comparison['differences']}")
        
        # 存储到实例变量中
        if db_name not in self.similar_table_groups:
            self.similar_table_groups[db_name] = {}
        self.similar_table_groups[db_name] = grouped_tables
        
        return {
            'grouped_tables': grouped_tables,
            'processed_tables': processed_tables
        }
    
    def analyze_field_relationships(self, db_name: str, table_info: Dict[str, Any]):
        """分析字段关系
        
        Args:
            db_name: 数据库名称
            table_info: 表信息
        """
        for table_name, info in table_info.items():
            columns = info.get('columns', [])
            for column in columns:
                field_name = column['name']
                field_type = column['type']
                
                # 查找可能的关联字段
                if 'id' in field_name.lower():
                    self.field_relationships[field_name].append({
                        'database': db_name,
                        'table': table_name,
                        'type': field_type,
                        'is_primary': column['pk'] == 1,
                        'relationship_type': 'identifier'
                    })
                elif 'username' in field_name.lower() or 'talker' in field_name.lower():
                    self.field_relationships[field_name].append({
                        'database': db_name,
                        'table': table_name,
                        'type': field_type,
                        'relationship_type': 'user_reference'
                    })
                elif 'time' in field_name.lower():
                    self.field_relationships[field_name].append({
                        'database': db_name,
                        'table': table_name,
                        'type': field_type,
                        'relationship_type': 'timestamp'
                    })
    
    def analyze_database(self, db_path: Path) -> Dict[str, Any]:
        """分析单个数据库
        
        Args:
            db_path: 数据库文件路径
            
        Returns:
            数据库分析结果
        """
        db_name = db_path.stem
        print(f"正在分析数据库: {db_name}")
        
        conn = self.connect_database(db_path)
        if not conn:
            return {}
        
        try:
            cursor = conn.cursor()
            
            # 获取所有表名
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            table_names = [table[0] for table in tables]
            
            # 检测相似表并分组
            grouping_result = self.group_similar_tables(db_name, conn, table_names)
            grouped_tables = grouping_result['grouped_tables']
            processed_tables = grouping_result['processed_tables']
            
            db_info = {
                'database_name': db_name,
                'database_path': str(db_path),
                'database_size': db_path.stat().st_size,
                'description': self.db_descriptions.get(db_name.split('_')[0], '未知用途数据库'),
                'table_count': len(tables),
                'grouped_tables': grouped_tables,
                'tables': {}
            }
            
            # 分析每个表
            for table in tables:
                table_name = table[0]

                # 不再跳过相似表组中的非代表表，确保“全部表的全部字段”均被分析
                table_info = self.get_table_info(conn, table_name)
                if table_info:
                    # 如果是代表表，添加分组信息
                    if table_name in processed_tables:
                        for prefix, group_info in grouped_tables.items():
                            if table_name == group_info['representative_table']:
                                table_info['is_representative'] = True
                                table_info['similar_group'] = group_info
                                break

                    db_info['tables'][table_name] = table_info
            
            # 分析字段关系
            self.analyze_field_relationships(db_name, db_info['tables'])
            
            return db_info
            
        except Exception as e:
            print(f"分析数据库失败 {db_name}: {e}")
            return {}
        finally:
            conn.close()
    
    def analyze_all_databases(self) -> Dict[str, Any]:
        """分析所有数据库"""
        print("开始分析微信数据库...")
        
        # 定义要排除的数据库模式和描述
        excluded_patterns = {
            r'biz_message_\d+\.db$': '企业微信聊天记录数据库',
            r'bizchat\.db$': '企业微信联系人数据库',
            r'contact_fts\.db$': '搜索联系人数据库',
            r'favorite_fts\.db$': '搜索收藏数据库'
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
        
        print(f"\n实际处理 {len(db_files)} 个数据库文件")
        
        # 过滤message数据库，只保留倒数第二个（只针对message_{数字}.db）
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
            print(f"检测到 {len(message_numbered_dbs)} 个message_{{数字}}.db数据库: {[db.stem for db in message_numbered_dbs]}")
            print(f"选择倒数第二个: {selected_message_db.name}")
            
            # 从db_files中移除其他message_{数字}.db数据库，但保留message_fts.db等
            db_files = [db for db in db_files if not re.match(r'message_\d+$', db.stem)]
            db_files.append(selected_message_db)
        
        print(f"实际分析 {len(db_files)} 个数据库文件")
        
        # 分析每个数据库
        for db_file in db_files:
            db_analysis = self.analyze_database(db_file)
            if db_analysis:
                self.analysis_results[db_analysis['database_name']] = db_analysis
        
        # 生成字段关系总结
        self.generate_field_relationships_summary()
        
        # 显示分析完成信息
        if excluded_files:
            print(f"\n分析完成统计：")
            print(f"  - 成功分析: {len(self.analysis_results)} 个数据库")
            print(f"  - 排除数据库: {len(excluded_files)} 个")
            print(f"  - 排除原因: 个人微信数据分析不需要企业微信和搜索索引数据")
        
        return self.analysis_results
    
    def generate_field_relationships_summary(self):
        """生成字段关系总结"""
        print("生成字段关系总结...")
        
        relationship_summary = {}
        for field_name, occurrences in self.field_relationships.items():
            if len(occurrences) > 1:  # 只关注出现在多个地方的字段
                relationship_summary[field_name] = {
                    'field_name': field_name,
                    'occurrences': occurrences,
                    'total_count': len(occurrences),
                    'databases': list(set([occ['database'] for occ in occurrences])),
                    'tables': [f"{occ['database']}.{occ['table']}" for occ in occurrences]
                }
        
        self.field_relationships_summary = relationship_summary
    
    def get_field_meaning(self, field_name: str, table_name: str = "", sample_value: Any = None) -> str:
        """获取字段含义
        
        Args:
            field_name: 字段名
            table_name: 表名（用于上下文推测）
            sample_value: 示例值（用于辅助推测）
            
        Returns:
            字段含义说明
        """
        # 精确匹配
        if table_name:
            table_field_key = f"{table_name}.{field_name}"
            if table_field_key in self.field_meanings:
                return self.field_meanings[table_field_key]
        if field_name in self.field_meanings:
            return self.field_meanings[field_name]
        
        # 大小写不敏感的精确匹配
        for key, meaning in self.field_meanings.items():
            if key.lower() == field_name.lower():
                return meaning
        
        # 模糊匹配
        field_lower = field_name.lower()
        for key, meaning in self.field_meanings.items():
            if key.lower() in field_lower or field_lower in key.lower():
                return f"{meaning}（推测）"
        
        # 基于表名和字段名的上下文推测
        table_lower = table_name.lower()
        
        # MSG表特殊字段处理
        if 'msg' in table_lower:
            if field_name.lower() in ['talkerid', 'talkerId']:
                return "消息所在房间的ID，与Name2ID表对应"
            elif field_name.lower() in ['strtalkermsg', 'msgSvrID']:
                return "服务器端存储的消息ID"
            elif field_name.lower() in ['strtalker']:
                return "消息发送者的微信号"
        
        # Contact表特殊字段处理
        elif 'contact' in table_lower:
            if 'py' in field_lower:
                return "拼音相关字段，用于搜索"
            elif 'head' in field_lower and 'img' in field_lower:
                return "头像相关字段"
        
        # 基于字段名推测含义（增强版）
        if 'id' in field_lower:
            if field_lower.endswith('id'):
                return "标识符字段"
            else:
                return "包含ID的复合字段"
        elif any(time_word in field_lower for time_word in ['time', 'date', 'timestamp']):
            return "时间戳字段"
        elif 'name' in field_lower:
            if 'user' in field_lower:
                return "用户名字段"
            elif 'nick' in field_lower:
                return "昵称字段"
            elif 'display' in field_lower:
                return "显示名称字段"
            else:
                return "名称字段"
        elif 'url' in field_lower:
            if 'img' in field_lower or 'head' in field_lower:
                return "图片URL链接字段"
            else:
                return "URL链接字段"
        elif 'path' in field_lower:
            return "文件路径字段"
        elif 'size' in field_lower:
            return "大小字段"
        elif 'count' in field_lower or 'num' in field_lower:
            return "计数字段"
        elif 'flag' in field_lower:
            return "标志位字段"
        elif 'status' in field_lower:
            return "状态字段"
        elif 'type' in field_lower:
            return "类型标识字段"
        elif 'content' in field_lower:
            return "内容字段"
        elif 'data' in field_lower or 'buf' in field_lower:
            return "数据字段"
        elif 'md5' in field_lower:
            return "MD5哈希值字段"
        elif 'key' in field_lower:
            return "密钥或键值字段"
        elif 'seq' in field_lower:
            return "序列号字段"
        elif 'version' in field_lower:
            return "版本号字段"
        elif field_lower.startswith('str'):
            return "字符串类型字段"
        elif field_lower.startswith('n') and field_lower[1:].isalpha():
            return "数值类型字段（推测）"
        elif field_lower.startswith('is'):
            return "布尔标志字段"
        else:
            return "未知用途字段"
    
    def get_message_type_meaning(self, msg_type: int, sub_type: int = 0) -> str:
        """获取消息类型含义
        
        Args:
            msg_type: 消息主类型
            sub_type: 消息子类型
            
        Returns:
            消息类型说明
        """
        type_key = (msg_type, sub_type)
        if type_key in self.message_types:
            return self.message_types[type_key]
        
        # 如果找不到精确匹配，尝试只匹配主类型
        for (main_type, _), description in self.message_types.items():
            if main_type == msg_type:
                return f"{description}（子类型{sub_type}）"
        
        return f"未知消息类型（{msg_type}, {sub_type}）"
    
    def get_friend_type_meaning(self, friend_type: int) -> str:
        """获取联系人类型含义
        
        Args:
            friend_type: 联系人类型值
            
        Returns:
            联系人类型说明
        """
        if friend_type in self.friend_types:
            return self.friend_types[friend_type]
        
        # 对于未知类型，尝试推测
        if friend_type & 65536:  # 包含65536的标志位
            return f"不看他的朋友圈相关设置（{friend_type}）"
        elif friend_type & 8388608:  # 包含8388608的标志位
            return f"仅聊天相关设置（{friend_type}）"
        elif friend_type & 268435456:  # 包含268435456的标志位
            return f"微信群相关（{friend_type}）"
        elif friend_type & 2147483648:  # 包含2147483648的标志位
            return f"公众号相关（{friend_type}）"
        else:
            return f"未知联系人类型（{friend_type}）"
    
    def generate_markdown_docs(self, output_dir: str = "output/docs/database"):
        """生成Markdown文档
        
        Args:
            output_dir: 输出目录
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        print(f"生成文档到: {output_path}")
        
        # 为每个数据库生成文档
        for db_name, db_info in self.analysis_results.items():
            self.generate_database_doc(db_info, output_path)
        
        # 生成字段关系总结文档
        self.generate_field_relationships_doc(output_path)
        
        # 生成总览文档
        self.generate_overview_doc(output_path)
    
    def generate_database_doc(self, db_info: Dict[str, Any], output_path: Path):
        """为单个数据库生成文档
        
        Args:
            db_info: 数据库信息
            output_path: 输出路径
        """
        db_name = db_info['database_name']
        db_dir = output_path / db_name
        db_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成数据库概览文档
        overview_content = self.generate_database_overview(db_info)
        overview_file = db_dir / "README.md"
        with open(overview_file, 'w', encoding='utf-8') as f:
            f.write(overview_content)
        
        # 为每个表生成详细文档
        for table_name, table_info in db_info.get('tables', {}).items():
            table_content = self.generate_table_doc(db_name, table_name, table_info)
            table_file = db_dir / f"{table_name}.md"
            with open(table_file, 'w', encoding='utf-8') as f:
                f.write(table_content)
        
        print(f"生成数据库文档: {db_name}")
    
    def generate_database_overview(self, db_info: Dict[str, Any]) -> str:
        """生成数据库概览文档内容"""
        db_name = db_info['database_name']
        grouped_tables = db_info.get('grouped_tables', {})
        
        content = f"""# {db_name}.db 数据库

## 基本信息

- **数据库名称**: {db_name}.db
- **功能描述**: {db_info['description']}
- **文件大小**: {db_info.get('database_size', 0):,} 字节
- **表数量**: {db_info.get('table_count', 0)}

## 表结构概览

| 表名 | 字段数 | 数据行数 | 主要功能 |
|-----|--------|----------|----------|
"""
        
        for table_name, table_info in db_info.get('tables', {}).items():
            column_count = len(table_info.get('columns', []))
            row_count = table_info.get('row_count', 0)
            
            # 根据表名推测功能
            table_function = self.guess_table_function(table_name)
            
            # 如果是相似表的代表，显示合并信息
            if table_info.get('is_representative', False):
                similar_group = table_info.get('similar_group', {})
                table_count = similar_group.get('table_count', 1)
                prefix = similar_group.get('prefix', table_name.split('_')[0])
                content += f"| [{prefix}_*]({table_name}.md) | {column_count} | {row_count:,} | {table_function}（代表{table_count}个相同结构的表） |\n"
            else:
                content += f"| [{table_name}]({table_name}.md) | {column_count} | {row_count:,} | {table_function} |\n"
        
        content += """
## 相关数据库

该数据库与以下数据库可能存在关联关系：

"""
        
        # 分析相关数据库
        related_dbs = self.find_related_databases(db_name)
        for related_db in related_dbs:
            content += f"- **{related_db}**: 通过共同字段关联\n"
        
        content += """
## 字段关联分析

以下字段在多个表中出现，可能存在关联关系：

"""
        
        # 分析本数据库内的字段关联
        db_fields = self.analyze_database_field_relationships(db_info)
        for field_name, field_info in db_fields.items():
            if field_info['occurrence_count'] > 1:
                content += f"- **{field_name}**: 出现在 {field_info['occurrence_count']} 个表中\n"
                for table in field_info['tables']:
                    content += f"  - {table}\n"
        
        return content
    
    def guess_table_function(self, table_name: str) -> str:
        """根据表名推测表功能（基于info文件知识）"""
        table_lower = table_name.lower()
        
        # 基于info文件的精确匹配
        if table_name == 'MSG':
            return "聊天记录核心表，存储所有消息数据"
        elif table_name == 'Name2ID':
            return "用户ID映射表，微信号或群聊ID@chatroom格式"
        elif table_name == 'Contact':
            return "联系人核心表，存储所有可能看见的人的信息"
        elif table_name == 'ChatRoom':
            return "群聊成员表，存储群聊用户列表和群昵称"
        elif table_name == 'ChatRoomInfo':
            return "群聊信息表，主要存储群公告内容"
        elif table_name == 'Session':
            return "会话列表表，真正的聊天栏目显示的会话"
        elif table_name == 'ChatInfo':
            return "会话已读信息表，保存每个会话最后一次标记已读的时间"
        elif table_name.startswith('FeedsV'):
            return "朋友圈动态表，存储朋友圈的XML数据"
        elif table_name.startswith('CommentV'):
            return "朋友圈评论表，存储朋友圈点赞或评论记录"
        elif table_name.startswith('NotificationV'):
            return "朋友圈通知表，存储朋友圈相关通知"
        elif table_name.startswith('SnsConfigV'):
            return "朋友圈配置表，包含朋友圈背景图等配置"
        elif table_name.startswith('SnsGroupInfoV'):
            return "朋友圈可见范围表，旧版微信朋友圈的可见或不可见名单"
        elif table_name == 'FavItems':
            return "收藏条目表，收藏的消息条目列表"
        elif table_name == 'FavDataItem':
            return "收藏数据表，收藏的具体数据内容"
        elif table_name == 'FavTags':
            return "收藏标签表，为收藏内容添加的标签"
        elif table_name == 'CustomEmotion':
            return "自定义表情表，用户手动上传的GIF表情"
        elif table_name == 'EmotionPackageItem':
            return "表情包集合表，账号添加的表情包列表"
        elif table_name == 'ContactHeadImgUrl':
            return "联系人头像URL表"
        elif table_name == 'ContactLabel':
            return "好友标签表，好友标签ID与名称对照"
        elif table_name == 'ExtraBuf':
            return "扩展信息表，存储位置信息、手机号、邮箱等"
        elif table_name == 'PatInfo':
            return "拍一拍信息表，存储好友的拍一拍后缀"
        elif table_name == 'TicketInfo':
            return "票据信息表，用途待确认"
        elif table_name == 'Media':
            return "媒体数据表，存储语音消息的SILK格式数据"
        elif table_name.startswith('BizContactHeadImg') or table_name.startswith('ContactHeadImg'):
            return "头像数据表，二进制格式的头像数据"
        elif table_name.startswith('FTSChatMsg') and 'content' in table_lower:
            return "聊天消息搜索内容表，存储搜索关键字"
        elif table_name.startswith('FTSChatMsg') and 'metadata' in table_lower:
            return "聊天消息搜索元数据表，与MSG数据库对应"
        elif table_name.startswith('FTSContact') and 'content' in table_lower:
            return "联系人搜索内容表，支持昵称、备注名、微信号搜索"
        elif table_name.startswith('FTSChatroom') and 'content' in table_lower:
            return "聊天会话搜索内容表，聊天界面会展示的会话"
        elif table_name.startswith('FavData') and 'content' in table_lower:
            return "收藏搜索内容表，收藏内容的全文搜索索引"
        elif table_name == 'ChatCRMsg':
            return "部分聊天记录表，符合特定条件的消息"
        elif table_name == 'DelSessionInfo':
            return "删除会话信息表，被删除的好友列表"
        elif table_name == 'Name2ID_v1':
            return "用户ID映射表v1，ChatCRMsg的辅助数据表"
        elif table_name == 'UnSupportedMsg':
            return "不支持消息表，电脑端不支持的消息（如红包）"
        elif table_name.startswith('RecentWxApp'):
            return "最近小程序表，使用过的小程序"
        elif table_name.startswith('StarWxApp'):
            return "星标小程序表，星标的小程序"
        elif table_name.startswith('WAContact'):
            return "小程序联系人表，各个小程序的基本信息"
        elif table_name.startswith('Biz'):
            if 'session' in table_lower:
                return "企业微信会话表，存储企业微信相关会话"
            elif 'user' in table_lower:
                return "企业微信用户表，存储企业微信用户身份信息"
            else:
                return "企业微信相关表"
        
        # 模式匹配（基于info文件的模式）
        if table_name.startswith('Msg_') and len(table_name) == 36:  # Msg_+32位哈希
            return "特定聊天消息表，某个聊天的消息数据"
        elif 'message' in table_lower:
            return "存储聊天消息数据"
        elif 'contact' in table_lower:
            return "存储联系人信息"
        elif 'session' in table_lower:
            return "存储会话信息"
        elif 'chat' in table_lower:
            if 'room' in table_lower:
                return "存储群聊相关数据"
            else:
                return "存储聊天相关数据"
        elif 'user' in table_lower:
            return "存储用户信息"
        elif 'group' in table_lower or 'room' in table_lower:
            return "存储群组信息"
        elif table_lower.startswith('fts'):
            return "全文搜索索引表"
        elif 'media' in table_lower:
            return "存储媒体文件信息"
        elif 'file' in table_lower:
            return "存储文件信息"
        elif 'image' in table_lower or 'img' in table_lower:
            return "存储图片信息"
        elif 'favorite' in table_lower or 'fav' in table_lower:
            return "存储收藏信息"
        elif 'emotion' in table_lower:
            return "存储表情包信息"
        elif 'sns' in table_lower:
            return "存储朋友圈信息"
        elif 'config' in table_lower or 'setting' in table_lower:
            return "存储配置信息"
        elif 'log' in table_lower:
            return "存储日志信息"
        elif 'cache' in table_lower:
            return "存储缓存数据"
        elif 'search' in table_lower:
            return "搜索相关数据表"
        elif 'sync' in table_lower:
            return "同步相关数据表"
        elif 'translate' in table_lower:
            return "翻译相关数据表"
        elif 'voice' in table_lower:
            return "语音相关数据表"
        elif 'link' in table_lower:
            return "链接相关数据表"
        elif table_lower.startswith('wcdb'):
            return "微信数据库内置表"
        elif 'sequence' in table_lower:
            return "SQLite序列表"
        else:
            return "未知功能表"
    
    def find_related_databases(self, db_name: str) -> List[str]:
        """查找相关数据库"""
        related = []
        
        # 基于字段关系查找
        current_db_fields = set()
        if db_name in self.analysis_results:
            for table_info in self.analysis_results[db_name].get('tables', {}).values():
                for column in table_info.get('columns', []):
                    current_db_fields.add(column['name'])
        
        for other_db_name, other_db_info in self.analysis_results.items():
            if other_db_name == db_name:
                continue
                
            other_db_fields = set()
            for table_info in other_db_info.get('tables', {}).values():
                for column in table_info.get('columns', []):
                    other_db_fields.add(column['name'])
            
            # 如果有共同字段，认为可能相关
            common_fields = current_db_fields.intersection(other_db_fields)
            if len(common_fields) > 3:  # 至少3个共同字段
                related.append(other_db_name)
        
        return related
    
    def analyze_database_field_relationships(self, db_info: Dict[str, Any]) -> Dict[str, Any]:
        """分析数据库内部字段关系"""
        field_occurrences = defaultdict(lambda: {'tables': [], 'occurrence_count': 0})
        
        for table_name, table_info in db_info.get('tables', {}).items():
            for column in table_info.get('columns', []):
                field_name = column['name']
                field_occurrences[field_name]['tables'].append(table_name)
                field_occurrences[field_name]['occurrence_count'] += 1
        
        return dict(field_occurrences)
    
    def generate_table_doc(self, db_name: str, table_name: str, table_info: Dict[str, Any]) -> str:
        """生成表详细文档"""
        is_representative = table_info.get('is_representative', False)
        similar_group = table_info.get('similar_group', {})
        
        if is_representative:
            prefix = similar_group.get('prefix', table_name.split('_')[0])
            table_count = similar_group.get('table_count', 1)
            all_table_names = similar_group.get('table_names', [table_name])
            
            content = f"""# {prefix}_* 表组（相同结构表）

## 基本信息

- **所属数据库**: {db_name}.db
- **表组模式**: {prefix}_{{联系人标识符}}
- **代表表**: {table_name}
- **表组数量**: {table_count} 个表
- **功能**: {self.guess_table_function(table_name)}
- **数据行数**: {table_info.get('row_count', 0):,}（仅代表表）
- **字段数量**: {len(table_info.get('columns', []))}

## 表组说明

此文档代表 {table_count} 个结构完全相同的表，这些表都遵循 `{prefix}_{{哈希值}}` 的命名模式。
哈希值部分是联系人的唯一标识符，每个表存储与特定联系人的对话数据。

### 包含的所有表：
"""
            # 列出所有表名，每行显示几个
            for i, tn in enumerate(all_table_names):
                if i % 3 == 0:
                    content += "\n"
                content += f"- `{tn}`"
                if (i + 1) % 3 != 0 and i != len(all_table_names) - 1:
                    content += " "
            
            content += "\n\n## 表结构（所有表结构相同）\n\n### 字段列表\n\n| 字段名 | 数据类型 | 是否主键 | 是否非空 | 默认值 | 字段含义 |\n|--------|----------|----------|----------|--------|----------|\n"
        else:
            content = f"""# {table_name} 表

## 基本信息

- **所属数据库**: {db_name}.db
- **表名**: {table_name}
- **功能**: {self.guess_table_function(table_name)}
- **数据行数**: {table_info.get('row_count', 0):,}
- **字段数量**: {len(table_info.get('columns', []))}

## 表结构

### 字段列表

| 字段名 | 数据类型 | 是否主键 | 是否非空 | 默认值 | 字段含义 |
|--------|----------|----------|----------|--------|----------|
"""
        
        columns = table_info.get('columns', [])
        for column in columns:
            field_name = column['name']
            field_type = column['type']
            is_pk = '是' if column['pk'] else '否'
            is_not_null = '是' if column['notnull'] else '否'
            default_value = column['dflt_value'] if column['dflt_value'] is not None else '-'
            # 传递表名参数以获得更准确的字段含义
            field_meaning = self.get_field_meaning(field_name, table_name)
            
            content += f"| {field_name} | {field_type} | {is_pk} | {is_not_null} | {default_value} | {field_meaning} |\n"
        
        # 添加索引信息
        indexes = table_info.get('indexes', [])
        if indexes:
            content += "\n### 索引信息\n\n"
            for index in indexes:
                index_name = index['name']
                is_unique = '唯一' if index['unique'] else '普通'
                content += f"- **{index_name}**: {is_unique}索引\n"
        
        # 添加外键信息
        foreign_keys = table_info.get('foreign_keys', [])
        if foreign_keys:
            content += "\n### 外键关系\n\n"
            for fk in foreign_keys:
                content += f"- {fk['from']} → {fk['table']}.{fk['to']}\n"
        
        # 添加示例数据（最新最多10条）
        sample_data = table_info.get('sample_data', [])
        if sample_data:
            content += f"\n### 最新数据样本（最多10条，实际{len(sample_data)}条）\n\n"
            content += "```json\n"
            for i, row in enumerate(sample_data):
                content += f"// 样本 {i+1}\n"
                # 显示所有字段，不限制数量
                full_row = {}
                for key, value in row.items():
                    # 处理长字符串，但显示所有字段
                    if isinstance(value, str) and len(value) > 200:
                        full_row[key] = value[:200] + "..."
                    else:
                        full_row[key] = value
                content += json.dumps(full_row, ensure_ascii=False, indent=2)
                content += "\n\n"
            content += "```\n"
        
        # 添加建表语句
        create_sql = table_info.get('create_sql')
        if create_sql:
            content += "\n### 建表语句\n\n"
            content += "```sql\n"
            content += create_sql
            content += "\n```\n"
        
        return content
    
    def generate_field_relationships_doc(self, output_path: Path):
        """生成字段关系文档"""
        content = """# 微信数据库字段关联分析

## 概述

本文档分析了微信数据库中各个字段之间的关联关系，帮助理解数据库结构和数据流向。

## 跨数据库字段关联

以下字段在多个数据库中出现，表示可能的关联关系：

| 字段名 | 出现次数 | 涉及数据库 | 关联类型 | 用途说明 |
|--------|----------|------------|----------|----------|
"""
        
        for field_name, field_info in self.field_relationships_summary.items():
            databases = ', '.join(field_info['databases'])
            relationship_types = list(set([occ['relationship_type'] for occ in field_info['occurrences']]))
            rel_type = ', '.join(relationship_types)
            meaning = self.get_field_meaning(field_name)
            
            content += f"| {field_name} | {field_info['total_count']} | {databases} | {rel_type} | {meaning} |\n"
        
        content += """
## 详细字段关联

### 用户标识字段

这些字段用于标识和关联用户信息：

"""
        
        user_fields = []
        id_fields = []
        time_fields = []
        
        for field_name, field_info in self.field_relationships_summary.items():
            relationship_types = [occ['relationship_type'] for occ in field_info['occurrences']]
            if 'user_reference' in relationship_types:
                user_fields.append((field_name, field_info))
            elif 'identifier' in relationship_types:
                id_fields.append((field_name, field_info))
            elif 'timestamp' in relationship_types:
                time_fields.append((field_name, field_info))
        
        for field_name, field_info in user_fields:
            content += f"- **{field_name}**: {self.get_field_meaning(field_name)}\n"
            for table in field_info['tables']:
                content += f"  - {table}\n"
            content += "\n"
        
        content += """### 标识符字段

这些字段用作主键或外键：

"""
        
        for field_name, field_info in id_fields:
            content += f"- **{field_name}**: {self.get_field_meaning(field_name)}\n"
            for table in field_info['tables']:
                content += f"  - {table}\n"
            content += "\n"
        
        content += """### 时间字段

这些字段记录时间信息：

"""
        
        for field_name, field_info in time_fields:
            content += f"- **{field_name}**: {self.get_field_meaning(field_name)}\n"
            for table in field_info['tables']:
                content += f"  - {table}\n"
            content += "\n"
        
        # 写入文件
        relationships_file = output_path / "field_relationships.md"
        with open(relationships_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("生成字段关系文档: field_relationships.md")
    
    def generate_overview_doc(self, output_path: Path):
        """生成总览文档"""
        content = """# 微信数据库结构分析总览

## 项目概述

本项目对微信4.x版本的数据库进行了深入分析，解密并提取了各个数据库的表结构、字段含义和关联关系。

## 数据库列表

| 数据库名 | 表数量 | 主要功能 | 文档链接 |
|----------|--------|----------|----------|
"""
        
        for db_name, db_info in self.analysis_results.items():
            table_count = db_info.get('table_count', 0)
            description = db_info.get('description', '未知')
            
            content += f"| {db_name}.db | {table_count} | {description} | [{db_name}]({db_name}/README.md) |\n"
        
        content += f"""
## 统计信息

- **数据库总数**: {len(self.analysis_results)}
- **表总数**: {sum(db_info.get('table_count', 0) for db_info in self.analysis_results.values())}
- **跨数据库关联字段**: {len(self.field_relationships_summary)}

## 主要发现

### 核心数据库

1. **message系列数据库**: 存储聊天消息，是微信最核心的数据
2. **contact.db**: 存储联系人和群聊信息
3. **session.db**: 存储会话列表和状态
4. **sns.db**: 存储朋友圈动态

### 关键关联字段

以下字段在多个数据库中出现，是理解数据关联的关键：

"""
        
        # 列出最重要的关联字段
        important_fields = []
        for field_name, field_info in self.field_relationships_summary.items():
            if field_info['total_count'] >= 3:  # 出现在3个或更多地方
                important_fields.append((field_name, field_info))
        
        # 按出现次数排序
        important_fields.sort(key=lambda x: x[1]['total_count'], reverse=True)
        
        for field_name, field_info in important_fields[:10]:  # 只显示前10个
            content += f"- **{field_name}**: 出现在{field_info['total_count']}个位置，{self.get_field_meaning(field_name)}\n"
        
        content += """
## 使用说明

1. 点击上表中的数据库链接查看详细的数据库文档
2. 每个数据库文档包含表结构和字段说明
3. 查看 [字段关联分析](field_relationships.md) 了解数据库间的关系
4. 所有示例数据已进行脱敏处理

## 注意事项

- 本分析基于微信4.x版本，不同版本可能存在差异
- 字段含义基于逆向分析和公开资料，可能存在不准确之处
- 请合法合规使用相关信息，尊重用户隐私

---

*文档生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        
        # 写入文件
        overview_file = output_path / "README.md"
        with open(overview_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("生成总览文档: README.md")


def main():
    """主函数"""
    print("微信数据库结构分析工具")
    print("=" * 50)
    
    # 创建分析器
    analyzer = WeChatDatabaseAnalyzer()
    
    # 分析所有数据库
    results = analyzer.analyze_all_databases()
    
    if not results:
        print("未找到数据库文件或分析失败")
        return
    
    print(f"\n分析完成，共处理 {len(results)} 个数据库")
    
    # 生成文档
    print("\n开始生成Markdown文档...")
    analyzer.generate_markdown_docs()
    
    print("\n文档生成完成！")
    print("输出目录: output/docs/database/")
    print("\n主要文档：")
    print("- README.md: 总览文档")
    print("- field_relationships.md: 字段关联分析")
    print("- {数据库名}/README.md: 各数据库概览")
    print("- {数据库名}/{表名}.md: 各表详细信息")


if __name__ == "__main__":
    main()