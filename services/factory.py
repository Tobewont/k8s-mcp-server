"""
服务实例工厂
"""
from typing import Optional

from .k8s_api_service import KubernetesAPIService
from .k8s_advanced_service import KubernetesAdvancedService


def get_k8s_api_service(kubeconfig_path: Optional[str] = None) -> KubernetesAPIService:
    """创建 KubernetesAPIService 实例"""
    svc = KubernetesAPIService()
    svc.load_config(kubeconfig_path=kubeconfig_path)
    return svc


def get_k8s_advanced_service(kubeconfig_path: Optional[str] = None) -> KubernetesAdvancedService:
    """创建 KubernetesAdvancedService 实例"""
    return KubernetesAdvancedService(kubeconfig_path=kubeconfig_path)
