"""
Kubernetes 资源常量 - 统一 API 版本与资源类型映射
"""
from typing import Dict

# Kind -> apiVersion（用于 k8s_advanced、动态资源等）
API_VERSION_MAP: Dict[str, str] = {
    "Deployment": "apps/v1",
    "StatefulSet": "apps/v1",
    "DaemonSet": "apps/v1",
    "Service": "v1",
    "ConfigMap": "v1",
    "Secret": "v1",
    "Job": "batch/v1",
    "CronJob": "batch/v1",
    "Ingress": "networking.k8s.io/v1",
    "PersistentVolumeClaim": "v1",
    "ServiceAccount": "v1",
    "Role": "rbac.authorization.k8s.io/v1",
    "RoleBinding": "rbac.authorization.k8s.io/v1",
    "HorizontalPodAutoscaler": "autoscaling/v2",
    "NetworkPolicy": "networking.k8s.io/v1",
    "ResourceQuota": "v1",
    "Namespace": "v1",
    "Node": "v1",
    "Pod": "v1",
    "PersistentVolume": "v1",
    "StorageClass": "storage.k8s.io/v1",
    "ClusterRole": "rbac.authorization.k8s.io/v1",
    "ClusterRoleBinding": "rbac.authorization.k8s.io/v1",
}

# resource_type (小写单数，用于 k8s_api 验证) -> Kind
RESOURCE_TYPE_SINGULAR_TO_KIND: Dict[str, str] = {
    "deployment": "Deployment",
    "statefulset": "StatefulSet",
    "daemonset": "DaemonSet",
    "service": "Service",
    "configmap": "ConfigMap",
    "secret": "Secret",
    "job": "Job",
    "cronjob": "CronJob",
    "ingress": "Ingress",
    "persistentvolumeclaim": "PersistentVolumeClaim",
    "serviceaccount": "ServiceAccount",
    "role": "Role",
    "rolebinding": "RoleBinding",
    "clusterrole": "ClusterRole",
    "clusterrolebinding": "ClusterRoleBinding",
    "namespace": "Namespace",
    "horizontalpodautoscaler": "HorizontalPodAutoscaler",
    "networkpolicy": "NetworkPolicy",
    "resourcequota": "ResourceQuota",
}


def get_api_version_for_resource_type(resource_type: str) -> str:
    """根据 resource_type（小写）获取 apiVersion"""
    kind = RESOURCE_TYPE_SINGULAR_TO_KIND.get(
        resource_type.lower() if resource_type else "",
        resource_type.capitalize() if resource_type else ""
    )
    return API_VERSION_MAP.get(kind, "v1")
