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

# ========================== 快捷操作工具 ==========================

@mcp.tool()
async def scale_deployment(name: str, replicas: int, namespace: str = "default", 
                          kubeconfig_path: str = None) -> str:
    """
    快速扩缩容Deployment（保留此工具作为常用快捷操作）
    
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
        
        scale_result = await k8s_service.update_deployment(
            name=name,
            namespace=namespace,
            replicas=replicas
        )
        
        result = {
            "success": True,
            "message": f"Deployment '{name}' 已扩缩容至 {replicas} 个副本",
            "result": scale_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def restart_deployment(name: str, namespace: str = "default", 
                           kubeconfig_path: str = None) -> str:
    """
    重启Deployment（通过添加重启注解触发滚动更新）
    
    Args:
        name: Deployment名称
        namespace: Kubernetes命名空间，默认为default
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        重启结果
    """
    try:
        import datetime
        
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        # 添加重启注解来触发滚动更新
        restart_annotation = {
            "kubectl.kubernetes.io/restartedAt": datetime.datetime.now().isoformat()
        }
        
        restart_result = await k8s_service.update_deployment(
            name=name,
            namespace=namespace,
            labels=restart_annotation  # 这里实际上会更新到 annotations
        )
        
        result = {
            "success": True,
            "message": f"Deployment '{name}' 重启成功",
            "result": restart_result
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

# ========================== 资源使用情况工具 ==========================

@mcp.tool()
async def get_resource_usage_summary(namespace: str = None, kubeconfig_path: str = None) -> str:
    """
    获取资源使用情况摘要
    
    Args:
        namespace: Kubernetes命名空间，默认使用默认集群的命名空间
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        资源使用情况摘要
    """
    try:
        # 解析命名空间
        namespace = _resolve_namespace(namespace)
        
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        # 获取各种资源的数量
        pods = await k8s_service.list_pods(namespace=namespace)
        deployments = await k8s_service.list_deployments(namespace=namespace)
        services = await k8s_service.list_services(namespace=namespace)
        configmaps = await k8s_service.list_configmaps(namespace=namespace)
        secrets = await k8s_service.list_secrets(namespace=namespace)
        
        # 统计Pod状态
        pod_status_count = {}
        for pod in pods:
            status = pod.get("status", "Unknown")
            pod_status_count[status] = pod_status_count.get(status, 0) + 1
        
        result = {
            "success": True,
            "namespace": namespace,
            "summary": {
                "pods": {
                    "total": len(pods),
                    "by_status": pod_status_count
                },
                "deployments": len(deployments),
                "services": len(services),
                "configmaps": len(configmaps),
                "secrets": len(secrets)
            }
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

# ========================== 故障排查工具 ==========================

@mcp.tool()
async def get_failing_pods(namespace: str = None, kubeconfig_path: str = None) -> str:
    """
    获取失败或异常的Pod列表
    
    Args:
        namespace: Kubernetes命名空间，默认使用默认集群的命名空间
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        失败Pod列表及其详细信息
    """
    try:
        # 解析命名空间
        namespace = _resolve_namespace(namespace)
        
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        pods = await k8s_service.list_pods(namespace=namespace)
        
        # 筛选出异常的Pod
        failing_pods = []
        for pod in pods:
            status = pod.get("status", "Unknown")
            if status in ["Failed", "CrashLoopBackOff", "Error", "ImagePullBackOff", "ErrImagePull"]:
                failing_pods.append(pod)
        
        result = {
            "success": True,
            "namespace": namespace,
            "failing_pods": failing_pods,
            "count": len(failing_pods)
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def get_recent_events(namespace: str = None, kubeconfig_path: str = None, 
                          minutes: int = 30) -> str:
    """
    获取最近的事件（用于故障排查）
    
    Args:
        namespace: Kubernetes命名空间，默认使用默认集群的命名空间
        kubeconfig_path: kubeconfig文件路径
        minutes: 获取最近多少分钟的事件，默认30分钟
    
    Returns:
        最近的事件列表
    """
    try:
        # 解析命名空间
        namespace = _resolve_namespace(namespace)
        
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        events = await k8s_service.list_events(namespace=namespace)
        
        # 这里可以添加时间过滤逻辑，暂时返回所有事件
        # TODO: 实现基于时间的事件过滤
        
        result = {
            "success": True,
            "namespace": namespace,
            "events": events,
            "count": len(events),
            "time_range_minutes": minutes
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

@mcp.tool()
async def delete_pod(name: str, namespace: str = "default", kubeconfig_path: str = None,
                          grace_period_seconds: int = None) -> str:
    """
    删除Pod（保留此工具因为Pod删除是常见的运维操作）
    
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