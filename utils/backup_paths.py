"""
备份路径公共逻辑
统一 backup_tools 与 backup_restore 的路径构建，含过期清理
"""
import logging
import os
import time
from typing import List, Optional

logger = logging.getLogger(__name__)

_last_cleanup_ts: float = 0.0
_CLEANUP_INTERVAL: float = 3600.0  # 最多每小时执行一次清理


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


def cleanup_expired_backups(base_dir: str, retention_days: int) -> int:
    """删除超过保留期限的备份文件，并清理残留空目录。

    内置节流：同一进程内最多每小时执行一次实际扫描，其余调用直接返回 0。

    Args:
        base_dir: 备份根目录
        retention_days: 保留天数（按文件 mtime 计算），0 表示不清理

    Returns:
        本次实际删除的文件数
    """
    global _last_cleanup_ts

    if retention_days <= 0:
        return 0

    now = time.time()
    if now - _last_cleanup_ts < _CLEANUP_INTERVAL:
        return 0
    _last_cleanup_ts = now

    if not os.path.isdir(base_dir):
        return 0

    cutoff = now - retention_days * 86400
    deleted = 0

    for root, _dirs, files in os.walk(base_dir, topdown=False):
        for fname in files:
            if not (fname.endswith(".yaml") or fname.endswith(".json")):
                continue
            fpath = os.path.join(root, fname)
            try:
                if os.path.getmtime(fpath) < cutoff:
                    os.unlink(fpath)
                    deleted += 1
            except OSError:
                pass
        # 清理空目录（不删除根目录本身）
        if root != base_dir:
            try:
                if not os.listdir(root):
                    os.rmdir(root)
            except OSError:
                pass

    if deleted:
        logger.info("清理过期备份: 删除 %d 个文件（保留 %d 天）", deleted, retention_days)
    return deleted
