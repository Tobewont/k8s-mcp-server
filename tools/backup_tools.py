"""
备份和恢复工具。
备份文件按集群、命名空间、资源类型存放。
"""
from typing import Optional, Tuple

from config import BACKUP_DIR
from services.factory import get_k8s_advanced_service
from utils.backup_paths import list_backup_files, resolve_backup_file
from utils.cluster_config import resolve_kubeconfig_path
from utils.decorators import handle_tool_errors
from utils.operations_logger import log_operation
from utils.resource_yaml import short_error
from utils.response import json_error, json_partial_success, json_success

# 导入共享的MCP实例
from . import mcp


@mcp.tool()
@handle_tool_errors
async def backup_namespace(namespace: str, cluster_name: Optional[str] = None, include_secrets: bool = True,
                          kubeconfig_path: Optional[str] = None) -> str:
    """备份命名空间中的指定内置资源和自定义资源，保存为多文档 YAML。Secret 默认包含，data 原样保留。
    
    Args:
        namespace: 命名空间名称
        cluster_name: 集群名称（可选）
        include_secrets: 是否包含 Secret，默认 True
        kubeconfig_path: kubeconfig 文件路径，不指定则使用 cluster_name 或默认集群
    """
    effective_path = resolve_kubeconfig_path(cluster_name, kubeconfig_path)
    service = get_k8s_advanced_service(effective_path)
    try:
        info = await service.backup_namespace(namespace, cluster_name, include_secrets)
    except Exception as exc:
        log_operation("backup_namespace", "backup", {"namespace": namespace, "cluster_name": cluster_name}, False)
        return json_error(short_error(exc))
    message = f"命名空间 {namespace} 备份完成"
    skipped = info.get("skipped") or []
    if skipped:
        names = ", ".join(item.get("resource_type", "") for item in skipped)
        message = f"{message}，跳过: {names}"
    log_operation("backup_namespace", "backup", {"namespace": namespace, "cluster_name": cluster_name, "backup_file": info.get("backup_file")}, True)
    payload = {
        "success": True,
        "backup_file": info.get("backup_file"),
        "resource_count": info.get("resource_count", 0),
        "message": message,
    }
    if skipped:
        payload["skipped"] = skipped
    return json_success(payload)


@mcp.tool()
@handle_tool_errors
async def backup_resource(resource_type: str, resource_name: str, namespace: str,
                         api_version: Optional[str] = None,
                         cluster_name: Optional[str] = None, kubeconfig_path: Optional[str] = None) -> str:
    """备份指定资源的原样 YAML。支持内置资源和自定义资源。
    
    Args:
        resource_type: 类型名、Kind 或复数名，如 deployment、Secret、mysqls
        resource_name: 资源名称
        namespace: 命名空间
        api_version: API 版本。同一 Kind 属于多个 API 组时必填，如 example.com/v1
        cluster_name: 集群名称（可选）
        kubeconfig_path: kubeconfig 文件路径，不指定则使用 cluster_name 或默认集群
    """
    effective_path = resolve_kubeconfig_path(cluster_name, kubeconfig_path)
    service = get_k8s_advanced_service(effective_path)
    try:
        backup_file = await service.backup_specific_resource(
            resource_type, resource_name, namespace, cluster_name, api_version
        )
    except Exception as exc:
        log_operation("backup_resource", "backup", {"resource_type": resource_type, "resource_name": resource_name, "namespace": namespace}, False)
        return json_error(short_error(exc))
    log_operation("backup_resource", "backup", {"resource_type": resource_type, "resource_name": resource_name, "namespace": namespace, "backup_file": backup_file}, True)
    return json_success({
        "success": True,
        "backup_file": backup_file,
        "message": f"资源 {resource_type}/{resource_name} 备份完成"
    })


def _validate_and_resolve_backup_path(backup_file: str) -> Tuple[Optional[str], Optional[str]]:
    """返回备份目录内的真实路径。失败时返回 (None, 错误信息)。"""
    try:
        return resolve_backup_file(BACKUP_DIR, backup_file), None
    except (ValueError, FileNotFoundError) as exc:
        return None, str(exc)


@mcp.tool()
@handle_tool_errors
async def restore_from_backup(backup_file: str, target_namespace: Optional[str] = None,
                             target_cluster: Optional[str] = None, kubeconfig_path: Optional[str] = None) -> str:
    """按备份文件写回资源。不存在则创建，已存在则替换。不提交 status，以及 uid、resourceVersion、generation、creationTimestamp、managedFields、selfLink、deletionTimestamp、deletionGracePeriodSeconds。
    
    Args:
        backup_file: 备份文件路径，必须位于备份目录内
        target_namespace: 目标命名空间。指定时必须与资源 metadata.namespace 一致
        target_cluster: 目标集群（可选）
        kubeconfig_path: kubeconfig 文件路径，不指定则使用 target_cluster 或默认集群
    """
    resolved_path, err = _validate_and_resolve_backup_path(backup_file)
    if err:
        return json_error(err)
    effective_path = resolve_kubeconfig_path(target_cluster, kubeconfig_path)
    service = get_k8s_advanced_service(effective_path)
    try:
        results = await service.restore_from_backup(resolved_path, target_namespace)
    except Exception as exc:
        log_operation("restore_from_backup", "restore", {"backup_file": backup_file, "target_namespace": target_namespace, "target_cluster": target_cluster}, False)
        return json_error(short_error(exc))
    restored = results.get("restored") or []
    failed = results.get("failed") or []
    payload = {"restored": restored, "failed": failed, "total": results.get("total", 0)}
    log_operation("restore_from_backup", "restore", {"backup_file": backup_file, "target_namespace": target_namespace, "target_cluster": target_cluster}, not failed)
    if failed and restored:
        return json_partial_success(payload, len(restored), len(failed))
    if failed:
        return json_error("恢复失败", **payload)
    return json_success(payload)


@mcp.tool()
@handle_tool_errors
async def list_backups(cluster_name: Optional[str] = None, namespace: Optional[str] = None) -> str:
    """列出备份文件（仅读取本地备份目录，无需 K8s 连接）
    
    Args:
        cluster_name: 集群名称（可选）
        namespace: 命名空间（可选）
    """
    backups = list_backup_files(BACKUP_DIR, cluster_name, namespace)
    return json_success({
        "success": True,
        "backups": backups,
        "total": len(backups)
    }) 