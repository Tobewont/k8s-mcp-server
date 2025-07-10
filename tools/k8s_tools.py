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

@mcp.tool()
async def list_pods(namespace: str = "default", kubeconfig_path: str = None, 
              label_selector: str = None) -> str:
    """
    列出指定命名空间中的Pod
    
    Args:
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
        label_selector: 标签选择器
    
    Returns:
        包含Pod列表的结果
    """
    try:
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

@mcp.tool()
async def list_deployments(namespace: str = "default", kubeconfig_path: str = None,
                    label_selector: str = None) -> str:
    """
    列出指定命名空间中的Deployment
    
    Args:
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
        label_selector: 标签选择器
    
    Returns:
        包含Deployment列表的结果
    """
    try:
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
async def scale_deployment(name: str, replicas: int, namespace: str = "default", 
                    kubeconfig_path: str = None) -> str:
    """
    扩缩容Deployment
    
    Args:
        name: Deployment名称
        replicas: 目标副本数
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        扩缩容结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        scale_result = await k8s_service.scale_deployment(
            name=name,
            namespace=namespace,
            replicas=replicas
        )
        
        result = {
            "success": True,
            "message": f"Deployment '{name}' 扩缩容成功",
            "result": scale_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def delete_deployment(name: str, namespace: str = "default", kubeconfig_path: str = None) -> str:
    """
    删除Deployment
    
    Args:
        name: Deployment名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        删除结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        delete_result = await k8s_service.delete_deployment(name=name, namespace=namespace)
        
        result = {
            "success": True,
            "message": f"Deployment '{name}' 删除成功",
            "result": delete_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

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