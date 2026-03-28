"""
统一的日志配置模块
"""

import logging
import os
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


def _can_use_logging_stream(stream) -> bool:
    try:
        if stream is None or getattr(stream, "closed", False):
            return False
    except Exception:
        return False

    try:
        stream.write("")
        stream.flush()
    except Exception:
        return False

    return True


class WeChatLogger:
    """微信解密工具统一日志管理器"""
    
    _instance: Optional['WeChatLogger'] = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Lazy-init in `setup_logging()` / accessors to avoid double-initialization when
        # callers instantiate the manager and then call `setup_logging()` again.
        pass
    
    def setup_logging(self, log_level: str = "INFO"):
        """设置日志配置"""
        # Allow overriding via env var for easier debugging (e.g. WECHAT_TOOL_LOG_LEVEL=DEBUG)
        env_level = str(os.environ.get("WECHAT_TOOL_LOG_LEVEL", "") or "").strip()
        if env_level:
            log_level = env_level

        console_logging_env = str(os.environ.get("WECHAT_TOOL_ENABLE_CONSOLE_LOG", "") or "").strip().lower()
        console_logging_forced = console_logging_env in {"1", "true", "yes", "on"}
        console_logging_disabled = console_logging_env in {"0", "false", "no", "off"}

        level = getattr(logging, str(log_level or "INFO").upper(), logging.INFO)

        # 创建日志目录
        now = datetime.now()
        from .app_paths import get_output_dir

        log_dir = get_output_dir() / "logs" / str(now.year) / f"{now.month:02d}" / f"{now.day:02d}"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置日志文件名
        date_str = now.strftime("%d")
        desired_log_file = log_dir / f"{date_str}_wechat_tool.log"

        root_logger = logging.getLogger()
        wants_console_handler = _can_use_logging_stream(sys.stdout)
        if getattr(sys, "frozen", False) and not console_logging_forced:
            wants_console_handler = False
        if console_logging_disabled:
            wants_console_handler = False

        if WeChatLogger._initialized:
            current_log_file = Path(getattr(self, "log_file", desired_log_file))
            has_expected_file_handler = False
            has_stream_handler = False
            for handler in root_logger.handlers:
                if isinstance(handler, logging.FileHandler):
                    try:
                        if Path(handler.baseFilename).resolve() == desired_log_file.resolve():
                            has_expected_file_handler = True
                    except Exception:
                        if Path(handler.baseFilename) == desired_log_file:
                            has_expected_file_handler = True
                elif isinstance(handler, logging.StreamHandler):
                    has_stream_handler = True
            if (
                current_log_file == desired_log_file
                and root_logger.level == level
                and has_expected_file_handler
                and (has_stream_handler or not wants_console_handler)
            ):
                self.log_file = desired_log_file
                return self.log_file

        self.log_file = desired_log_file
        
        # 清除现有的处理器
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
        
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
        file_handler.setLevel(level)

        # 控制台处理器
        console_handler = None
        if wants_console_handler:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(console_formatter)
            console_handler.setLevel(level)
        
        # 配置根日志器
        root_logger.setLevel(level)
        root_logger.addHandler(file_handler)
        if console_handler is not None:
            root_logger.addHandler(console_handler)
        
        # 只为uvicorn日志器添加文件处理器，保持其原有的控制台处理器（带颜色）
        uvicorn_logger = logging.getLogger("uvicorn")
        for handler in uvicorn_logger.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                uvicorn_logger.removeHandler(handler)
                try:
                    handler.close()
                except Exception:
                    pass
        uvicorn_logger.addHandler(file_handler)
        uvicorn_logger.setLevel(level)

        # 只为uvicorn.access日志器添加文件处理器
        uvicorn_access_logger = logging.getLogger("uvicorn.access")
        for handler in uvicorn_access_logger.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                uvicorn_access_logger.removeHandler(handler)
                try:
                    handler.close()
                except Exception:
                    pass
        uvicorn_access_logger.addHandler(file_handler)
        uvicorn_access_logger.setLevel(level)

        # 只为uvicorn.error日志器添加文件处理器
        uvicorn_error_logger = logging.getLogger("uvicorn.error")
        for handler in uvicorn_error_logger.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                uvicorn_error_logger.removeHandler(handler)
                try:
                    handler.close()
                except Exception:
                    pass
        uvicorn_error_logger.addHandler(file_handler)
        uvicorn_error_logger.setLevel(level)

        # 配置FastAPI日志器
        fastapi_logger = logging.getLogger("fastapi")
        for handler in fastapi_logger.handlers[:]:
            fastapi_logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
        fastapi_logger.addHandler(file_handler)
        if console_handler is not None:
            fastapi_logger.addHandler(console_handler)
        fastapi_logger.setLevel(level)
        
        # 记录初始化信息
        logger = logging.getLogger(__name__)
        logger.info("=" * 60)
        logger.info("微信解密工具日志系统初始化完成")
        logger.info(f"日志文件: {self.log_file}")
        logger.info(f"日志级别: {logging.getLevelName(level)}")
        logger.info("=" * 60)

        WeChatLogger._initialized = True
        
        return self.log_file
    
    def get_logger(self, name: str) -> logging.Logger:
        """获取指定名称的日志器"""
        return logging.getLogger(name)
    
    def get_log_file_path(self) -> Path:
        """获取当前日志文件路径"""
        if not hasattr(self, "log_file"):
            self.setup_logging()
        return self.log_file


def setup_logging(log_level: str = "INFO") -> Path:
    """设置日志配置的便捷函数"""
    logger_manager = WeChatLogger()
    return logger_manager.setup_logging(log_level)


def get_logger(name: str) -> logging.Logger:
    """获取日志器的便捷函数"""
    logger_manager = WeChatLogger()
    if not WeChatLogger._initialized:
        logger_manager.setup_logging()
    return logger_manager.get_logger(name)


def get_log_file_path() -> Path:
    """获取当前日志文件路径的便捷函数"""
    logger_manager = WeChatLogger()
    if not WeChatLogger._initialized:
        logger_manager.setup_logging()
    return logger_manager.get_log_file_path()
