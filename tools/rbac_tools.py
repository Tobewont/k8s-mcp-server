"""
RBAC管理工具
提供角色模板和用户绑定功能
"""

import json
from typing import List, Dict, Any
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
        result = await service.create_developer_role(namespace, role_name)
        
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
        result = await service.create_admin_role(namespace, role_name)
        
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
        result = await service.create_operator_role(namespace, role_name)
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def bind_user_to_role(namespace: str, role_name: str, 
                           user_name: str, binding_name: str = None) -> str:
    """将用户绑定到角色
    
    Args:
        namespace: 命名空间
        role_name: 角色名称
        user_name: 用户名
        binding_name: 绑定名称（可选）
    """
    try:
        k8s_service = KubernetesAdvancedService()
        
        if not binding_name:
            binding_name = f"{user_name}-{role_name}-binding"
        
        role_ref = {
            "api_group": "rbac.authorization.k8s.io",
            "kind": "Role",
            "name": role_name
        }
        
        subjects = [{
            "kind": "User",
            "name": user_name,
            "api_group": "rbac.authorization.k8s.io"
        }]
        
        result = await k8s_service.k8s_service.create_role_binding(binding_name, namespace, role_ref, subjects)
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def bind_user_to_cluster_role(user_name: str, cluster_role_name: str, 
                                  binding_name: str = None) -> str:
    """将用户绑定到集群角色
    
    Args:
        user_name: 用户名
        cluster_role_name: 集群角色名称
        binding_name: 绑定名称（可选）
    """
    try:
        k8s_service = KubernetesAdvancedService()
        
        if not binding_name:
            binding_name = f"{user_name}-{cluster_role_name}-binding"
        
        role_ref = {
            "api_group": "rbac.authorization.k8s.io",
            "kind": "ClusterRole",
            "name": cluster_role_name
        }
        
        subjects = [{
            "kind": "User",
            "name": user_name,
            "api_group": "rbac.authorization.k8s.io"
        }]
        
        result = await k8s_service.k8s_service.create_cluster_role_binding(binding_name, role_ref, subjects)
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2) 
