"""
工具层装饰器
"""
import logging
from functools import wraps

from .response import json_error

logger = logging.getLogger(__name__)


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
            return json_error(str(e))
    return wrapper
