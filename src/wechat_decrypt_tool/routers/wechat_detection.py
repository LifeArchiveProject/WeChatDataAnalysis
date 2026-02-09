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
        info['current_account'] = current_account_info

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
    检查系统中是否有 Weixin.exe 或 WeChat.exe 进程在运行
    返回: status=0 成功, wx_status={is_running: bool, pid: int, ...}
    """
    process_name_targets = ["Weixin.exe", "WeChat.exe"]

    wx_status = {
        "is_running": False,
        "pid": None,
        "exe_path": None,
        "memory_usage_mb": 0.0
    }

    try:
        for proc in psutil.process_iter(['pid', 'name', 'exe', 'memory_info']):
            try:
                if proc.info['name'] and proc.info['name'] in process_name_targets:
                    wx_status["is_running"] = True
                    wx_status["pid"] = proc.info['pid']
                    wx_status["exe_path"] = proc.info['exe']

                    mem = proc.info['memory_info']
                    if mem:
                        wx_status["memory_usage_mb"] = round(mem.rss / (1024 * 1024), 2)

                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        return {
            "status": 0,
            "errmsg": "ok",
            "wx_status": wx_status
        }

    except Exception as e:
        # 即使出错也返回 JSON，但 status 非 0
        return {
            "status": -1,
            "errmsg": f"检查进程失败: {str(e)}",
            "wx_status": wx_status
        }
