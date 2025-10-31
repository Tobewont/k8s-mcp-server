"""
Kubernetes 工具集合
提供集群健康检查、查询功能和基本信息查询功能
"""

import json
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

# ========================== 集群信息工具 ==========================

@mcp.tool()
async def get_cluster_info(kubeconfig_path: str = None) -> str:
    """
    获取Kubernetes集群信息
    
    Args:
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        集群信息
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        cluster_info = await k8s_service.get_cluster_info()
        
        result = {
            "success": True,
            "cluster_info": cluster_info
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

# ========================== Pod 日志和操作工具 ==========================

@mcp.tool()
async def get_pod_logs(name: str, namespace: str = "default", lines: int = 100, 
                 container: str = None, kubeconfig_path: str = None) -> str:
    """
    获取Pod的日志
    
    Args:
        name: Pod名称
        namespace: Kubernetes命名空间，默认为default
        lines: 日志行数，默认为100
        container: 容器名称，如果Pod有多个容器则需要指定
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
            lines=lines,
            container=container
        )
        
        result = {
            "success": True,
            "logs": logs,
            "pod_name": name,
            "namespace": namespace,
            "container": container,
            "lines": lines
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

# ========================== 交互式操作工具 ==========================

@mcp.tool()
async def exec_pod_command(pod_name: str, command: list, namespace: str = "default", 
                          container: str = None, kubeconfig_path: str = None) -> str:
    """
    在Pod中执行命令
    
    Args:
        pod_name: Pod名称
        command: 要执行的命令列表，如 ["ls", "-la"]
        namespace: Kubernetes命名空间，默认为default
        container: 容器名称，如果Pod有多个容器则需要指定
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        命令执行结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        # 执行命令
        exec_result = await k8s_service.exec_pod_command(
            pod_name=pod_name,
            command=command,
            namespace=namespace,
            container=container
        )
        
        result = {
            "success": True,
            "pod_name": pod_name,
            "namespace": namespace,
            "container": container,
            "command": command,
            "output": exec_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def port_forward(pod_name: str, local_port: int, pod_port: int, 
                      namespace: str = "default", kubeconfig_path: str = None) -> str:
    """
    Pod端口转发
    
    Args:
        pod_name: Pod名称
        local_port: 本地端口
        pod_port: Pod端口
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        端口转发结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        # 启动端口转发
        forward_result = await k8s_service.port_forward(
            pod_name=pod_name,
            local_port=local_port,
            pod_port=pod_port,
            namespace=namespace
        )
        
        result = {
            "success": True,
            "pod_name": pod_name,
            "namespace": namespace,
            "local_port": local_port,
            "pod_port": pod_port,
            "forward_info": forward_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)