"""
备份路径公共逻辑
统一 backup_tools 与 backup_restore 的路径构建
"""
import os
from typing import List, Optional


def get_backup_path(
    base_dir: str,
    cluster_name: str,
    namespace: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_name: Optional[str] = None,
    create_dirs: bool = False,
) -> str:
    """
    获取备份目录或文件的父路径。
    
    Args:
        base_dir: 备份根目录
        cluster_name: 集群名称
        namespace: 命名空间（可选）
        resource_type: 资源类型（可选）
        resource_name: 资源名称（可选）
        create_dirs: 是否创建目录
        
    Returns:
        路径字符串，如 data/backup/cluster/namespaces/ns/resources/deployment/resource_name
    """
    path_parts: List[str] = [base_dir, cluster_name]
    if namespace:
        path_parts.extend(["namespaces", namespace])
    if resource_type:
        path_parts.extend(["resources", resource_type])
    if resource_name:
        path_parts.append(resource_name)
    path = os.path.join(*path_parts)
    if create_dirs:
        os.makedirs(path, exist_ok=True)
    return path


def get_backup_search_path(
    base_dir: str,
    cluster_name: Optional[str] = None,
    namespace: Optional[str] = None,
) -> str:
    """
    获取备份搜索路径（仅读，不创建目录）。
    用于列出/搜索备份文件。
    
    Args:
        base_dir: 备份根目录
        cluster_name: 集群名称（可选）
        namespace: 命名空间（可选）
        
    Returns:
        搜索路径
    """
    path_parts: List[str] = [base_dir]
    if cluster_name:
        path_parts.append(cluster_name)
        if namespace:
            path_parts.extend(["namespaces", namespace])
    return os.path.join(*path_parts)
