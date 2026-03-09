"""
Kubernetes 工具集合
提供集群健康检查、查询功能和基本信息查询功能
"""
import os

from config import COPYFILES_DIR
from services.factory import get_k8s_api_service
from utils.decorators import handle_tool_errors
from utils.operations_logger import log_operation
from utils.response import json_error, json_success

# 导入共享的MCP实例
from . import mcp

# ========================== 集群信息工具 ==========================

@mcp.tool()
@handle_tool_errors
async def get_cluster_info(kubeconfig_path: str = None) -> str:
    """
    获取Kubernetes集群信息
    
    Args:
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        集群信息
    """
    k8s_service = get_k8s_api_service(kubeconfig_path)
    cluster_info = await k8s_service.get_cluster_info()
    return json_success({"success": True, "cluster_info": cluster_info})

# ========================== Pod 日志和操作工具 ==========================

@mcp.tool()
@handle_tool_errors
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
    if not isinstance(lines, int) or lines < 1:
        return json_error("lines 必须为正整数")
    k8s_service = get_k8s_api_service(kubeconfig_path)
    logs = await k8s_service.get_pod_logs(name=name, namespace=namespace, lines=lines, container=container, previous=previous)
    return json_success({"success": True, "logs": logs, "pod_name": name, "namespace": namespace, "container": container, "lines": lines, "previous": previous})

# ========================== 交互式操作工具 ==========================

@mcp.tool()
@handle_tool_errors
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
    if not command or not isinstance(command, (list, tuple)):
        return json_error("command 必须为非空列表")
    k8s_service = get_k8s_api_service(kubeconfig_path)
    exec_result = await k8s_service.exec_pod_command(pod_name=pod_name, command=command, namespace=namespace, container=container)
    return json_success({"success": True, "pod_name": pod_name, "namespace": namespace, "container": container, "command": command, "output": exec_result})


@mcp.tool()
@handle_tool_errors
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
    if not source_path or not str(source_path).strip():
        return json_error("source_path 不能为空")
    if direction not in ("from_pod", "to_pod"):
        return json_error(f"direction 必须是 from_pod 或 to_pod，当前为 {direction}")
    if direction == "to_pod" and not dest_path:
        return json_error("to_pod 方向必须指定 dest_path（Pod 内目标路径）")
    k8s_service = get_k8s_api_service(kubeconfig_path)
    if direction == "from_pod":
        if not dest_path:
            base = os.path.basename(source_path.rstrip('/')) or "file"
            dest_path = os.path.join(COPYFILES_DIR, pod_name, base)
        result_path = await k8s_service.copy_from_pod(pod_name=pod_name, pod_path=source_path, local_path=dest_path, namespace=namespace, container=container)
        log_operation("copy_pod_file", "copy", {"direction": "from_pod", "pod_name": pod_name, "pod_path": source_path, "local_path": result_path, "namespace": namespace}, True)
        return json_success({"success": True, "direction": "from_pod", "pod_path": source_path, "local_path": result_path, "message": f"已从 Pod 拷贝到 {result_path}"})
    result_path = await k8s_service.copy_to_pod(pod_name=pod_name, local_path=source_path, pod_path=dest_path, namespace=namespace, container=container)
    log_operation("copy_pod_file", "copy", {"direction": "to_pod", "pod_name": pod_name, "local_path": source_path, "pod_path": result_path, "namespace": namespace}, True)
    return json_success({"success": True, "direction": "to_pod", "local_path": source_path, "pod_path": result_path, "message": f"已拷贝到 Pod {result_path}"})


@mcp.tool()
@handle_tool_errors
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
    if not (1 <= local_port <= 65535) or not (1 <= pod_port <= 65535):
        return json_error("local_port 和 pod_port 必须在 1-65535 范围内")
    k8s_service = get_k8s_api_service(kubeconfig_path)
    forward_result = await k8s_service.port_forward(pod_name=pod_name, local_port=local_port, pod_port=pod_port, namespace=namespace)
    return json_success({"success": True, "pod_name": pod_name, "namespace": namespace, "local_port": local_port, "pod_port": pod_port, "forward_info": forward_result})