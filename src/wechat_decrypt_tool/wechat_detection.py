"""微信数据库检测模块

提供微信安装检测和数据库发现功能。
基于PyWxDump的检测逻辑。
"""

import os
import re
import psutil
import ctypes
from pathlib import Path
from typing import List, Dict, Any, Union
from ctypes import wintypes
from datetime import datetime



def get_wx_db(msg_dir: str = None,
              db_types: Union[List[str], str] = None,
              wxids: Union[List[str], str] = None) -> List[dict]:
    r"""
    获取微信数据库路径（基于PyWxDump逻辑）
    :param msg_dir:  微信数据库目录 eg: C:\Users\user\Documents\WeChat Files （非wxid目录）
    :param db_types:  需要获取的数据库类型,如果为空,则获取所有数据库
    :param wxids:  微信id列表,如果为空,则获取所有wxid下的数据库
    :return: [{"wxid": wxid, "db_type": db_type, "db_path": db_path, "wxid_dir": wxid_dir}, ...]
    """
    result = []

    if not msg_dir or not os.path.exists(msg_dir):
        print(f"[-] 微信文件目录不存在: {msg_dir}, 将使用默认路径")
        msg_dir = get_wx_dir_by_reg()

    if not os.path.exists(msg_dir):
        print(f"[-] 目录不存在: {msg_dir}")
        return result

    wxids = wxids.split(";") if isinstance(wxids, str) else wxids
    if not isinstance(wxids, list) or len(wxids) <= 0:
        wxids = None
    db_types = db_types.split(";") if isinstance(db_types, str) and db_types else db_types
    if not isinstance(db_types, list) or len(db_types) <= 0:
        db_types = None

    wxid_dirs = {}  # wx用户目录
    if wxids or "All Users" in os.listdir(msg_dir) or "Applet" in os.listdir(msg_dir) or "WMPF" in os.listdir(msg_dir):
        for sub_dir in os.listdir(msg_dir):
            if os.path.isdir(os.path.join(msg_dir, sub_dir)) and sub_dir not in ["All Users", "Applet", "WMPF"]:
                wxid_dirs[os.path.basename(sub_dir)] = os.path.join(msg_dir, sub_dir)
    else:
        wxid_dirs[os.path.basename(msg_dir)] = msg_dir
    
    for wxid, wxid_dir in wxid_dirs.items():
        if wxids and wxid not in wxids:  # 如果指定wxid,则过滤掉其他wxid
            continue
        for root, dirs, files in os.walk(wxid_dir):
            # 只处理db_storage目录下的数据库文件
            if "db_storage" not in root:
                continue
            for file_name in files:
                if not file_name.endswith(".db"):
                    continue
                # 排除不需要解密的数据库
                if file_name in ["key_info.db"]:
                    continue
                db_type = re.sub(r"\d*\.db$", "", file_name)
                if db_types and db_type not in db_types:  # 如果指定db_type,则过滤掉其他db_type
                    continue
                db_path = os.path.join(root, file_name)
                result.append({"wxid": wxid, "db_type": db_type, "db_path": db_path, "wxid_dir": wxid_dir})
    return result

# Windows API 常量和结构
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MAX_PATH = 260
TH32CS_SNAPPROCESS = 0x00000002

# Windows API 函数
kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

OpenProcess = kernel32.OpenProcess
CloseHandle = kernel32.CloseHandle
GetModuleFileNameExW = psapi.GetModuleFileNameExW
CreateToolhelp32Snapshot = kernel32.CreateToolhelp32Snapshot
Process32FirstW = kernel32.Process32FirstW
Process32NextW = kernel32.Process32NextW

class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ('dwSize', wintypes.DWORD),
        ('cntUsage', wintypes.DWORD),
        ('th32ProcessID', wintypes.DWORD),
        ('th32DefaultHeapID', ctypes.POINTER(wintypes.ULONG)),
        ('th32ModuleID', wintypes.DWORD),
        ('cntThreads', wintypes.DWORD),
        ('th32ParentProcessID', wintypes.DWORD),
        ('pcPriClassBase', wintypes.LONG),
        ('dwFlags', wintypes.DWORD),
        ('szExeFile', wintypes.WCHAR * MAX_PATH)
    ]


# 删除了WeChatDecryptor类，解密功能已移至独立的wechat_decrypt.py脚本


def find_wechat_databases() -> List[str]:
    """在新的xwechat_files目录中查找微信数据库文件

    返回值:
        数据库文件路径列表
    """
    db_files = []

    # 获取用户的Documents目录
    documents_dir = Path.home() / "Documents"

    # 检查新的微信4.0+目录结构
    wechat_dirs = [
        documents_dir / "xwechat_files",  # 新版微信4.0+
        documents_dir / "WeChat Files"     # 旧版微信
    ]
    
    for wechat_dir in wechat_dirs:
        if not wechat_dir.exists():
            continue
        
        # 查找用户目录（wxid_*模式）
        for user_dir in wechat_dir.iterdir():
            if not user_dir.is_dir():
                continue

            # 跳过系统目录
            if user_dir.name in ['All Users', 'Applet', 'WMPF']:
                continue

            # 查找Msg目录
            msg_dir = user_dir / "Msg"
            if msg_dir.exists():
                # 查找数据库文件
                for db_file in msg_dir.glob("*.db"):
                    if db_file.is_file():
                        db_files.append(str(db_file))

                # 同时检查Multi目录
                multi_dir = msg_dir / "Multi"
                if multi_dir.exists():
                    for db_file in multi_dir.glob("*.db"):
                        if db_file.is_file():
                            db_files.append(str(db_file))
    
    return db_files


def get_process_exe_path(process_id):
    """获取进程可执行文件路径"""
    h_process = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, process_id)
    if not h_process:
        return None
    
    exe_path = ctypes.create_unicode_buffer(MAX_PATH)
    if GetModuleFileNameExW(h_process, None, exe_path, MAX_PATH) > 0:
        CloseHandle(h_process)
        return exe_path.value
    else:
        CloseHandle(h_process)
        return None

def get_process_list():
    """获取系统进程列表"""
    h_process_snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if h_process_snap == ctypes.wintypes.HANDLE(-1).value:
        return []
    
    pe32 = PROCESSENTRY32W()
    pe32.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    process_list = []
    
    if not Process32FirstW(h_process_snap, ctypes.byref(pe32)):
        CloseHandle(h_process_snap)
        return []
    
    while True:
        process_list.append((pe32.th32ProcessID, pe32.szExeFile))
        if not Process32NextW(h_process_snap, ctypes.byref(pe32)):
            break
    
    CloseHandle(h_process_snap)
    return process_list

def auto_detect_wechat_data_dirs():
    """
    自动检测微信数据目录 - 多策略组合检测
    :return: 检测到的微信数据目录列表
    """
    detected_dirs = []
    
    # 策略1：注册表检测已移除

    # 策略2和策略3：注册表相关检测已移除

    # 策略1：常见驱动器扫描微信相关目录
    common_wechat_patterns = [
        "WeChat Files", "wechat_files", "xwechat_files", "wechatMSG",
        "WeChat", "微信", "Weixin", "wechat"
    ]

    # 扫描常见驱动器
    drives = ['C:', 'D:', 'E:', 'F:']
    for drive in drives:
        if not os.path.exists(drive):
            continue
        
        try:
            # 扫描驱动器根目录和常见目录
            scan_paths = [
                drive + os.sep,
                os.path.join(drive + os.sep, "Users"),
            ]
            
            for scan_path in scan_paths:
                if not os.path.exists(scan_path):
                    continue
                
                try:
                    for item in os.listdir(scan_path):
                        item_path = os.path.join(scan_path, item)
                        if not os.path.isdir(item_path):
                            continue
                        
                        # 检查是否匹配微信目录模式
                        for pattern in common_wechat_patterns:
                            if pattern.lower() in item.lower():
                                # 检查是否包含wxid目录
                                if has_wxid_directories(item_path):
                                    if item_path not in detected_dirs:
                                        detected_dirs.append(item_path)
                                        print(f"[DEBUG] 目录扫描检测成功: {item_path}")
                                break
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            continue
    
    # 策略2：进程内存分析（简化版）
    try:
        process_list = get_process_list()
        for pid, process_name in process_list:
            if process_name.lower() in ['weixin.exe', 'wechat.exe']:
                # 尝试获取进程的工作目录
                try:
                    import psutil
                    proc = psutil.Process(pid)
                    cwd = proc.cwd()
                    # 从进程工作目录向上查找可能的数据目录
                    parent_dirs = [cwd]
                    current = cwd
                    for _ in range(3):  # 向上查找3级目录
                        parent = os.path.dirname(current)
                        if parent != current:
                            parent_dirs.append(parent)
                            current = parent
                        else:
                            break
                    
                    for parent_dir in parent_dirs:
                        for pattern in common_wechat_patterns:
                            potential_dir = os.path.join(parent_dir, pattern)
                            if os.path.exists(potential_dir) and has_wxid_directories(potential_dir):
                                if potential_dir not in detected_dirs:
                                    detected_dirs.append(potential_dir)
                                    print(f"[DEBUG] 进程分析检测成功: {potential_dir}")
                except:
                    pass
    except:
        pass
    
    return detected_dirs


# 删除了所有解密相关函数，解密功能已移至独立的wechat_decrypt.py脚本

def has_wxid_directories(directory):
    """
    检查目录是否包含wxid格式的子目录
    :param directory: 要检查的目录
    :return: 是否包含wxid目录
    """
    try:
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            if os.path.isdir(item_path) and (item.startswith('wxid_') or len(item) > 10):
                # 进一步检查是否包含数据库文件
                for root, _, files in os.walk(item_path):
                    for file in files:
                        if file.endswith('.db'):
                            return True
        return False
    except:
        return False

def get_wx_dir_by_reg(wxid="all"):
    """
    通过多种方法获取微信目录 - 改进的自动检测
    :param wxid: 微信id，如果为"all"则返回WeChat Files目录，否则返回具体wxid目录
    :return: 微信目录路径
    """
    if not wxid:
        return None

    # 使用新的自动检测方法
    detected_dirs = auto_detect_wechat_data_dirs()

    if not detected_dirs:
        print(f"[DEBUG] 未检测到任何微信数据目录")
        return None

    # 返回第一个检测到的目录
    wx_dir = detected_dirs[0]
    print(f"[DEBUG] 使用检测到的微信目录: {wx_dir}")

    # 如果指定了具体的wxid，返回wxid目录
    if wxid and wxid != "all":
        wxid_dir = os.path.join(wx_dir, wxid)
        return wxid_dir if os.path.exists(wxid_dir) else None

    return wx_dir if os.path.exists(wx_dir) else None

def detect_wechat_accounts_from_backup(backup_base_path: str = None) -> List[Dict[str, Any]]:
    """
    从指定的备份路径检测微信账号

    Args:
        backup_base_path: 微信文件基础路径，如果为None则自动检测

    Returns:
        账号信息列表，每个账号包含：
        - account_name: 账号名
        - backup_dir: 备份目录路径
        - data_dir: 实际数据目录路径
        - databases: 数据库文件列表
    """
    accounts = []

    # 如果没有指定路径，尝试自动检测
    if backup_base_path is None:
        # 使用自动检测找到包含Backup的路径
        detected_dirs = auto_detect_wechat_data_dirs()
        for detected_dir in detected_dirs:
            # 首先检查直接的Backup目录
            backup_test_dir = os.path.join(detected_dir, "Backup")
            if os.path.exists(backup_test_dir):
                backup_base_path = detected_dir
                break

            # 然后检查子目录中的Backup目录（如xwechat_files/Backup）
            try:
                for subdir in os.listdir(detected_dir):
                    subdir_path = os.path.join(detected_dir, subdir)
                    if os.path.isdir(subdir_path):
                        backup_test_dir = os.path.join(subdir_path, "Backup")
                        if os.path.exists(backup_test_dir):
                            backup_base_path = subdir_path
                            break
                if backup_base_path:
                    break
            except (PermissionError, OSError):
                continue

        # 如果还是没找到，返回空列表
        if backup_base_path is None:
            return accounts

    # 检查备份目录
    backup_dir = os.path.join(backup_base_path, "Backup")
    if not os.path.exists(backup_dir):
        return accounts

    try:
        # 遍历备份目录下的所有子文件夹（每个代表一个账号）
        for item in os.listdir(backup_dir):
            account_backup_path = os.path.join(backup_dir, item)
            if not os.path.isdir(account_backup_path):
                continue

            account_name = item

            # 在上级目录中查找对应的实际数据文件夹
            # 命名规则：{账号名}_{随机字符}
            data_dir = None
            try:
                for data_item in os.listdir(backup_base_path):
                    data_item_path = os.path.join(backup_base_path, data_item)
                    if (os.path.isdir(data_item_path) and
                        data_item.startswith(f"{account_name}_") and
                        data_item != "Backup"):
                        data_dir = data_item_path
                        break
            except (PermissionError, OSError):
                continue

            # 收集该账号的数据库文件
            databases = []
            if data_dir and os.path.exists(data_dir):
                databases = collect_account_databases(data_dir, account_name)

            account_info = {
                "account_name": account_name,
                "backup_dir": account_backup_path,
                "data_dir": data_dir,
                "databases": databases,
                "database_count": len(databases)
            }

            accounts.append(account_info)

    except (PermissionError, OSError) as e:
        # 如果无法访问备份目录，返回空列表
        pass

    return accounts


def _resolve_login_paths_from_base(provided_path: str) -> Dict[str, str]:
    """
    根据用户提供的路径推断 base_path 和 login_dir。

    兼容三种传入：
    - 直接传 xwechat_files 根目录
    - 传 xwechat_files/all_users
    - 传 xwechat_files/all_users/login
    """
    base_path = provided_path
    login_dir = os.path.join(provided_path, "all_users", "login")

    try:
        norm = os.path.normpath(provided_path)
        last = os.path.basename(norm).lower()
        parent = os.path.dirname(norm)
        parent_last = os.path.basename(parent).lower() if parent else ""

        if last == "login" and parent_last == "all_users":
            # .../xwechat_files/all_users/login -> base_path 为 xwechat_files
            base_path = os.path.dirname(parent)
            login_dir = norm
        elif last == "all_users":
            # .../xwechat_files/all_users -> login_dir 追加 login
            base_path = os.path.dirname(norm)
            login_dir = os.path.join(norm, "login")
        else:
            # 认为传的是 xwechat_files 根
            base_path = norm
            login_dir = os.path.join(norm, "all_users", "login")
    except Exception:
        # 兜底：保持初始推断
        pass

    return {"base_path": base_path, "login_dir": login_dir}


def detect_wechat_accounts_from_login(login_base_path: str = None) -> List[Dict[str, Any]]:
    """
    通过登录信息目录检测微信账号，并映射到实际数据目录。

    Args:
        login_base_path: 可选的微信数据根目录。

    Returns:
        账号信息列表（与 Backup 检测返回结构一致）
    """
    accounts: List[Dict[str, Any]] = []

    # 若用户提供路径，则优先按该路径推断
    if login_base_path:
        paths = _resolve_login_paths_from_base(login_base_path)
        base_path = paths["base_path"]
        login_dir = paths["login_dir"]

        if not os.path.exists(login_dir):
            return accounts
    else:
        # 自动检测：遍历候选根目录，寻找登录信息目录
        base_path = None
        login_dir = None
        detected_dirs = auto_detect_wechat_data_dirs()
        for detected_dir in detected_dirs:
            try:
                test_login = os.path.join(detected_dir, "all_users", "login")
                if os.path.exists(test_login):
                    base_path = detected_dir
                    login_dir = test_login
                    break

                # 也检查一层子目录
                for sub in os.listdir(detected_dir):
                    sub_path = os.path.join(detected_dir, sub)
                    if not os.path.isdir(sub_path):
                        continue
                    test_login = os.path.join(sub_path, "all_users", "login")
                    if os.path.exists(test_login):
                        base_path = sub_path
                        login_dir = test_login
                        break
                if base_path:
                    break
            except (PermissionError, OSError):
                continue

        if not base_path or not login_dir:
            return accounts

    # 枚举 login 目录下的子项，每个子项代表一个账号标识（可能是文件或文件夹）
    try:
        for item in os.listdir(login_dir):
            account_name = item
            account_login_item_path = os.path.join(login_dir, item)
            # 无论是文件还是文件夹，都视为一个账号标识
            if not os.path.exists(account_login_item_path):
                continue

            # 在 base_path 下查找以 {account_name}_ 开头的数据目录（与 Backup 规则一致）
            data_dir = None
            try:
                for data_item in os.listdir(base_path):
                    data_item_path = os.path.join(base_path, data_item)
                    if (
                        os.path.isdir(data_item_path)
                        and data_item.startswith(f"{account_name}_")
                        and data_item not in ["Backup", "all_users"]
                    ):
                        data_dir = data_item_path
                        break
            except (PermissionError, OSError):
                pass

            databases = collect_account_databases(data_dir, account_name) if data_dir else []

            accounts.append(
                {
                    "account_name": account_name,
                    "backup_dir": None,
                    "data_dir": data_dir,
                    "databases": databases,
                    "database_count": len(databases),
                }
            )
    except (PermissionError, OSError):
        # 无权限访问时返回已收集的账号
        return accounts

    return accounts

def collect_account_databases(data_dir: str, account_name: str) -> List[Dict[str, Any]]:
    """
    收集指定账号数据目录下的所有数据库文件

    Args:
        data_dir: 账号数据目录
        account_name: 账号名

    Returns:
        数据库文件信息列表
    """
    databases = []

    if not os.path.exists(data_dir):
        return databases

    try:
        # 递归查找所有.db文件
        for root, dirs, files in os.walk(data_dir):
            for file_name in files:
                if not file_name.endswith('.db'):
                    continue

                # 排除不需要解密的数据库
                if file_name in ["key_info.db"]:
                    continue

                db_path = os.path.join(root, file_name)

                # 确定数据库类型
                db_type = re.sub(r'\d*\.db$', '', file_name)

                try:
                    file_size = os.path.getsize(db_path)
                except OSError:
                    file_size = 0

                db_info = {
                    "path": db_path,
                    "name": file_name,
                    "type": db_type,
                    "size": file_size,
                    "relative_path": os.path.relpath(db_path, data_dir)
                }

                databases.append(db_info)

    except (PermissionError, OSError):
        pass

    return databases


def detect_wechat_installation(data_root_path: str | None = None) -> Dict[str, Any]:
    """
    检测微信安装情况 - 改进的多账户检测逻辑
    """
    result = {
        "wechat_version": None,
        "wechat_install_path": None,
        "wechat_exe_path": None,
        "is_running": False,
        "accounts": [],
        "total_accounts": 0,
        "total_databases": 0,
        "detection_errors": [],
        "detection_methods": [],
        # 保持向后兼容性的字段
        "wechat_data_dirs": [],
        "message_dirs": [],
        "databases": [],
        "user_accounts": []
    }

    # 1. 进程检测 - 检测微信是否运行
    result["detection_methods"].append("进程检测")
    process_list = get_process_list()

    for pid, process_name in process_list:
        # 检查Weixin.exe进程
        if process_name.lower() == 'weixin.exe':
            try:
                exe_path = get_process_exe_path(pid)
                if exe_path:
                    result["wechat_exe_path"] = exe_path
                    result["wechat_install_path"] = os.path.dirname(exe_path)
                    result["is_running"] = True
                    result["detection_methods"].append(f"检测到微信进程: {process_name} (PID: {pid})")

                    # 尝试获取版本信息
                    try:
                        import win32api
                        version_info = win32api.GetFileVersionInfo(exe_path, "\\")
                        version = f"{version_info['FileVersionMS'] >> 16}.{version_info['FileVersionMS'] & 0xFFFF}.{version_info['FileVersionLS'] >> 16}.{version_info['FileVersionLS'] & 0xFFFF}"
                        result["wechat_version"] = version
                        result["detection_methods"].append(f"获取到微信版本: {version}")
                    except ImportError:
                        result["detection_errors"].append("win32api库未安装，无法获取版本信息")
                    except Exception as e:
                        result["detection_errors"].append(f"版本获取失败: {e}")
                    break
            except Exception as e:
                result["detection_errors"].append(f"进程信息获取失败: {e}")

    if not result["is_running"]:
        result["detection_methods"].append("未检测到微信进程")

    # 2. 使用新的账号检测逻辑：同时支持 Backup 与登录信息目录，并合并结果
    result["detection_methods"].append("多账户检测（多来源合并）")
    try:
        # 支持前端兜底路径：若提供 data_root_path，则两种方式都以该路径为基准
        accounts_from_backup = detect_wechat_accounts_from_backup(
            backup_base_path=data_root_path
        )
        accounts_from_login = detect_wechat_accounts_from_login(
            login_base_path=data_root_path
        )

        # 合并账号：按 account_name 去重，优先保留信息更完整者
        account_map: Dict[str, Dict[str, Any]] = {}

        def _merge_account(acc: Dict[str, Any]):
            name = acc.get("account_name")
            if not name:
                return
            if name not in account_map:
                account_map[name] = {
                    "account_name": name,
                    "backup_dir": acc.get("backup_dir"),
                    "data_dir": acc.get("data_dir"),
                    "databases": list(acc.get("databases", [])),
                    "database_count": int(acc.get("database_count", 0)),
                }
            else:
                existing = account_map[name]
                if not existing.get("backup_dir") and acc.get("backup_dir"):
                    existing["backup_dir"] = acc.get("backup_dir")
                if not existing.get("data_dir") and acc.get("data_dir"):
                    existing["data_dir"] = acc.get("data_dir")
                # 合并数据库（按 path 去重）
                seen_paths = {d.get("path") for d in existing.get("databases", [])}
                for db in acc.get("databases", []):
                    if db.get("path") not in seen_paths:
                        existing.setdefault("databases", []).append(db)
                        seen_paths.add(db.get("path"))
                existing["database_count"] = len(existing.get("databases", []))

        for acc in accounts_from_backup:
            _merge_account(acc)
        for acc in accounts_from_login:
            _merge_account(acc)

        accounts = list(account_map.values())
        result["accounts"] = accounts
        result["total_accounts"] = len(accounts)

        # 统计总数据库数量
        total_db_count = sum(account.get("database_count", 0) for account in accounts)
        result["total_databases"] = total_db_count

        if accounts:
            result["detection_methods"].append(
                f"检测到 {len(accounts)} 个微信账户（已合并两种来源）"
            )
            result["detection_methods"].append(f"总计 {total_db_count} 个数据库文件")

            # 为每个账户添加详细信息
            for account in accounts:
                account_name = account.get("account_name")
                db_count = account.get("database_count", 0)
                data_dir_status = "已找到" if account.get("data_dir") else "未找到"
                result["detection_methods"].append(
                    f"账户 {account_name}: {db_count} 个数据库, 数据目录{data_dir_status}"
                )
        else:
            result["detection_methods"].append("未检测到微信账户")

        # 填充向后兼容性字段
        for account in accounts:
            if account.get("data_dir"):
                result["wechat_data_dirs"].append(account["data_dir"])
                result["message_dirs"].append(account["data_dir"])
            result["user_accounts"].append(account.get("account_name"))

            # 添加数据库到兼容性列表
            for db in account.get("databases", []):
                result["databases"].append({
                    "path": db["path"],
                    "name": db["name"],
                    "type": db["type"],
                    "size": db["size"],
                    "user": account.get("account_name"),
                    "user_dir": account.get("data_dir"),
                })

    except Exception as e:
        result["detection_errors"].append(f"账户检测失败: {str(e)}")

    # 3. 如果新检测方法没有找到账户，尝试旧的检测方法作为备用
    if not result["accounts"]:
        result["detection_methods"].append("备用检测方法")
        try:
            wx_dir = get_wx_dir_by_reg()
            if wx_dir and os.path.exists(wx_dir):
                result["wechat_data_dirs"].append(wx_dir)
                result["detection_methods"].append(f"通过备用方法找到微信目录: {wx_dir}")

                # 使用旧的检测逻辑
                db_list = get_wx_db(msg_dir=wx_dir)

                # 按账户组织数据库
                account_db_map = {}
                for db_info in db_list:
                    wxid = db_info["wxid"]
                    if wxid not in account_db_map:
                        account_db_map[wxid] = {
                            "account_name": wxid,
                            "backup_dir": None,
                            "data_dir": db_info["wxid_dir"],
                            "databases": [],
                            "database_count": 0
                        }

                    if os.path.exists(db_info["db_path"]):
                        db_entry = {
                            "path": db_info["db_path"],
                            "name": os.path.basename(db_info["db_path"]),
                            "type": db_info["db_type"],
                            "size": os.path.getsize(db_info["db_path"]),
                            "relative_path": os.path.relpath(db_info["db_path"], db_info["wxid_dir"])
                        }
                        account_db_map[wxid]["databases"].append(db_entry)
                        account_db_map[wxid]["database_count"] += 1

                result["accounts"] = list(account_db_map.values())
                result["total_accounts"] = len(result["accounts"])
                result["total_databases"] = sum(account["database_count"] for account in result["accounts"])

                result["detection_methods"].append(f"备用方法检测到 {result['total_accounts']} 个账户")
                result["detection_methods"].append(f"总计 {result['total_databases']} 个数据库文件")
            else:
                result["detection_methods"].append("备用检测方法未找到微信目录")
        except Exception as e:
            result["detection_errors"].append(f"备用检测失败: {str(e)}")

    return result


def detect_current_logged_in_account(base_path: str = None) -> Dict[str, Any]:
    """
    通过key_info.db文件时间检测当前登录的微信账号
    
    Args:
        base_path: 微信数据根目录，如果为None则自动检测
        
    Returns:
        当前登录账号信息
    """
    current_account = None
    latest_time = None
    
    # 添加调试信息
    print(f"[DEBUG] 开始检测当前登录账号，提供的base_path: {base_path}")
    
    # 如果没有指定路径，尝试自动检测
    if base_path is None:
        detected_dirs = auto_detect_wechat_data_dirs()
        print(f"[DEBUG] 自动检测到的目录: {detected_dirs}")
        if not detected_dirs:
            return {
                "current_account": None,
                "latest_time": None,
                "message": "未检测到微信数据目录"
            }
        base_path = detected_dirs[0]
    
    print(f"[DEBUG] 使用的base_path: {base_path}")
    
    # 查找登录信息目录 - 尝试多个可能的路径
    possible_login_paths = [
        os.path.join(base_path, "all_users", "login"),  # 标准路径
        os.path.join(base_path, "login"),               # 备选路径1
    ]
    
    # 也尝试在子目录中查找
    try:
        for item in os.listdir(base_path):
            item_path = os.path.join(base_path, item)
            if os.path.isdir(item_path):
                possible_login_paths.extend([
                    os.path.join(item_path, "all_users", "login"),  # 子目录中的标准路径
                    os.path.join(item_path, "login"),               # 子目录中的备选路径
                ])
    except (PermissionError, OSError):
        pass
    
    login_dir = None
    for path in possible_login_paths:
        print(f"[DEBUG] 检查路径: {path}")
        if os.path.exists(path):
            login_dir = path
            print(f"[DEBUG] 找到登录目录: {login_dir}")
            break
    
    if not login_dir:
        return {
            "current_account": None,
            "latest_time": None,
            "message": f"未找到登录信息目录，尝试的路径: {possible_login_paths}"
        }
    
    try:
        # 遍历登录目录下的所有账号文件夹
        items = os.listdir(login_dir)
        print(f"[DEBUG] 登录目录内容: {items}")
        
        for item in items:
            item_path = os.path.join(login_dir, item)
            print(f"[DEBUG] 检查项目: {item}, 路径: {item_path}, 是否为目录: {os.path.isdir(item_path)}")
            
            if not os.path.isdir(item_path):
                continue
                
            # 检查key_info.db文件
            key_info_path = os.path.join(item_path, "key_info.db")
            print(f"[DEBUG] 检查key_info.db文件: {key_info_path}, 是否存在: {os.path.exists(key_info_path)}")
            
            if not os.path.exists(key_info_path):
                continue
                
            # 获取文件修改时间
            try:
                file_time = os.path.getmtime(key_info_path)
                file_datetime = datetime.fromtimestamp(file_time)
                print(f"[DEBUG] 找到key_info.db文件: {key_info_path}, 修改时间: {file_datetime}")
                
                # 更新最新登录的账号
                if latest_time is None or file_time > latest_time:
                    latest_time = file_time
                    current_account = item
                    print(f"[DEBUG] 更新最新登录账号: {current_account}, 时间: {file_datetime}")
                    
            except OSError as e:
                print(f"[DEBUG] 无法获取文件时间: {key_info_path}, 错误: {e}")
                continue
                
    except (PermissionError, OSError) as e:
        print(f"[DEBUG] 无法访问登录目录: {login_dir}, 错误: {e}")
        return {
            "current_account": None,
            "latest_time": None,
            "message": f"无法访问登录目录: {e}"
        }
    
    if current_account:
        print(f"[DEBUG] 最终结果: 当前登录账号 {current_account}, 时间 {latest_time}")
        return {
            "current_account": current_account,
            "latest_time": latest_time,
            "latest_time_formatted": datetime.fromtimestamp(latest_time).isoformat() if latest_time else None,
            "message": f"检测到当前登录账号: {current_account}"
        }
    else:
        print(f"[DEBUG] 最终结果: 未检测到当前登录账号")
        return {
            "current_account": None,
            "latest_time": None,
            "message": "未检测到当前登录账号"
        }


def get_wechat_info() -> Dict[str, Any]:
    """获取微信安装和数据库信息

    返回值:
        包含微信信息的字典
    """
    return detect_wechat_installation()
