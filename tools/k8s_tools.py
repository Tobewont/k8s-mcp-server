"""
Kubernetes 工具集合
提供集群健康检查、查询功能和基本信息查询功能
"""

import json
import os
from services.k8s_api_service import KubernetesAPIService
from config import COPYFILES_DIR

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
                 container: str = None, previous: bool = False, kubeconfig_path: str = None) -> str:
    """
    获取Pod的日志
    
    Args:
        name: Pod名称
        namespace: Kubernetes命名空间，默认为default
        lines: 日志行数，默认为100
        container: 容器名称，如果Pod有多个容器则需要指定
        previous: 是否获取上一实例（崩溃/重启前）的日志，默认为False
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
            container=container,
            previous=previous
        )
        
        result = {
            "success": True,
            "logs": logs,
            "pod_name": name,
            "namespace": namespace,
            "container": container,
            "lines": lines,
            "previous": previous
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
async def copy_pod_file(pod_name: str, direction: str, source_path: str, dest_path: str = None,
                        namespace: str = "default", container: str = None,
                        kubeconfig_path: str = None) -> str:
    """
    Pod 与本地之间拷贝文件/目录
    
    Args:
        pod_name: Pod 名称
        direction: 拷贝方向，"from_pod" 从 Pod 拷贝到本地，"to_pod" 从本地拷贝到 Pod
        source_path: 源路径。from_pod 时为 Pod 内路径，to_pod 时为本地路径
        dest_path: 目标路径。from_pod 时为本地路径（默认保存到 data/copyfiles/<pod_name>/），to_pod 时为 Pod 内路径
        namespace: 命名空间，默认为 default
        container: 容器名称，多容器 Pod 需指定
        kubeconfig_path: kubeconfig 文件路径
    
    Returns:
        拷贝结果，包含实际保存路径
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        if direction == "from_pod":
            if not dest_path:
                base = os.path.basename(source_path.rstrip('/')) or "file"
                dest_path = os.path.join(COPYFILES_DIR, pod_name, base)
            result_path = await k8s_service.copy_from_pod(
                pod_name=pod_name,
                pod_path=source_path,
                local_path=dest_path,
                namespace=namespace,
                container=container
            )
            return json.dumps({
                "success": True,
                "direction": "from_pod",
                "pod_path": source_path,
                "local_path": result_path,
                "message": f"已从 Pod 拷贝到 {result_path}"
            }, ensure_ascii=False, indent=2)
        elif direction == "to_pod":
            if not dest_path:
                return json.dumps({
                    "success": False,
                    "error": "to_pod 方向必须指定 dest_path（Pod 内目标路径）"
                }, ensure_ascii=False, indent=2)
            result_path = await k8s_service.copy_to_pod(
                pod_name=pod_name,
                local_path=source_path,
                pod_path=dest_path,
                namespace=namespace,
                container=container
            )
            return json.dumps({
                "success": True,
                "direction": "to_pod",
                "local_path": source_path,
                "pod_path": result_path,
                "message": f"已拷贝到 Pod {result_path}"
            }, ensure_ascii=False, indent=2)
        else:
            return json.dumps({
                "success": False,
                "error": f"direction 必须是 from_pod 或 to_pod，当前为 {direction}"
            }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


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