"""
备份和恢复工具
支持集群、命名空间、资源对象的层级备份结构
"""

import yaml
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from services.k8s_advanced_service import KubernetesAdvancedService


# 导入共享的MCP实例
from . import mcp


@mcp.tool()
async def backup_namespace(namespace: str, cluster_name: str = None, include_secrets: bool = True) -> str:
    """备份命名空间
    
    Args:
        namespace: 命名空间名称
        cluster_name: 集群名称（可选）
    """
    try:
        service = KubernetesAdvancedService()
        backup_file = await service.backup_namespace(namespace, cluster_name, include_secrets)
        
        return json.dumps({
            "success": True,
            "backup_file": backup_file,
            "message": f"命名空间 {namespace} 备份完成"
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def backup_resource(resource_type: str, resource_name: str, namespace: str, 
                         cluster_name: str = None) -> str:
    """备份特定资源
    
    Args:
        resource_type: 资源类型（deployment, service, configmap等）
        resource_name: 资源名称
        namespace: 命名空间
        cluster_name: 集群名称（可选）
    """
    try:
        service = KubernetesAdvancedService()
        backup_file = await service.backup_specific_resource(resource_type, resource_name, namespace, cluster_name)
        
        return json.dumps({
            "success": True,
            "backup_file": backup_file,
            "message": f"资源 {resource_type}/{resource_name} 备份完成"
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def restore_from_backup(backup_file: str, target_namespace: str = None, 
                             target_cluster: str = None) -> str:
    """从备份恢复资源
    
    Args:
        backup_file: 备份文件路径
        target_namespace: 目标命名空间（可选）
        target_cluster: 目标集群（可选）
    """
    try:
        service = KubernetesAdvancedService()
        results = await service.restore_from_backup(backup_file, target_namespace, target_cluster)
        
        return json.dumps(results, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2)


@mcp.tool()
async def list_backups(cluster_name: str = None, namespace: str = None) -> str:
    """列出备份文件
    
    Args:
        cluster_name: 集群名称（可选）
        namespace: 命名空间（可选）
    """
    try:
        service = KubernetesAdvancedService()
        backups = service.list_backups(cluster_name, namespace)
        
        return json.dumps({
            "success": True,
            "backups": backups,
            "total": len(backups)
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2) 