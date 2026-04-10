"""
工具层装饰器
"""
import logging
import re
from functools import wraps

from .response import json_error

logger = logging.getLogger(__name__)

_IP_PORT_RE = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?")
_SENSITIVE_KEYS = ("token", "password", "secret", "authorization", "bearer")


def _sanitize_error(msg: str) -> str:
    """对异常消息做基本脱敏，去除内部 IP 和敏感关键字值。"""
    msg = _IP_PORT_RE.sub("[REDACTED_IP]", msg)
    lower = msg.lower()
    for key in _SENSITIVE_KEYS:
        idx = lower.find(key)
        while idx != -1:
            end = msg.find("\n", idx)
            if end == -1:
                end = min(idx + 200, len(msg))
            msg = msg[:idx] + f"[{key} REDACTED]" + msg[end:]
            lower = msg.lower()
            idx = lower.find(key, idx + len(key) + 12)
    return msg


def handle_tool_errors(f):
    """统一工具异常处理：捕获异常并返回 json_error，不吞掉 KeyboardInterrupt/SystemExit"""
    @wraps(f)
    async def wrapper(*args, **kwargs):
        try:
            return await f(*args, **kwargs)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            logger.exception("工具 %s 执行异常: %s", f.__name__, e)
            return json_error(_sanitize_error(str(e)))
    return wrapper
