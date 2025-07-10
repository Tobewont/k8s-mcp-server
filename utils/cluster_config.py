"""
集群配置管理器
"""
import json
import os
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from config import CLUSTERS_CONFIG_FILE, KUBECONFIGS_DIR

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
    """集群配置管理器"""
    
    def __init__(self):
        """初始化集群配置管理器"""
        self.config_file = CLUSTERS_CONFIG_FILE
        self.kubeconfigs_dir = KUBECONFIGS_DIR
        self._ensure_config_file()
    
    def _ensure_config_file(self):
        """确保配置文件存在"""
        if not os.path.exists(self.config_file):
            self._save_clusters([])
    
    def _load_clusters(self) -> List[Dict[str, Any]]:
        """加载集群配置"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
    
    def _save_clusters(self, clusters: List[Dict[str, Any]]):
        """保存集群配置"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(clusters, f, indent=2, ensure_ascii=False)
    
    def add_cluster(self, cluster_info: ClusterInfo) -> bool:
        """
        添加集群配置
        
        Args:
            cluster_info: 集群信息
            
        Returns:
            是否添加成功
        """
        clusters = self._load_clusters()
        
        # 检查是否已存在同名集群
        for cluster in clusters:
            if cluster['name'] == cluster_info.name:
                return False
        
        # 如果设置为默认集群，取消其他集群的默认状态
        if cluster_info.is_default:
            for cluster in clusters:
                cluster['is_default'] = False
        
        clusters.append(asdict(cluster_info))
        self._save_clusters(clusters)
        return True
    
    def update_cluster(self, cluster_info: ClusterInfo) -> bool:
        """
        更新集群配置
        
        Args:
            cluster_info: 集群信息
            
        Returns:
            是否更新成功
        """
        clusters = self._load_clusters()
        
        for i, cluster in enumerate(clusters):
            if cluster['name'] == cluster_info.name:
                # 如果设置为默认集群，取消其他集群的默认状态
                if cluster_info.is_default:
                    for other_cluster in clusters:
                        other_cluster['is_default'] = False
                
                clusters[i] = asdict(cluster_info)
                self._save_clusters(clusters)
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
        clusters = self._load_clusters()
        initial_count = len(clusters)
        clusters = [cluster for cluster in clusters if cluster['name'] != name]
        
        if len(clusters) < initial_count:
            self._save_clusters(clusters)
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
        clusters = self._load_clusters()
        found = False
        
        for cluster in clusters:
            if cluster['name'] == name:
                cluster['is_default'] = True
                found = True
            else:
                cluster['is_default'] = False
        
        if found:
            self._save_clusters(clusters)
        
        return found
    
    def save_kubeconfig(self, name: str, kubeconfig_content: str) -> str:
        """
        保存 kubeconfig 文件
        
        Args:
            name: 集群名称
            kubeconfig_content: kubeconfig 内容
            
        Returns:
            保存的文件路径
        """
        kubeconfig_path = os.path.join(self.kubeconfigs_dir, f"{name}.yaml")
        
        with open(kubeconfig_path, 'w', encoding='utf-8') as f:
            f.write(kubeconfig_content)
        
        return kubeconfig_path 