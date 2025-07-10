"""
Kubernetes 诊断工具集合
提供集群健康检查、节点健康检查、Pod健康检查等诊断功能
"""

import json
from datetime import datetime
from typing import Dict, List, Any
from services.k8s_api_service import KubernetesAPIService

# 导入共享的MCP实例
from . import mcp

@mcp.tool()
async def check_cluster_health(kubeconfig_path: str = None) -> str:
    """
    检查Kubernetes集群健康状态
    
    Args:
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        集群健康检查结果
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        # 获取集群基本信息
        cluster_info = await k8s_service.get_cluster_info()
        
        # 获取节点状态
        nodes = await k8s_service.list_nodes()
        
        # 统计节点状态
        ready_nodes = [node for node in nodes if node["status"] == "Ready"]
        not_ready_nodes = [node for node in nodes if node["status"] != "Ready"]
        
        # 检查系统命名空间的 Pod
        system_namespaces = ["kube-system", "kube-public", "kube-node-lease"]
        system_pod_issues = []
        
        for namespace in system_namespaces:
            try:
                pods = await k8s_service.list_pods(namespace=namespace)
                failed_pods = [pod for pod in pods if pod["status"] not in ["Running", "Succeeded"]]
                if failed_pods:
                    system_pod_issues.extend(failed_pods)
            except:
                # 如果命名空间不存在，跳过
                continue
        
        # API 服务器健康检查
        api_health = await k8s_service.check_api_health()
        
        # 计算健康得分
        total_score = 100
        if api_health["status"] != "healthy":
            total_score -= 50
        if not_ready_nodes:
            total_score -= len(not_ready_nodes) * 20
        if system_pod_issues:
            total_score -= len(system_pod_issues) * 5
        
        health_score = max(0, total_score)
        
        # 确定整体状态
        if health_score >= 90:
            overall_status = "healthy"
        elif health_score >= 70:
            overall_status = "warning"
        else:
            overall_status = "critical"
        
        result = {
            "success": True,
            "overall_status": overall_status,
            "health_score": health_score,
            "cluster_info": cluster_info,
            "node_summary": {
                "total": len(nodes),
                "ready": len(ready_nodes),
                "not_ready": len(not_ready_nodes)
            },
            "api_server": api_health,
            "issues": {
                "not_ready_nodes": not_ready_nodes,
                "failed_system_pods": system_pod_issues
            },
            "recommendations": _generate_health_recommendations(not_ready_nodes, system_pod_issues, api_health)
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def check_node_health(node_name: str = None, kubeconfig_path: str = None) -> str:
    """
    检查节点健康状态
    
    Args:
        node_name: 节点名称，如果不提供则检查所有节点
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        节点健康状态报告
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        if node_name:
            # 检查单个节点
            node_details = await k8s_service.get_node(name=node_name)
            nodes_to_check = [node_details]
        else:
            # 检查所有节点
            nodes = await k8s_service.list_nodes()
            nodes_to_check = []
            for node in nodes:
                node_details = await k8s_service.get_node(name=node["name"])
                nodes_to_check.append(node_details)
        
        node_reports = []
        for node in nodes_to_check:
            node_report = _analyze_node_health(node)
            node_reports.append(node_report)
        
        # 汇总结果
        healthy_nodes = [n for n in node_reports if n["status"] == "healthy"]
        warning_nodes = [n for n in node_reports if n["status"] == "warning"]
        critical_nodes = [n for n in node_reports if n["status"] == "critical"]
        
        result = {
            "success": True,
            "summary": {
                "total_nodes": len(node_reports),
                "healthy": len(healthy_nodes),
                "warning": len(warning_nodes),
                "critical": len(critical_nodes)
            },
            "node_details": node_reports
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def check_pod_health(pod_name: str = None, namespace: str = "default", 
                     kubeconfig_path: str = None) -> str:
    """
    检查Pod健康状态
    
    Args:
        pod_name: Pod名称，如果不提供则检查命名空间中的所有Pod
        namespace: Kubernetes命名空间
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        Pod健康状态报告
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        if pod_name:
            # 检查单个Pod
            pod_details = await k8s_service.get_pod(name=pod_name, namespace=namespace)
            # 获取相关事件
            events = await k8s_service.list_events(
                namespace=namespace,
                field_selector=f"involvedObject.name={pod_name}"
            )
            pods_to_check = [{"details": pod_details, "events": events}]
        else:
            # 检查命名空间中的所有Pod
            pods = await k8s_service.list_pods(namespace=namespace)
            pods_to_check = []
            
            for pod in pods:
                pod_details = await k8s_service.get_pod(name=pod["name"], namespace=namespace)
                # 获取Pod相关事件
                try:
                    events = await k8s_service.list_events(
                        namespace=namespace,
                        field_selector=f"involvedObject.name={pod['name']}"
                    )
                except:
                    events = []
                
                pods_to_check.append({"details": pod_details, "events": events})
        
        pod_reports = []
        for pod_data in pods_to_check:
            pod_report = _analyze_pod_health(pod_data["details"], pod_data["events"])
            pod_reports.append(pod_report)
        
        # 汇总结果
        healthy_pods = [p for p in pod_reports if p["status"] == "healthy"]
        warning_pods = [p for p in pod_reports if p["status"] == "warning"]
        critical_pods = [p for p in pod_reports if p["status"] == "critical"]
        
        result = {
            "success": True,
            "namespace": namespace,
            "summary": {
                "total_pods": len(pod_reports),
                "healthy": len(healthy_pods),
                "warning": len(warning_pods),
                "critical": len(critical_pods)
            },
            "pod_details": pod_reports
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def check_resource_usage(namespace: str = "all", kubeconfig_path: str = None) -> str:
    """
    检查资源使用情况
    
    Args:
        namespace: Kubernetes命名空间，"all"表示所有命名空间
        kubeconfig_path: kubeconfig文件路径
    
    Returns:
        资源使用情况报告
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        # 获取节点资源信息
        nodes = await k8s_service.list_nodes()
        node_resources = {}
        
        for node in nodes:
            node_details = await k8s_service.get_node(name=node["name"])
            capacity = node_details["status"]["capacity"]
            allocatable = node_details["status"]["allocatable"]
            
            node_resources[node["name"]] = {
                "capacity": capacity,
                "allocatable": allocatable,
                "status": node["status"]
            }
        
        # 获取Pod资源使用情况
        pods = await k8s_service.list_pods(namespace=namespace if namespace != "all" else "default")
        
        # 如果是所有命名空间，需要获取所有Pod
        if namespace == "all":
            # 获取所有命名空间的Pod
            try:
                pods = await k8s_service.list_pods(namespace="all")
            except:
                # 如果不支持，则逐个命名空间获取
                namespaces = await k8s_service.list_namespaces()
                all_pods = []
                for ns in namespaces:
                    try:
                        ns_pods = await k8s_service.list_pods(namespace=ns["name"])
                        all_pods.extend(ns_pods)
                    except:
                        continue
                pods = all_pods
        
        pod_resources = []
        for pod in pods:
            try:
                pod_details = await k8s_service.get_pod(name=pod["name"], namespace=pod["namespace"])
                
                # 计算Pod资源请求和限制
                pod_requests = {"cpu": 0, "memory": 0}
                pod_limits = {"cpu": 0, "memory": 0}
                
                for container in pod_details["spec"]["containers"]:
                    resources = container.get("resources", {})
                    requests = resources.get("requests", {})
                    limits = resources.get("limits", {})
                    
                    # CPU处理
                    if "cpu" in requests:
                        pod_requests["cpu"] += _parse_cpu(requests["cpu"])
                    if "cpu" in limits:
                        pod_limits["cpu"] += _parse_cpu(limits["cpu"])
                    
                    # 内存处理
                    if "memory" in requests:
                        pod_requests["memory"] += _parse_memory(requests["memory"])
                    if "memory" in limits:
                        pod_limits["memory"] += _parse_memory(limits["memory"])
                
                pod_resources.append({
                    "name": pod["name"],
                    "namespace": pod["namespace"],
                    "node": pod["node"],
                    "requests": pod_requests,
                    "limits": pod_limits,
                    "status": pod["status"]
                })
            except:
                continue
        
        # 分析资源使用情况
        analysis = _analyze_resource_usage(node_resources, pod_resources)
        
        result = {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "cluster_resources": {
                "nodes": node_resources,
                "total_pods": len(pod_resources)
            },
            "resource_analysis": analysis,
            "pod_resources": pod_resources[:50] if len(pod_resources) > 50 else pod_resources  # 限制返回数量
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def get_cluster_events(namespace: str = "all", kubeconfig_path: str = None, 
                       event_type: str = None, limit: int = 100) -> str:
    """
    获取集群事件
    
    Args:
        namespace: Kubernetes命名空间，"all"表示所有命名空间
        kubeconfig_path: kubeconfig文件路径
        event_type: 事件类型过滤（Warning, Normal等）
        limit: 返回事件数量限制
    
    Returns:
        集群事件列表
    """
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        # 获取事件
        events = await k8s_service.list_events(namespace=namespace if namespace != "all" else "default")
        
        # 如果指定了事件类型，进行过滤
        if event_type:
            events = [event for event in events if event.get("type") == event_type]
        
        # 按时间排序（最新的在前）
        events.sort(key=lambda x: x.get("last_timestamp", ""), reverse=True)
        
        # 限制数量
        if limit:
            events = events[:limit]
        
        # 统计事件类型
        event_stats = {}
        for event in events:
            event_type_val = event.get("type", "Unknown")
            event_stats[event_type_val] = event_stats.get(event_type_val, 0) + 1
        
        result = {
            "success": True,
            "namespace": namespace,
            "total_events": len(events),
            "event_statistics": event_stats,
            "events": events
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

# 辅助函数
def _generate_health_recommendations(not_ready_nodes: List[Dict], system_pod_issues: List[Dict], 
                                   api_health: Dict) -> List[str]:
    """生成健康建议"""
    recommendations = []
    
    if api_health["status"] != "healthy":
        recommendations.append("API服务器不健康，请检查集群连接和配置")
    
    if not_ready_nodes:
        recommendations.append(f"有 {len(not_ready_nodes)} 个节点不可用，请检查节点状态")
    
    if system_pod_issues:
        recommendations.append(f"系统命名空间中有 {len(system_pod_issues)} 个Pod存在问题")
    
    if not recommendations:
        recommendations.append("集群状态良好")
    
    return recommendations

def _analyze_node_health(node: Dict[str, Any]) -> Dict[str, Any]:
    """分析节点健康状态"""
    conditions = node["status"]["conditions"]
    issues = []
    warnings = []
    
    # 检查节点条件
    for condition in conditions:
        if condition["type"] == "Ready":
            if condition["status"] != "True":
                issues.append(f"节点未就绪: {condition.get('reason', 'Unknown')}")
        elif condition["type"] in ["DiskPressure", "MemoryPressure", "PIDPressure"]:
            if condition["status"] == "True":
                issues.append(f"{condition['type']}: {condition.get('message', 'No message')}")
        elif condition["type"] == "NetworkUnavailable":
            if condition["status"] == "True":
                issues.append("网络不可用")
    
    # 检查资源容量
    capacity = node["status"]["capacity"]
    allocatable = node["status"]["allocatable"]
    
    # CPU检查
    if "cpu" in capacity and "cpu" in allocatable:
        cpu_ratio = _parse_cpu(allocatable["cpu"]) / _parse_cpu(capacity["cpu"])
        if cpu_ratio < 0.8:
            warnings.append(f"CPU可分配比例较低: {cpu_ratio:.2%}")
    
    # 内存检查
    if "memory" in capacity and "memory" in allocatable:
        memory_ratio = _parse_memory(allocatable["memory"]) / _parse_memory(capacity["memory"])
        if memory_ratio < 0.8:
            warnings.append(f"内存可分配比例较低: {memory_ratio:.2%}")
    
    # 确定状态
    if issues:
        status = "critical"
    elif warnings:
        status = "warning"
    else:
        status = "healthy"
    
    return {
        "name": node["metadata"]["name"],
        "status": status,
        "issues": issues,
        "warnings": warnings,
        "capacity": capacity,
        "allocatable": allocatable,
        "conditions": conditions
    }

def _analyze_pod_health(pod: Dict[str, Any], events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """分析Pod健康状态"""
    issues = []
    warnings = []
    
    # 检查Pod状态
    phase = pod["status"]["phase"]
    if phase in ["Failed", "Unknown"]:
        issues.append(f"Pod状态异常: {phase}")
    elif phase == "Pending":
        warnings.append("Pod处于等待状态")
    
    # 检查容器状态
    container_statuses = pod["status"].get("container_statuses", [])
    for container_status in container_statuses:
        if not container_status["ready"]:
            warnings.append(f"容器 {container_status['name']} 未就绪")
        
        if container_status["restart_count"] > 5:
            warnings.append(f"容器 {container_status['name']} 重启次数过多: {container_status['restart_count']}")
        
        state = container_status["state"]
        if state.get("state") == "waiting":
            reason = state.get("reason", "Unknown")
            if reason in ["ImagePullBackOff", "ErrImagePull", "CrashLoopBackOff"]:
                issues.append(f"容器 {container_status['name']} {reason}")
        elif state.get("state") == "terminated":
            exit_code = state.get("exit_code", 0)
            if exit_code != 0:
                issues.append(f"容器 {container_status['name']} 异常退出: {exit_code}")
    
    # 检查事件
    warning_events = [e for e in events if e.get("type") == "Warning"]
    if warning_events:
        for event in warning_events[-3:]:  # 只显示最近3个警告事件
            warnings.append(f"事件: {event.get('reason', 'Unknown')} - {event.get('message', '')}")
    
    # 确定状态
    if issues:
        status = "critical"
    elif warnings:
        status = "warning"
    else:
        status = "healthy"
    
    return {
        "name": pod["metadata"]["name"],
        "namespace": pod["metadata"]["namespace"],
        "status": status,
        "phase": phase,
        "issues": issues,
        "warnings": warnings,
        "container_statuses": container_statuses,
        "recent_events": warning_events[-5:] if warning_events else []
    }

def _analyze_resource_usage(node_resources: Dict, pod_resources: List[Dict]) -> Dict[str, Any]:
    """分析资源使用情况"""
    analysis = {
        "cluster_summary": {},
        "node_utilization": {},
        "resource_pressure": []
    }
    
    # 集群总资源
    total_cpu_capacity = 0
    total_memory_capacity = 0
    total_cpu_allocatable = 0
    total_memory_allocatable = 0
    
    for node_name, node_info in node_resources.items():
        capacity = node_info["capacity"]
        allocatable = node_info["allocatable"]
        
        if "cpu" in capacity:
            total_cpu_capacity += _parse_cpu(capacity["cpu"])
        if "memory" in capacity:
            total_memory_capacity += _parse_memory(capacity["memory"])
        if "cpu" in allocatable:
            total_cpu_allocatable += _parse_cpu(allocatable["cpu"])
        if "memory" in allocatable:
            total_memory_allocatable += _parse_memory(allocatable["memory"])
    
    # Pod资源请求汇总
    total_cpu_requests = 0
    total_memory_requests = 0
    
    for pod in pod_resources:
        total_cpu_requests += pod["requests"]["cpu"]
        total_memory_requests += pod["requests"]["memory"]
    
    # 计算使用率
    cpu_utilization = total_cpu_requests / total_cpu_allocatable if total_cpu_allocatable > 0 else 0
    memory_utilization = total_memory_requests / total_memory_allocatable if total_memory_allocatable > 0 else 0
    
    analysis["cluster_summary"] = {
        "total_nodes": len(node_resources),
        "total_pods": len(pod_resources),
        "cpu_capacity": f"{total_cpu_capacity:.2f} cores",
        "memory_capacity": f"{total_memory_capacity / (1024**3):.2f} GB",
        "cpu_utilization": f"{cpu_utilization:.2%}",
        "memory_utilization": f"{memory_utilization:.2%}"
    }
    
    # 节点利用率分析
    for node_name, node_info in node_resources.items():
        node_pods = [p for p in pod_resources if p["node"] == node_name]
        node_cpu_requests = sum(p["requests"]["cpu"] for p in node_pods)
        node_memory_requests = sum(p["requests"]["memory"] for p in node_pods)
        
        allocatable = node_info["allocatable"]
        node_cpu_allocatable = _parse_cpu(allocatable.get("cpu", "0"))
        node_memory_allocatable = _parse_memory(allocatable.get("memory", "0"))
        
        node_cpu_util = node_cpu_requests / node_cpu_allocatable if node_cpu_allocatable > 0 else 0
        node_memory_util = node_memory_requests / node_memory_allocatable if node_memory_allocatable > 0 else 0
        
        analysis["node_utilization"][node_name] = {
            "cpu_utilization": f"{node_cpu_util:.2%}",
            "memory_utilization": f"{node_memory_util:.2%}",
            "pod_count": len(node_pods),
            "status": node_info["status"]
        }
        
        # 检查资源压力
        if node_cpu_util > 0.8:
            analysis["resource_pressure"].append(f"节点 {node_name} CPU使用率过高: {node_cpu_util:.2%}")
        if node_memory_util > 0.8:
            analysis["resource_pressure"].append(f"节点 {node_name} 内存使用率过高: {node_memory_util:.2%}")
    
    return analysis

def _parse_cpu(cpu_str: str) -> float:
    """解析CPU字符串为核心数"""
    if not cpu_str:
        return 0.0
    
    cpu_str = str(cpu_str).lower()
    if cpu_str.endswith('m'):
        return float(cpu_str[:-1]) / 1000
    elif cpu_str.endswith('n'):
        return float(cpu_str[:-1]) / 1000000000
    else:
        return float(cpu_str)

def _parse_memory(memory_str: str) -> int:
    """解析内存字符串为字节数"""
    if not memory_str:
        return 0
    
    memory_str = str(memory_str)
    units = {
        'Ki': 1024,
        'Mi': 1024**2,
        'Gi': 1024**3,
        'Ti': 1024**4,
        'K': 1000,
        'M': 1000**2,
        'G': 1000**3,
        'T': 1000**4
    }
    
    for unit, multiplier in units.items():
        if memory_str.endswith(unit):
            return int(float(memory_str[:-len(unit)]) * multiplier)
    
    # 如果没有单位，假设是字节
    return int(memory_str) 