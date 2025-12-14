#!/usr/bin/env python3
"""
测试数据库文件的可读性和数据内容
"""

import sqlite3
import os
from pathlib import Path

def test_database(db_path):
    """测试单个数据库文件"""
    db_name = db_path.name
    print(f"\n=== 测试数据库: {db_name} ===")
    
    try:
        # 检查文件大小
        file_size = db_path.stat().st_size
        print(f"文件大小: {file_size:,} 字节")
        
        if file_size == 0:
            print("❌ 文件为空")
            return False
            
        # 尝试连接数据库
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # 获取所有表名
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"表数量: {len(tables)}")
        
        if len(tables) == 0:
            print("❌ 没有表")
            conn.close()
            return False
            
        # 检查每个表的数据量
        table_with_data = 0
        total_rows = 0
        
        for table in tables:
            table_name = table[0]
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                row_count = cursor.fetchone()[0]
                total_rows += row_count
                if row_count > 0:
                    table_with_data += 1
                    print(f"  ✅ {table_name}: {row_count:,} 行")
                else:
                    print(f"  ❌ {table_name}: 0 行")
            except Exception as e:
                print(f"  ⚠️  {table_name}: 查询失败 - {e}")
        
        print(f"有数据的表: {table_with_data}/{len(tables)}")
        print(f"总数据行数: {total_rows:,}")
        
        conn.close()
        
        if total_rows > 0:
            print("✅ 数据库可用")
            return True
        else:
            print("❌ 数据库无数据")
            return False
            
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return False

def main():
    """主函数"""
    print("微信数据库文件测试工具")
    print("=" * 50)
    
    databases_path = Path("output/databases")
    if not databases_path.exists():
        print("❌ 数据库目录不存在")
        return
    
    # 查找所有数据库文件
    db_files = []
    for account_dir in databases_path.iterdir():
        if account_dir.is_dir():
            for db_file in account_dir.glob("*.db"):
                db_files.append(db_file)
    
    print(f"找到 {len(db_files)} 个数据库文件")
    
    available_dbs = []
    empty_dbs = []
    error_dbs = []
    
    for db_file in sorted(db_files):
        result = test_database(db_file)
        if result:
            available_dbs.append(db_file.name)
        elif db_file.stat().st_size == 0:
            empty_dbs.append(db_file.name)
        else:
            error_dbs.append(db_file.name)
    
    print("\n" + "=" * 50)
    print("测试结果总结:")
    print(f"✅ 可用数据库 ({len(available_dbs)}): {', '.join(available_dbs) if available_dbs else '无'}")
    print(f"❌ 空数据库 ({len(empty_dbs)}): {', '.join(empty_dbs) if empty_dbs else '无'}")
    print(f"⚠️  问题数据库 ({len(error_dbs)}): {', '.join(error_dbs) if error_dbs else '无'}")

if __name__ == "__main__":
    main()