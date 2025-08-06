"""
资源操作验证工具
提供操作前后的对比和验证功能
"""

import json
from typing import Dict, List, Any, Optional
from services.k8s_advanced_service import KubernetesAdvancedService


# 导入共享的MCP实例
from . import mcp


# ============================================================================
# Deployment 相关验证和预览工具
# ============================================================================

@mcp.tool()
async def validate_deployment_update(name: str, namespace: str = "default",
                                   replicas: int = None, image: str = None,
                                   labels: str = None) -> str:
    """验证Deployment更新操作
    
    Args:
        name: Deployment名称
        namespace: 命名空间
        replicas: 新的副本数
        image: 新的镜像
        labels: JSON格式的新标签
    """
    try:
        service = KubernetesAdvancedService()
        kwargs = {}
        
        if replicas is not None:
            kwargs["replicas"] = replicas
        
        if image is not None:
            kwargs["image"] = image
            
        if labels is not None:
            kwargs["labels"] = json.loads(labels)
            
        if not kwargs:
            return json.dumps({
                "success": False,
                "error": "必须指定至少一个更新参数"
            }, ensure_ascii=False, indent=2)
        
        result = await service.validate_deployment_operation(
            name, namespace, "update", **kwargs
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def preview_deployment_changes(name: str, namespace: str = "default",
                                   replicas: int = None, image: str = None,
                                   labels: str = None) -> str:
    """预览Deployment的变更
    
    Args:
        name: Deployment名称
        namespace: 命名空间
        replicas: 新的副本数
        image: 新的镜像
        labels: JSON格式的新标签
    """
    try:
        service = KubernetesAdvancedService()
        
        # 获取当前状态
        current_state = await service.get_resource_before_operation("deployment", name, namespace)
        
        if "error" in current_state:
            return json.dumps({
                "success": False,
                "error": current_state["error"]
            }, ensure_ascii=False, indent=2)
        
        # 构建预览状态
        preview_state = current_state.copy()
        
        if replicas is not None:
            preview_state["spec"]["replicas"] = replicas
        
        if image is not None and preview_state.get("spec", {}).get("template", {}).get("spec", {}).get("containers"):
            preview_state["spec"]["template"]["spec"]["containers"][0]["image"] = image
        
        if labels is not None:
            labels_dict = json.loads(labels)
            preview_state["metadata"]["labels"] = labels_dict
            
        # 比较变化
        changes = service.compare_deployment_changes(current_state, preview_state)
            
        return json.dumps({
            "success": True,
            "resource": f"deployment/{name}",
            "namespace": namespace,
            "current_state": current_state,
            "preview_state": preview_state,
            "changes": changes
        }, ensure_ascii=False, indent=2)
            
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


# ============================================================================
# StatefulSet 相关验证和预览工具
# ============================================================================

@mcp.tool()
async def validate_statefulset_update(name: str, namespace: str = "default",
                                   replicas: int = None, image: str = None,
                                   labels: str = None) -> str:
    """验证StatefulSet更新操作
    
    Args:
        name: StatefulSet名称
        namespace: 命名空间
        replicas: 新的副本数
        image: 新的镜像
        labels: JSON格式的新标签
    """
    try:
        service = KubernetesAdvancedService()
        kwargs = {}
        
        if replicas is not None:
            kwargs["replicas"] = replicas
        
        if image is not None:
            kwargs["image"] = image
            
        if labels is not None:
            kwargs["labels"] = json.loads(labels)
            
        if not kwargs:
            return json.dumps({
                "success": False,
                "error": "必须指定至少一个更新参数"
            }, ensure_ascii=False, indent=2)
        
        result = await service.validate_statefulset_operation(
            name, namespace, "update", **kwargs
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def preview_statefulset_changes(name: str, namespace: str = "default",
                                   replicas: int = None, image: str = None,
                                   labels: str = None) -> str:
    """预览StatefulSet的变更
    
    Args:
        name: StatefulSet名称
        namespace: 命名空间
        replicas: 新的副本数
        image: 新的镜像
        labels: JSON格式的新标签
    """
    try:
        service = KubernetesAdvancedService()
        
        # 获取当前状态
        current_state = await service.get_resource_before_operation("statefulset", name, namespace)
        
        if "error" in current_state:
            return json.dumps({
                "success": False,
                "error": current_state["error"]
            }, ensure_ascii=False, indent=2)
        
        # 构建预览状态
        preview_state = current_state.copy()
        
        if replicas is not None:
            preview_state["spec"]["replicas"] = replicas
        
        if image is not None and "containers" in preview_state.get("spec", {}).get("template", {}).get("spec", {}):
            containers = preview_state["spec"]["template"]["spec"]["containers"]
            if containers and len(containers) > 0:
                containers[0]["image"] = image
        
        if labels is not None:
            labels_dict = json.loads(labels)
            preview_state["metadata"]["labels"] = labels_dict
        
        # 比较变化
        changes = service.compare_statefulset_changes(current_state, preview_state)
        
        return json.dumps({
            "success": True,
            "resource": f"statefulset/{name}",
            "namespace": namespace,
            "current_state": current_state,
            "preview_state": preview_state,
            "changes": changes
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


# ============================================================================
# DaemonSet 相关验证和预览工具
# ============================================================================

@mcp.tool()
async def validate_daemonset_update(name: str, namespace: str = "default",
                                 image: str = None, labels: str = None) -> str:
    """验证DaemonSet更新操作
    
    Args:
        name: DaemonSet名称
        namespace: 命名空间
        image: 新的镜像
        labels: JSON格式的新标签
    """
    try:
        service = KubernetesAdvancedService()
        kwargs = {}
        
        if image is not None:
            kwargs["image"] = image
            
        if labels is not None:
            kwargs["labels"] = json.loads(labels)
            
        if not kwargs:
            return json.dumps({
                "success": False,
                "error": "必须指定至少一个更新参数"
            }, ensure_ascii=False, indent=2)
        
        result = await service.validate_daemonset_operation(
            name, namespace, "update", **kwargs
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def preview_daemonset_changes(name: str, namespace: str = "default",
                                 image: str = None, labels: str = None) -> str:
    """预览DaemonSet的变更
    
    Args:
        name: DaemonSet名称
        namespace: 命名空间
        image: 新的镜像
        labels: JSON格式的新标签
    """
    try:
        service = KubernetesAdvancedService()
        
        # 获取当前状态
        current_state = await service.get_resource_before_operation("daemonset", name, namespace)
        
        if "error" in current_state:
            return json.dumps({
                "success": False,
                "error": current_state["error"]
            }, ensure_ascii=False, indent=2)
        
        # 构建预览状态
        preview_state = current_state.copy()
        
        if image is not None and "containers" in preview_state.get("spec", {}).get("template", {}).get("spec", {}):
            containers = preview_state["spec"]["template"]["spec"]["containers"]
            if containers and len(containers) > 0:
                containers[0]["image"] = image
        
        if labels is not None:
            labels_dict = json.loads(labels)
            preview_state["metadata"]["labels"] = labels_dict
            
            # 比较变化
        changes = service.compare_daemonset_changes(current_state, preview_state)
            
        return json.dumps({
                "success": True,
            "resource": f"daemonset/{name}",
                "namespace": namespace,
            "current_state": current_state,
            "preview_state": preview_state,
                "changes": changes
        }, ensure_ascii=False, indent=2)
    
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


# ============================================================================
# Service 相关验证和预览工具
# ============================================================================

@mcp.tool()
async def validate_service_update(name: str, namespace: str = "default",
                                service_type: str = None, ports: str = None,
                                selector: str = None) -> str:
    """验证Service更新操作
    
    Args:
        name: Service名称
        namespace: 命名空间
        service_type: 服务类型 (ClusterIP, NodePort, LoadBalancer)
        ports: JSON格式的端口配置
        selector: JSON格式的选择器
    """
    try:
        service = KubernetesAdvancedService()
        kwargs = {}
        
        if service_type:
            kwargs["service_type"] = service_type
        
        if ports:
            kwargs["ports"] = json.loads(ports)
        
        if selector:
            kwargs["selector"] = json.loads(selector)
            
        if not kwargs:
            return json.dumps({
                "success": False,
                "error": "必须指定至少一个更新参数"
            }, ensure_ascii=False, indent=2)
        
        result = await service.validate_service_operation(
            name, namespace, "update", **kwargs
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def preview_service_changes(name: str, namespace: str = "default",
                                service_type: str = None, ports: str = None,
                                selector: str = None, labels: str = None) -> str:
    """预览Service的变更
    
    Args:
        name: Service名称
        namespace: 命名空间
        service_type: 新的服务类型
        ports: JSON格式的新端口配置
        selector: JSON格式的新选择器
        labels: JSON格式的新标签
    """
    try:
        service = KubernetesAdvancedService()
        
        # 获取当前状态
        current_state = await service.get_resource_before_operation("service", name, namespace)
        
        if "error" in current_state:
            return json.dumps({
                "success": False,
                "error": current_state["error"]
            }, ensure_ascii=False, indent=2)
        
        # 构建预览状态
        preview_state = current_state.copy()
        
        if service_type is not None:
            preview_state["spec"]["type"] = service_type
        
        if ports is not None:
            ports_list = json.loads(ports)
            preview_state["spec"]["ports"] = ports_list
        
        if selector is not None:
            selector_dict = json.loads(selector)
            preview_state["spec"]["selector"] = selector_dict
        
        if labels is not None:
            labels_dict = json.loads(labels)
            preview_state["metadata"]["labels"] = labels_dict
            
            # 比较变化
        changes = service.compare_service_changes(current_state, preview_state)
            
        return json.dumps({
                "success": True,
                "resource": f"service/{name}",
                "namespace": namespace,
            "current_state": current_state,
            "preview_state": preview_state,
                "changes": changes
        }, ensure_ascii=False, indent=2)
    
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


# ============================================================================
# ConfigMap 相关验证和预览工具
# ============================================================================

@mcp.tool()
async def validate_configmap_update(name: str, namespace: str = "default",
                                  data: str = None, binary_data: str = None) -> str:
    """验证ConfigMap更新操作
    
    Args:
        name: ConfigMap名称
        namespace: 命名空间
        data: JSON格式的数据
        binary_data: JSON格式的二进制数据
    """
    try:
        service = KubernetesAdvancedService()
        kwargs = {}
        
        if data:
            kwargs["data"] = json.loads(data)
        
        if binary_data:
            kwargs["binary_data"] = json.loads(binary_data)
            
        if not kwargs:
            return json.dumps({
                "success": False,
                "error": "必须指定至少一个更新参数"
            }, ensure_ascii=False, indent=2)
        
        result = await service.validate_configmap_operation(
            name, namespace, "update", **kwargs
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def preview_configmap_changes(name: str, namespace: str = "default",
                                  data: str = None, binary_data: str = None,
                                  labels: str = None) -> str:
    """预览ConfigMap的变更
    
    Args:
        name: ConfigMap名称
        namespace: 命名空间
        data: JSON格式的新数据
        binary_data: JSON格式的新二进制数据
        labels: JSON格式的新标签
    """
    try:
        service = KubernetesAdvancedService()
        
        # 获取当前状态
        current_state = await service.get_resource_before_operation("configmap", name, namespace)
        
        if "error" in current_state:
            return json.dumps({
                "success": False,
                "error": current_state["error"]
            }, ensure_ascii=False, indent=2)
        
        # 构建预览状态
        preview_state = current_state.copy()
        
        if data is not None:
            data_dict = json.loads(data)
            preview_state["data"] = data_dict
        
        if binary_data is not None:
            binary_data_dict = json.loads(binary_data)
            preview_state["binaryData"] = binary_data_dict
        
        if labels is not None:
            labels_dict = json.loads(labels)
            preview_state["metadata"]["labels"] = labels_dict
            
            # 比较变化
        changes = service.compare_configmap_changes(current_state, preview_state)
            
        return json.dumps({
                "success": True,
            "resource": f"configmap/{name}",
                "namespace": namespace,
            "current_state": current_state,
            "preview_state": preview_state,
                "changes": changes
        }, ensure_ascii=False, indent=2)
            
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


# ============================================================================
# Secret 相关验证和预览工具
# ============================================================================

@mcp.tool()
async def validate_secret_update(name: str, namespace: str = "default",
                               data: str = None, string_data: str = None,
                               secret_type: str = None) -> str:
    """验证Secret更新操作
    
    Args:
        name: Secret名称
        namespace: 命名空间
        data: JSON格式的数据 (Base64编码)
        string_data: JSON格式的字符串数据 (明文)
        secret_type: Secret类型
    """
    try:
        service = KubernetesAdvancedService()
        kwargs = {}
        
        if data:
            kwargs["data"] = json.loads(data)
        
        if string_data:
            kwargs["string_data"] = json.loads(string_data)
            
        if secret_type:
            kwargs["type"] = secret_type
            
        if not kwargs:
            return json.dumps({
                "success": False,
                "error": "必须指定至少一个更新参数"
            }, ensure_ascii=False, indent=2)
        
        result = await service.validate_secret_operation(
            name, namespace, "update", **kwargs
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def preview_secret_changes(name: str, namespace: str = "default",
                               data: str = None, string_data: str = None,
                               secret_type: str = None, labels: str = None) -> str:
    """预览Secret的变更
    
    Args:
        name: Secret名称
        namespace: 命名空间
        data: JSON格式的数据 (Base64编码)
        string_data: JSON格式的字符串数据 (明文)
        secret_type: Secret类型
        labels: JSON格式的新标签
    """
    try:
        service = KubernetesAdvancedService()
        
        # 获取当前状态
        current_state = await service.get_resource_before_operation("secret", name, namespace)
        
        if "error" in current_state:
            return json.dumps({
                "success": False,
                "error": current_state["error"]
            }, ensure_ascii=False, indent=2)
        
        # 构建预览状态
        preview_state = current_state.copy()
        
        if data is not None:
            data_dict = json.loads(data)
            preview_state["data"] = data_dict
        
        if string_data is not None:
            string_data_dict = json.loads(string_data)
            preview_state["stringData"] = string_data_dict
        
        if secret_type is not None:
            preview_state["type"] = secret_type
        
        if labels is not None:
            labels_dict = json.loads(labels)
            preview_state["metadata"]["labels"] = labels_dict
        
        # 比较变化
        changes = service.compare_secret_changes(current_state, preview_state)
        
        return json.dumps({
            "success": True,
            "resource": f"secret/{name}",
            "namespace": namespace,
            "current_state": current_state,
            "preview_state": preview_state,
            "changes": changes
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


# ============================================================================
# Job 相关验证和预览工具
# ============================================================================

@mcp.tool()
async def validate_job_update(name: str, namespace: str = "default",
                            parallelism: int = None, completions: int = None,
                            backoff_limit: int = None) -> str:
    """验证Job更新操作
    
    Args:
        name: Job名称
        namespace: 命名空间
        parallelism: 并行度
        completions: 完成数
        backoff_limit: 回退限制
    """
    try:
        service = KubernetesAdvancedService()
        kwargs = {}
        
        if parallelism is not None:
            kwargs["parallelism"] = parallelism
        
        if completions is not None:
            kwargs["completions"] = completions
            
        if backoff_limit is not None:
            kwargs["backoff_limit"] = backoff_limit
            
        if not kwargs:
            return json.dumps({
                "success": False,
                "error": "必须指定至少一个更新参数"
            }, ensure_ascii=False, indent=2)
        
        result = await service.validate_job_operation(
            name, namespace, "update", **kwargs
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def preview_job_changes(name: str, namespace: str = "default",
                            parallelism: int = None, completions: int = None,
                            backoff_limit: int = None, labels: str = None) -> str:
    """预览Job的变更
    
    Args:
        name: Job名称
        namespace: 命名空间
        parallelism: 新的并行度
        completions: 新的完成数
        backoff_limit: 新的回退限制
        labels: JSON格式的新标签
    """
    try:
        service = KubernetesAdvancedService()
        
        # 获取当前状态
        current_state = await service.get_resource_before_operation("job", name, namespace)
        
        if "error" in current_state:
            return json.dumps({
                "success": False,
                "error": current_state["error"]
            }, ensure_ascii=False, indent=2)
        
        # 构建预览状态
        preview_state = current_state.copy()
        
        if parallelism is not None:
            preview_state["spec"]["parallelism"] = parallelism
        
        if completions is not None:
            preview_state["spec"]["completions"] = completions
        
        if backoff_limit is not None:
            preview_state["spec"]["backoffLimit"] = backoff_limit
        
        if labels is not None:
            labels_dict = json.loads(labels)
            preview_state["metadata"]["labels"] = labels_dict
        
        # 比较变化
        changes = service.compare_job_changes(current_state, preview_state)
        
        return json.dumps({
            "success": True,
            "resource": f"job/{name}",
            "namespace": namespace,
            "current_state": current_state,
            "preview_state": preview_state,
            "changes": changes
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


# ============================================================================
# CronJob 相关验证和预览工具
# ============================================================================

@mcp.tool()
async def validate_cronjob_update(name: str, namespace: str = "default",
                               schedule: str = None, suspend: bool = None,
                               image: str = None) -> str:
    """验证CronJob更新操作
    
    Args:
        name: CronJob名称
        namespace: 命名空间
        schedule: 新的调度表达式
        suspend: 是否暂停
        image: 新的镜像
    """
    try:
        service = KubernetesAdvancedService()
        kwargs = {}
        
        if schedule is not None:
            kwargs["schedule"] = schedule
        
        if suspend is not None:
            kwargs["suspend"] = suspend
            
        if image is not None:
            kwargs["image"] = image
            
        if not kwargs:
            return json.dumps({
                "success": False,
                "error": "必须指定至少一个更新参数"
            }, ensure_ascii=False, indent=2)
        
        result = await service.validate_cronjob_operation(
            name, namespace, "update", **kwargs
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def preview_cronjob_changes(name: str, namespace: str = "default",
                               schedule: str = None, suspend: bool = None,
                               image: str = None, labels: str = None) -> str:
    """预览CronJob的变更
    
    Args:
        name: CronJob名称
        namespace: 命名空间
        schedule: 新的调度表达式
        suspend: 是否暂停
        image: 新的镜像
        labels: JSON格式的新标签
    """
    try:
        service = KubernetesAdvancedService()
        
        # 获取当前状态
        current_state = await service.get_resource_before_operation("cronjob", name, namespace)
        
        if "error" in current_state:
            return json.dumps({
                "success": False,
                "error": current_state["error"]
            }, ensure_ascii=False, indent=2)
        
        # 构建预览状态
        preview_state = current_state.copy()
        
        if schedule is not None:
            preview_state["spec"]["schedule"] = schedule
        
        if suspend is not None:
            preview_state["spec"]["suspend"] = suspend
        
        if image is not None and "jobTemplate" in preview_state.get("spec", {}):
            # 更新容器镜像
            containers = preview_state["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"]
            if containers and len(containers) > 0:
                containers[0]["image"] = image
        
        if labels is not None:
            labels_dict = json.loads(labels)
            preview_state["metadata"]["labels"] = labels_dict
        
        # 比较变化
        changes = service.compare_cronjob_changes(current_state, preview_state)
        
        return json.dumps({
            "success": True,
            "resource": f"cronjob/{name}",
            "namespace": namespace,
            "current_state": current_state,
            "preview_state": preview_state,
            "changes": changes
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


# ============================================================================
# Ingress 相关验证和预览工具
# ============================================================================

@mcp.tool()
async def validate_ingress_update(name: str, namespace: str = "default",
                                rules: str = None, tls: str = None,
                                ingress_class: str = None) -> str:
    """验证Ingress更新操作
    
    Args:
        name: Ingress名称
        namespace: 命名空间
        rules: JSON格式的规则配置
        tls: JSON格式的TLS配置
        ingress_class: Ingress类名
    """
    try:
        service = KubernetesAdvancedService()
        kwargs = {}
        
        if rules:
            kwargs["rules"] = json.loads(rules)
        
        if tls:
            kwargs["tls"] = json.loads(tls)
            
        if ingress_class:
            kwargs["ingress_class"] = ingress_class
            
        if not kwargs:
            return json.dumps({
                "success": False,
                "error": "必须指定至少一个更新参数"
            }, ensure_ascii=False, indent=2)
        
        result = await service.validate_ingress_operation(
            name, namespace, "update", **kwargs
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def preview_ingress_changes(name: str, namespace: str = "default",
                                rules: str = None, tls: str = None,
                                ingress_class: str = None, labels: str = None) -> str:
    """预览Ingress的变更
    
    Args:
        name: Ingress名称
        namespace: 命名空间
        rules: JSON格式的新规则配置
        tls: JSON格式的新TLS配置
        ingress_class: 新的Ingress类名
        labels: JSON格式的新标签
    """
    try:
        service = KubernetesAdvancedService()
        
        # 获取当前状态
        current_state = await service.get_resource_before_operation("ingress", name, namespace)
        
        if "error" in current_state:
            return json.dumps({
                "success": False,
                "error": current_state["error"]
            }, ensure_ascii=False, indent=2)
        
        # 构建预览状态
        preview_state = current_state.copy()
        
        if rules is not None:
            rules_list = json.loads(rules)
            preview_state["spec"]["rules"] = rules_list
        
        if tls is not None:
            tls_list = json.loads(tls)
            preview_state["spec"]["tls"] = tls_list
        
        if ingress_class is not None:
            preview_state["spec"]["ingressClassName"] = ingress_class
        
        if labels is not None:
            labels_dict = json.loads(labels)
            preview_state["metadata"]["labels"] = labels_dict
            
        # 比较变化
        changes = service.compare_ingress_changes(current_state, preview_state)
            
        return json.dumps({
            "success": True,
            "resource": f"ingress/{name}",
            "namespace": namespace,
            "current_state": current_state,
            "preview_state": preview_state,
            "changes": changes
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


# ============================================================================
# StorageClass 相关验证和预览工具
# ============================================================================

@mcp.tool()
async def validate_storageclass_update(name: str, allow_volume_expansion: bool = None,
                                     parameters: str = None, labels: str = None) -> str:
    """验证StorageClass更新操作
    
    Args:
        name: StorageClass名称
        allow_volume_expansion: 是否允许卷扩容
        parameters: JSON格式的存储类参数
        labels: JSON格式的标签
    """
    try:
        service = KubernetesAdvancedService()
        kwargs = {}
        
        if allow_volume_expansion is not None:
            kwargs["allow_volume_expansion"] = allow_volume_expansion
        
        if parameters is not None:
            kwargs["parameters"] = json.loads(parameters)
            
        if labels is not None:
            kwargs["labels"] = json.loads(labels)
            
        if not kwargs:
            return json.dumps({
                "success": False,
                "error": "必须指定至少一个更新参数"
            }, ensure_ascii=False, indent=2)
        
        result = await service.validate_storageclass_operation(
            name, "update", **kwargs
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def preview_storageclass_changes(name: str, allow_volume_expansion: bool = None,
                                     parameters: str = None, labels: str = None) -> str:
    """预览StorageClass的变更
    
    Args:
        name: StorageClass名称
        allow_volume_expansion: 是否允许卷扩容
        parameters: JSON格式的存储类参数
        labels: JSON格式的标签
    """
    try:
        service = KubernetesAdvancedService()
        
        # 获取当前状态
        current_state = await service.get_resource_before_operation("storageclass", name)
        
        if "error" in current_state:
            return json.dumps({
                "success": False,
                "error": current_state["error"]
            }, ensure_ascii=False, indent=2)
        
        # 构建预览状态
        preview_state = current_state.copy()
        
        if allow_volume_expansion is not None:
            preview_state["allow_volume_expansion"] = allow_volume_expansion
        
        if parameters is not None:
            parameters_dict = json.loads(parameters)
            preview_state["parameters"] = parameters_dict
        
        if labels is not None:
            labels_dict = json.loads(labels)
            preview_state["metadata"]["labels"] = labels_dict
        
        # 比较变化
        changes = service.compare_storageclass_changes(current_state, preview_state)
        
        return json.dumps({
            "success": True,
            "resource": f"storageclass/{name}",
            "current_state": current_state,
            "preview_state": preview_state,
            "changes": changes
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


# ============================================================================
# PersistentVolume 相关验证和预览工具
# ============================================================================

@mcp.tool()
async def validate_persistentvolume_update(name: str, capacity: str = None,
                                         access_modes: str = None, reclaim_policy: str = None,
                                         storage_class_name: str = None, labels: str = None) -> str:
    """验证PersistentVolume更新操作
    
    Args:
        name: PersistentVolume名称
        capacity: 新的容量大小
        access_modes: JSON格式的访问模式列表
        reclaim_policy: 新的回收策略
        storage_class_name: 新的存储类名称
        labels: JSON格式的标签
    """
    try:
        service = KubernetesAdvancedService()
        kwargs = {}
        
        if capacity is not None:
            kwargs["capacity"] = capacity
        
        if access_modes is not None:
            kwargs["access_modes"] = json.loads(access_modes)
        
        if reclaim_policy is not None:
            kwargs["reclaim_policy"] = reclaim_policy
        
        if storage_class_name is not None:
            kwargs["storage_class_name"] = storage_class_name
        
        if labels is not None:
            kwargs["labels"] = json.loads(labels)
            
        if not kwargs:
            return json.dumps({
                "success": False,
                "error": "必须指定至少一个更新参数"
            }, ensure_ascii=False, indent=2)
        
        result = await service.validate_persistentvolume_operation(
            name, "update", **kwargs
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def preview_persistentvolume_changes(name: str, capacity: str = None,
                                         access_modes: str = None, reclaim_policy: str = None,
                                         storage_class_name: str = None, labels: str = None) -> str:
    """预览PersistentVolume的变更
    
    Args:
        name: PersistentVolume名称
        capacity: 新的容量大小
        access_modes: JSON格式的访问模式列表
        reclaim_policy: 新的回收策略
        storage_class_name: 新的存储类名称
        labels: JSON格式的标签
    """
    try:
        service = KubernetesAdvancedService()
        
        # 获取当前状态
        current_state = await service.get_resource_before_operation("persistentvolume", name)
        
        if "error" in current_state:
            return json.dumps({
                "success": False,
                "error": current_state["error"]
            }, ensure_ascii=False, indent=2)
        
        # 构建预览状态
        preview_state = current_state.copy()
        
        if capacity is not None:
            if "capacity" not in preview_state:
                preview_state["capacity"] = {}
            preview_state["capacity"]["storage"] = capacity
        
        if access_modes is not None:
            access_modes_list = json.loads(access_modes)
            preview_state["access_modes"] = access_modes_list
        
        if reclaim_policy is not None:
            preview_state["reclaim_policy"] = reclaim_policy
        
        if storage_class_name is not None:
            preview_state["storage_class_name"] = storage_class_name
        
        if labels is not None:
            labels_dict = json.loads(labels)
            preview_state["metadata"]["labels"] = labels_dict
        
        # 比较变化
        changes = service.compare_persistentvolume_changes(current_state, preview_state)
        
        return json.dumps({
            "success": True,
            "resource": f"persistentvolume/{name}",
            "current_state": current_state,
            "preview_state": preview_state,
            "changes": changes
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


# ============================================================================
# PersistentVolumeClaim 相关验证和预览工具
# ============================================================================

@mcp.tool()
async def validate_persistentvolumeclaim_update(name: str, namespace: str = "default", 
                                        size: str = None, access_modes: str = None,
                                        labels: str = None) -> str:
    """验证PVC更新操作
    
    Args:
        name: PVC名称
        namespace: 命名空间
        size: 新的存储大小
        access_modes: JSON格式的访问模式列表
        labels: JSON格式的标签
    """
    try:
        service = KubernetesAdvancedService()
        kwargs = {}
        
        if size is not None:
            kwargs["size"] = size
            
        if access_modes is not None:
            kwargs["access_modes"] = json.loads(access_modes)
            
        if labels is not None:
            kwargs["labels"] = json.loads(labels)
            
        if not kwargs:
            return json.dumps({
                "success": False,
                "error": "必须指定至少一个更新参数"
            }, ensure_ascii=False, indent=2)
        
        result = await service.validate_persistentvolumeclaim_operation(
            name, namespace, "update", **kwargs
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def preview_persistentvolumeclaim_changes(name: str, namespace: str = "default", 
                                         size: str = None, access_modes: str = None,
                                         labels: str = None) -> str:
    """预览PVC更新操作的变化
    
    Args:
        name: PVC名称
        namespace: 命名空间
        size: 新的存储大小
        access_modes: JSON格式的访问模式列表
        labels: JSON格式的标签
    """
    try:
        service = KubernetesAdvancedService()
        kwargs = {}
        
        if size is not None:
            kwargs["size"] = size
            
        if access_modes is not None:
            kwargs["access_modes"] = json.loads(access_modes)
            
        if labels is not None:
            kwargs["labels"] = json.loads(labels)
            
        if not kwargs:
            return json.dumps({
                "success": False,
                "error": "必须指定至少一个预览参数"
            }, ensure_ascii=False, indent=2)
        
        # 获取资源当前状态
        before = await service.get_resource_before_operation("persistentvolumeclaim", name, namespace)
        
        # 预览变更但不实际应用
        changes = {}
        if "size" in kwargs:
            changes["size"] = {"before": before.get("spec", {}).get("resources", {}).get("requests", {}).get("storage"), "after": kwargs["size"]}
            
        if "access_modes" in kwargs:
            changes["access_modes"] = {"before": before.get("spec", {}).get("accessModes"), "after": kwargs["access_modes"]}
            
        if "labels" in kwargs:
            changes["labels"] = {"before": before.get("metadata", {}).get("labels"), "after": kwargs["labels"]}
        
        return json.dumps({
            "success": True,
            "resource": f"persistentvolumeclaim/{name}",
            "namespace": namespace,
            "changes": changes,
            "preview": True
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


# ============================================================================
# ServiceAccount 相关验证和预览工具
# ============================================================================

@mcp.tool()
async def validate_serviceaccount_update(name: str, namespace: str = "default",
                                       labels: str = None, annotations: str = None,
                                       secrets: str = None, image_pull_secrets: str = None,
                                       automount_service_account_token: bool = None) -> str:
    """验证ServiceAccount更新操作
    
    Args:
        name: ServiceAccount名称
        namespace: 命名空间
        labels: JSON格式的新标签
        annotations: JSON格式的新注解
        secrets: JSON格式的关联secrets列表
        image_pull_secrets: JSON格式的镜像拉取secrets列表
        automount_service_account_token: 是否自动挂载服务账户令牌
    """
    try:
        service = KubernetesAdvancedService()
        kwargs = {}
        
        if labels is not None:
            kwargs["labels"] = json.loads(labels)
            
        if annotations is not None:
            kwargs["annotations"] = json.loads(annotations)
            
        if secrets is not None:
            kwargs["secrets"] = json.loads(secrets)
            
        if image_pull_secrets is not None:
            kwargs["image_pull_secrets"] = json.loads(image_pull_secrets)
            
        if automount_service_account_token is not None:
            kwargs["automount_service_account_token"] = automount_service_account_token
            
        if not kwargs:
            return json.dumps({
                "success": False,
                "error": "必须指定至少一个更新参数"
            }, ensure_ascii=False, indent=2)
        
        result = await service.validate_serviceaccount_operation(
            name, namespace, "update", **kwargs
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def preview_serviceaccount_changes(name: str, namespace: str = "default",
                                       labels: str = None, annotations: str = None,
                                       secrets: str = None, image_pull_secrets: str = None,
                                       automount_service_account_token: bool = None) -> str:
    """预览ServiceAccount变更效果
    
    Args:
        name: ServiceAccount名称
        namespace: 命名空间
        labels: JSON格式的新标签
        annotations: JSON格式的新注解
        secrets: JSON格式的关联secrets列表
        image_pull_secrets: JSON格式的镜像拉取secrets列表
        automount_service_account_token: 是否自动挂载服务账户令牌
    """
    try:
        service = KubernetesAdvancedService()
        
        # 获取当前状态
        current_state = await service.get_resource_before_operation("serviceaccount", name, namespace)
        
        if current_state.get("error"):
            return json.dumps({
                "success": False,
                "error": f"无法获取ServiceAccount当前状态: {current_state['error']}"
            }, ensure_ascii=False, indent=2)
        
        # 模拟变更后的状态
        simulated_state = current_state.copy()
        
        if labels is not None:
            simulated_state["labels"] = json.loads(labels)
            
        if annotations is not None:
            simulated_state["annotations"] = json.loads(annotations)
            
        if secrets is not None:
            simulated_state["secrets"] = json.loads(secrets)
            
        if image_pull_secrets is not None:
            simulated_state["image_pull_secrets"] = json.loads(image_pull_secrets)
            
        if automount_service_account_token is not None:
            simulated_state["automount_service_account_token"] = automount_service_account_token
        
        # 比较变化
        changes = service.compare_serviceaccount_changes(current_state, simulated_state)
        
        return json.dumps({
            "success": True,
            "resource": f"serviceaccount/{name}",
            "namespace": namespace,
            "current_state": current_state,
            "simulated_state": simulated_state,
            "changes": changes
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


# ============================================================================
# Role 相关验证和预览工具
# ============================================================================

@mcp.tool()
async def validate_role_update(name: str, namespace: str = "default",
                            rules: str = None, labels: str = None) -> str:
    """验证Role更新操作
    
    Args:
        name: Role名称
        namespace: 命名空间
        rules: JSON格式的规则列表
        labels: JSON格式的标签
    """
    try:
        service = KubernetesAdvancedService()
        kwargs = {}
        
        if rules is not None:
            kwargs["rules"] = json.loads(rules)
        
        if labels is not None:
            kwargs["labels"] = json.loads(labels)
            
        if not kwargs:
            return json.dumps({
                "success": False,
                "error": "必须指定至少一个更新参数"
            }, ensure_ascii=False, indent=2)
        
        result = await service.validate_role_operation(
            name, namespace, "update", **kwargs
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def preview_role_changes(name: str, namespace: str = "default",
                            rules: str = None, labels: str = None) -> str:
    """预览Role的变更
    
    Args:
        name: Role名称
        namespace: 命名空间
        rules: JSON格式的规则列表
        labels: JSON格式的标签
    """
    try:
        service = KubernetesAdvancedService()
        
        # 获取当前状态
        current_state = await service.get_resource_before_operation("role", name, namespace)
        
        if "error" in current_state:
            return json.dumps({
                "success": False,
                "error": current_state["error"]
            }, ensure_ascii=False, indent=2)
        
        # 构建预览状态
        preview_state = current_state.copy()
        
        if rules is not None:
            rules_list = json.loads(rules)
            preview_state["rules"] = rules_list
        
        if labels is not None:
            labels_dict = json.loads(labels)
            preview_state["metadata"]["labels"] = labels_dict
        
        # 比较变化
        changes = service.compare_role_changes(current_state, preview_state)
        
        return json.dumps({
            "success": True,
            "resource": f"role/{name}",
            "namespace": namespace,
            "current_state": current_state,
            "preview_state": preview_state,
            "changes": changes
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


# ============================================================================
# ClusterRole 相关验证和预览工具
# ============================================================================

@mcp.tool()
async def validate_cluster_role_update(name: str, rules: str = None, labels: str = None) -> str:
    """验证ClusterRole更新操作
    
    Args:
        name: ClusterRole名称
        rules: JSON格式的规则列表
        labels: JSON格式的标签
    """
    try:
        service = KubernetesAdvancedService()
        kwargs = {}
        
        if rules is not None:
            kwargs["rules"] = json.loads(rules)
        
        if labels is not None:
            kwargs["labels"] = json.loads(labels)
            
        if not kwargs:
            return json.dumps({
                "success": False,
                "error": "必须指定至少一个更新参数"
            }, ensure_ascii=False, indent=2)
        
        result = await service.validate_cluster_role_operation(
            name, "update", **kwargs
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def preview_cluster_role_changes(name: str, rules: str = None, labels: str = None) -> str:
    """预览ClusterRole的变更
    
    Args:
        name: ClusterRole名称
        rules: JSON格式的规则列表
        labels: JSON格式的标签
    """
    try:
        service = KubernetesAdvancedService()
        
        # 获取当前状态
        current_state = await service.get_resource_before_operation("clusterrole", name)
        
        if "error" in current_state:
            return json.dumps({
                "success": False,
                "error": current_state["error"]
            }, ensure_ascii=False, indent=2)
        
        # 构建预览状态
        preview_state = current_state.copy()
        
        if rules is not None:
            rules_list = json.loads(rules)
            preview_state["rules"] = rules_list
        
        if labels is not None:
            labels_dict = json.loads(labels)
            preview_state["metadata"]["labels"] = labels_dict
        
        # 比较变化
        changes = service.compare_cluster_role_changes(current_state, preview_state)
        
        return json.dumps({
            "success": True,
            "resource": f"clusterrole/{name}",
            "current_state": current_state,
            "preview_state": preview_state,
            "changes": changes
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


# ============================================================================
# RoleBinding 相关验证和预览工具
# ============================================================================

@mcp.tool()
async def validate_role_binding_update(name: str, namespace: str = "default",
                                     subjects: str = None, labels: str = None) -> str:
    """验证RoleBinding更新操作
    
    Args:
        name: RoleBinding名称
        namespace: 命名空间
        subjects: JSON格式的主体列表
        labels: JSON格式的标签
    """
    try:
        service = KubernetesAdvancedService()
        kwargs = {}
        
        if subjects is not None:
            kwargs["subjects"] = json.loads(subjects)
        
        if labels is not None:
            kwargs["labels"] = json.loads(labels)
            
        if not kwargs:
            return json.dumps({
                "success": False,
                "error": "必须指定至少一个更新参数"
            }, ensure_ascii=False, indent=2)
        
        result = await service.validate_role_binding_operation(
            name, namespace, "update", **kwargs
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def preview_role_binding_changes(name: str, namespace: str = "default",
                                     subjects: str = None, labels: str = None) -> str:
    """预览RoleBinding的变更
    
    Args:
        name: RoleBinding名称
        namespace: 命名空间
        subjects: JSON格式的主体列表
        labels: JSON格式的标签
    """
    try:
        service = KubernetesAdvancedService()
        
        # 获取当前状态
        current_state = await service.get_resource_before_operation("rolebinding", name, namespace)
        
        if "error" in current_state:
            return json.dumps({
                "success": False,
                "error": current_state["error"]
            }, ensure_ascii=False, indent=2)
        
        # 构建预览状态
        preview_state = current_state.copy()
        
        if subjects is not None:
            subjects_list = json.loads(subjects)
            preview_state["subjects"] = subjects_list
        
        if labels is not None:
            labels_dict = json.loads(labels)
            preview_state["metadata"]["labels"] = labels_dict
        
        # 比较变化
        changes = service.compare_role_binding_changes(current_state, preview_state)
        
        return json.dumps({
            "success": True,
            "resource": f"rolebinding/{name}",
            "namespace": namespace,
            "current_state": current_state,
            "preview_state": preview_state,
            "changes": changes
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


# ============================================================================
# ClusterRoleBinding 相关验证和预览工具
# ============================================================================

@mcp.tool()
async def validate_cluster_role_binding_update(name: str, subjects: str = None, labels: str = None) -> str:
    """验证ClusterRoleBinding更新操作
    
    Args:
        name: ClusterRoleBinding名称
        subjects: JSON格式的主体列表
        labels: JSON格式的标签
    """
    try:
        service = KubernetesAdvancedService()
        kwargs = {}
        
        if subjects is not None:
            kwargs["subjects"] = json.loads(subjects)
        
        if labels is not None:
            kwargs["labels"] = json.loads(labels)
            
        if not kwargs:
            return json.dumps({
                "success": False,
                "error": "必须指定至少一个更新参数"
            }, ensure_ascii=False, indent=2)
        
        result = await service.validate_cluster_role_binding_operation(
            name, "update", **kwargs
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def preview_cluster_role_binding_changes(name: str, subjects: str = None, labels: str = None) -> str:
    """预览ClusterRoleBinding的变更
    
    Args:
        name: ClusterRoleBinding名称
        subjects: JSON格式的主体列表
        labels: JSON格式的标签
    """
    try:
        service = KubernetesAdvancedService()
        
        # 获取当前状态
        current_state = await service.get_resource_before_operation("clusterrolebinding", name)
        
        if "error" in current_state:
            return json.dumps({
                "success": False,
                "error": current_state["error"]
            }, ensure_ascii=False, indent=2)
        
        # 构建预览状态
        preview_state = current_state.copy()
        
        if subjects is not None:
            subjects_list = json.loads(subjects)
            preview_state["subjects"] = subjects_list
        
        if labels is not None:
            labels_dict = json.loads(labels)
            preview_state["metadata"]["labels"] = labels_dict
        
        # 比较变化
        changes = service.compare_cluster_role_binding_changes(current_state, preview_state)
        
        return json.dumps({
            "success": True,
            "resource": f"clusterrolebinding/{name}",
            "current_state": current_state,
            "preview_state": preview_state,
            "changes": changes
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


# ============================================================================
# 通用资源变化获取工具
# ============================================================================

@mcp.tool()
async def get_resource_changes(resource_type: str, resource_name: str, 
                             namespace: str = "default") -> str:
    """获取资源的变化对比
    
    Args:
        resource_type: 资源类型
        resource_name: 资源名称
        namespace: 命名空间
    """
    try:
        service = KubernetesAdvancedService()
        
        # 获取当前状态
        current_state = await service.get_resource_before_operation(resource_type, resource_name, namespace)
        
        if "error" in current_state:
            return json.dumps({
                "success": False,
                "error": current_state["error"]
            }, ensure_ascii=False, indent=2)
        
        # 根据资源类型生成变化摘要
        changes_summary = {}
        
        if resource_type == "deployment":
            replicas = current_state.get("spec", {}).get("replicas", 0)
            containers = current_state.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
            image = containers[0].get("image", "") if containers else ""
            
            changes_summary = {
                "replicas": replicas,
                "image": image,
                "labels": current_state.get("metadata", {}).get("labels", {}),
                "annotations": current_state.get("metadata", {}).get("annotations", {})
            }
        
        elif resource_type == "persistentvolumeclaim":
            size = current_state.get("spec", {}).get("resources", {}).get("requests", {}).get("storage", "")
            access_modes = current_state.get("spec", {}).get("access_modes", [])
            storage_class = current_state.get("spec", {}).get("storage_class_name", "")
            
            changes_summary = {
                "size": size,
                "access_modes": access_modes,
                "storage_class": storage_class,
                "labels": current_state.get("metadata", {}).get("labels", {}),
                "annotations": current_state.get("metadata", {}).get("annotations", {})
            }
        
        elif resource_type == "service":
            service_type = current_state.get("spec", {}).get("type", "")
            ports = current_state.get("spec", {}).get("ports", [])
            selector = current_state.get("spec", {}).get("selector", {})
            
            changes_summary = {
                "service_type": service_type,
                "ports": ports,
                "selector": selector,
                "labels": current_state.get("metadata", {}).get("labels", {}),
                "annotations": current_state.get("metadata", {}).get("annotations", {})
            }
        
        elif resource_type == "configmap":
            data = current_state.get("data", {})
            binary_data = current_state.get("binaryData", {})
            
            changes_summary = {
                "data": data,
                "binary_data": binary_data,
                "labels": current_state.get("metadata", {}).get("labels", {}),
                "annotations": current_state.get("metadata", {}).get("annotations", {})
            }
            
        elif resource_type == "secret":
            # 对于Secret，我们只显示键名，不显示具体值
            data = current_state.get("data", {})
            data_keys = list(data.keys()) if data else []
            secret_type = current_state.get("type", "")
            
            changes_summary = {
                "data_keys": data_keys,
                "type": secret_type,
                "labels": current_state.get("metadata", {}).get("labels", {}),
                "annotations": current_state.get("metadata", {}).get("annotations", {})
            }
            
        elif resource_type == "ingress":
            rules = current_state.get("spec", {}).get("rules", [])
            tls = current_state.get("spec", {}).get("tls", [])
            ingress_class = current_state.get("spec", {}).get("ingressClassName", "")
            
            changes_summary = {
                "rules": rules,
                "tls": tls,
                "ingress_class": ingress_class,
                "labels": current_state.get("metadata", {}).get("labels", {}),
                "annotations": current_state.get("metadata", {}).get("annotations", {})
            }
            
        elif resource_type == "job":
            parallelism = current_state.get("spec", {}).get("parallelism")
            completions = current_state.get("spec", {}).get("completions")
            backoff_limit = current_state.get("spec", {}).get("backoffLimit")
            
            changes_summary = {
                "parallelism": parallelism,
                "completions": completions,
                "backoff_limit": backoff_limit,
                "labels": current_state.get("metadata", {}).get("labels", {}),
                "annotations": current_state.get("metadata", {}).get("annotations", {})
            }
        
        return json.dumps({
            "success": True,
            "resource_type": resource_type,
            "resource_name": resource_name,
            "namespace": namespace,
            "current_state": current_state,
            "changes_summary": changes_summary
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2) 