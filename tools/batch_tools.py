"""
批量操作工具模块
提供批量创建、更新和删除资源的功能
"""
import json
from datetime import datetime
from typing import Optional

from services.factory import get_k8s_advanced_service
from utils.cluster_config import resolve_kubeconfig_path
from utils.decorators import handle_tool_errors
from utils.operations_logger import log_operation
from utils.param_parsers import (
    parse_json_or_single,
    parse_json_array,
    parse_and_validate_resources,
    parse_and_validate_resource_specs,
)
from utils.response import json_error, json_success, json_partial_success

# 导入共享的MCP实例
from . import mcp

VALID_ROLLOUT_ACTIONS = ("status", "undo", "pause", "resume")


@mcp.tool()
@handle_tool_errors
async def batch_list_resources(resource_types: str, namespace: str = "default",
                              kubeconfig_path: Optional[str] = None,
                              cluster_name: Optional[str] = None) -> str:
    """批量查看资源
    
    Args:
        resource_types: 资源类型，支持：1) "all" 列出集群所有可用 API 资源类型；2) JSON 数组如 ["pods","deployments"]；3) 单个类型如 "pods"。支持任意集群内可发现的资源（含 CRD）
        namespace: 命名空间
        kubeconfig_path: kubeconfig 文件路径，不指定则使用 cluster_name 或默认集群
        cluster_name: 集群配置名称（clusters.json 中的 name），kubeconfig_path 未指定时使用
    
    Returns:
        批量查看结果
    """
    resource_types_list, err = parse_json_or_single(resource_types)
    if err:
        return json_error(err)
    effective_path = resolve_kubeconfig_path(cluster_name, kubeconfig_path)
    service = get_k8s_advanced_service(effective_path)
    result = await service.batch_list_resources(resource_types_list, namespace)
    return json_success(result)


@mcp.tool()
@handle_tool_errors
async def batch_create_resources(resources: str, namespace: str = "default",
                               rollback_on_failure: bool = True,
                               kubeconfig_path: Optional[str] = None,
                               cluster_name: Optional[str] = None) -> str:
    """批量创建资源
    
    Args:
        resources: JSON格式的资源列表，每个资源包含kind、metadata、spec
        namespace: 命名空间
        rollback_on_failure: 失败时是否回滚已创建的资源
        kubeconfig_path: kubeconfig 文件路径，不指定则使用 cluster_name 或默认集群
        cluster_name: 集群配置名称（clusters.json 中的 name），kubeconfig_path 未指定时使用
    """
    resources_list, err = parse_and_validate_resources(resources)
    if err:
        return json_error(err)

    effective_path = resolve_kubeconfig_path(cluster_name, kubeconfig_path)
    service = get_k8s_advanced_service(effective_path)
    result = await service.batch_create_resources(resources_list, namespace)
    created = [r.get("name", r.get("kind", "")) for r in result.get("success", [])]
    failed = [r.get("name", r.get("kind", "")) for r in result.get("failed", [])]
    log_operation("batch_create_resources", "create", {"namespace": namespace, "created": created, "failed": failed}, len(failed) == 0)

    # 如果有失败且需要回滚
    if result["failed"] and rollback_on_failure and result["success"]:
        rollback_resources = [{"kind": r["kind"], "metadata": {"name": r["name"]}} for r in result["success"]]
        rollback_result = await service.batch_delete_resources(rollback_resources, namespace)
        result["rollback"] = rollback_result

    success_count = len(result.get("success", []))
    failed_count = len(result.get("failed", []))
    if success_count > 0 and failed_count > 0:
        return json_partial_success(result, success_count, failed_count)
    return json_success(result)


@mcp.tool()
@handle_tool_errors
async def batch_update_resources(resources: str, namespace: str = "default",
                                kubeconfig_path: Optional[str] = None,
                                cluster_name: Optional[str] = None) -> str:
    """批量更新资源
    
    Args:
        resources: JSON格式的资源列表
        namespace: 命名空间
        kubeconfig_path: kubeconfig 文件路径，不指定则使用 cluster_name 或默认集群
        cluster_name: 集群配置名称（clusters.json 中的 name），kubeconfig_path 未指定时使用
    """
    resources_list, err = parse_and_validate_resources(resources)
    if err:
        return json_error(err)

    effective_path = resolve_kubeconfig_path(cluster_name, kubeconfig_path)
    service = get_k8s_advanced_service(effective_path)
    result = await service.batch_update_resources(resources_list, namespace)
    updated = [r.get("name", r.get("kind", "")) for r in result.get("success", [])]
    failed = [r.get("name", r.get("kind", "")) for r in result.get("failed", [])]
    log_operation("batch_update_resources", "update", {"namespace": namespace, "updated": updated, "failed": failed}, len(failed) == 0)
    return json_success(result)


@mcp.tool()
@handle_tool_errors
async def batch_delete_resources(resources: str, namespace: str = "default",
                               grace_period_seconds: Optional[int] = None,
                               kubeconfig_path: Optional[str] = None,
                               cluster_name: Optional[str] = None) -> str:
    """批量删除资源
    
    Args:
        resources: JSON格式的资源列表
        namespace: 命名空间
        grace_period_seconds: 优雅删除等待时间
        kubeconfig_path: kubeconfig 文件路径，不指定则使用 cluster_name 或默认集群
        cluster_name: 集群配置名称（clusters.json 中的 name），kubeconfig_path 未指定时使用
    """
    resources_list, err = parse_and_validate_resources(resources)
    if err:
        return json_error(err)

    effective_path = resolve_kubeconfig_path(cluster_name, kubeconfig_path)
    service = get_k8s_advanced_service(effective_path)
    result = await service.batch_delete_resources(resources_list, namespace, grace_period_seconds)
    deleted = [r.get("name", r.get("metadata", {}).get("name", "")) for r in result.get("success", [])]
    failed = [r.get("name", r.get("metadata", {}).get("name", "")) for r in result.get("failed", [])]
    log_operation("batch_delete_resources", "delete", {"namespace": namespace, "deleted": deleted, "failed": failed}, len(failed) == 0)
    success_count, failed_count = len(deleted), len(failed)
    if success_count > 0 and failed_count > 0:
        return json_partial_success(result, success_count, failed_count)
    return json_success(result)


@mcp.tool()
@handle_tool_errors
async def batch_describe_resources(resource_specs: str, namespace: str = "default",
                                  kubeconfig_path: Optional[str] = None,
                                  cluster_name: Optional[str] = None) -> str:
    """批量获取资源详细信息
    
    Args:
        resource_specs: 资源规格列表，格式：[{"kind": "Pod", "name": "my-pod"}, {"kind": "Service", "name": "my-svc"}]
        namespace: 命名空间
        kubeconfig_path: kubeconfig 文件路径，不指定则使用 cluster_name 或默认集群
        cluster_name: 集群配置名称（clusters.json 中的 name），kubeconfig_path 未指定时使用
    
    Returns:
        批量资源详细信息
    """
    specs_list, err = parse_and_validate_resource_specs(resource_specs)
    if err:
        return json_error(err)

    effective_path = resolve_kubeconfig_path(cluster_name, kubeconfig_path)
    service = get_k8s_advanced_service(effective_path)
    result = await service.batch_describe_resources(specs_list, namespace)
    return json_success(result)


@mcp.tool()
@handle_tool_errors
async def batch_restart_resources(resources: str, namespace: str = "default",
                                 kubeconfig_path: Optional[str] = None,
                                 cluster_name: Optional[str] = None) -> str:
    """批量重启资源
    
    Args:
        resources: JSON格式的资源列表，格式：[{"kind": "Deployment", "name": "my-app"}, {"kind": "StatefulSet", "name": "my-db"}]
        namespace: 命名空间
        kubeconfig_path: kubeconfig 文件路径，不指定则使用 cluster_name 或默认集群
        cluster_name: 集群配置名称（clusters.json 中的 name），kubeconfig_path 未指定时使用
    
    Returns:
        批量重启结果
    """
    # 解析资源列表 [{"kind","name"}]
    resources_list, err = parse_and_validate_resource_specs(resources)
    if err:
        return json_error(err)

    supported_kinds = ["Deployment", "StatefulSet", "DaemonSet"]
    for resource in resources_list:
        if resource.get("kind") not in supported_kinds:
            return json_error(f"不支持的资源类型: {resource.get('kind')}，支持的类型: {supported_kinds}")

    effective_path = resolve_kubeconfig_path(cluster_name, kubeconfig_path)
    service = get_k8s_advanced_service(effective_path)
    restart_resources = []
    timestamp = datetime.now().isoformat()
    
    for resource in resources_list:
        kind = resource["kind"]
        name = resource["name"]
        
        # 构建重启资源定义
        restart_resource = {
            "apiVersion": "apps/v1",
            "kind": kind,
            "metadata": {
                "name": name,
                "namespace": namespace,
                "annotations": {
                    "kubectl.kubernetes.io/restartedAt": timestamp
                }
            },
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": timestamp
                        }
                    }
                }
            }
        }
        restart_resources.append(restart_resource)
    
    # 执行批量更新
    result = await service.batch_update_resources(restart_resources, namespace)
    
    # 格式化返回结果
    formatted_result = {
        "success": result.get("success", []),
        "failed": result.get("failed", []),
        "total": len(resources_list),
        "message": f"批量重启完成: 成功 {len(result.get('success', []))}, 失败 {len(result.get('failed', []))}"
    }
    restarted = [r.get("name", "") for r in result.get("success", [])]
    failed = [r.get("name", "") for r in result.get("failed", [])]
    log_operation("batch_restart_resources", "update", {"namespace": namespace, "restarted": restarted, "failed": failed}, len(failed) == 0)
    return json_success(formatted_result)


@mcp.tool()
@handle_tool_errors
async def batch_rollout_resources(operations: str, namespace: str = "default",
                                 kubeconfig_path: Optional[str] = None,
                                 cluster_name: Optional[str] = None) -> str:
    """批量发布操作：查看状态、回滚、暂停、恢复
    
    Args:
        operations: JSON 数组，每项格式 {"kind":"Deployment","name":"xxx","action":"status|undo|pause|resume","revision":3}
            action: status 查看发布状态, undo 回滚(不指定 revision 则回滚到上一版本, 指定 revision 则回滚到该版本), pause 暂停(仅Deployment), resume 恢复(仅Deployment)
        namespace: 命名空间
        kubeconfig_path: kubeconfig 文件路径，不指定则使用 cluster_name 或默认集群
        cluster_name: 集群配置名称（clusters.json 中的 name），kubeconfig_path 未指定时使用
    
    Returns:
        批量操作结果
    """
    ops_list, err = parse_json_array(operations, error_msg="operations 必须是有效的 JSON 数组")
    if err:
        return json_error(err)
    for i, op in enumerate(ops_list):
        if isinstance(op, dict) and op.get("action") and op.get("action") not in VALID_ROLLOUT_ACTIONS:
            return json_error(f"operations[{i}].action 必须是 {VALID_ROLLOUT_ACTIONS} 之一")
    effective_path = resolve_kubeconfig_path(cluster_name, kubeconfig_path)
    service = get_k8s_advanced_service(effective_path)
    result = await service.batch_rollout_resources(ops_list, namespace)
    # 仅对写操作（undo/pause/resume）记录日志，status 为只读不记录
    write_actions = {"undo", "pause", "resume"}
    has_write = any((op.get("action") or "").lower() in write_actions for op in ops_list if isinstance(op, dict))
    if has_write:
        success = not result.get("failed", [])
        log_operation("batch_rollout_resources", "update", {"namespace": namespace, "operations": ops_list, "result": result}, success)
    return json_success(result)


@mcp.tool()
@handle_tool_errors
async def batch_top_resources(resource_types: str, namespace: str = "default",
                             kubeconfig_path: Optional[str] = None,
                             cluster_name: Optional[str] = None) -> str:
    """批量查看 Node/Pod 的 CPU、内存使用（类似 kubectl top）
    
    Args:
        resource_types: 资源类型，JSON 数组如 ["nodes","pods"] 或 "nodes" 或 "pods"
        namespace: 命名空间（仅对 pods 有效）
        kubeconfig_path: kubeconfig 文件路径，不指定则使用 cluster_name 或默认集群
        cluster_name: 集群配置名称（clusters.json 中的 name），kubeconfig_path 未指定时使用
    
    Returns:
        nodes 和/或 pods 的 CPU、内存使用数据。依赖集群已部署 metrics-server。
    """
    types_list, err = parse_json_or_single(resource_types)
    if err:
        return json_error(err)
    effective_path = resolve_kubeconfig_path(cluster_name, kubeconfig_path)
    service = get_k8s_advanced_service(effective_path)
    result = await service.batch_top_resources(types_list, namespace)
    return json_success(result)
