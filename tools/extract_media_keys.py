#!/usr/bin/env python3
"""
提取微信 4.x 媒体解密密钥 (需要管理员权限运行)

用法:
1. 确保微信正在运行
2. 以管理员身份运行 PowerShell
3. cd 到项目目录
4. 运行: uv run python tools/extract_media_keys.py
"""

import sys
sys.path.insert(0, "src")
sys.path.insert(0, "WxDatDecrypt")

import json
from pathlib import Path

try:
    from key import find_key
except ImportError as e:
    print(f"[ERROR] 无法导入 WxDatDecrypt: {e}")
    print("请确保 pymem, yara-python, pycryptodome 已安装")
    sys.exit(1)

# ========== 配置 ==========
REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DB_DIR = REPO_ROOT / "output" / "databases"


def main():
    print("=" * 60)
    print("微信 4.x 媒体解密密钥提取工具")
    print("=" * 60)
    
    # 1. 列出所有账号
    print("\n[1] 列出已解密账号...")
    if not OUTPUT_DB_DIR.exists():
        print("[ERROR] output/databases 目录不存在")
        sys.exit(1)
    
    accounts = []
    for p in OUTPUT_DB_DIR.iterdir():
        if p.is_dir() and (p / "_source.json").exists():
            accounts.append(p.name)
    
    if not accounts:
        print("[ERROR] 没有找到已解密的账号")
        sys.exit(1)
    
    print(f"    找到 {len(accounts)} 个账号")
    
    # 2. 处理每个账号
    for account in accounts:
        print(f"\n[2] 处理账号: {account}")
        account_dir = OUTPUT_DB_DIR / account
        
        # 读取 _source.json
        source_json = account_dir / "_source.json"
        with open(source_json, "r", encoding="utf-8") as f:
            source = json.load(f)
        
        wxid_dir_str = source.get("wxid_dir", "")
        if not wxid_dir_str:
            print("    [SKIP] 没有 wxid_dir")
            continue
        
        wxid_dir = Path(wxid_dir_str)
        if not wxid_dir.exists():
            print(f"    [SKIP] wxid_dir 不存在: {wxid_dir}")
            continue
        
        # 使用 WxDatDecrypt 的 find_key 函数
        print(f"    wxid_dir: {wxid_dir}")
        print("    正在提取密钥 (需要微信正在运行且有管理员权限)...")
        
        try:
            xor_key, aes_key = find_key(wxid_dir, version=4)
            
            # 保存到 _media_keys.json
            keys_file = account_dir / "_media_keys.json"
            keys_data = {
                "xor": xor_key,
                "aes": aes_key.decode("ascii") if isinstance(aes_key, bytes) else str(aes_key),
            }
            with open(keys_file, "w", encoding="utf-8") as f:
                json.dump(keys_data, f, indent=2)
            print(f"    [OK] 密钥已保存到: {keys_file}")
            print(f"    XOR key: {xor_key}")
            print(f"    AES key: {keys_data['aes']}")
        except Exception as e:
            print(f"    [ERROR] 提取失败: {e}")
    
    print("\n" + "=" * 60)
    print("完成！请重启后端服务以使密钥生效。")
    print("=" * 60)


if __name__ == "__main__":
    main()
