"""
Kubernetes 工具集合
提供 Pod、Deployment、Service、Node、Namespace、ConfigMap、Secret、Event 管理功能
"""

import json
import os
from typing import Dict, List
from services.k8s_api_service import KubernetesAPIService

# 导入共享的MCP实例
from . import mcp


def _resolve_namespace(namespace: str = None) -> str:
    """
    解析命名空间，如果没有指定则使用默认集群的命名空间
    
    Args:
        namespace: 指定的命名空间
        
    Returns:
        解析后的命名空间
    """
    if namespace is not None:
        return namespace
    
    try:
        from utils.cluster_config import ClusterConfigManager
        cluster_manager = ClusterConfigManager()
        default_cluster = cluster_manager.get_default_cluster()
        return default_cluster.namespace if default_cluster else "default"
    except Exception:
        return "default"

# ========================== Pod Tools ==========================

@mcp.tool()
async def list_pods(namespace: str = None, kubeconfig_path: str = None, 
              label_selector: str = None) -> str:
    """
    列出指定命名空间中的Pod
    
    Args:
        namespace: Kubernetes命名空间，默认使用默认集群的命名空间
        kubeconfig_path: kubeconfig文件路径
        label_selector: 标签选择器
    
    Returns:
        包含Pod列表的结果
    """
    try:
        # 解析命名空间
        namespace = _resolve_namespace(namespace)
        
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        pods = await k8s_service.list_pods(
            namespace=namespace,
            label_selector=label_selector
        )
        
        result = {
            "success": True,
            "pods": pods,
            "count": len(pods),
            "namespace": namespace
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def describe_pod(name: str, namespace: str = "default", kubeconfig_path: str = None) -> str:
    """
    获取Pod的详细信息
    
    Args:
        name: Pod名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        包含Pod详细信息的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        pod_details = await k8s_service.get_pod(name=name, namespace=namespace)
        
        result = {
            "success": True,
            "pod": pod_details
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def get_pod_logs(name: str, namespace: str = "default", lines: int = 100, 
                 container: str = None, kubeconfig_path: str = None) -> str:
    """
    获取Pod的日志
    
    Args:
        name: Pod名称
        namespace: Kubernetes命名空间，默认为default
        lines: 显示的日志行数，默认100行
        container: 容器名称（可选）
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        包含Pod日志的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        logs = await k8s_service.get_pod_logs(
            name=name,
            namespace=namespace,
            container=container,
            lines=lines
        )
        
        result = {
            "success": True,
            "logs": logs,
            "pod": name,
            "namespace": namespace,
            "container": container,
            "lines": lines
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def delete_pod(name: str, namespace: str = "default", kubeconfig_path: str = None,
               grace_period_seconds: int = None) -> str:
    """
    删除Pod
    
    Args:
        name: Pod名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
        grace_period_seconds: 优雅关闭时间（秒）
    
    Returns:
        删除结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        delete_result = await k8s_service.delete_pod(
            name=name,
            namespace=namespace,
            grace_period_seconds=grace_period_seconds
        )
        
        result = {
            "success": True,
            "message": f"Pod '{name}' 删除成功",
            "result": delete_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

# ========================== Deployment Tools ==========================

@mcp.tool()
async def list_deployments(namespace: str = None, kubeconfig_path: str = None,
                    label_selector: str = None) -> str:
    """
    列出指定命名空间中的Deployment
    
    Args:
        namespace: Kubernetes命名空间，默认使用默认集群的命名空间
        kubeconfig_path: kubeconfig文件路径
        label_selector: 标签选择器
    
    Returns:
        包含Deployment列表的结果
    """
    try:
        # 解析命名空间
        namespace = _resolve_namespace(namespace)
        
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        deployments = await k8s_service.list_deployments(
            namespace=namespace,
            label_selector=label_selector
        )
        
        result = {
            "success": True,
            "deployments": deployments,
            "count": len(deployments),
            "namespace": namespace
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def describe_deployment(name: str, namespace: str = "default", kubeconfig_path: str = None) -> str:
    """
    获取Deployment的详细信息
    
    Args:
        name: Deployment名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        包含Deployment详细信息的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        deployment_details = await k8s_service.get_deployment(name=name, namespace=namespace)
        
        result = {
            "success": True,
            "deployment": deployment_details
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def create_deployment(name: str, image: str, namespace: str = "default", 
                     replicas: int = 1, kubeconfig_path: str = None,
                     labels: dict = None, env_vars: dict = None,
                     ports: list = None, resources: dict = None) -> str:
    """
    创建Deployment
    
    Args:
        name: Deployment名称
        image: 容器镜像
        namespace: Kubernetes命名空间，默认为default
        replicas: 副本数量，默认为1
        kubeconfig_path: kubeconfig文件路径
        labels: 标签字典
        env_vars: 环境变量字典
        ports: 端口列表，格式如 [{"name": "http", "containerPort": 80}]
        resources: 资源配置，格式如 {"requests": {"cpu": "100m", "memory": "128Mi"}}
    
    Returns:
        创建结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        deployment_result = await k8s_service.create_deployment(
            name=name,
            image=image,
            namespace=namespace,
            replicas=replicas,
            labels=labels,
            env_vars=env_vars,
            ports=ports,
            resources=resources
        )
        
        result = {
            "success": True,
            "message": f"Deployment '{name}' 创建成功",
            "result": deployment_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def update_deployment(name: str, namespace: str = "default", 
                     kubeconfig_path: str = None, image: str = None,
                     replicas: int = None, labels: dict = None,
                     env_vars: dict = None, resources: dict = None) -> str:
    """
    更新Deployment
    
    Args:
        name: Deployment名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
        image: 新的容器镜像
        replicas: 新的副本数量
        labels: 新的标签字典
        env_vars: 新的环境变量字典
        resources: 新的资源配置，格式如 {"requests": {"cpu": "100m", "memory": "128Mi"}}
    
    Returns:
        更新结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        update_result = await k8s_service.update_deployment(
            name=name,
            namespace=namespace,
            image=image,
            replicas=replicas,
            labels=labels,
            env_vars=env_vars,
            resources=resources
        )
        
        result = {
            "success": True,
            "message": f"Deployment '{name}' 更新成功",
            "result": update_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def delete_deployment(name: str, namespace: str = "default", kubeconfig_path: str = None,
                          grace_period_seconds: int = None) -> str:
    """
    删除Deployment
    
    Args:
        name: Deployment名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
        grace_period_seconds: 优雅关闭时间（秒）
    
    Returns:
        删除结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        delete_result = await k8s_service.delete_deployment(name=name, namespace=namespace, grace_period_seconds=grace_period_seconds)
        
        result = {
            "success": True,
            "message": f"Deployment '{name}' 删除成功",
            "result": delete_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

# ========================== StatefulSet Tools ==========================

@mcp.tool()
async def list_statefulsets(namespace: str = None, kubeconfig_path: str = None,
                      label_selector: str = None) -> str:
    """
    列出指定命名空间中的StatefulSet
    
    Args:
        namespace: Kubernetes命名空间，默认使用默认集群的命名空间
        kubeconfig_path: kubeconfig文件路径
        label_selector: 标签选择器
    
    Returns:
        包含StatefulSet列表的结果
    """
    try:
        namespace = _resolve_namespace(namespace)
        
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        statefulsets = await k8s_service.list_statefulsets(
            namespace=namespace,
            label_selector=label_selector
        )
        
        result = {
            "success": True,
            "statefulsets": statefulsets,
            "count": len(statefulsets),
            "namespace": namespace
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def describe_statefulset(name: str, namespace: str = "default", kubeconfig_path: str = None) -> str:
    """
    获取StatefulSet的详细信息
    
    Args:
        name: StatefulSet名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        包含StatefulSet详细信息的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        statefulset_details = await k8s_service.get_statefulset(name=name, namespace=namespace)
        
        result = {
            "success": True,
            "statefulset": statefulset_details
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def create_statefulset(name: str, image: str, namespace: str = "default",
                      replicas: int = 1, kubeconfig_path: str = None,
                      labels: dict = None, env_vars: dict = None,
                      ports: list = None, resources: dict = None,
                      volume_claims: list = None) -> str:
    """
    创建StatefulSet
    
    Args:
        name: StatefulSet名称
        image: 容器镜像
        namespace: Kubernetes命名空间，默认为default
        replicas: 副本数量，默认为1
        kubeconfig_path: kubeconfig文件路径
        labels: 标签字典
        env_vars: 环境变量字典
        ports: 端口列表
        resources: 资源配置
        volume_claims: 卷声明模板列表
    
    Returns:
        创建结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        statefulset_result = await k8s_service.create_statefulset(
            name=name,
            image=image,
            namespace=namespace,
            replicas=replicas,
            labels=labels,
            env_vars=env_vars,
            ports=ports,
            resources=resources,
            volume_claims=volume_claims
        )
        
        result = {
            "success": True,
            "message": f"StatefulSet '{name}' 创建成功",
            "result": statefulset_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def update_statefulset(name: str, namespace: str = "default", kubeconfig_path: str = None,
                      image: str = None, replicas: int = None, 
                      labels: dict = None, env_vars: dict = None) -> str:
    """
    更新StatefulSet
    
    Args:
        name: StatefulSet名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
        image: 新的容器镜像
        replicas: 新的副本数量
        labels: 新的标签字典
        env_vars: 新的环境变量字典
    
    Returns:
        更新结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        update_result = await k8s_service.update_statefulset(
            name=name,
            namespace=namespace,
            image=image,
            replicas=replicas,
            labels=labels,
            env_vars=env_vars
        )
        
        result = {
            "success": True,
            "message": f"StatefulSet '{name}' 更新成功",
            "result": update_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def delete_statefulset(name: str, namespace: str = "default", kubeconfig_path: str = None,
                           grace_period_seconds: int = None) -> str:
    """
    删除StatefulSet
    
    Args:
        name: StatefulSet名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
        grace_period_seconds: 优雅关闭时间（秒）
    
    Returns:
        删除结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        delete_result = await k8s_service.delete_statefulset(name=name, namespace=namespace, grace_period_seconds=grace_period_seconds)
        
        result = {
            "success": True,
            "message": f"StatefulSet '{name}' 删除成功",
            "result": delete_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)


# ========================== DaemonSet Tools ==========================

@mcp.tool()
async def list_daemonsets(namespace: str = None, kubeconfig_path: str = None,
                    label_selector: str = None) -> str:
    """
    列出指定命名空间中的DaemonSet
    
    Args:
        namespace: Kubernetes命名空间，默认使用默认集群的命名空间
        kubeconfig_path: kubeconfig文件路径
        label_selector: 标签选择器
    
    Returns:
        包含DaemonSet列表的结果
    """
    try:
        namespace = _resolve_namespace(namespace)
        
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        daemonsets = await k8s_service.list_daemonsets(
            namespace=namespace,
            label_selector=label_selector
        )
        
        result = {
            "success": True,
            "daemonsets": daemonsets,
            "count": len(daemonsets),
            "namespace": namespace
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def describe_daemonset(name: str, namespace: str = "default", kubeconfig_path: str = None) -> str:
    """
    获取DaemonSet的详细信息
    
    Args:
        name: DaemonSet名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        包含DaemonSet详细信息的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        daemonset_details = await k8s_service.get_daemonset(name=name, namespace=namespace)
        
        result = {
            "success": True,
            "daemonset": daemonset_details
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def create_daemonset(name: str, image: str, namespace: str = "default",
                    kubeconfig_path: str = None, labels: dict = None,
                    env_vars: dict = None, ports: list = None,
                    resources: dict = None, volumes: list = None) -> str:
    """
    创建DaemonSet
    
    Args:
        name: DaemonSet名称
        image: 容器镜像
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
        labels: 标签字典
        env_vars: 环境变量字典
        ports: 端口列表
        resources: 资源配置
        volumes: 卷配置列表
    
    Returns:
        创建结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        daemonset_result = await k8s_service.create_daemonset(
            name=name,
            image=image,
            namespace=namespace,
            labels=labels,
            env_vars=env_vars,
            ports=ports,
            resources=resources,
            volumes=volumes
        )
        
        result = {
            "success": True,
            "message": f"DaemonSet '{name}' 创建成功",
            "result": daemonset_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def update_daemonset(name: str, namespace: str = "default", kubeconfig_path: str = None,
                    image: str = None, labels: dict = None, env_vars: dict = None) -> str:
    """
    更新DaemonSet
    
    Args:
        name: DaemonSet名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
        image: 新的容器镜像
        labels: 新的标签字典
        env_vars: 新的环境变量字典
    
    Returns:
        更新结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        update_result = await k8s_service.update_daemonset(
            name=name,
            namespace=namespace,
            image=image,
            labels=labels,
            env_vars=env_vars
        )
        
        result = {
            "success": True,
            "message": f"DaemonSet '{name}' 更新成功",
            "result": update_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def delete_daemonset(name: str, namespace: str = "default", kubeconfig_path: str = None) -> str:
    """
    删除DaemonSet
    
    Args:
        name: DaemonSet名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        删除结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        delete_result = await k8s_service.delete_daemonset(name=name, namespace=namespace)
        
        result = {
            "success": True,
            "message": f"DaemonSet '{name}' 删除成功",
            "result": delete_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

# ========================== Service Tools ==========================

@mcp.tool()
async def list_services(namespace: str = "default", kubeconfig_path: str = None,
                 label_selector: str = None) -> str:
    """
    列出指定命名空间中的Service
    
    Args:
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
        label_selector: 标签选择器
    
    Returns:
        包含Service列表的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        services = await k8s_service.list_services(
            namespace=namespace,
            label_selector=label_selector
        )
        
        result = {
            "success": True,
            "services": services,
            "count": len(services),
            "namespace": namespace
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def describe_service(name: str, namespace: str = "default", kubeconfig_path: str = None) -> str:
    """
    获取Service的详细信息
        
        Args:
        name: Service名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
            
        Returns:
        包含Service详细信息的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        service_details = await k8s_service.get_service(name=name, namespace=namespace)
        
        result = {
            "success": True,
            "service": service_details
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def create_service(name: str, selector: dict, ports: list, namespace: str = "default",
                  service_type: str = "ClusterIP", kubeconfig_path: str = None) -> str:
    """
    创建Service
    
    Args:
        name: Service名称
        selector: 选择器字典，如 {"app": "nginx"}
        ports: 端口列表，格式如 [{"name": "http", "port": 80, "targetPort": 8080}]
        namespace: Kubernetes命名空间，默认为default
        service_type: 服务类型，默认为ClusterIP
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        创建结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        service_result = await k8s_service.create_service(
            name=name,
            selector=selector,
            ports=ports,
            namespace=namespace,
            service_type=service_type
        )
        
        result = {
            "success": True,
            "message": f"Service '{name}' 创建成功",
            "result": service_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def update_service(name: str, namespace: str = "default", kubeconfig_path: str = None,
                  service_type: str = None, ports: str = None, selector: str = None,
                  labels: str = None, annotations: str = None) -> str:
    """
    更新Service
    
    Args:
        name: Service名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
        service_type: 服务类型 (ClusterIP, NodePort, LoadBalancer)
        ports: JSON格式的端口列表
        selector: JSON格式的选择器
        labels: JSON格式的标签
        annotations: JSON格式的注解
    
    Returns:
        包含更新结果的JSON字符串
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        # 解析JSON参数
        ports_list = json.loads(ports) if ports else None
        selector_dict = json.loads(selector) if selector else None
        labels_dict = json.loads(labels) if labels else None
        annotations_dict = json.loads(annotations) if annotations else None
        
        result = await k8s_service.update_service(
            name=name,
            namespace=namespace,
            service_type=service_type,
            ports=ports_list,
            selector=selector_dict,
            labels=labels_dict,
            annotations=annotations_dict
        )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def delete_service(name: str, namespace: str = "default", kubeconfig_path: str = None) -> str:
    """
    删除Service
    
    Args:
        name: Service名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        删除结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        delete_result = await k8s_service.delete_service(name=name, namespace=namespace)
        
        result = {
            "success": True,
            "message": f"Service '{name}' 删除成功",
            "result": delete_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

# ========================== ConfigMap Tools ==========================

@mcp.tool()
async def list_configmaps(namespace: str = "default", kubeconfig_path: str = None,
                   label_selector: str = None) -> str:
    """
    列出指定命名空间中的ConfigMap
        
        Args:
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
        label_selector: 标签选择器
            
        Returns:
        包含ConfigMap列表的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        configmaps = await k8s_service.list_configmaps(
            namespace=namespace,
            label_selector=label_selector
        )
        
        result = {
            "success": True,
            "configmaps": configmaps,
            "count": len(configmaps),
            "namespace": namespace
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def describe_configmap(name: str, namespace: str = "default", kubeconfig_path: str = None) -> str:
    """
    获取ConfigMap的详细信息
    
    Args:
        name: ConfigMap名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        包含ConfigMap详细信息的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        configmap_details = await k8s_service.get_configmap(name=name, namespace=namespace)
        
        result = {
            "success": True,
            "configmap": configmap_details
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def create_configmap(name: str, data: dict, namespace: str = "default",
                     kubeconfig_path: str = None, labels: dict = None) -> str:
    """
    创建ConfigMap
        
        Args:
        name: ConfigMap名称
        data: 数据字典
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
        labels: 标签字典
    
    Returns:
        创建结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        configmap_result = await k8s_service.create_configmap(
            name=name,
            data=data,
            namespace=namespace,
            labels=labels
        )
        
        result = {
            "success": True,
            "message": f"ConfigMap '{name}' 创建成功",
            "result": configmap_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def update_configmap(name: str, data: dict, namespace: str = "default",
                     kubeconfig_path: str = None, labels: dict = None) -> str:
    """
    更新ConfigMap
    
    Args:
        name: ConfigMap名称
        data: 新的数据字典
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
        labels: 新的标签字典
    
    Returns:
        更新结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        update_result = await k8s_service.update_configmap(
            name=name,
            data=data,
            namespace=namespace,
            labels=labels
        )
        
        result = {
            "success": True,
            "message": f"ConfigMap '{name}' 更新成功",
            "result": update_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def delete_configmap(name: str, namespace: str = "default", kubeconfig_path: str = None) -> str:
    """
    删除ConfigMap
    
    Args:
        name: ConfigMap名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        删除结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        delete_result = await k8s_service.delete_configmap(name=name, namespace=namespace)
        
        result = {
            "success": True,
            "message": f"ConfigMap '{name}' 删除成功",
            "result": delete_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

# ========================== Secret Tools ==========================

@mcp.tool()
async def list_secrets(namespace: str = "default", kubeconfig_path: str = None,
                label_selector: str = None) -> str:
    """
    列出指定命名空间中的Secret
    
    Args:
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
        label_selector: 标签选择器
            
        Returns:
        包含Secret列表的结果（不显示敏感数据）
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        secrets = await k8s_service.list_secrets(
            namespace=namespace,
            label_selector=label_selector
        )
        
        result = {
            "success": True,
            "secrets": secrets,
            "count": len(secrets),
            "namespace": namespace
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def get_secret(name: str, namespace: str = "default", kubeconfig_path: str = None) -> str:
    """
    获取Secret详细信息
    
    Args:
        name: Secret名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        Secret详细信息
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        secret_details = await k8s_service.get_secret(name=name, namespace=namespace)
        
        result = {
            "success": True,
            "secret": secret_details
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def create_secret(name: str, data: dict, namespace: str = "default",
                  secret_type: str = "Opaque", kubeconfig_path: str = None,
                  labels: dict = None) -> str:
    """
    创建Secret
    
    Args:
        name: Secret名称
        data: 数据字典（将被base64编码）
        namespace: Kubernetes命名空间，默认为default
        secret_type: Secret类型，默认为Opaque
        kubeconfig_path: kubeconfig文件路径
        labels: 标签字典
    
    Returns:
        创建结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        secret_result = await k8s_service.create_secret(
            name=name,
            data=data,
            namespace=namespace,
            secret_type=secret_type,
            labels=labels
        )
        
        result = {
            "success": True,
            "message": f"Secret '{name}' 创建成功",
            "result": secret_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def update_secret(name: str, data: dict, namespace: str = "default",
                  kubeconfig_path: str = None, labels: dict = None) -> str:
    """
    更新Secret
        
        Args:
        name: Secret名称
        data: 新的数据字典（将被base64编码）
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
        labels: 新的标签字典
    
    Returns:
        更新结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        update_result = await k8s_service.update_secret(
            name=name,
            data=data,
            namespace=namespace,
            labels=labels
        )
        
        result = {
            "success": True,
            "message": f"Secret '{name}' 更新成功",
            "result": update_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def delete_secret(name: str, namespace: str = "default", kubeconfig_path: str = None) -> str:
    """
    删除Secret
    
    Args:
        name: Secret名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
            
        Returns:
        删除结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        delete_result = await k8s_service.delete_secret(name=name, namespace=namespace)
        
        result = {
            "success": True,
            "message": f"Secret '{name}' 删除成功",
            "result": delete_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

# ========================== Job Tools ==========================

@mcp.tool()
async def list_jobs(namespace: str = None, kubeconfig_path: str = None,
                   label_selector: str = None) -> str:
    """
    列出指定命名空间中的Job
    
    Args:
        namespace: Kubernetes命名空间，默认使用默认集群的命名空间
        kubeconfig_path: kubeconfig文件路径
        label_selector: 标签选择器
    
    Returns:
        包含Job列表的结果
    """
    try:
        namespace = _resolve_namespace(namespace)
        
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        jobs = await k8s_service.list_jobs(
            namespace=namespace,
            label_selector=label_selector
        )
        
        result = {
            "success": True,
            "jobs": jobs,
            "count": len(jobs),
            "namespace": namespace
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def describe_job(name: str, namespace: str = "default", kubeconfig_path: str = None) -> str:
    """
    获取Job的详细信息
    
    Args:
        name: Job名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        包含Job详细信息的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        job_details = await k8s_service.get_job(name=name, namespace=namespace)
        
        result = {
            "success": True,
            "job": job_details
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def create_job(name: str, image: str, namespace: str = "default",
               command: list = None, args: list = None,
               kubeconfig_path: str = None, labels: dict = None,
               env_vars: dict = None, resources: dict = None,
               restart_policy: str = "Never", backoff_limit: int = 6) -> str:
    """
    创建Job
    
    Args:
        name: Job名称
        image: 容器镜像
        namespace: Kubernetes命名空间，默认为default
        command: 容器命令列表
        args: 容器参数列表
        kubeconfig_path: kubeconfig文件路径
        labels: 标签字典
        env_vars: 环境变量字典
        resources: 资源配置
        restart_policy: 重启策略，默认为Never
        backoff_limit: 重试次数限制，默认为6
    
    Returns:
        创建结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        job_result = await k8s_service.create_job(
            name=name,
            image=image,
            namespace=namespace,
            command=command,
            args=args,
            labels=labels,
            env_vars=env_vars,
            resources=resources,
            restart_policy=restart_policy,
            backoff_limit=backoff_limit
        )
        
        result = {
            "success": True,
            "message": f"Job '{name}' 创建成功",
            "result": job_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def delete_job(name: str, namespace: str = "default", kubeconfig_path: str = None) -> str:
    """
    删除Job
    
    Args:
        name: Job名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        删除结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        delete_result = await k8s_service.delete_job(name=name, namespace=namespace)
        
        result = {
            "success": True,
            "message": f"Job '{name}' 删除成功",
            "result": delete_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

# ========================== CronJob Tools ==========================

@mcp.tool()
async def list_cronjobs(namespace: str = None, kubeconfig_path: str = None,
                  label_selector: str = None) -> str:
    """
    列出指定命名空间中的CronJob
    
    Args:
        namespace: Kubernetes命名空间，默认使用默认集群的命名空间
        kubeconfig_path: kubeconfig文件路径
        label_selector: 标签选择器
    
    Returns:
        包含CronJob列表的结果
    """
    try:
        namespace = _resolve_namespace(namespace)
        
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        cronjobs = await k8s_service.list_cronjobs(
            namespace=namespace,
            label_selector=label_selector
        )
        
        result = {
            "success": True,
            "cronjobs": cronjobs,
            "count": len(cronjobs),
            "namespace": namespace
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def describe_cronjob(name: str, namespace: str = "default", kubeconfig_path: str = None) -> str:
    """
    获取CronJob的详细信息
        
        Args:
        name: CronJob名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
            
        Returns:
        包含CronJob详细信息的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        cronjob_details = await k8s_service.get_cronjob(name=name, namespace=namespace)
        
        result = {
            "success": True,
            "cronjob": cronjob_details
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def create_cronjob(name: str, image: str, schedule: str, namespace: str = "default",
                   command: list = None, args: list = None,
                   kubeconfig_path: str = None, labels: dict = None,
                   env_vars: dict = None, resources: dict = None,
                   restart_policy: str = "Never", suspend: bool = False) -> str:
    """
    创建CronJob
    
    Args:
        name: CronJob名称
        image: 容器镜像
        schedule: Cron调度表达式
        namespace: Kubernetes命名空间，默认为default
        command: 容器命令列表
        args: 容器参数列表
        kubeconfig_path: kubeconfig文件路径
        labels: 标签字典
        env_vars: 环境变量字典
        resources: 资源配置
        restart_policy: 重启策略，默认为Never
        suspend: 是否暂停，默认为False
    
    Returns:
        创建结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        cronjob_result = await k8s_service.create_cronjob(
            name=name,
            image=image,
            schedule=schedule,
            namespace=namespace,
            command=command,
            args=args,
            labels=labels,
            env_vars=env_vars,
            resources=resources,
            restart_policy=restart_policy,
            suspend=suspend
        )
        
        result = {
            "success": True,
            "message": f"CronJob '{name}' 创建成功",
            "result": cronjob_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def update_cronjob(name: str, namespace: str = "default", kubeconfig_path: str = None,
                   schedule: str = None, suspend: bool = None,
                   image: str = None, labels: dict = None) -> str:
    """
    更新CronJob
    
    Args:
        name: CronJob名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
        schedule: 新的Cron调度表达式
        suspend: 是否暂停
        image: 新的容器镜像
        labels: 新的标签字典
    
    Returns:
        更新结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        update_result = await k8s_service.update_cronjob(
            name=name,
            namespace=namespace,
            schedule=schedule,
            suspend=suspend,
            image=image,
            labels=labels
        )
        
        result = {
            "success": True,
            "message": f"CronJob '{name}' 更新成功",
            "result": update_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def delete_cronjob(name: str, namespace: str = "default", kubeconfig_path: str = None) -> str:
    """
    删除CronJob
    
    Args:
        name: CronJob名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        删除结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        delete_result = await k8s_service.delete_cronjob(name=name, namespace=namespace)
        
        result = {
            "success": True,
            "message": f"CronJob '{name}' 删除成功",
            "result": delete_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

# ========================== Ingress Tools ==========================

@mcp.tool()
async def list_ingresses(namespace: str = None, kubeconfig_path: str = None,
                label_selector: str = None) -> str:
    """
    列出指定命名空间中的Ingress
    
    Args:
        namespace: Kubernetes命名空间，默认使用默认集群的命名空间
        kubeconfig_path: kubeconfig文件路径
        label_selector: 标签选择器
    
    Returns:
        包含Ingress列表的结果
    """
    try:
        namespace = _resolve_namespace(namespace)
        
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        ingresses = await k8s_service.list_ingresses(
            namespace=namespace,
            label_selector=label_selector
        )
        
        result = {
            "success": True,
            "ingresses": ingresses,
            "count": len(ingresses),
            "namespace": namespace
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def describe_ingress(name: str, namespace: str = "default", kubeconfig_path: str = None) -> str:
    """
    获取Ingress的详细信息
    
    Args:
        name: Ingress名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        包含Ingress详细信息的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        ingress_details = await k8s_service.get_ingress(name=name, namespace=namespace)
        
        result = {
            "success": True,
            "ingress": ingress_details
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def create_ingress(name: str, rules: list, namespace: str = "default",
                   kubeconfig_path: str = None, labels: dict = None,
                   annotations: dict = None, ingress_class: str = None, tls: list = None) -> str:
    """
    创建Ingress
    
    Args:
        name: Ingress名称
        rules: 规则列表，格式如 [{"host": "example.com", "paths": [{"path": "/", "service": "web", "port": 80}]}]
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
        labels: 标签字典
        annotations: 注解字典
        ingress_class: Ingress类名
        tls: TLS 配置
    
    Returns:
        创建结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        # 只传递 create_ingress 支持的参数，并将 ingress_class 映射为 ingress_class_name
        ingress_kwargs = {
            "name": name,
            "rules": rules,
            "namespace": namespace,
            "labels": labels,
            "annotations": annotations,
            "tls": tls
        }
        if ingress_class:
            ingress_kwargs["ingress_class_name"] = ingress_class
        ingress_result = await k8s_service.create_ingress(**ingress_kwargs)
        result = {
            "success": True,
            "message": f"Ingress '{name}' 创建成功",
            "result": ingress_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def update_ingress(name: str, namespace: str = "default", kubeconfig_path: str = None,
                   rules: list = None, labels: dict = None,
                   annotations: dict = None, tls: list = None, ingress_class: str = None) -> str:
    """
    更新Ingress
    
    Args:
        name: Ingress名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
        rules: 新的规则列表
        labels: 新的标签字典
        annotations: 新的注解字典
        tls: 新的TLS配置
        ingress_class: 新的IngressClass
    
    Returns:
        更新结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        update_kwargs = {
            "name": name,
            "namespace": namespace,
            "rules": rules,
            "labels": labels,
            "annotations": annotations,
        }
        if tls is not None:
            update_kwargs["tls"] = tls
        if ingress_class is not None:
            update_kwargs["ingress_class_name"] = ingress_class
        update_result = await k8s_service.update_ingress(**update_kwargs)
        result = {
            "success": True,
            "message": f"Ingress '{name}' 更新成功",
            "result": update_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def delete_ingress(name: str, namespace: str = "default", kubeconfig_path: str = None) -> str:
    """
    删除Ingress
    
    Args:
        name: Ingress名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        删除结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        delete_result = await k8s_service.delete_ingress(name=name, namespace=namespace)
        
        result = {
            "success": True,
            "message": f"Ingress '{name}' 删除成功",
            "result": delete_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2) 

# ========================== StorageClass Tools ==========================

@mcp.tool()
async def list_storageclasses(kubeconfig_path: str = None, label_selector: str = None) -> str:
    """
    列出集群中的StorageClass
    
    Args:
        kubeconfig_path: kubeconfig文件路径
        label_selector: 标签选择器
    
    Returns:
        包含StorageClass列表的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        storageclasses = await k8s_service.list_storageclasses(label_selector=label_selector)
        
        result = {
            "success": True,
            "storageclasses": storageclasses,
            "count": len(storageclasses)
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def describe_storageclass(name: str, kubeconfig_path: str = None) -> str:
    """
    获取StorageClass的详细信息
    
    Args:
        name: StorageClass名称
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        包含StorageClass详细信息的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        storageclass_details = await k8s_service.get_storageclass(name=name)
        
        result = {
            "success": True,
            "storageclass": storageclass_details
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def create_storageclass(name: str, provisioner: str, kubeconfig_path: str = None,
                        parameters: dict = None, reclaim_policy: str = "Delete",
                        volume_binding_mode: str = "Immediate",
                        allow_volume_expansion: bool = False,
                        labels: dict = None, annotations: dict = None) -> str:
    """
    创建StorageClass
    
    Args:
        name: StorageClass名称
        provisioner: 存储提供者
        kubeconfig_path: kubeconfig文件路径
        parameters: 存储参数字典
        reclaim_policy: 回收策略，默认为Delete
        volume_binding_mode: 卷绑定模式，默认为Immediate
        allow_volume_expansion: 是否允许卷扩容，默认为False
        labels: 标签字典
        annotations: 注解字典
    
    Returns:
        创建结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        storageclass_result = await k8s_service.create_storageclass(
            name=name,
            provisioner=provisioner,
            parameters=parameters,
            reclaim_policy=reclaim_policy,
            volume_binding_mode=volume_binding_mode,
            allow_volume_expansion=allow_volume_expansion,
            labels=labels,
            annotations=annotations
        )
        
        result = {
            "success": True,
            "message": f"StorageClass '{name}' 创建成功",
            "result": storageclass_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def update_storageclass(name: str, kubeconfig_path: str = None,
                        allow_volume_expansion: bool = None,
                        parameters: dict = None, labels: dict = None,
                        annotations: dict = None) -> str:
    """
    更新StorageClass（仅允许更新 allow_volume_expansion、parameters、labels、annotations）
    
    Args:
        name: StorageClass名称
        kubeconfig_path: kubeconfig文件路径
        allow_volume_expansion: 是否允许卷扩容
        parameters: 新的存储参数字典
        labels: 新的标签字典
        annotations: 新的注解字典
    
    Returns:
        更新结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        update_kwargs = {
            "name": name,
            "allow_volume_expansion": allow_volume_expansion,
            "parameters": parameters,
            "labels": labels,
            "annotations": annotations
        }
        # 只保留可更新字段，且值不为 None
        update_kwargs = {k: v for k, v in update_kwargs.items() if v is not None}
        update_result = await k8s_service.update_storageclass(**update_kwargs)
        result = {
            "success": True,
            "message": f"StorageClass '{name}' 更新成功",
            "result": update_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def delete_storageclass(name: str, kubeconfig_path: str = None) -> str:
    """
    删除StorageClass
    
    Args:
        name: StorageClass名称
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        删除结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        delete_result = await k8s_service.delete_storageclass(name=name)
        
        result = {
            "success": True,
            "message": f"StorageClass '{name}' 删除成功",
            "result": delete_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

# ========================== PersistentVolume Tools ==========================

@mcp.tool()
async def list_persistentvolumes(kubeconfig_path: str = None, label_selector: str = None) -> str:
    """
    列出集群中的PersistentVolume
    
    Args:
        kubeconfig_path: kubeconfig文件路径
        label_selector: 标签选择器
    
    Returns:
        包含PersistentVolume列表的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        persistentvolumes = await k8s_service.list_persistentvolumes(label_selector=label_selector)
        
        result = {
            "success": True,
            "persistentvolumes": persistentvolumes,
            "count": len(persistentvolumes)
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def describe_persistentvolume(name: str, kubeconfig_path: str = None) -> str:
    """
    获取PersistentVolume的详细信息
    
    Args:
        name: PersistentVolume名称
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        包含PersistentVolume详细信息的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        pv_details = await k8s_service.get_persistentvolume(name=name)
        
        result = {
            "success": True,
            "persistentvolume": pv_details
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def create_persistentvolume(name: str, capacity: str, access_modes: list,
                            kubeconfig_path: str = None, storage_class: str = None,
                            reclaim_policy: str = "Retain", volume_mode: str = "Filesystem",
                            labels: dict = None, annotations: dict = None,
                            host_path: str = None, nfs: dict = None, csi: dict = None) -> str:
    """
    创建PersistentVolume
    
    Args:
        name: PersistentVolume名称
        capacity: 存储容量，如 "10Gi"
        access_modes: 访问模式列表，如 ["ReadWriteOnce"]
        kubeconfig_path: kubeconfig文件路径
        storage_class: 存储类名称
        reclaim_policy: 回收策略，默认为Retain
        volume_mode: 卷模式，默认为Filesystem
        labels: 标签字典
        annotations: 注解字典
        host_path: 主机路径（hostPath 类型 PV）
        nfs: NFS 配置字典（如 {"server": "1.2.3.4", "path": "/data", "read_only": False}）
        csi: CSI 卷配置字典（如 {"driver": "rbd.csi.ceph.com", "fsType": "ext4", ...}）
        
        三者只能三选一，且必须至少指定一个，否则会报错。
    
    Returns:
        创建结果
    """
    try:
        # 参数校验，三选一
        if not (host_path or nfs or csi):
            return json.dumps({"success": False, "error": "必须指定 host_path、nfs 或 csi 三者之一作为底层卷类型！"}, ensure_ascii=False, indent=2)
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        pv_result = await k8s_service.create_persistentvolume(
            name=name,
            capacity=capacity,
            access_modes=access_modes,
            storage_class_name=storage_class,
            reclaim_policy=reclaim_policy,
            volume_mode=volume_mode,
            labels=labels,
            annotations=annotations,
            host_path=host_path,
            nfs=nfs,
            csi=csi
        )
        
        result = {
            "success": True,
            "message": f"PersistentVolume '{name}' 创建成功",
            "result": pv_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def update_persistentvolume(name: str, kubeconfig_path: str = None,
                            size: str = None, access_modes: list = None,
                            reclaim_policy: str = None, storage_class: str = None,
                            labels: dict = None, annotations: dict = None) -> str:
    """
    更新PersistentVolume（仅允许更新 size/capacity、access_modes、reclaim_policy、storage_class、labels、annotations）
    
    Args:
        name: PersistentVolume名称
        kubeconfig_path: kubeconfig文件路径
        size: 新的存储大小（如 "5Gi"）
        access_modes: 新的访问模式列表
        reclaim_policy: 新的回收策略
        storage_class: 新的存储类名称
        labels: 新的标签字典
        annotations: 新的注解字典
    
    Returns:
        更新结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        update_kwargs = {
            "name": name,
            "capacity": size,
            "access_modes": access_modes,
            "reclaim_policy": reclaim_policy,
            "storage_class_name": storage_class,
            "labels": labels,
            "annotations": annotations
        }
        # 只保留有值的参数
        update_kwargs = {k: v for k, v in update_kwargs.items() if v is not None}
        update_result = await k8s_service.update_persistentvolume(**update_kwargs)
        result = {
            "success": True,
            "message": f"PersistentVolume '{name}' 更新成功",
            "result": update_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def delete_persistentvolume(name: str, kubeconfig_path: str = None) -> str:
    """
    删除PersistentVolume
    
    Args:
        name: PersistentVolume名称
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        删除结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        delete_result = await k8s_service.delete_persistentvolume(name=name)
        
        result = {
            "success": True,
            "message": f"PersistentVolume '{name}' 删除成功",
            "result": delete_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

# ========================== PersistentVolumeClaim Tools ==========================

@mcp.tool()
async def list_persistentvolumeclaims(namespace: str = None, kubeconfig_path: str = None,
                                label_selector: str = None) -> str:
    """
    列出指定命名空间中的PersistentVolumeClaim
    
    Args:
        namespace: Kubernetes命名空间，默认使用默认集群的命名空间
        kubeconfig_path: kubeconfig文件路径
        label_selector: 标签选择器
    
    Returns:
        包含PersistentVolumeClaim列表的结果
    """
    try:
        namespace = _resolve_namespace(namespace)
        
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        pvcs = await k8s_service.list_persistentvolumeclaims(
            namespace=namespace,
            label_selector=label_selector
        )
        
        result = {
            "success": True,
            "persistentvolumeclaims": pvcs,
            "count": len(pvcs),
            "namespace": namespace
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def describe_persistentvolumeclaim(name: str, namespace: str = "default", kubeconfig_path: str = None) -> str:
    """
    获取PersistentVolumeClaim的详细信息
    
    Args:
        name: PersistentVolumeClaim名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        包含PersistentVolumeClaim详细信息的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        pvc_details = await k8s_service.get_persistentvolumeclaim(name=name, namespace=namespace)
        
        result = {
            "success": True,
            "persistentvolumeclaim": pvc_details
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def create_persistentvolumeclaim(name: str, size: str, namespace: str = "default",
                                 access_modes: list = None, storage_class: str = None,
                                 kubeconfig_path: str = None, labels: dict = None,
                                 annotations: dict = None) -> str:
    """
    创建PersistentVolumeClaim
    
    Args:
        name: PersistentVolumeClaim名称
        size: 存储大小，如 "10Gi"
        namespace: Kubernetes命名空间，默认为default
        access_modes: 访问模式列表，默认为["ReadWriteOnce"]
        storage_class: 存储类名称
        kubeconfig_path: kubeconfig文件路径
        labels: 标签字典
        annotations: 注解字典
    
    Returns:
        创建结果
    """
    try:
        if access_modes is None:
            access_modes = ["ReadWriteOnce"]
            
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        pvc_result = await k8s_service.create_persistentvolumeclaim(
            name=name,
            size=size,
            namespace=namespace,
            access_modes=access_modes,
            storage_class_name=storage_class,
            labels=labels,
            annotations=annotations
        )
        
        result = {
            "success": True,
            "message": f"PersistentVolumeClaim '{name}' 创建成功",
            "result": pvc_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def update_persistentvolumeclaim(name: str, namespace: str = "default",
                                 kubeconfig_path: str = None, size: str = None,
                                 access_modes: list = None, storage_class: str = None,
                                 labels: dict = None, annotations: dict = None) -> str:
    """
    更新PersistentVolumeClaim
    
    Args:
        name: PersistentVolumeClaim名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
        size: 新的存储大小（如 "5Gi"）
        access_modes: 新的访问模式列表
        storage_class: 新的存储类名称
        labels: 新的标签字典
        annotations: 新的注解字典
    
    Returns:
        更新结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        update_kwargs = {
            "name": name,
            "namespace": namespace,
            "size": size,
            "access_modes": access_modes,
            "storage_class_name": storage_class,
            "labels": labels,
            "annotations": annotations
        }
        # 只保留有值的参数
        update_kwargs = {k: v for k, v in update_kwargs.items() if v is not None}
        update_result = await k8s_service.update_persistentvolumeclaim(**update_kwargs)
        result = {
            "success": True,
            "message": f"PersistentVolumeClaim '{name}' 更新成功",
            "result": update_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def delete_persistentvolumeclaim(name: str, namespace: str = "default", kubeconfig_path: str = None) -> str:
    """
    删除PersistentVolumeClaim
    
    Args:
        name: PersistentVolumeClaim名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        删除结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        delete_result = await k8s_service.delete_persistentvolumeclaim(name=name, namespace=namespace)
        
        result = {
            "success": True,
            "message": f"PersistentVolumeClaim '{name}' 删除成功",
            "result": delete_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2) 

# ========================== Node Tools ==========================

@mcp.tool()
async def list_nodes(kubeconfig_path: str = None, label_selector: str = None) -> str:
    """
    列出集群中的节点
        
        Args:
        kubeconfig_path: kubeconfig文件路径
        label_selector: 标签选择器
            
        Returns:
        包含节点列表的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        nodes = await k8s_service.list_nodes(label_selector=label_selector)
        
        result = {
            "success": True,
            "nodes": nodes,
            "count": len(nodes)
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def describe_node(name: str, kubeconfig_path: str = None) -> str:
    """
    获取节点的详细信息
    
    Args:
        name: 节点名称
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        包含节点详细信息的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        node_details = await k8s_service.get_node(name=name)
        
        result = {
            "success": True,
            "node": node_details
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

# ========================== Namespace Tools ==========================

@mcp.tool()
async def list_namespaces(kubeconfig_path: str = None, label_selector: str = None) -> str:
    """
    列出集群中的命名空间
        
        Args:
        kubeconfig_path: kubeconfig文件路径
        label_selector: 标签选择器
            
        Returns:
        包含命名空间列表的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        namespaces = await k8s_service.list_namespaces(label_selector=label_selector)
        
        result = {
            "success": True,
            "namespaces": namespaces,
            "count": len(namespaces)
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def create_namespace(name: str, kubeconfig_path: str = None, 
                    labels: Dict[str, str] = None) -> str:
    """
    创建命名空间
    
    Args:
        name: 命名空间名称
        kubeconfig_path: kubeconfig文件路径
        labels: 标签字典
    
    Returns:
        创建结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        create_result = await k8s_service.create_namespace(name=name, labels=labels)
        
        result = {
            "success": True,
            "message": f"命名空间 '{name}' 创建成功",
            "result": create_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def delete_namespace(name: str, kubeconfig_path: str = None) -> str:
    """
    删除命名空间
        
        Args:
        name: 命名空间名称
        kubeconfig_path: kubeconfig文件路径
            
        Returns:
        删除结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        delete_result = await k8s_service.delete_namespace(name=name)
        
        result = {
            "success": True,
            "message": f"命名空间 '{name}' 删除成功",
            "result": delete_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

# ========================== Event Tools ==========================

@mcp.tool()
async def list_events(namespace: str = "default", kubeconfig_path: str = None,
               field_selector: str = None) -> str:
    """
    列出指定命名空间中的事件
        
        Args:
        namespace: Kubernetes命名空间，默认为default，"all"表示所有命名空间
        kubeconfig_path: kubeconfig文件路径
        field_selector: 字段选择器
            
        Returns:
        包含事件列表的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        events = await k8s_service.list_events(
            namespace=namespace,
            field_selector=field_selector
        )
        
        result = {
            "success": True,
            "events": events,
            "count": len(events),
            "namespace": namespace
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

# ========================== Cluster Tools ==========================

@mcp.tool()
async def get_cluster_info(kubeconfig_path: str = None) -> str:
    """
    获取集群基本信息
    
    Args:
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        包含集群信息的结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        cluster_info = await k8s_service.get_cluster_info()
        
        result = {
            "success": True,
            "cluster": cluster_info
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2) 
