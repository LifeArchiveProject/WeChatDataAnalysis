from typing import Optional
import psutil
from fastapi import APIRouter

from ..logging_config import get_logger
from ..path_fix import PathFixRoute

logger = get_logger(__name__)

router = APIRouter(route_class=PathFixRoute)


@router.get("/api/wechat-detection", summary="详细检测微信安装信息")
async def detect_wechat_detailed(data_root_path: Optional[str] = None):
    """详细检测微信安装信息，包括版本、路径、消息目录等。"""
    logger.info("开始执行微信检测")
    try:
        from ..wechat_detection import detect_wechat_installation, detect_current_logged_in_account

        info = detect_wechat_installation(data_root_path=data_root_path)

        # 检测当前登录账号
        current_account_info = detect_current_logged_in_account(data_root_path)

        # 【新增特性】目录匹配校验：处理目录名 wxid_xxxx_yyyy 与真实 wxid_xxxx 的适配
        if current_account_info and current_account_info.get("current_account"):
            base_wxid = current_account_info["current_account"]
            current_account_info["matched_folder"] = base_wxid  # 默认兜底

            # 遍历寻找以该 wxid 开头的用户文件夹（支持后缀匹配）
            for acc in info.get("accounts", []):
                acc_name = acc["account_name"]
                if acc_name == base_wxid or acc_name.startswith(f"{base_wxid}_"):
                    current_account_info["matched_folder"] = acc_name
                    break

        info['current_account'] = current_account_info
        # logger.info(current_account_info)

        # 添加一些统计信息
        stats = {
            'total_databases': len(info['databases']),
            'total_user_accounts': len(info['user_accounts']),
            'total_message_dirs': len(info['message_dirs']),
            'has_wechat_installed': info['wechat_install_path'] is not None,
            'detection_time': __import__('datetime').datetime.now().isoformat(),
        }

        logger.info(f"微信检测完成: 检测到 {stats['total_user_accounts']} 个账户, {stats['total_databases']} 个数据库")

        return {
            'status': 'success',
            'data': info,
            'statistics': stats,
        }
    except Exception as e:
        logger.error(f"微信检测失败: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'data': None,
            'statistics': None,
        }


@router.get("/api/current-account", summary="检测当前登录账号")
async def detect_current_account(data_root_path: Optional[str] = None):
    """检测当前登录的微信账号"""
    logger.info("开始检测当前登录账号")
    try:
        from ..wechat_detection import detect_current_logged_in_account

        result = detect_current_logged_in_account(data_root_path)

        logger.info(f"当前账号检测完成: {result.get('message', '无结果')}")

        return {
            'status': 'success',
            'data': result,
        }
    except Exception as e:
        logger.error(f"当前账号检测失败: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'data': None,
        }


@router.get("/api/wechat/status", summary="检查微信运行状态")
async def check_wechat_status():
    """
    检查系统微信主进程状态
    逻辑：
    1. 匹配进程名 Weixin.exe 或 WeChat.exe
    2. 校验命令行必须包含 exe 名称（排除崩溃后的残留/无效进程）
    3. 在有效进程中选择命令行最短的一个作为主进程
    """
    process_name_targets = ["Weixin.exe", "WeChat.exe"]

    wx_status = {
        "is_running": False,
        "pid": None,
        "exe_path": None,
        "memory_usage_mb": 0.0
    }

    try:
        candidates = []

        for proc in psutil.process_iter(['pid', 'name', 'exe', 'memory_info', 'cmdline']):
            try:
                p_name = proc.info.get('name')
                if p_name and p_name in process_name_targets:
                    # 获取命令行并合并为字符串
                    cmdline_list = proc.info.get('cmdline') or []
                    cmdline_str = " ".join(cmdline_list).lower()

                    if any(target.lower() in cmdline_str for target in process_name_targets):
                        candidates.append({
                            "pid": proc.info['pid'],
                            "exe_path": proc.info['exe'],
                            "cmd_len": len(cmdline_str),
                            "memory_info": proc.info['memory_info']
                        })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        if candidates:
            main_proc = min(candidates, key=lambda x: x['cmd_len'])

            wx_status["is_running"] = True
            wx_status["pid"] = main_proc["pid"]
            wx_status["exe_path"] = main_proc["exe_path"]

            mem = main_proc["memory_info"]
            if mem:
                wx_status["memory_usage_mb"] = round(mem.rss / (1024 * 1024), 2)

        return {
            "status": 0,
            "errmsg": "ok",
            "wx_status": wx_status
        }

    except Exception as e:
        return {
            "status": -1,
            "errmsg": f"检查微信主进程失败: {str(e)}",
            "wx_status": wx_status
        }