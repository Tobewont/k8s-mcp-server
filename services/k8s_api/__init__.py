"""
Kubernetes API 服务包
拆分为多个模块便于维护
"""
from typing import Optional

from .base import BaseK8sService
from .pod_ops import PodOpsMixin
from .workload_ops import WorkloadOpsMixin
from .service_config_ops import ServiceConfigOpsMixin
from .jobcronjob_ops import JobCronJobOpsMixin
from .networking_storage_ops import NetworkingStorageOpsMixin
from .rbac_ops import RbacOpsMixin
from .autoscaling_policy_ops import AutoscalingPolicyOpsMixin
from .interactive_ops import InteractiveOpsMixin
from .cluster_ops import ClusterOpsMixin


class KubernetesAPIService(
    PodOpsMixin,
    WorkloadOpsMixin,
    ServiceConfigOpsMixin,
    JobCronJobOpsMixin,
    NetworkingStorageOpsMixin,
    RbacOpsMixin,
    AutoscalingPolicyOpsMixin,
    InteractiveOpsMixin,
    ClusterOpsMixin,
    BaseK8sService,
):
    """Kubernetes API 服务类（整合各模块）"""

    def __init__(self, kubeconfig_path: Optional[str] = None):
        super().__init__()
        self.load_config(kubeconfig_path=kubeconfig_path)


__all__ = ["KubernetesAPIService"]
