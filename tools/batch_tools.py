"""
批量操作工具模块
提供批量创建、更新和删除资源的功能
"""

import json
import asyncio
from typing import List, Dict, Any, Optional, Union
from services.k8s_advanced_service import KubernetesAdvancedService


# 导入共享的MCP实例
from . import mcp


@mcp.tool()
async def batch_list_resources(resource_types: Union[str, List[str]], namespace: str = "default") -> str:
    """批量查看资源
    
    Args:
        resource_types: JSON格式的资源类型列表或单个资源类型
        namespace: 命名空间
    
    Returns:
        批量查看结果
    """
    try:
        if isinstance(resource_types, str):
            try:
                resource_types_list = json.loads(resource_types)
            except:
                # 如果不是JSON，则当作单个资源类型
                resource_types_list = [resource_types]
        else:
            resource_types_list = resource_types
        
        if not isinstance(resource_types_list, list):
            resource_types_list = [resource_types_list]
        
        service = KubernetesAdvancedService()
        result = await service.batch_list_resources(resource_types_list, namespace)
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def batch_create_resources(resources: Union[str, List[Dict]], namespace: str = "default", 
                               rollback_on_failure: bool = True) -> str:
    """批量创建资源
    
    Args:
        resources: JSON格式的资源列表，每个资源包含kind、metadata、spec
        namespace: 命名空间
        rollback_on_failure: 失败时是否回滚已创建的资源
    """
    try:
        service = KubernetesAdvancedService()
        # 如果resources是字符串，尝试解析为JSON
        if isinstance(resources, str):
            try:
                resources_list = json.loads(resources)
            except json.JSONDecodeError:
                return json.dumps({"success": False, "error": "资源列表必须是有效的JSON字符串"}, ensure_ascii=False, indent=2)
        else:
            resources_list = resources
        
        # 验证资源列表格式
        if not isinstance(resources_list, list):
            return json.dumps({"success": False, "error": "资源列表必须是数组"}, ensure_ascii=False, indent=2)
        
        # 验证每个资源对象
        for resource in resources_list:
            if not isinstance(resource, dict):
                return json.dumps({"success": False, "error": "资源列表中的每个项目必须是字典"}, ensure_ascii=False, indent=2)
            if "kind" not in resource:
                return json.dumps({"success": False, "error": "每个资源必须指定kind字段"}, ensure_ascii=False, indent=2)
            if "metadata" not in resource:
                return json.dumps({"success": False, "error": "每个资源必须指定metadata字段"}, ensure_ascii=False, indent=2)
            if "name" not in resource["metadata"]:
                return json.dumps({"success": False, "error": "每个资源的metadata必须包含name字段"}, ensure_ascii=False, indent=2)
        
        result = await service.batch_create_resources(resources_list, namespace)
        
        # 如果有失败且需要回滚
        if result["failed"] and rollback_on_failure and result["success"]:
            # 回滚已创建的资源
            rollback_resources = []
            for success_item in result["success"]:
                rollback_resources.append({
                    "kind": success_item["kind"],
                    "metadata": {"name": success_item["name"]}
                })
            
            rollback_result = await service.batch_delete_resources(rollback_resources, namespace)
            result["rollback"] = rollback_result
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def batch_update_resources(resources: Union[str, List[Dict]], namespace: str = "default") -> str:
    """批量更新资源
    
    Args:
        resources: JSON格式的资源列表
        namespace: 命名空间
    """
    try:
        service = KubernetesAdvancedService()
        # 如果resources是字符串，尝试解析为JSON
        if isinstance(resources, str):
            try:
                resources_list = json.loads(resources)
            except json.JSONDecodeError:
                return json.dumps({"success": False, "error": "资源列表必须是有效的JSON字符串"}, ensure_ascii=False, indent=2)
        else:
            resources_list = resources
        
        # 验证资源列表格式
        if not isinstance(resources_list, list):
            return json.dumps({"success": False, "error": "资源列表必须是数组"}, ensure_ascii=False, indent=2)
        
        # 验证每个资源对象
        for resource in resources_list:
            if not isinstance(resource, dict):
                return json.dumps({"success": False, "error": "资源列表中的每个项目必须是字典"}, ensure_ascii=False, indent=2)
            if "kind" not in resource:
                return json.dumps({"success": False, "error": "每个资源必须指定kind字段"}, ensure_ascii=False, indent=2)
            if "metadata" not in resource:
                return json.dumps({"success": False, "error": "每个资源必须指定metadata字段"}, ensure_ascii=False, indent=2)
            if "name" not in resource["metadata"]:
                return json.dumps({"success": False, "error": "每个资源的metadata必须包含name字段"}, ensure_ascii=False, indent=2)
        
        result = await service.batch_update_resources(resources_list, namespace)
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def batch_delete_resources(resources: Union[str, List[Dict]], namespace: str = "default", 
                               grace_period_seconds: int = None) -> str:
    """批量删除资源
    
    Args:
        resources: JSON格式的资源列表
        namespace: 命名空间
        grace_period_seconds: 优雅删除等待时间
    """
    try:
        service = KubernetesAdvancedService()
        # 如果resources是字符串，尝试解析为JSON
        if isinstance(resources, str):
            try:
                resources_list = json.loads(resources)
            except json.JSONDecodeError:
                return json.dumps({"success": False, "error": "资源列表必须是有效的JSON字符串"}, ensure_ascii=False, indent=2)
        else:
            resources_list = resources
        
        # 验证资源列表格式
        if not isinstance(resources_list, list):
            return json.dumps({"success": False, "error": "资源列表必须是数组"}, ensure_ascii=False, indent=2)
        
        # 验证每个资源对象
        for resource in resources_list:
            if not isinstance(resource, dict):
                return json.dumps({"success": False, "error": "资源列表中的每个项目必须是字典"}, ensure_ascii=False, indent=2)
            if "kind" not in resource:
                return json.dumps({"success": False, "error": "每个资源必须指定kind字段"}, ensure_ascii=False, indent=2)
            if "metadata" not in resource:
                return json.dumps({"success": False, "error": "每个资源必须指定metadata字段"}, ensure_ascii=False, indent=2)
            if "name" not in resource["metadata"]:
                return json.dumps({"success": False, "error": "每个资源的metadata必须包含name字段"}, ensure_ascii=False, indent=2)
        
        result = await service.batch_delete_resources(resources_list, namespace, grace_period_seconds)
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def batch_describe_resources(resource_specs: Union[str, List[Dict]], namespace: str = "default") -> str:
    """批量获取资源详细信息
    
    Args:
        resource_specs: 资源规格列表，格式：[{"kind": "Pod", "name": "my-pod"}, {"kind": "Service", "name": "my-svc"}]
        namespace: 命名空间
    
    Returns:
        批量资源详细信息
    """
    try:
        # 解析资源规格
        if isinstance(resource_specs, str):
            try:
                specs_list = json.loads(resource_specs)
            except json.JSONDecodeError:
                return json.dumps({"success": False, "error": "资源规格必须是有效的JSON字符串"}, ensure_ascii=False, indent=2)
        else:
            specs_list = resource_specs
        
        if not isinstance(specs_list, list):
            specs_list = [specs_list]
        
        # 验证资源规格格式
        for spec in specs_list:
            if not isinstance(spec, dict):
                return json.dumps({"success": False, "error": "每个资源规格必须是字典"}, ensure_ascii=False, indent=2)
            if "kind" not in spec or "name" not in spec:
                return json.dumps({"success": False, "error": "每个资源规格必须包含kind和name字段"}, ensure_ascii=False, indent=2)
        
        service = KubernetesAdvancedService()
        result = await service.batch_describe_resources(specs_list, namespace)
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)
