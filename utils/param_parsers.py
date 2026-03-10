"""
工具层参数解析辅助
"""
import json
from typing import List, Dict, Optional, Tuple, Union


def parse_json_or_single(
    value: Union[str, list], default_as_list: bool = True
) -> Tuple[Optional[list], Optional[str]]:
    """解析 JSON 字符串或单个值，返回 (list, error_msg)。成功时 error_msg 为 None。"""
    if isinstance(value, list):
        return value, None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None, "参数不能为空"
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value] if default_as_list else None, (
                None if default_as_list else "无效的 JSON 格式"
            )
        if isinstance(parsed, list):
            return parsed, None
        return [parsed] if default_as_list else None, None
    return None, "参数类型错误"


def parse_json_array(
    value, error_msg: str = "资源列表必须是有效的JSON字符串"
) -> Tuple[Optional[List], Optional[str]]:
    """解析 JSON 字符串或列表为数组，返回 (list, error_msg)。成功时 error_msg 为 None。"""
    if isinstance(value, list):
        return value, None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None, "参数不能为空"
        try:
            parsed = json.loads(s)
        except json.JSONDecodeError:
            return None, error_msg
        if not isinstance(parsed, list):
            return None, "资源列表必须是数组"
        return parsed, None
    return None, "参数类型错误"


def parse_and_validate_resources(
    resources,
) -> Tuple[Optional[List[Dict]], Optional[str]]:
    """解析并验证资源列表，返回 (resources_list, error_msg)。成功时 error_msg 为 None。"""
    resources_list, err = parse_json_array(resources)
    if err:
        return None, err

    for resource in resources_list:
        if not isinstance(resource, dict):
            return None, "资源列表中的每个项目必须是字典"
        if "kind" not in resource:
            return None, "每个资源必须指定kind字段"
        if "metadata" not in resource:
            return None, "每个资源必须指定metadata字段"
        if "name" not in resource.get("metadata", {}):
            return None, "每个资源的metadata必须包含name字段"

    return resources_list, None


def parse_and_validate_resource_specs(
    resources,
) -> Tuple[Optional[List[Dict]], Optional[str]]:
    """解析并验证资源规格列表 [{"kind","name"}]，返回 (specs_list, error_msg)。成功时 error_msg 为 None。"""
    specs_list, err = parse_json_array(resources)
    if err:
        return None, err

    for spec in specs_list:
        if not isinstance(spec, dict):
            return None, "每个资源规格必须是字典"
        if "kind" not in spec or "name" not in spec:
            return None, "每个资源规格必须包含kind和name字段"

    return specs_list, None
