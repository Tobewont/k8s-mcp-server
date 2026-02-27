"""
RBAC管理工具
提供角色模板、权限分析等RBAC功能
"""

import json
from typing import List, Dict, Any, Optional
from services.k8s_advanced_service import KubernetesAdvancedService
from utils.operations_logger import log_operation

# 导入共享的MCP实例
from . import mcp

@mcp.tool()
async def create_role_template(template_type: str, namespace: str, role_name: str = None) -> str:
    """创建角色模板（统一工具）
    
    Args:
        template_type: 角色模板类型，支持：developer, admin, operator, readonly, deployer, monitor, debug
        namespace: 命名空间
        role_name: 角色名称，默认使用模板类型作为名称
    
    Returns:
        角色创建结果
    """
    try:
        # 支持的模板类型
        supported_templates = {
            "developer": "开发者角色模板",
            "admin": "管理员角色模板", 
            "operator": "运维角色模板",
            "readonly": "只读角色模板",
            "deployer": "部署者角色模板（可以部署和管理应用，但不能修改RBAC）",
            "monitor": "监控角色模板（可以查看所有资源状态和指标）",
            "debug": "调试角色模板（可以执行Pod内命令和查看日志）"
        }
        
        if template_type not in supported_templates:
            return json.dumps({
                "success": False, 
                "error": f"不支持的模板类型: {template_type}。支持的类型: {', '.join(supported_templates.keys())}"
            }, ensure_ascii=False, indent=2)
        
        # 如果没有指定角色名称，使用模板类型作为默认名称
        if role_name is None:
            role_name = template_type
            
        service = KubernetesAdvancedService()
        result = await service.create_role_template(template_type, namespace, role_name)
        
        # 添加模板描述信息
        if result.get("success"):
            log_operation("create_role_template", "create", {"template_type": template_type, "role_name": role_name, "namespace": namespace}, True)
            result["template_info"] = {
                "type": template_type,
                "description": supported_templates[template_type],
                "role_name": role_name,
                "namespace": namespace
            }
        
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