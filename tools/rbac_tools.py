"""
RBAC管理工具
提供角色模板、权限分析等RBAC功能
"""

import json
from typing import List, Dict, Any, Optional
from services.k8s_advanced_service import KubernetesAdvancedService


# 导入共享的MCP实例
from . import mcp

@mcp.tool()
async def create_developer_role_template(namespace: str, role_name: str = "developer") -> str:
    """创建开发者角色模板
    
    Args:
        namespace: 命名空间
        role_name: 角色名称
    """
    try:
        service = KubernetesAdvancedService()
        result = await service.create_role_template("developer", namespace, role_name)
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def create_admin_role_template(namespace: str, role_name: str = "admin") -> str:
    """创建管理员角色模板
    
    Args:
        namespace: 命名空间
        role_name: 角色名称
    """
    try:
        service = KubernetesAdvancedService()
        result = await service.create_role_template("admin", namespace, role_name)
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def create_operator_role_template(namespace: str, role_name: str = "operator") -> str:
    """创建运维角色模板
    
    Args:
        namespace: 命名空间
        role_name: 角色名称
    """
    try:
        service = KubernetesAdvancedService()
        result = await service.create_role_template("operator", namespace, role_name)
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def create_readonly_role_template(namespace: str, role_name: str = "readonly") -> str:
    """创建只读角色模板
    
    Args:
        namespace: 命名空间
        role_name: 角色名称
    """
    try:
        service = KubernetesAdvancedService()
        result = await service.create_role_template("readonly", namespace, role_name)
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def create_deployer_role_template(namespace: str, role_name: str = "deployer") -> str:
    """创建部署者角色模板（可以部署和管理应用，但不能修改RBAC）
    
    Args:
        namespace: 命名空间
        role_name: 角色名称
    """
    try:
        service = KubernetesAdvancedService()
        result = await service.create_role_template("deployer", namespace, role_name)
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def create_monitor_role_template(namespace: str, role_name: str = "monitor") -> str:
    """创建监控角色模板（可以查看所有资源状态和指标）
    
    Args:
        namespace: 命名空间
        role_name: 角色名称
    """
    try:
        service = KubernetesAdvancedService()
        result = await service.create_role_template("monitor", namespace, role_name)
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def create_debug_role_template(namespace: str, role_name: str = "debug") -> str:
    """创建调试角色模板（可以执行Pod内命令和查看日志）
    
    Args:
        namespace: 命名空间
        role_name: 角色名称
    """
    try:
        service = KubernetesAdvancedService()
        result = await service.create_role_template("debug", namespace, role_name)
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


# ==================== ServiceAccount权限分析工具 ====================

@mcp.tool()
async def analyze_serviceaccount_permissions(service_account_name: str, namespace: str) -> str:
    """分析ServiceAccount的权限
    
    Args:
        service_account_name: ServiceAccount名称
        namespace: 命名空间
    """
    try:
        service = KubernetesAdvancedService()
        result = await service.analyze_serviceaccount_permissions(service_account_name, namespace)
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def check_serviceaccount_permission_conflicts(namespace: str) -> str:
    """检查命名空间中ServiceAccount的权限冲突
    
    Args:
        namespace: 命名空间
    """
    try:
        service = KubernetesAdvancedService()
        result = await service.check_serviceaccount_permission_conflicts(namespace)
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2) 


@mcp.tool()
async def list_role_serviceaccounts(role_name: str, namespace: str, role_type: str = "Role") -> str:
    """列出绑定到指定角色的所有ServiceAccount
    
    Args:
        role_name: 角色名称
        namespace: 命名空间
        role_type: 角色类型（Role或ClusterRole）
    """
    try:
        service = KubernetesAdvancedService()
        result = await service.list_role_serviceaccounts(role_name, namespace, role_type)
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)