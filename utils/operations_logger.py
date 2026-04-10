"""
操作日志记录模块
将写操作（创建、更新、删除、导入、备份等）记录到用户目录下的 operations.log
"""
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from config import TIMEZONE_OFFSET_HOURS, get_user_data_root

logger = logging.getLogger(__name__)


def _utc8_now() -> str:
    """当前时间（按配置时区）"""
    return datetime.now(timezone(timedelta(hours=TIMEZONE_OFFSET_HOURS))).strftime("%Y-%m-%d %H:%M:%S")


def _get_log_path() -> str:
    """获取当前用户的操作日志路径：data/users/<user_id>/operations.log"""
    from utils.auth_context import get_effective_user_id
    uid = get_effective_user_id()
    user_root = get_user_data_root(uid)
    os.makedirs(user_root, exist_ok=True)
    return os.path.join(user_root, "operations.log")


def log_operation(tool_name: str, action: str, details: dict, success: bool) -> None:
    """
    记录操作日志到当前用户的 operations.log

    Args:
        tool_name: 工具名称，如 batch_create_resources
        action: 操作类型，如 create/update/delete/import/backup/restore
        details: 操作详情（可 JSON 序列化），如 namespace, resource_names 等
        success: 是否成功
    """
    try:
        from utils.auth_context import get_effective_user_id
        entry = {
            "timestamp": _utc8_now(),
            "user": get_effective_user_id(),
            "tool": tool_name,
            "action": action,
            "success": success,
            "details": details,
        }
        log_path = _get_log_path()
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        logger.warning("操作日志写入失败: %s", e)


def log_admin_api(endpoint: str, caller: str, details: dict, success: bool) -> None:
    """记录 REST 管理 API 操作到调用者的 operations.log"""
    try:
        user_root = get_user_data_root(caller if caller else None)
        os.makedirs(user_root, exist_ok=True)
        log_path = os.path.join(user_root, "operations.log")
        entry = {
            "timestamp": _utc8_now(),
            "user": caller,
            "tool": "admin_api",
            "action": endpoint,
            "success": success,
            "details": details,
        }
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        logger.warning("REST API 审计日志写入失败: %s", e)
