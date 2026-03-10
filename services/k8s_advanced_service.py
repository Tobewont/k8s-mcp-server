"""
Kubernetes 进阶服务层
整合批量操作、备份恢复、资源验证等功能
"""
import os
from typing import Dict, Optional

from services.dynamic_resource_service import DynamicResourceService
from config import BACKUP_DIR

from services.k8s_advanced import (
    ResourceManager,
    API_VERSION_MAP,
    RESOURCE_TYPE_TO_KIND,
    ResourceConversionMixin,
    BatchOpsMixin,
    BackupRestoreMixin,
    RbacAdvancedMixin,
    ValidationMixin,
)


class KubernetesAdvancedService(
    ResourceConversionMixin,
    BatchOpsMixin,
    BackupRestoreMixin,
    RbacAdvancedMixin,
    ValidationMixin,
):
    """Kubernetes 进阶服务类
    整合批量操作、备份恢复、资源验证等功能
    """

    def __init__(self, kubeconfig_path: Optional[str] = None):
        from services.factory import get_k8s_api_service
        self.k8s_service = get_k8s_api_service(kubeconfig_path)
        self.backup_dir = BACKUP_DIR
        os.makedirs(self.backup_dir, exist_ok=True)
        self.operation_history = []

        self.resource_manager = ResourceManager(self.k8s_service)
        self._dynamic_service = DynamicResourceService(self.k8s_service)

        self.k8s_service.set_validation_service(self)

        self._api_version_map: Dict[str, str] = dict(API_VERSION_MAP)
        self._resource_type_to_kind: Dict[str, str] = dict(RESOURCE_TYPE_TO_KIND)
