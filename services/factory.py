"""
服务实例工厂
按 kubeconfig_path 缓存实例，避免重复初始化
"""
import threading
from typing import Optional

from .k8s_api import KubernetesAPIService
from .k8s_advanced_service import KubernetesAdvancedService

_api_cache: dict = {}
_advanced_cache: dict = {}
# RLock：KubernetesAdvancedService.__init__ 会调用 get_k8s_api_service，需可重入
_cache_lock = threading.RLock()


def _cache_key(path: Optional[str]) -> str:
    """生成缓存键，None 与空串视为默认"""
    return path if path else "__default__"


def get_k8s_api_service(kubeconfig_path: Optional[str] = None) -> KubernetesAPIService:
    """获取 KubernetesAPIService 实例（按 kubeconfig_path 缓存）"""
    key = _cache_key(kubeconfig_path)
    with _cache_lock:
        if key not in _api_cache:
            _api_cache[key] = KubernetesAPIService(kubeconfig_path=kubeconfig_path)
        return _api_cache[key]


def get_k8s_advanced_service(kubeconfig_path: Optional[str] = None) -> KubernetesAdvancedService:
    """获取 KubernetesAdvancedService 实例（按 kubeconfig_path 缓存）"""
    key = _cache_key(kubeconfig_path)
    with _cache_lock:
        if key not in _advanced_cache:
            _advanced_cache[key] = KubernetesAdvancedService(kubeconfig_path=kubeconfig_path)
        return _advanced_cache[key]


def clear_service_cache() -> None:
    """清空服务缓存（用于测试或切换集群后强制重新加载）"""
    with _cache_lock:
        _api_cache.clear()
        _advanced_cache.clear()
