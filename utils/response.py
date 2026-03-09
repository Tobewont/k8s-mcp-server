"""
MCP 工具统一响应格式化
"""
import json
from typing import Any, Optional


def json_success(data: dict, extra: Optional[dict] = None) -> str:
    """返回成功 JSON 响应"""
    if extra:
        data = {**data, **extra}
    return json.dumps(data, ensure_ascii=False, indent=2)


def json_partial_success(data: dict, success_count: int, failed_count: int, **extra: Any) -> str:
    """返回部分成功（如批量操作有成功有失败）的 JSON 响应"""
    result = {"success": True, "partial": True, "success_count": success_count, "failed_count": failed_count, **data, **extra}
    return json.dumps(result, ensure_ascii=False, indent=2)


def json_error(error: str, error_code: Optional[int] = None, **extra: Any) -> str:
    """返回错误 JSON 响应
    
    Args:
        error: 错误信息
        error_code: 可选错误码
        **extra: 额外字段（如 valid=False）
    """
    result: dict = {"success": False, "error": error, **extra}
    if error_code is not None:
        result["error_code"] = error_code
    return json.dumps(result, ensure_ascii=False, indent=2)
