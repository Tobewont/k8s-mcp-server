"""
MCP 工具统一响应格式化

规范：
- 成功响应：使用 json_success(data)，data 应包含 "success": True；若未包含则自动添加
- 错误响应：使用 json_error(msg)，自动包含 "success": False
- 扩展字段：通过 **extra 传入，如 json_error("msg", valid=False)
"""
import json
from typing import Any, Dict, Optional


def json_success(data: Dict, extra: Optional[Dict] = None) -> str:
    """返回成功 JSON 响应。若 data 未包含 success 字段则自动添加 success: True"""
    if extra:
        data = {**data, **extra}
    if "success" not in data:
        data = {"success": True, **data}
    return json.dumps(data, ensure_ascii=False, indent=2)


def json_partial_success(data: Dict, success_count: int, failed_count: int, **extra: Any) -> str:
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
    result: Dict = {"success": False, "error": error, **extra}
    if error_code is not None:
        result["error_code"] = error_code
    return json.dumps(result, ensure_ascii=False, indent=2)
