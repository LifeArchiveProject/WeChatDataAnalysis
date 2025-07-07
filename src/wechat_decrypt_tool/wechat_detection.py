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

def detect_wechat_installation() -> Dict[str, Any]:
    """
    检测微信安装情况 - 完全按照PyWxDump的逻辑实现
    """
    result = {
        "wechat_version": None,
        "wechat_install_path": None,
        "wechat_exe_path": None,
        "wechat_data_dirs": [],
        "message_dirs": [],
        "databases": [],
        "version_detected": None,
        "is_running": False,
        "user_accounts": [],
        "detection_errors": [],
        "detection_methods": []
    }

    # 进程检测 - 只检测Weixin.exe（按照用户要求）
    result["detection_methods"].append("进程检测")
    process_list = get_process_list()

    for pid, process_name in process_list:
        # 只检查Weixin.exe进程
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

    # 2. 使用自动检测逻辑获取微信目录和数据库
    result["detection_methods"].append("目录自动检测")
    try:
        wx_dir = get_wx_dir_by_reg()
        if wx_dir and os.path.exists(wx_dir):
            result["wechat_data_dirs"].append(wx_dir)
            result["detection_methods"].append(f"通过自动检测找到微信目录: {wx_dir}")

            # 使用PyWxDump的get_wx_db函数获取数据库信息
            db_list = get_wx_db(msg_dir=wx_dir)  # 移除db_types限制，获取所有.db文件

            # 统计用户账户和消息目录
            user_accounts_set = set()
            message_dirs_set = set()

            for db_info in db_list:
                wxid = db_info["wxid"]
                wxid_dir = db_info["wxid_dir"]
                db_path = db_info["db_path"]
                db_type = db_info["db_type"]

                # 添加用户账户
                user_accounts_set.add(wxid)
                message_dirs_set.add(wxid_dir)

                # 添加数据库信息
                if os.path.exists(db_path):
                    result["databases"].append({
                        "path": db_path,
                        "name": os.path.basename(db_path),
                        "type": db_type,
                        "size": os.path.getsize(db_path),
                        "user": wxid,
                        "user_dir": wxid_dir
                    })

            # 转换为列表
            result["user_accounts"] = list(user_accounts_set)
            result["message_dirs"] = list(message_dirs_set)

            result["detection_methods"].append(f"检测到 {len(result['user_accounts'])} 个用户账户")
            result["detection_methods"].append(f"检测到 {len(result['databases'])} 个数据库文件")

            # 按数据库类型统计
            db_type_count = {}
            for db in result["databases"]:
                db_type = db["type"]
                db_type_count[db_type] = db_type_count.get(db_type, 0) + 1

            if db_type_count:
                type_summary = ", ".join([f"{k}({v})" for k, v in db_type_count.items()])
                result["detection_methods"].append(f"数据库类型分布: {type_summary}")
        else:
            result["detection_methods"].append("自动检测未找到微信目录")
    except Exception as e:
        result["detection_errors"].append(f"目录检测失败: {str(e)}")


    return result


def get_wechat_info() -> Dict[str, Any]:
    """获取微信安装和数据库信息

    返回值:
        包含微信信息的字典
    """
    return detect_wechat_installation()
