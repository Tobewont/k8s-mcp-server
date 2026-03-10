"""
Kubernetes 进阶服务 - 基础类与常量
"""
from typing import Dict, Callable, Optional

from services.k8s_constants import API_VERSION_MAP as _API_VERSION_MAP


class ResourceConfig:
    """资源配置类"""

    def __init__(self, kind: str, list_method: str, get_method: str, skip_condition: Optional[Callable] = None):
        self.kind = kind
        self.list_method = list_method
        self.get_method = get_method
        self.skip_condition = skip_condition


class ResourceManager:
    """资源管理器，统一管理资源配置和操作"""

    def __init__(self, k8s_service):
        self.k8s_service = k8s_service
        self._resource_configs = self._init_resource_configs()

    def _init_resource_configs(self):
        """初始化资源配置"""
        return {
            "deployments": ResourceConfig("Deployment", "list_deployments", "get_deployment"),
            "statefulsets": ResourceConfig("StatefulSet", "list_statefulsets", "get_statefulset"),
            "daemonsets": ResourceConfig("DaemonSet", "list_daemonsets", "get_daemonset"),
            "services": ResourceConfig("Service", "list_services", "get_service"),
            "configmaps": ResourceConfig("ConfigMap", "list_configmaps", "get_configmap",
                                         skip_condition=lambda name: name in ["kube-root-ca.crt"]),
            "secrets": ResourceConfig("Secret", "list_secrets", "get_secret",
                                      skip_condition=lambda name: name.startswith("default-token-")),
            "jobs": ResourceConfig("Job", "list_jobs", "get_job"),
            "cronjobs": ResourceConfig("CronJob", "list_cronjobs", "get_cronjob"),
            "ingresses": ResourceConfig("Ingress", "list_ingresses", "get_ingress"),
            "persistentvolumeclaims": ResourceConfig("PersistentVolumeClaim", "list_persistentvolumeclaims", "get_persistentvolumeclaim"),
            "serviceaccounts": ResourceConfig("ServiceAccount", "list_serviceaccounts", "get_serviceaccount",
                                              skip_condition=lambda name: name == "default"),
            "roles": ResourceConfig("Role", "list_roles", "get_role"),
            "rolebindings": ResourceConfig("RoleBinding", "list_role_bindings", "get_role_binding"),
            "horizontalpodautoscalers": ResourceConfig("HorizontalPodAutoscaler", "list_hpas", "get_hpa"),
            "networkpolicies": ResourceConfig("NetworkPolicy", "list_network_policies", "get_network_policy"),
            "resourcequotas": ResourceConfig("ResourceQuota", "list_resource_quotas", "get_resource_quota")
        }

    def get_resource_config(self, resource_type: str):
        """获取资源配置"""
        return self._resource_configs.get(resource_type)

    def get_operation_method(self, resource_type: str, operation: str, namespace: str = "default"):
        """获取操作方法"""
        config = self.get_resource_config(resource_type)
        if not config:
            raise ValueError(f"不支持的资源类型: {resource_type}")

        if operation == "list":
            return lambda: getattr(self.k8s_service, config.list_method)(namespace=namespace)
        elif operation == "get":
            return lambda name: getattr(self.k8s_service, config.get_method)(name, namespace)
        else:
            raise ValueError(f"不支持的操作类型: {operation}")


class BatchOperationResult:
    """批量操作结果类"""

    def __init__(self):
        self.success = []
        self.failed = []
        self.total = 0

    def add_success(self, resource_info):
        self.success.append(resource_info)
        self.total += 1

    def add_failure(self, resource_info, error):
        self.failed.append({"resource": resource_info, "error": str(error)})
        self.total += 1

    def to_dict(self):
        return {
            "success": self.success,
            "failed": self.failed,
            "total": self.total
        }


# 使用统一的 API 版本映射（来自 k8s_constants）
API_VERSION_MAP: Dict[str, str] = dict(_API_VERSION_MAP)

# resource_type (复数) -> kind，用于动态解析
RESOURCE_TYPE_TO_KIND: Dict[str, str] = {
    "deployments": "Deployment", "statefulsets": "StatefulSet", "daemonsets": "DaemonSet",
    "services": "Service", "configmaps": "ConfigMap", "secrets": "Secret",
    "jobs": "Job", "cronjobs": "CronJob", "ingresses": "Ingress",
    "persistentvolumeclaims": "PersistentVolumeClaim", "persistentvolumes": "PersistentVolume",
    "serviceaccounts": "ServiceAccount", "roles": "Role", "rolebindings": "RoleBinding",
    "clusterroles": "ClusterRole", "clusterrolebindings": "ClusterRoleBinding",
    "namespaces": "Namespace", "pods": "Pod", "nodes": "Node",
    "horizontalpodautoscalers": "HorizontalPodAutoscaler", "networkpolicies": "NetworkPolicy",
    "resourcequotas": "ResourceQuota", "storageclasses": "StorageClass",
}
