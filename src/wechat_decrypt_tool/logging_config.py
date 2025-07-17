"""
统一的日志配置模块
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器"""

    # ANSI颜色代码
    COLORS = {
        'DEBUG': '\033[36m',      # 青色
        'INFO': '\033[32m',       # 绿色
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[35m',   # 紫色
        'RESET': '\033[0m'        # 重置
    }

    def format(self, record):
        # 获取原始格式化的消息
        formatted = super().format(record)

        # 只在控制台输出时添加颜色
        if hasattr(sys.stderr, 'isatty') and sys.stderr.isatty():
            level_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
            reset_color = self.COLORS['RESET']

            # 为日志级别添加颜色
            formatted = formatted.replace(
                f' | {record.levelname} | ',
                f' | {level_color}{record.levelname}{reset_color} | '
            )

        return formatted


class WeChatLogger:
    """微信解密工具统一日志管理器"""
    
    _instance: Optional['WeChatLogger'] = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.setup_logging()
            WeChatLogger._initialized = True
    
    def setup_logging(self, log_level: str = "INFO"):
        """设置日志配置"""
        # 创建日志目录
        now = datetime.now()
        log_dir = Path("output/logs") / str(now.year) / f"{now.month:02d}" / f"{now.day:02d}"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置日志文件名
        date_str = now.strftime("%d")
        self.log_file = log_dir / f"{date_str}_wechat_tool.log"
        
        # 清除现有的处理器
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # 配置日志格式
        # 文件格式（无颜色）
        file_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 控制台格式（有颜色）
        console_formatter = ColoredFormatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 文件处理器
        file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(getattr(logging, log_level.upper()))

        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        
        # 配置根日志器
        root_logger.setLevel(getattr(logging, log_level.upper()))
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        
        # 只为uvicorn日志器添加文件处理器，保持其原有的控制台处理器（带颜色）
        uvicorn_logger = logging.getLogger("uvicorn")
        uvicorn_logger.addHandler(file_handler)
        uvicorn_logger.setLevel(getattr(logging, log_level.upper()))

        # 只为uvicorn.access日志器添加文件处理器
        uvicorn_access_logger = logging.getLogger("uvicorn.access")
        uvicorn_access_logger.addHandler(file_handler)
        uvicorn_access_logger.setLevel(getattr(logging, log_level.upper()))

        # 只为uvicorn.error日志器添加文件处理器
        uvicorn_error_logger = logging.getLogger("uvicorn.error")
        uvicorn_error_logger.addHandler(file_handler)
        uvicorn_error_logger.setLevel(getattr(logging, log_level.upper()))

        # 配置FastAPI日志器
        fastapi_logger = logging.getLogger("fastapi")
        fastapi_logger.handlers = []
        fastapi_logger.addHandler(file_handler)
        fastapi_logger.addHandler(console_handler)
        fastapi_logger.setLevel(getattr(logging, log_level.upper()))
        
        # 记录初始化信息
        logger = logging.getLogger(__name__)
        logger.info("=" * 60)
        logger.info("微信解密工具日志系统初始化完成")
        logger.info(f"日志文件: {self.log_file}")
        logger.info(f"日志级别: {log_level}")
        logger.info("=" * 60)
        
        return self.log_file
    
    def get_logger(self, name: str) -> logging.Logger:
        """获取指定名称的日志器"""
        return logging.getLogger(name)
    
    def get_log_file_path(self) -> Path:
        """获取当前日志文件路径"""
        return self.log_file


def setup_logging(log_level: str = "INFO") -> Path:
    """设置日志配置的便捷函数"""
    logger_manager = WeChatLogger()
    return logger_manager.setup_logging(log_level)


def get_logger(name: str) -> logging.Logger:
    """获取日志器的便捷函数"""
    logger_manager = WeChatLogger()
    return logger_manager.get_logger(name)


def get_log_file_path() -> Path:
    """获取当前日志文件路径的便捷函数"""
    logger_manager = WeChatLogger()
    return logger_manager.get_log_file_path()
