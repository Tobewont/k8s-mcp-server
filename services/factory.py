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
    """生成缓存键：多租户时包含用户数据根目录，避免共用 kubeconfig 缓存串号"""
    from config import DATA_DIR, MCP_AUTH_ENABLED, get_user_data_root
    from utils.auth_context import get_effective_user_id

    if MCP_AUTH_ENABLED:
        uid = get_effective_user_id()
        prefix = get_user_data_root(uid)
    else:
        prefix = DATA_DIR
    p = path if path else "__default__"
    return f"{prefix}|{p}"


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


def invalidate_user_service_cache(user_id: str) -> int:
    """失效指定用户的所有 K8s 服务缓存。

    当用户的 kubeconfig 文件被更新（grant_access 重写 token）或删除
    （revoke_access）后，必须调用此函数，否则后续请求仍使用旧的
    ApiClient 实例（持有过期 token），导致 401 Unauthorized。

    Returns:
        被清除的缓存条目数
    """
    from config import get_user_data_root
    prefix = get_user_data_root(user_id) + "|"
    removed = 0
    with _cache_lock:
        for cache in (_api_cache, _advanced_cache):
            keys = [k for k in cache if k.startswith(prefix)]
            for k in keys:
                del cache[k]
                removed += 1
    return removed


def invalidate_cluster_service_cache(kubeconfig_path: Optional[str]) -> int:
    """失效指定 kubeconfig_path 对应的服务缓存。

    用于 kubeconfig 文件被外部更新（如 kubectl cp）或
    test_cluster_connection 需要强制重新加载时调用。

    Returns:
        被清除的缓存条目数
    """
    key = _cache_key(kubeconfig_path)
    removed = 0
    with _cache_lock:
        for cache in (_api_cache, _advanced_cache):
            if key in cache:
                del cache[key]
                removed += 1
    return removed


def invalidate_current_user_cache() -> int:
    """失效当前请求用户的 K8s 服务缓存。

    供 cluster_tools 等模块在 kubeconfig 变更后调用。
    非认证模式下清空全局缓存。
    """
    from config import MCP_AUTH_ENABLED
    if MCP_AUTH_ENABLED:
        from utils.auth_context import get_effective_user_id
        uid = get_effective_user_id()
        return invalidate_user_service_cache(uid)
    else:
        with _cache_lock:
            n = len(_api_cache) + len(_advanced_cache)
            _api_cache.clear()
            _advanced_cache.clear()
        return n
