"""
操作日志记录模块
将写操作（创建、更新、删除、导入、备份等）记录到 operations.log
"""
import json
from datetime import datetime, timezone, timedelta
from config import OPERATIONS_LOG_FILE


def _utc8_now() -> str:
    """东八区当前时间"""
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")


def log_operation(tool_name: str, action: str, details: dict, success: bool) -> None:
    """
    记录操作日志到 operations.log
    
    Args:
        tool_name: 工具名称，如 batch_create_resources
        action: 操作类型，如 create/update/delete/import/backup/restore
        details: 操作详情（可 JSON 序列化），如 namespace, resource_names 等
        success: 是否成功
    """
    try:
        entry = {
            "timestamp": _utc8_now(),
            "tool": tool_name,
            "action": action,
            "success": success,
            "details": details,
        }
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with open(OPERATIONS_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass  # 日志失败不应影响主流程
