"""
Kubernetes API 服务 - 基础模块
包含初始化、配置加载、验证框架及通用辅助方法
"""
import logging
import os
import tempfile
import weakref
from typing import Dict, List, Any, Optional

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

logger = logging.getLogger(__name__)


class BaseK8sService:
    """Kubernetes API 服务基类"""

    def __init__(self):
        self._api_client = None
        self.v1_api = None
        self.apps_v1_api = None
        self.networking_v1_api = None
        self.rbac_v1_api = None
        self.storage_v1_api = None
        self.extensions_v1beta1_api = None
        self.batch_v1_api = None
        self.batch_v1beta1_api = None
        self.autoscaling_v2_api = None
        self._advanced_service_ref = None

    def set_validation_service(self, advanced_service):
        """设置验证服务（使用弱引用避免循环引用）"""
        self._advanced_service_ref = weakref.ref(advanced_service) if advanced_service else None

    def _get_validation_service(self):
        """获取验证服务实例"""
        return self._advanced_service_ref() if self._advanced_service_ref else None

    async def _execute_with_validation_and_preview(
        self,
        operation_type: str,
        resource_type: str,
        resource_name: str,
        namespace: str = "default",
        resource_data: Optional[Dict] = None,
        original_operation=None,
        **kwargs,
    ):
        """统一的验证、预览和执行方法"""
        advanced_service = self._get_validation_service()
        if not advanced_service:
            if original_operation:
                return await original_operation()
            raise Exception("验证服务未初始化且未提供原始操作方法")

        logger.info("%s %s/%s", operation_type.upper(), resource_type, resource_name)

        if operation_type in ["update", "delete"]:
            validation_result = await advanced_service.validate_and_preview_operation(
                resource_type, resource_name, operation_type, namespace, resource_data
            )
            if not validation_result["valid"]:
                logger.info(validation_result["message"])
                return {"error": validation_result["message"]}
            logger.info(validation_result["message"])
            if validation_result["changes"]:
                for change in validation_result["changes"]:
                    logger.debug("  %s", change)
            for warning in validation_result["warnings"]:
                logger.warning(warning)
        elif operation_type == "create":
            validation_result = await advanced_service.validate_and_preview_operation(
                resource_type, resource_name, operation_type, namespace, resource_data
            )
            if not validation_result["valid"]:
                logger.info(validation_result["message"])
                return {"error": validation_result["message"]}
            logger.info(validation_result["message"])

        logger.info("执行操作...")
        try:
            result = await original_operation()
            logger.info("操作成功完成")
            return result
        except Exception as e:
            logger.error("操作失败: %s", e)
            raise

    def _build_resource_data_for_validation(
        self, resource_type: str, name: str, namespace: str, resource: Optional[Dict] = None, **params
    ) -> Dict:
        """为验证构建资源数据的通用方法"""
        if resource:
            return resource
        from services.k8s_api.resource_builders import build_resource_data
        api_version = self._get_api_version_for_resource(resource_type)
        return build_resource_data(resource_type, name, namespace, api_version, params)

    def _get_api_version_for_resource(self, resource_type: str) -> str:
        """获取资源类型的API版本"""
        from services.k8s_constants import get_api_version_for_resource_type
        return get_api_version_for_resource_type(resource_type)

    def _extract_volume_info(self, volume) -> Dict:
        """统一的卷信息提取方法"""
        vinfo = {"name": volume.name}
        if volume.config_map:
            vinfo["type"] = "ConfigMap"
            config_map_info = {"name": volume.config_map.name}
            if volume.config_map.optional:
                config_map_info["optional"] = volume.config_map.optional
            vinfo["configMap"] = config_map_info
        elif volume.secret:
            vinfo["type"] = "Secret"
            secret_info = {"secretName": volume.secret.secret_name}
            if volume.secret.optional:
                secret_info["optional"] = volume.secret.optional
            vinfo["secret"] = secret_info
        elif volume.persistent_volume_claim:
            vinfo["type"] = "PersistentVolumeClaim"
            vinfo["persistentVolumeClaim"] = {"claimName": volume.persistent_volume_claim.claim_name}
        elif volume.host_path:
            vinfo["type"] = "HostPath"
            vinfo["hostPath"] = {"path": volume.host_path.path}
            if volume.host_path.type:
                vinfo["hostPath"]["type"] = volume.host_path.type
        elif volume.empty_dir:
            vinfo["type"] = "EmptyDir"
            vinfo["emptyDir"] = {}
            if volume.empty_dir.size_limit:
                vinfo["emptyDir"]["sizeLimit"] = volume.empty_dir.size_limit
        return vinfo

    def _extract_container_info(self, container) -> Dict:
        """统一的容器信息提取方法"""
        requests = {}
        limits = {}
        if container.resources:
            if container.resources.requests:
                requests = dict(container.resources.requests) if hasattr(container.resources.requests, 'get') else {}
            if container.resources.limits:
                limits = dict(container.resources.limits) if hasattr(container.resources.limits, 'get') else {}
        return {
            "name": container.name,
            "image": container.image,
            "imagePullPolicy": container.image_pull_policy,
            "ports": [
                {"containerPort": port.container_port, "name": port.name, "protocol": port.protocol}
                for port in (container.ports or [])
            ],
            "env": [
                {
                    "name": env.name,
                    "value": env.value,
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": env.value_from.secret_key_ref.name,
                            "key": env.value_from.secret_key_ref.key,
                        }
                        if env.value_from and env.value_from.secret_key_ref
                        else None,
                        "configMapKeyRef": {
                            "name": env.value_from.config_map_key_ref.name,
                            "key": env.value_from.config_map_key_ref.key,
                        }
                        if env.value_from and env.value_from.config_map_key_ref
                        else None,
                    }
                    if env.value_from
                    else None,
                }
                for env in (container.env or [])
            ],
            "resources": {
                "requests": {"memory": requests.get("memory"), "cpu": requests.get("cpu")},
                "limits": {"memory": limits.get("memory"), "cpu": limits.get("cpu")},
            }
            if container.resources
            else {},
            "livenessProbe": {
                "httpGet": {
                    "path": container.liveness_probe.http_get.path,
                    "port": container.liveness_probe.http_get.port,
                }
                if container.liveness_probe and container.liveness_probe.http_get
                else None,
                "initialDelaySeconds": container.liveness_probe.initial_delay_seconds,
                "periodSeconds": container.liveness_probe.period_seconds,
                "successThreshold": container.liveness_probe.success_threshold,
                "failureThreshold": container.liveness_probe.failure_threshold,
            }
            if container.liveness_probe
            else None,
            "readinessProbe": {
                "httpGet": {
                    "path": container.readiness_probe.http_get.path,
                    "port": container.readiness_probe.http_get.port,
                }
                if container.readiness_probe and container.readiness_probe.http_get
                else None,
                "initialDelaySeconds": container.readiness_probe.initial_delay_seconds,
                "periodSeconds": container.readiness_probe.period_seconds,
                "successThreshold": container.readiness_probe.success_threshold,
                "failureThreshold": container.readiness_probe.failure_threshold,
            }
            if container.readiness_probe
            else None,
            "volumeMounts": [
                {"mountPath": v.mount_path, "name": v.name, "readOnly": v.read_only}
                for v in (container.volume_mounts or [])
            ],
        }

    def load_config(self, kubeconfig_content: Optional[str] = None, kubeconfig_path: Optional[str] = None):
        """加载 Kubernetes 配置"""
        if kubeconfig_content:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write(kubeconfig_content)
                temp_path = f.name
            try:
                config.load_kube_config(config_file=temp_path)
            finally:
                try:
                    os.unlink(temp_path)
                except OSError as e:
                    logger.warning("清理临时 kubeconfig 文件失败 %s: %s", temp_path, e)
        elif kubeconfig_path:
            config.load_kube_config(config_file=kubeconfig_path)
        else:
            try:
                from utils.cluster_config import get_cluster_config_manager
                default_cluster = get_cluster_config_manager().get_default_cluster()
                if default_cluster and default_cluster.kubeconfig_path:
                    config.load_kube_config(config_file=default_cluster.kubeconfig_path)
                else:
                    config.load_kube_config()
            except Exception:
                config.load_kube_config()

        self._api_client = client.ApiClient()
        self.v1_api = client.CoreV1Api()
        self.apps_v1_api = client.AppsV1Api()
        self.networking_v1_api = client.NetworkingV1Api()
        self.rbac_v1_api = client.RbacAuthorizationV1Api()
        self.storage_v1_api = client.StorageV1Api()
        self.batch_v1_api = client.BatchV1Api()
        self.autoscaling_v2_api = client.AutoscalingV2Api()
        try:
            self.extensions_v1beta1_api = client.ExtensionsV1beta1Api()
        except Exception:
            self.extensions_v1beta1_api = None
        if hasattr(client, 'BatchV1beta1Api'):
            try:
                self.batch_v1beta1_api = client.BatchV1beta1Api()
            except Exception:
                self.batch_v1beta1_api = None
        else:
            self.batch_v1beta1_api = None
        self._validate_api_clients()

    def _validate_api_clients(self):
        """验证所有需要的 API 客户端是否已初始化"""
        required_apis = [
            'v1_api', 'apps_v1_api', 'networking_v1_api',
            'rbac_v1_api', 'storage_v1_api', 'batch_v1_api',
            'autoscaling_v2_api',
        ]
        for api_name in required_apis:
            if not hasattr(self, api_name) or getattr(self, api_name) is None:
                raise AttributeError(f"API 客户端 {api_name} 未正确初始化")

    def get_dynamic_client(self):
        """获取 DynamicClient，用于动态操作任意 API 资源"""
        if self._api_client is None:
            raise RuntimeError("API 客户端未初始化，请先调用 load_config()")
        from kubernetes.dynamic import DynamicClient
        return DynamicClient(self._api_client)
