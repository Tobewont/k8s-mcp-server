"""
备份和恢复工具
支持集群、命名空间、资源对象的层级备份结构
"""
import os
from typing import Dict, List, Optional, Tuple

from config import BACKUP_DIR
from services.factory import get_k8s_advanced_service
from utils.backup_paths import get_backup_search_path
from utils.cluster_config import resolve_kubeconfig_path
from utils.decorators import handle_tool_errors
from utils.operations_logger import log_operation
from utils.response import json_error, json_success

# 导入共享的MCP实例
from . import mcp


def _list_backups_local(cluster_name: Optional[str] = None, namespace: Optional[str] = None) -> List[Dict]:
    """列出本地备份文件（不依赖 K8s 连接）"""
    backups = []
    search_path = get_backup_search_path(BACKUP_DIR, cluster_name, namespace)
    if not os.path.exists(search_path):
        return backups
    for root, dirs, files in os.walk(search_path):
        for file in files:
            if file.endswith('.json') or file.endswith('.yaml'):
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, BACKUP_DIR)
                path_parts = relative_path.split(os.sep)
                backup_info = {
                    "file_path": file_path,
                    "relative_path": relative_path,
                    "cluster_name": path_parts[0] if path_parts else "unknown",
                    "namespace": None,
                    "resource_type": None,
                    "resource_name": None,
                    "timestamp": file.split('_')[-1].replace('.json', '').replace('.yaml', '') if '_' in file else "unknown"
                }
                if len(path_parts) > 2 and path_parts[1] == "namespaces":
                    backup_info["namespace"] = path_parts[2]
                if len(path_parts) > 4 and path_parts[3] == "resources":
                    backup_info["resource_type"] = path_parts[4]
                    if len(path_parts) > 5:
                        backup_info["resource_name"] = path_parts[5]
                backups.append(backup_info)
    return backups


@mcp.tool()
@handle_tool_errors
async def backup_namespace(namespace: str, cluster_name: Optional[str] = None, include_secrets: bool = True,
                          kubeconfig_path: Optional[str] = None) -> str:
    """备份命名空间
    
    Args:
        namespace: 命名空间名称
        cluster_name: 集群名称（可选）
        include_secrets: 是否包含 Secret 资源，默认 True
        kubeconfig_path: kubeconfig 文件路径，不指定则使用 cluster_name 或默认集群
    """
    effective_path = resolve_kubeconfig_path(cluster_name, kubeconfig_path)
    service = get_k8s_advanced_service(effective_path)
    backup_file = await service.backup_namespace(namespace, cluster_name, include_secrets)
    log_operation("backup_namespace", "backup", {"namespace": namespace, "cluster_name": cluster_name, "backup_file": backup_file}, True)
    return json_success({
        "success": True,
        "backup_file": backup_file,
        "message": f"命名空间 {namespace} 备份完成"
    })


@mcp.tool()
@handle_tool_errors
async def backup_resource(resource_type: str, resource_name: str, namespace: str,
                         cluster_name: Optional[str] = None, kubeconfig_path: Optional[str] = None) -> str:
    """备份特定资源
    
    Args:
        resource_type: 资源类型（deployment, service, configmap等）
        resource_name: 资源名称
        namespace: 命名空间
        cluster_name: 集群名称（可选）
        kubeconfig_path: kubeconfig 文件路径，不指定则使用 cluster_name 或默认集群
    """
    effective_path = resolve_kubeconfig_path(cluster_name, kubeconfig_path)
    service = get_k8s_advanced_service(effective_path)
    backup_file = await service.backup_specific_resource(resource_type, resource_name, namespace, cluster_name)
    log_operation("backup_resource", "backup", {"resource_type": resource_type, "resource_name": resource_name, "namespace": namespace, "backup_file": backup_file}, True)
    return json_success({
        "success": True,
        "backup_file": backup_file,
        "message": f"资源 {resource_type}/{resource_name} 备份完成"
    })


def _validate_and_resolve_backup_path(backup_file: str) -> Tuple[Optional[str], Optional[str]]:
    """校验备份路径在 BACKUP_DIR 下并解析为绝对路径。返回 (resolved_path, error_msg)，成功时 error_msg 为 None。"""
    if not backup_file or not str(backup_file).strip():
        return None, "backup_file 不能为空"
    abs_backup_dir = os.path.abspath(BACKUP_DIR)
    abs_backup = os.path.abspath(
        os.path.join(BACKUP_DIR, backup_file) if not os.path.isabs(backup_file) else backup_file
    )
    try:
        if os.path.commonpath([abs_backup, abs_backup_dir]) != abs_backup_dir:
            return None, "备份路径必须在备份目录下"
    except ValueError:
        return None, "备份路径不合法"
    return abs_backup, None


@mcp.tool()
@handle_tool_errors
async def restore_from_backup(backup_file: str, target_namespace: Optional[str] = None,
                             target_cluster: Optional[str] = None, kubeconfig_path: Optional[str] = None) -> str:
    """从备份恢复资源
    
    Args:
        backup_file: 备份文件路径
        target_namespace: 目标命名空间（可选）
        target_cluster: 目标集群（可选）
        kubeconfig_path: kubeconfig 文件路径，不指定则使用默认集群
    """
    resolved_path, err = _validate_and_resolve_backup_path(backup_file)
    if err:
        return json_error(err)
    effective_path = resolve_kubeconfig_path(None, kubeconfig_path)
    service = get_k8s_advanced_service(effective_path)
    results = await service.restore_from_backup(resolved_path, target_namespace, target_cluster)
    success = results.get("success", True) if isinstance(results, dict) else True
    log_operation("restore_from_backup", "restore", {"backup_file": backup_file, "target_namespace": target_namespace, "target_cluster": target_cluster}, success)
    return json_success(results)


@mcp.tool()
@handle_tool_errors
async def list_backups(cluster_name: Optional[str] = None, namespace: Optional[str] = None) -> str:
    """列出备份文件（仅读取本地备份目录，无需 K8s 连接）
    
    Args:
        cluster_name: 集群名称（可选）
        namespace: 命名空间（可选）
    """
    backups = _list_backups_local(cluster_name, namespace)
    return json_success({
        "success": True,
        "backups": backups,
        "total": len(backups)
    }) 