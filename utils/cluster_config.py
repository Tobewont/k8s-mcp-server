"""
集群配置管理器
"""
import json
import logging
import os
import threading
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from config import DATA_DIR, get_user_data_root
from utils.auth_context import get_effective_user_id

logger = logging.getLogger(__name__)

_cluster_managers: Dict[str, "ClusterConfigManager"] = {}
_managers_lock = threading.Lock()


def _is_path_within(path: str, base: str) -> bool:
    """检查 path 是否在 base 目录内（防止路径穿越）"""
    try:
        real_path = os.path.realpath(path)
        real_base = os.path.realpath(base)
        return real_path.startswith(real_base + os.sep) or real_path == real_base
    except (OSError, ValueError):
        return False


def resolve_kubeconfig_path(
    cluster_name: Optional[str] = None,
    kubeconfig_path: Optional[str] = None,
) -> Optional[str]:
    """
    解析得到实际使用的 kubeconfig 文件路径。

    优先级：kubeconfig_path（若为有效路径且在当前用户数据目录内）> cluster_name（从 clusters.json 查找）> 默认集群 > None

    安全：kubeconfig_path 只允许指向当前用户自己的数据目录，防止跨用户读取。
    """
    if kubeconfig_path and os.path.isfile(kubeconfig_path):
        uid = get_effective_user_id()
        user_root = get_user_data_root(uid)
        if not _is_path_within(kubeconfig_path, user_root):
            logger.warning(
                "拒绝访问用户数据目录之外的 kubeconfig 路径: path=%s, allowed_root=%s",
                kubeconfig_path, user_root,
            )
            return None
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
    """根据当前用户数据目录解析 kubeconfig 路径（兼容旧接口）"""
    return get_cluster_config_manager().get_kubeconfig_path(name, for_write=for_write)


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
    """集群配置管理器（按用户数据目录隔离）"""

    _lock = threading.Lock()

    def __init__(self, base_dir: Optional[str] = None) -> None:
        self.base_dir = base_dir if base_dir is not None else DATA_DIR
        self.config_file = os.path.join(self.base_dir, "clusters.json")
        self.kubeconfigs_dir = os.path.join(self.base_dir, "kubeconfigs")
        self._ensure_config_file()

    def get_kubeconfig_path(self, name: str, for_write: bool = False) -> Optional[str]:
        """在管理器对应目录下解析 kubeconfig 路径"""
        kd = self.kubeconfigs_dir
        if for_write:
            return os.path.join(kd, f"{name}.yaml")
        for ext in (".yaml", ".yml"):
            path = os.path.join(kd, f"{name}{ext}")
            if os.path.exists(path):
                return path
        return None

    def _ensure_config_file(self) -> None:
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.kubeconfigs_dir, exist_ok=True)
        if not os.path.exists(self.config_file):
            with self._lock:
                self._save_clusters_raw([])

    def _load_clusters_raw(self) -> List[Dict[str, Any]]:
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_clusters_raw(self, clusters: List[Dict[str, Any]]) -> None:
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(clusters, f, indent=2, ensure_ascii=False)
        except (IOError, OSError) as e:
            logger.exception("保存集群配置失败: %s", e)
            raise

    def _load_clusters(self) -> List[Dict[str, Any]]:
        with self._lock:
            return self._load_clusters_raw()

    def _save_clusters(self, clusters: List[Dict[str, Any]]) -> None:
        with self._lock:
            self._save_clusters_raw(clusters)

    def add_cluster(self, cluster_info: ClusterInfo) -> bool:
        with self._lock:
            clusters = self._load_clusters_raw()
            for cluster in clusters:
                if cluster["name"] == cluster_info.name:
                    return False
            if cluster_info.is_default:
                for cluster in clusters:
                    cluster["is_default"] = False
            clusters.append(asdict(cluster_info))
            self._save_clusters_raw(clusters)
            return True

    def update_cluster(self, cluster_info: ClusterInfo) -> bool:
        with self._lock:
            clusters = self._load_clusters_raw()
            for i, cluster in enumerate(clusters):
                if cluster["name"] == cluster_info.name:
                    if cluster_info.is_default:
                        for other_cluster in clusters:
                            other_cluster["is_default"] = False
                    clusters[i] = asdict(cluster_info)
                    self._save_clusters_raw(clusters)
                    return True
            return False

    def remove_cluster(self, name: str) -> bool:
        with self._lock:
            clusters = self._load_clusters_raw()
            initial_count = len(clusters)
            clusters = [c for c in clusters if c["name"] != name]
            if len(clusters) < initial_count:
                self._save_clusters_raw(clusters)
                return True
            return False

    def get_cluster(self, name: str) -> ClusterInfo:
        clusters = self._load_clusters()
        for cluster in clusters:
            if cluster["name"] == name:
                return ClusterInfo(**cluster)
        raise ValueError(f"集群 '{name}' 不存在")

    def list_clusters(self) -> List[ClusterInfo]:
        clusters = self._load_clusters()
        return [ClusterInfo(**cluster) for cluster in clusters]

    def get_default_cluster(self) -> Optional[ClusterInfo]:
        clusters = self._load_clusters()
        for cluster in clusters:
            if cluster.get("is_default", False):
                return ClusterInfo(**cluster)
        return None

    def set_default_cluster(self, name: str) -> bool:
        with self._lock:
            clusters = self._load_clusters_raw()
            found = False
            for cluster in clusters:
                if cluster["name"] == name:
                    cluster["is_default"] = True
                    found = True
                else:
                    cluster["is_default"] = False
            if found:
                self._save_clusters_raw(clusters)
            return found

    def save_kubeconfig(self, name: str, kubeconfig_content: str) -> str:
        os.makedirs(self.kubeconfigs_dir, exist_ok=True)
        kubeconfig_path = self.get_kubeconfig_path(name, for_write=True)
        assert kubeconfig_path is not None
        yml_path = os.path.join(self.kubeconfigs_dir, f"{name}.yml")
        if os.path.exists(yml_path):
            os.remove(yml_path)
        with open(kubeconfig_path, "w", encoding="utf-8") as f:
            f.write(kubeconfig_content)
        return kubeconfig_path


def _manager_cache_key() -> str:
    uid = get_effective_user_id()
    root = get_user_data_root(uid)
    return root


def get_cluster_config_manager() -> ClusterConfigManager:
    """按当前用户上下文返回 ClusterConfigManager（同进程内缓存）"""
    key = _manager_cache_key()
    with _managers_lock:
        if key not in _cluster_managers:
            _cluster_managers[key] = ClusterConfigManager(base_dir=key)
        return _cluster_managers[key]


def reset_cluster_config_managers() -> None:
    """清空管理器缓存（仅测试）"""
    global _cluster_managers
    with _managers_lock:
        _cluster_managers.clear()
