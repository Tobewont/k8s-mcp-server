"""
Kubernetes 辅助函数
"""
import base64
import json
import yaml
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from config import TIMEZONE_OFFSET_HOURS


def parse_secret_data(data: Dict[str, str]) -> Dict[str, Any]:
    """
    将 base64 编码的 Secret data 字段解码为明文，并自动尝试解析 yaml/json 内容。
    返回格式：{key: 明文或解析后的对象}
    """
    result = {}
    for k, v in (data or {}).items():
        try:
            decoded = base64.b64decode(v).decode('utf-8')
            try:
                result[k] = json.loads(decoded)
            except Exception:
                try:
                    result[k] = yaml.safe_load(decoded)
                except Exception:
                    result[k] = decoded
        except Exception as e:
            result[k] = f"<解码失败: {e}>"
    return result


def to_local_time_str(dt, tz_offset_hours: Optional[int] = None) -> str:
    """
    将时间戳（datetime 或 ISO 字符串）转换为指定时区的字符串。
    :param dt: datetime 对象或 ISO 格式字符串
    :param tz_offset_hours: 时区偏移（小时），默认使用 config.TIMEZONE_OFFSET_HOURS
    :return: 格式化后的时间字符串
    """
    if tz_offset_hours is None:
        tz_offset_hours = TIMEZONE_OFFSET_HOURS
    if not dt:
        return ""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except Exception:
            return dt
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(timezone(timedelta(hours=tz_offset_hours)))
    return local.strftime('%Y-%m-%d %H:%M:%S')
