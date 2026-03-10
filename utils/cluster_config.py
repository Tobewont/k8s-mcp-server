"""
集群配置管理器
"""
import json
import logging
import os
import threading
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from config import CLUSTERS_CONFIG_FILE, KUBECONFIGS_DIR

logger = logging.getLogger(__name__)


def resolve_kubeconfig_path(
    cluster_name: Optional[str] = None,
    kubeconfig_path: Optional[str] = None,
) -> Optional[str]:
    """
    解析得到实际使用的 kubeconfig 文件路径。
    
    优先级：kubeconfig_path（若为有效路径）> cluster_name（从 clusters.json 查找）> 默认集群 > None
    
    Args:
        cluster_name: 集群配置名称（clusters.json 中的 name）
        kubeconfig_path: kubeconfig 文件路径，可直接传入
        
    Returns:
        解析后的 kubeconfig 路径，None 表示使用默认集群
    """
    if kubeconfig_path and os.path.isfile(kubeconfig_path):
        return kubeconfig_path
    if cluster_name:
        try:
            cluster = get_cluster_config_manager().get_cluster(cluster_name)
            return cluster.kubeconfig_path if cluster else None
        except ValueError:
            return None
    default = get_cluster_config_manager().get_default_cluster()
    return default.kubeconfig_path if default else None


def get_kubeconfig_path(name: str, for_write: bool = False) -> Optional[str]:
    """
    获取 kubeconfig 文件路径，支持 .yaml 和 .yml 扩展名。
    
    Args:
        name: 配置名称（不含扩展名）
        for_write: 若为 True，返回用于保存的路径（固定 .yaml）；否则返回已存在文件的路径
    
    Returns:
        文件路径，若不存在且 for_write=False 则返回 None
    """
    if for_write:
        return os.path.join(KUBECONFIGS_DIR, f"{name}.yaml")
    for ext in (".yaml", ".yml"):
        path = os.path.join(KUBECONFIGS_DIR, f"{name}{ext}")
        if os.path.exists(path):
            return path
    return None


@dataclass
class ClusterInfo:
    """集群信息数据类"""
    name: str
    kubeconfig_path: str
    service_account: Optional[str] = None
    namespace: Optional[str] = "default"
    is_default: bool = False
    description: Optional[str] = None


class ClusterConfigManager:
    """集群配置管理器（单例，线程安全）"""

    _lock = threading.Lock()

    def __init__(self):
        """初始化集群配置管理器"""
        self.config_file = CLUSTERS_CONFIG_FILE
        self.kubeconfigs_dir = KUBECONFIGS_DIR
        self._ensure_config_file()
    
    def _ensure_config_file(self):
        """确保配置文件存在"""
        if not os.path.exists(self.config_file):
            with self._lock:
                self._save_clusters_raw([])
    
    def _load_clusters_raw(self) -> List[Dict[str, Any]]:
        """加载集群配置（内部使用，调用方需持有锁）"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_clusters_raw(self, clusters: List[Dict[str, Any]]) -> None:
        """保存集群配置（内部使用，调用方需持有锁）"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(clusters, f, indent=2, ensure_ascii=False)
        except (IOError, OSError) as e:
            logger.exception("保存集群配置失败: %s", e)
            raise

    def _load_clusters(self) -> List[Dict[str, Any]]:
        """加载集群配置（线程安全）"""
        with self._lock:
            return self._load_clusters_raw()

    def _save_clusters(self, clusters: List[Dict[str, Any]]) -> None:
        """保存集群配置（线程安全）"""
        with self._lock:
            self._save_clusters_raw(clusters)

    def add_cluster(self, cluster_info: ClusterInfo) -> bool:
        """
        添加集群配置
        
        Args:
            cluster_info: 集群信息
            
        Returns:
            是否添加成功
        """
        with self._lock:
            clusters = self._load_clusters_raw()
            for cluster in clusters:
                if cluster['name'] == cluster_info.name:
                    return False
            if cluster_info.is_default:
                for cluster in clusters:
                    cluster['is_default'] = False
            clusters.append(asdict(cluster_info))
            self._save_clusters_raw(clusters)
            return True

    def update_cluster(self, cluster_info: ClusterInfo) -> bool:
        """
        更新集群配置
        
        Args:
            cluster_info: 集群信息
            
        Returns:
            是否更新成功
        """
        with self._lock:
            clusters = self._load_clusters_raw()
            for i, cluster in enumerate(clusters):
                if cluster['name'] == cluster_info.name:
                    if cluster_info.is_default:
                        for other_cluster in clusters:
                            other_cluster['is_default'] = False
                    clusters[i] = asdict(cluster_info)
                    self._save_clusters_raw(clusters)
                    return True
            return False

    def remove_cluster(self, name: str) -> bool:
        """
        移除集群配置
        
        Args:
            name: 集群名称
            
        Returns:
            是否移除成功
        """
        with self._lock:
            clusters = self._load_clusters_raw()
            initial_count = len(clusters)
            clusters = [c for c in clusters if c['name'] != name]
            if len(clusters) < initial_count:
                self._save_clusters_raw(clusters)
                return True
            return False

    def get_cluster(self, name: str) -> ClusterInfo:
        """
        获取集群配置
        
        Args:
            name: 集群名称
            
        Returns:
            集群信息
            
        Raises:
            ValueError: 集群不存在
        """
        clusters = self._load_clusters()
        
        for cluster in clusters:
            if cluster['name'] == name:
                return ClusterInfo(**cluster)
        
        raise ValueError(f"集群 '{name}' 不存在")
    
    def list_clusters(self) -> List[ClusterInfo]:
        """
        列出所有集群
        
        Returns:
            集群信息列表
        """
        clusters = self._load_clusters()
        return [ClusterInfo(**cluster) for cluster in clusters]
    
    def get_default_cluster(self) -> Optional[ClusterInfo]:
        """
        获取默认集群
        
        Returns:
            默认集群信息，如果没有默认集群则返回 None
        """
        clusters = self._load_clusters()
        
        for cluster in clusters:
            if cluster.get('is_default', False):
                return ClusterInfo(**cluster)
        
        return None
    
    def set_default_cluster(self, name: str) -> bool:
        """
        设置默认集群
        
        Args:
            name: 集群名称
            
        Returns:
            是否设置成功
        """
        with self._lock:
            clusters = self._load_clusters_raw()
            found = False
            for cluster in clusters:
                if cluster['name'] == name:
                    cluster['is_default'] = True
                    found = True
                else:
                    cluster['is_default'] = False
            if found:
                self._save_clusters_raw(clusters)
            return found
    
    def save_kubeconfig(self, name: str, kubeconfig_content: str) -> str:
        """
        保存 kubeconfig 文件（统一使用 .yaml 扩展名）
        
        Args:
            name: 集群名称
            kubeconfig_content: kubeconfig 内容
            
        Returns:
            保存的文件路径
        """
        os.makedirs(self.kubeconfigs_dir, exist_ok=True)
        kubeconfig_path = get_kubeconfig_path(name, for_write=True)
        # 若存在同名 .yml，删除以避免重复
        yml_path = os.path.join(self.kubeconfigs_dir, f"{name}.yml")
        if os.path.exists(yml_path):
            os.remove(yml_path)
        with open(kubeconfig_path, 'w', encoding='utf-8') as f:
            f.write(kubeconfig_content)
        return kubeconfig_path


_cluster_config_manager: Optional[ClusterConfigManager] = None


def get_cluster_config_manager() -> ClusterConfigManager:
    """获取 ClusterConfigManager 单例"""
    global _cluster_config_manager
    if _cluster_config_manager is None:
        _cluster_config_manager = ClusterConfigManager()
    return _cluster_config_manager
