import json
import os
import re
from typing import Callable, Optional

from fastapi import HTTPException, Request
from fastapi.routing import APIRoute

from .logging_config import get_logger

logger = get_logger(__name__)


class PathFixRequest(Request):
    """自定义Request类，自动修复JSON中的路径问题并检测相对路径"""

    def _is_absolute_path(self, path: str) -> bool:
        """检测是否为绝对路径，支持Windows、macOS、Linux"""
        if not path:
            return False

        # Windows绝对路径：以盘符开头 (C:\, D:\, etc.)
        if re.match(r'^[A-Za-z]:[/\\]', path):
            return True

        # Unix-like系统绝对路径：以 / 开头
        if path.startswith('/'):
            return True

        return False

    def _validate_paths_in_json(self, json_data: dict) -> Optional[str]:
        """验证JSON中的路径，返回错误信息（如果有）"""
        logger.info(f"开始验证路径，JSON数据: {json_data}")
        # 检查db_storage_path字段（现在是必需的）
        if 'db_storage_path' not in json_data:
            return "缺少必需的db_storage_path参数，请提供具体的数据库存储路径。"

        if 'db_storage_path' in json_data:
            path = json_data['db_storage_path']

            # 检查路径是否为空
            if not path or not path.strip():
                return "db_storage_path参数不能为空，请提供具体的数据库存储路径。"

            logger.info(f"检查路径: {path}")
            is_absolute = self._is_absolute_path(path)
            logger.info(f"是否为绝对路径: {is_absolute}")
            if not is_absolute:
                error_msg = f"请提供绝对路径，当前输入的是相对路径: {path}。\n" \
                           f"Windows绝对路径示例: D:\\wechatMSG\\xwechat_files\\wxid_xxx\\db_storage"
                return error_msg

            # 检查路径是否存在
            logger.info(f"检查路径是否存在: {path}")
            path_exists = os.path.exists(path)
            logger.info(f"路径存在性: {path_exists}")
            if not path_exists:
                # 检查父目录
                parent_path = os.path.dirname(path)
                logger.info(f"检查父目录: {parent_path}")
                parent_exists = os.path.exists(parent_path)
                logger.info(f"父目录存在性: {parent_exists}")
                if parent_exists:
                    try:
                        files = os.listdir(parent_path)
                        logger.info(f"父目录内容: {files}")
                        error_msg = f"指定的路径不存在: {path}\n" \
                                   f"父目录存在但不包含 'db_storage' 文件夹。\n" \
                                   f"请检查路径是否正确，或确保微信数据已生成。"
                    except PermissionError:
                        logger.info(f"无法访问父目录，权限不足")
                        error_msg = f"指定的路径不存在: {path}\n" \
                                   f"无法访问父目录，可能是权限问题。"
                else:
                    error_msg = f"指定的路径不存在: {path}\n" \
                               f"父目录也不存在，请检查路径是否正确。"
                logger.info(f"返回路径错误: {error_msg}")
                return error_msg
            else:
                logger.info(f"路径存在，使用递归方式检查数据库文件")
                try:
                    # 使用与自动检测相同的逻辑：递归查找.db文件
                    db_files = []
                    for root, dirs, files in os.walk(path):
                        # 只处理db_storage目录下的数据库文件（与自动检测逻辑一致）
                        if "db_storage" not in root:
                            continue
                        for file_name in files:
                            if not file_name.endswith(".db"):
                                continue
                            # 排除不需要解密的数据库（与自动检测逻辑一致）
                            if file_name in ["key_info.db"]:
                                continue
                            db_path = os.path.join(root, file_name)
                            db_files.append(db_path)

                    logger.info(f"递归查找到的数据库文件: {db_files}")
                    if not db_files:
                        error_msg = f"路径存在但没有找到有效的数据库文件: {path}\n" \
                                   f"请确保该目录或其子目录包含微信数据库文件(.db文件)。\n" \
                                   f"注意：key_info.db文件会被自动排除。"
                        logger.info(f"返回错误: 递归查找未找到有效.db文件")
                        return error_msg
                    logger.info(f"路径验证通过，递归找到{len(db_files)}个有效数据库文件")
                except PermissionError:
                    error_msg = f"无法访问路径: {path}\n" \
                               f"权限不足，请检查文件夹权限。"
                    return error_msg
                except Exception as e:
                    logger.warning(f"检查路径内容时出错: {e}")
                    # 如果无法检查内容，继续执行，让后续逻辑处理

        return None

    async def body(self) -> bytes:
        """重写body方法，预处理JSON中的路径问题"""
        body = await super().body()

        # 只处理JSON请求
        content_type = self.headers.get("content-type", "")
        if "application/json" not in content_type:
            return body

        try:
            # 将bytes转换为字符串
            body_str = body.decode('utf-8')

            # 首先尝试解析JSON以验证路径
            try:
                json_data = json.loads(body_str)
                path_error = self._validate_paths_in_json(json_data)
                if path_error:
                    logger.info(f"检测到路径错误: {path_error}")
                    # 我们将错误信息存储在请求中，稍后在路由处理器中检查
                    self.state.path_validation_error = path_error
                    return body
            except json.JSONDecodeError as e:
                # JSON格式错误，继续尝试修复
                logger.info(f"JSON解析失败，尝试修复: {e}")
                pass

            # 使用正则表达式安全地处理Windows路径中的反斜杠
            # 需要处理两种情况：
            # 1. 以盘符开头的绝对路径：D:\path\to\file
            # 2. 不以盘符开头的相对路径：wechatMSG\xwechat_files\...

            # 匹配引号内包含反斜杠的路径（不管是否以盘符开头）
            pattern = r'"([^"]*?\\[^"]*?)"'

            def fix_path(match):
                path = match.group(1)
                # 将单个反斜杠替换为双反斜杠，但避免替换已经转义的反斜杠
                fixed_path = re.sub(r'(?<!\\)\\(?!\\)', r'\\\\', path)
                return f'"{fixed_path}"'

            # 应用修复
            fixed_body_str = re.sub(pattern, fix_path, body_str)

            # 记录修复信息（仅在有修改时）
            if fixed_body_str != body_str:
                logger.info(f"自动修复JSON路径格式: {body_str[:100]}... -> {fixed_body_str[:100]}...")

            # 修复后重新验证路径
            try:
                json_data = json.loads(fixed_body_str)
                logger.info(f"修复后解析JSON成功，开始验证路径")
                path_error = self._validate_paths_in_json(json_data)
                if path_error:
                    logger.info(f"修复后检测到路径错误: {path_error}")
                    self.state.path_validation_error = path_error
                    return fixed_body_str.encode('utf-8')
                else:
                    logger.info(f"修复后路径验证通过")
            except json.JSONDecodeError as e:
                logger.warning(f"修复后JSON仍然解析失败: {e}")

            return fixed_body_str.encode('utf-8')

        except Exception as e:
            # 如果处理失败，返回原始body
            logger.warning(f"JSON路径修复失败，使用原始请求体: {e}")
            return body


class PathFixRoute(APIRoute):
    """自定义APIRoute类，使用PathFixRequest并处理路径验证错误"""

    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> any:
            # 将Request替换为我们的自定义Request
            custom_request = PathFixRequest(request.scope, request.receive)

            # 检查是否有路径验证错误
            if hasattr(custom_request.state, 'path_validation_error'):
                raise HTTPException(
                    status_code=400,
                    detail=custom_request.state.path_validation_error,
                )

            return await original_route_handler(custom_request)

        return custom_route_handler
