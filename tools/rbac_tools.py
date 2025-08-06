"""
RBAC管理工具
提供角色和权限管理的功能
"""

import json
from typing import List, Dict, Any
from services.k8s_advanced_service import KubernetesAdvancedService


# 导入共享的MCP实例
from . import mcp


@mcp.tool()
async def list_serviceaccounts(namespace: str = "default") -> str:
    """列出命名空间中的ServiceAccount
    
    Args:
        namespace: 命名空间
    """
    try:
        k8s_service = KubernetesAdvancedService()
        serviceaccounts = await k8s_service.k8s_service.list_serviceaccounts(namespace)
        
        return json.dumps({
            "success": True,
            "serviceaccounts": serviceaccounts,
            "count": len(serviceaccounts),
            "namespace": namespace
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def describe_serviceaccount(name: str, namespace: str = "default") -> str:
    """获取ServiceAccount详情
    
    Args:
        name: ServiceAccount名称
        namespace: 命名空间
    """
    try:
        k8s_service = KubernetesAdvancedService()
        serviceaccount = await k8s_service.k8s_service.get_serviceaccount(name, namespace)
        
        return json.dumps({
            "success": True,
            "serviceaccount": serviceaccount,
            "name": name,
            "namespace": namespace
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def create_serviceaccount(name: str, namespace: str = "default",
                              labels: str = None, annotations: str = None,
                              secrets: str = None, image_pull_secrets: str = None,
                              automount_service_account_token: bool = None) -> str:
    """创建ServiceAccount
    
    Args:
        name: ServiceAccount名称
        namespace: 命名空间
        labels: 标签 (JSON格式字符串)
        annotations: 注解 (JSON格式字符串)
        secrets: 关联的secrets列表 (JSON格式字符串)
        image_pull_secrets: 镜像拉取secrets列表 (JSON格式字符串)
        automount_service_account_token: 是否自动挂载服务账户令牌
    """
    try:
        k8s_service = KubernetesAdvancedService()
        
        # 解析JSON参数
        parsed_labels = json.loads(labels) if labels else None
        parsed_annotations = json.loads(annotations) if annotations else None
        parsed_secrets = json.loads(secrets) if secrets else None
        parsed_image_pull_secrets = json.loads(image_pull_secrets) if image_pull_secrets else None
        
        result = await k8s_service.k8s_service.create_serviceaccount(
            name=name,
            namespace=namespace,
            labels=parsed_labels,
            annotations=parsed_annotations,
            secrets=parsed_secrets,
            image_pull_secrets=parsed_image_pull_secrets,
            automount_service_account_token=automount_service_account_token
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def update_serviceaccount(name: str, namespace: str = "default",
                              labels: str = None, annotations: str = None,
                              secrets: str = None, image_pull_secrets: str = None,
                              automount_service_account_token: bool = None) -> str:
    """更新ServiceAccount
    
    Args:
        name: ServiceAccount名称
        namespace: 命名空间
        labels: 标签 (JSON格式字符串)
        annotations: 注解 (JSON格式字符串)
        secrets: 关联的secrets列表 (JSON格式字符串)
        image_pull_secrets: 镜像拉取secrets列表 (JSON格式字符串)
        automount_service_account_token: 是否自动挂载服务账户令牌
    """
    try:
        k8s_service = KubernetesAdvancedService()
        
        # 解析JSON参数
        parsed_labels = json.loads(labels) if labels else None
        parsed_annotations = json.loads(annotations) if annotations else None
        parsed_secrets = json.loads(secrets) if secrets else None
        parsed_image_pull_secrets = json.loads(image_pull_secrets) if image_pull_secrets else None
        
        result = await k8s_service.k8s_service.update_serviceaccount(
            name=name,
            namespace=namespace,
            labels=parsed_labels,
            annotations=parsed_annotations,
            secrets=parsed_secrets,
            image_pull_secrets=parsed_image_pull_secrets,
            automount_service_account_token=automount_service_account_token
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def delete_serviceaccount(name: str, namespace: str = "default",
                              grace_period_seconds: int = None) -> str:
    """删除ServiceAccount
    
    Args:
        name: ServiceAccount名称
        namespace: 命名空间
        grace_period_seconds: 优雅删除时间（秒）
    """
    try:
        k8s_service = KubernetesAdvancedService()
        result = await k8s_service.k8s_service.delete_serviceaccount(
            name=name,
            namespace=namespace,
            grace_period_seconds=grace_period_seconds
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)

@mcp.tool()
async def list_roles(namespace: str = "default") -> str:
    """列出命名空间中的Role
    
    Args:
        namespace: 命名空间
    """
    try:
        k8s_service = KubernetesAdvancedService()
        roles = await k8s_service.k8s_service.list_roles(namespace)
        
        return json.dumps({
            "success": True,
            "roles": roles,
            "count": len(roles),
            "namespace": namespace
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)

@mcp.tool()
async def describe_role(name: str, namespace: str = "default") -> str:
    """获取Role详情
    
    Args:
        name: Role名称
        namespace: 命名空间
    """
    try:
        k8s_service = KubernetesAdvancedService()
        role = await k8s_service.k8s_service.get_role(name, namespace)
        
        return json.dumps({
            "success": True,
            "role": role
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def create_role(name: str, namespace: str = "default", rules: str = None,
                     labels: str = None, annotations: str = None) -> str:
    """创建Role
    
    Args:
        name: Role名称
        namespace: 命名空间
        rules: JSON格式的规则列表
        labels: JSON格式的标签
        annotations: JSON格式的注解
    """
    try:
        k8s_service = KubernetesAdvancedService()
        
        # 解析参数
        rules_list = json.loads(rules) if rules else []
        labels_dict = json.loads(labels) if labels else None
        annotations_dict = json.loads(annotations) if annotations else None
        
        result = await k8s_service.k8s_service.create_role(name, namespace, rules_list, labels_dict, annotations_dict)
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def update_role(name: str, namespace: str = "default", rules: str = None,
                     labels: str = None, annotations: str = None) -> str:
    """更新Role
    
    Args:
        name: Role名称
        namespace: 命名空间
        rules: JSON格式的规则列表
        labels: JSON格式的标签
        annotations: JSON格式的注解
    """
    try:
        k8s_service = KubernetesAdvancedService()
        
        # 解析参数
        rules_list = json.loads(rules) if rules else None
        labels_dict = json.loads(labels) if labels else None
        annotations_dict = json.loads(annotations) if annotations else None
        
        result = await k8s_service.k8s_service.update_role(name, namespace, rules_list, labels_dict, annotations_dict)
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def delete_role(name: str, namespace: str = "default") -> str:
    """删除Role
    
    Args:
        name: Role名称
        namespace: 命名空间
    """
    try:
        k8s_service = KubernetesAdvancedService()
        result = await k8s_service.k8s_service.delete_role(name, namespace)
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def list_cluster_roles() -> str:
    """列出ClusterRole"""
    try:
        k8s_service = KubernetesAdvancedService()
        cluster_roles = await k8s_service.k8s_service.list_cluster_roles()
        
        return json.dumps({
            "success": True,
            "cluster_roles": cluster_roles,
            "count": len(cluster_roles)
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def describe_cluster_role(name: str) -> str:
    """获取ClusterRole详情
    
    Args:
        name: ClusterRole名称
    """
    try:
        k8s_service = KubernetesAdvancedService()
        cluster_role = await k8s_service.k8s_service.get_cluster_role(name)
        
        return json.dumps({
            "success": True,
            "cluster_role": cluster_role
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def create_cluster_role(name: str, rules: str = None,
                            labels: str = None, annotations: str = None) -> str:
    """创建ClusterRole
    
    Args:
        name: ClusterRole名称
        rules: JSON格式的规则列表
        labels: JSON格式的标签
        annotations: JSON格式的注解
    """
    try:
        k8s_service = KubernetesAdvancedService()
        
        # 解析参数
        rules_list = json.loads(rules) if rules else []
        labels_dict = json.loads(labels) if labels else None
        annotations_dict = json.loads(annotations) if annotations else None
        
        result = await k8s_service.k8s_service.create_cluster_role(name, rules_list, labels_dict, annotations_dict)
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def delete_cluster_role(name: str) -> str:
    """删除ClusterRole
    
    Args:
        name: ClusterRole名称
    """
    try:
        k8s_service = KubernetesAdvancedService()
        result = await k8s_service.k8s_service.delete_cluster_role(name)
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def list_role_bindings(namespace: str = "default") -> str:
    """列出命名空间中的RoleBinding
    
    Args:
        namespace: 命名空间
    """
    try:
        k8s_service = KubernetesAdvancedService()
        role_bindings = await k8s_service.k8s_service.list_role_bindings(namespace)
        
        return json.dumps({
            "success": True,
            "role_bindings": role_bindings,
            "count": len(role_bindings),
            "namespace": namespace
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def describe_role_binding(name: str, namespace: str = "default") -> str:
    """获取RoleBinding详情
    
    Args:
        name: RoleBinding名称
        namespace: 命名空间
    """
    try:
        k8s_service = KubernetesAdvancedService()
        role_binding = await k8s_service.k8s_service.get_role_binding(name, namespace)
        
        return json.dumps({
            "success": True,
            "role_binding": role_binding
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def create_role_binding(name: str, namespace: str = "default", 
                            role_ref: str = None, subjects: str = None,
                            labels: str = None, annotations: str = None) -> str:
    """创建RoleBinding
    
    Args:
        name: RoleBinding名称
        namespace: 命名空间
        role_ref: JSON格式的角色引用
        subjects: JSON格式的主体列表
        labels: JSON格式的标签
        annotations: JSON格式的注解
    """
    try:
        k8s_service = KubernetesAdvancedService()
        
        # 解析参数
        role_ref_dict = json.loads(role_ref) if role_ref else None
        subjects_list = json.loads(subjects) if subjects else []
        labels_dict = json.loads(labels) if labels else None
        annotations_dict = json.loads(annotations) if annotations else None
        
        result = await k8s_service.k8s_service.create_role_binding(name, namespace, role_ref_dict, subjects_list, labels_dict, annotations_dict)
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def delete_role_binding(name: str, namespace: str = "default") -> str:
    """删除RoleBinding
    
    Args:
        name: RoleBinding名称
        namespace: 命名空间
    """
    try:
        k8s_service = KubernetesAdvancedService()
        result = await k8s_service.k8s_service.delete_role_binding(name, namespace)
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def list_cluster_role_bindings() -> str:
    """列出ClusterRoleBinding"""
    try:
        k8s_service = KubernetesAdvancedService()
        cluster_role_bindings = await k8s_service.k8s_service.list_cluster_role_bindings()
        
        return json.dumps({
            "success": True,
            "cluster_role_bindings": cluster_role_bindings,
            "count": len(cluster_role_bindings)
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def describe_cluster_role_binding(name: str) -> str:
    """获取ClusterRoleBinding详情
    
    Args:
        name: ClusterRoleBinding名称
    """
    try:
        k8s_service = KubernetesAdvancedService()
        cluster_role_binding = await k8s_service.k8s_service.get_cluster_role_binding(name)
        
        return json.dumps({
            "success": True,
            "cluster_role_binding": cluster_role_binding
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def create_cluster_role_binding(name: str, role_ref: str = None, 
                                    subjects: str = None,
                                    labels: str = None, annotations: str = None) -> str:
    """创建ClusterRoleBinding
    
    Args:
        name: ClusterRoleBinding名称
        role_ref: JSON格式的角色引用
        subjects: JSON格式的主体列表
        labels: JSON格式的标签
        annotations: JSON格式的注解
    """
    try:
        k8s_service = KubernetesAdvancedService()
        
        # 解析参数
        role_ref_dict = json.loads(role_ref) if role_ref else None
        subjects_list = json.loads(subjects) if subjects else []
        labels_dict = json.loads(labels) if labels else None
        annotations_dict = json.loads(annotations) if annotations else None
        
        result = await k8s_service.k8s_service.create_cluster_role_binding(name, role_ref_dict, subjects_list, labels_dict, annotations_dict)
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def delete_cluster_role_binding(name: str) -> str:
    """删除ClusterRoleBinding
    
    Args:
        name: ClusterRoleBinding名称
    """
    try:
        k8s_service = KubernetesAdvancedService()
        result = await k8s_service.k8s_service.delete_cluster_role_binding(name)
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


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
