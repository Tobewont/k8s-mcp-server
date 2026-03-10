"""
RBAC管理工具
提供角色模板、权限分析等RBAC功能
"""
from typing import Optional

from services.factory import get_k8s_advanced_service
from utils.decorators import handle_tool_errors
from utils.operations_logger import log_operation
from utils.response import json_error, json_success

# 导入共享的MCP实例
from . import mcp

@mcp.tool()
@handle_tool_errors
async def create_role_template(template_type: str, namespace: str, role_name: Optional[str] = None,
                              kubeconfig_path: Optional[str] = None) -> str:
    """创建角色模板（统一工具）
    
    Args:
        template_type: 角色模板类型，支持：developer, admin, operator, readonly, deployer, monitor, debug
        namespace: 命名空间
        role_name: 角色名称，默认使用模板类型作为名称
        kubeconfig_path: kubeconfig 文件路径，不指定则使用默认集群
    
    Returns:
        角色创建结果
    """
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
        return json_error(f"不支持的模板类型: {template_type}。支持的类型: {', '.join(supported_templates.keys())}")
    if role_name is None:
        role_name = template_type
    service = get_k8s_advanced_service(kubeconfig_path)
    result = await service.create_role_template(template_type, namespace, role_name)
    if result.get("success"):
        log_operation("create_role_template", "create", {"template_type": template_type, "role_name": role_name, "namespace": namespace}, True)
        result["template_info"] = {"type": template_type, "description": supported_templates[template_type], "role_name": role_name, "namespace": namespace}
    return json_success(result)

@mcp.tool()
@handle_tool_errors
async def analyze_serviceaccount_permissions(service_account_name: str, namespace: str,
                                             kubeconfig_path: Optional[str] = None) -> str:
    """分析ServiceAccount的权限
    
    Args:
        service_account_name: ServiceAccount名称
        namespace: 命名空间
        kubeconfig_path: kubeconfig 文件路径，不指定则使用默认集群
    """
    service = get_k8s_advanced_service(kubeconfig_path)
    result = await service.analyze_serviceaccount_permissions(service_account_name, namespace)
    return json_success(result)

@mcp.tool()
@handle_tool_errors
async def check_serviceaccount_permission_conflicts(namespace: str,
                                                    kubeconfig_path: Optional[str] = None) -> str:
    """检查命名空间中ServiceAccount的权限冲突
    
    Args:
        namespace: 命名空间
        kubeconfig_path: kubeconfig 文件路径，不指定则使用默认集群
    """
    service = get_k8s_advanced_service(kubeconfig_path)
    result = await service.check_serviceaccount_permission_conflicts(namespace)
    return json_success(result)

@mcp.tool()
@handle_tool_errors
async def list_role_serviceaccounts(role_name: str, namespace: str, role_type: str = "Role",
                                   kubeconfig_path: Optional[str] = None) -> str:
    """列出绑定到指定角色的所有ServiceAccount
    
    Args:
        role_name: 角色名称
        namespace: 命名空间
        role_type: 角色类型（Role或ClusterRole）
        kubeconfig_path: kubeconfig 文件路径，不指定则使用默认集群
    """
    if role_type not in ("Role", "ClusterRole"):
        return json_error("role_type 必须是 Role 或 ClusterRole")
    service = get_k8s_advanced_service(kubeconfig_path)
    result = await service.list_role_serviceaccounts(role_name, namespace, role_type)
    return json_success(result)