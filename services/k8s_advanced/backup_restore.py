"""
Kubernetes 进阶服务 - 备份与恢复
"""
import json
import logging
import os
import yaml
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from config import BACKUP_RETENTION_DAYS
from utils.backup_paths import cleanup_expired_backups, get_backup_path, get_backup_search_path

logger = logging.getLogger(__name__)

# 资源类型（支持单复数）-> (Kind, create_method_name)
_RESOURCE_CREATE_SPECS: Dict[str, Tuple[str, str]] = {
    "deployment": ("Deployment", "create_deployment"),
    "deployments": ("Deployment", "create_deployment"),
    "statefulset": ("StatefulSet", "create_statefulset"),
    "statefulsets": ("StatefulSet", "create_statefulset"),
    "daemonset": ("DaemonSet", "create_daemonset"),
    "daemonsets": ("DaemonSet", "create_daemonset"),
    "service": ("Service", "create_service"),
    "services": ("Service", "create_service"),
    "configmap": ("ConfigMap", "create_configmap"),
    "configmaps": ("ConfigMap", "create_configmap"),
    "secret": ("Secret", "create_secret"),
    "secrets": ("Secret", "create_secret"),
    "job": ("Job", "create_job"),
    "jobs": ("Job", "create_job"),
    "cronjob": ("CronJob", "create_cronjob"),
    "cronjobs": ("CronJob", "create_cronjob"),
    "ingress": ("Ingress", "create_ingress"),
    "ingresses": ("Ingress", "create_ingress"),
    "persistentvolumeclaim": ("PersistentVolumeClaim", "create_persistentvolumeclaim"),
    "persistentvolumeclaims": ("PersistentVolumeClaim", "create_persistentvolumeclaim"),
    "serviceaccount": ("ServiceAccount", "create_serviceaccount"),
    "serviceaccounts": ("ServiceAccount", "create_serviceaccount"),
    "role": ("Role", "create_role"),
    "roles": ("Role", "create_role"),
    "rolebinding": ("RoleBinding", "create_role_binding"),
    "rolebindings": ("RoleBinding", "create_role_binding"),
}


class BackupRestoreMixin:
    """备份与恢复 Mixin"""

    async def _backup_resource_type(self, resource_type: str, namespace: str) -> List[Dict]:
        """统一的资源类型备份方法"""
        try:
            config = self.resource_manager.get_resource_config(resource_type)
            if not config:
                return []

            resources = []
            list_method = self.resource_manager.get_operation_method(resource_type, "list", namespace)
            get_method = self.resource_manager.get_operation_method(resource_type, "get", namespace)
            listed = await list_method()

            for r in listed:
                resource_name = r.get("name")
                if not resource_name:
                    continue
                if config.skip_condition and config.skip_condition(resource_name):
                    continue
                try:
                    resource_data = await get_method(resource_name)
                    if not resource_data or resource_data == {}:
                        continue
                    k8s_resource = self._convert_flat_to_k8s_format(resource_data, config.kind)
                    processed_resource = self._sanitize_for_backup(k8s_resource)
                    resources.append(processed_resource)
                except Exception as e:
                    logger.warning("获取 %s %s 失败: %s", config.kind, resource_name, e)
                    continue
        except Exception as e:
            logger.warning("备份 %s 失败: %s", resource_type, e)
            return []
        return resources

    def _get_backup_path(self, cluster_name: str, namespace: Optional[str] = None,
                         resource_type: Optional[str] = None, resource_name: Optional[str] = None) -> str:
        """获取备份文件路径"""
        return get_backup_path(
            self.backup_dir, cluster_name,
            namespace=namespace,
            resource_type=resource_type,
            resource_name=resource_name,
            create_dirs=True,
        )

    async def backup_namespace(self, namespace: str, cluster_name: Optional[str] = None, include_secrets: bool = True) -> str:
        """备份整个命名空间的资源"""
        if not cluster_name:
            cluster_info = await self.k8s_service.get_cluster_info()
            cluster_name = cluster_info.get("cluster_name", "default")

        backup_data = {
            "metadata": {"cluster_name": cluster_name, "namespace": namespace, "version": "v1"},
            "namespace": None,
            "resources": {}
        }

        try:
            ns_info = await self.k8s_service.get_namespace(namespace)
            namespace_resource = {
                "apiVersion": "v1",
                "kind": "Namespace",
                "metadata": {
                    "name": ns_info.get("name"),
                    "labels": ns_info.get("labels", {}),
                    "annotations": ns_info.get("annotations", {})
                }
            }
            backup_data["namespace"] = self._sanitize_for_backup(namespace_resource)
        except Exception as e:
            logger.warning("备份命名空间元数据 %s 失败（可能权限不足）: %s", namespace, e)

        resource_types = [
            "deployments", "statefulsets", "daemonsets",
            "services", "configmaps", "jobs", "cronjobs", "ingresses",
            "persistentvolumeclaims", "serviceaccounts", "roles", "rolebindings"
        ]
        if include_secrets:
            resource_types.append("secrets")

        for resource_type in resource_types:
            try:
                resources = await self._backup_resource_type(resource_type, namespace)
                backup_data["resources"][resource_type] = resources
            except Exception as e:
                logger.warning("备份 %s 失败: %s", resource_type, e)
                backup_data["resources"][resource_type] = {"error": str(e)}

        backup_path = self._get_backup_path(cluster_name, namespace)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_path, f"namespace_backup_{timestamp}.yaml")

        class CustomYamlDumper(yaml.SafeDumper):
            def ignore_aliases(self, data):
                return True

            def represent_str(self, data):
                if '\n' in data:
                    return self.represent_scalar('tag:yaml.org,2002:str', data, style='|')
                return self.represent_scalar('tag:yaml.org,2002:str', data)

        CustomYamlDumper.add_representer(str, CustomYamlDumper.represent_str)
        with open(backup_file, 'w', encoding='utf-8') as f:
            yaml.dump(backup_data, f, sort_keys=False, allow_unicode=True, Dumper=CustomYamlDumper, default_flow_style=False)

        cleanup_expired_backups(self.backup_dir, BACKUP_RETENTION_DAYS)
        return backup_file

    async def backup_specific_resource(self, resource_type: str, resource_name: str,
                                       namespace: str, cluster_name: Optional[str] = None) -> str:
        """备份特定资源"""
        if not cluster_name:
            cluster_info = await self.k8s_service.get_cluster_info()
            cluster_name = cluster_info.get("cluster_name", "default")

        _GET_METHOD_MAP = {
            "deployment": "get_deployment",
            "statefulset": "get_statefulset",
            "daemonset": "get_daemonset",
            "service": "get_service",
            "configmap": "get_configmap",
            "secret": "get_secret",
            "job": "get_job",
            "cronjob": "get_cronjob",
            "ingress": "get_ingress",
            "persistentvolumeclaim": "get_persistentvolumeclaim",
            "serviceaccount": "get_serviceaccount",
            "role": "get_role",
            "rolebinding": "get_role_binding",
        }
        try:
            get_method = _GET_METHOD_MAP.get(resource_type)
            if not get_method:
                raise ValueError(f"不支持的资源类型: {resource_type}")
            method = getattr(self.k8s_service, get_method)
            resource_data = await method(resource_name, namespace)

            backup_data = {
                "metadata": {
                    "cluster_name": cluster_name,
                    "namespace": namespace,
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                    "version": "v1"
                },
                "resource": resource_data
            }
            backup_path = self._get_backup_path(cluster_name, namespace, resource_type, resource_name)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(backup_path, f"{resource_name}_{timestamp}.yaml")
            with open(backup_file, 'w', encoding='utf-8') as f:
                yaml.dump(backup_data, f, sort_keys=False, allow_unicode=True, default_flow_style=False)

            cleanup_expired_backups(self.backup_dir, BACKUP_RETENTION_DAYS)
            return backup_file
        except Exception as e:
            raise Exception(f"备份资源失败: {e}")

    async def restore_from_backup(self, backup_file: str, target_namespace: Optional[str] = None,
                                 target_cluster: Optional[str] = None) -> Dict:
        """从备份文件恢复资源"""
        if not os.path.exists(backup_file):
            raise FileNotFoundError(f"备份文件不存在: {backup_file}")

        with open(backup_file, 'r', encoding='utf-8') as f:
            backup_data = yaml.safe_load(f)

        metadata = backup_data["metadata"]
        original_namespace = metadata["namespace"]
        original_cluster = metadata["cluster_name"]

        if target_namespace and target_namespace != original_namespace:
            raise ValueError(f"不允许恢复到不同的命名空间。原命名空间: {original_namespace}, 目标命名空间: {target_namespace}")

        target_namespace = original_namespace
        target_cluster = target_cluster or original_cluster
        results = {"success": [], "failed": [], "total": 0}

        if "namespace" in backup_data:
            try:
                namespace_resource = backup_data["namespace"]
                await self.k8s_service.create_namespace(resource=namespace_resource)
                results["success"].append(f"namespace/{original_namespace}")
                results["total"] += 1
                logger.info("成功恢复命名空间: %s", original_namespace)
            except Exception as e:
                err_str = str(e).lower()
                if "already exists" in err_str or "conflict" in err_str:
                    logger.info("命名空间 %s 已存在，跳过创建", original_namespace)
                elif "forbidden" in err_str:
                    logger.warning("无权创建命名空间 %s（需集群级 namespaces create），跳过", original_namespace)
                else:
                    results["failed"].append({"resource": f"namespace/{original_namespace}", "error": str(e)})
                    logger.warning("恢复命名空间失败: %s", e)
        else:
            try:
                await self.k8s_service.create_namespace(name=target_namespace)
            except Exception:
                pass

        if "resources" in backup_data:
            for resource_type, resources in backup_data["resources"].items():
                if isinstance(resources, dict) and "error" in resources:
                    results["failed"].append({"resource_type": resource_type, "error": resources["error"]})
                    continue
                valid_resources = []
                for resource in resources:
                    if not resource or resource == {}:
                        continue
                    resource_name = resource.get("metadata", {}).get("name", "")
                    if not resource_name or resource_name in ["kube-root-ca.crt"] or resource_name.startswith("default-token-"):
                        continue
                    valid_resources.append(resource)

                for resource in valid_resources:
                    try:
                        if "metadata" in resource:
                            current_ns = resource["metadata"].get("namespace")
                            if current_ns and current_ns != target_namespace:
                                logger.warning("资源 %s 的命名空间 %s 与目标命名空间 %s 不匹配",
                                               resource.get('metadata', {}).get('name'), current_ns, target_namespace)
                            resource["metadata"]["namespace"] = target_namespace

                        if resource_type in _RESOURCE_CREATE_SPECS:
                            kind, method_name = _RESOURCE_CREATE_SPECS[resource_type]
                            create_func = getattr(self.k8s_service, method_name)
                            await create_func(resource=self._convert_to_k8s_resource(resource, kind), namespace=target_namespace)
                        results["success"].append(f"{resource_type}/{resource['metadata']['name']}")
                        results["total"] += 1
                    except Exception as e:
                        results["failed"].append({
                            "resource": f"{resource_type}/{resource.get('metadata', {}).get('name', 'unknown')}",
                            "error": str(e)
                        })

        elif "resource" in backup_data:
            resource = backup_data["resource"]
            resource_type = metadata["resource_type"]
            try:
                if "metadata" in resource:
                    resource["metadata"]["namespace"] = target_namespace
                if resource_type in _RESOURCE_CREATE_SPECS:
                    kind, method_name = _RESOURCE_CREATE_SPECS[resource_type]
                    create_func = getattr(self.k8s_service, method_name)
                    await create_func(resource=self._convert_to_k8s_resource(resource, kind), namespace=target_namespace)
                results["success"].append(f"{resource_type}/{resource['metadata']['name']}")
                results["total"] += 1
            except Exception as e:
                results["failed"].append({
                    "resource": f"{resource_type}/{resource.get('metadata', {}).get('name', 'unknown')}",
                    "error": str(e)
                })
        return results

    def _convert_to_k8s_resource(self, resource_data: Dict, kind: str) -> Dict:
        """将备份的资源数据转换为标准的 Kubernetes 资源定义"""
        k8s_resource = self._create_base_k8s_resource(resource_data, kind, from_backup=True)
        k8s_resource = self._populate_resource_content(k8s_resource, resource_data, kind, from_backup=True)
        if "metadata" in k8s_resource:
            metadata = k8s_resource["metadata"]
            for field in ["uid", "resourceVersion", "generation", "creationTimestamp", "created", "managedFields"]:
                metadata.pop(field, None)
        return k8s_resource

    def _sanitize_for_backup(self, resource_obj: Dict) -> Dict:
        """按照 K8s YAML 标准严格过滤字段，仅保留声明式配置"""
        if not isinstance(resource_obj, dict):
            return resource_obj

        resource = json.loads(json.dumps(resource_obj))
        allowed_top_fields = {"apiVersion", "kind", "metadata", "spec", "data", "binaryData", "type", "rules", "roleRef", "subjects"}
        keys_to_remove = [k for k in list(resource.keys()) if k not in allowed_top_fields]
        for k in keys_to_remove:
            resource.pop(k, None)

        metadata = resource.get("metadata", {})
        if metadata:
            allowed_meta_fields = {"name", "namespace", "labels", "annotations"}
            meta_keys_to_remove = [k for k in list(metadata.keys()) if k not in allowed_meta_fields]
            for k in meta_keys_to_remove:
                metadata.pop(k, None)
            resource["metadata"] = metadata

        resource.pop("status", None)

        if resource.get("spec", {}).get("template", {}).get("spec", {}).get("volumes"):
            volumes = resource["spec"]["template"]["spec"]["volumes"]
            for volume in volumes:
                volume.pop("type", None)

        if resource.get("kind") in ["Job", "CronJob"]:
            template_metadata = None
            if resource.get("kind") == "Job":
                template_metadata = resource.get("spec", {}).get("template", {}).get("metadata", {})
            elif resource.get("kind") == "CronJob":
                template_metadata = resource.get("spec", {}).get("jobTemplate", {}).get("spec", {}).get("template", {}).get("metadata", {})
            if template_metadata:
                runtime_labels = ["batch.kubernetes.io/controller-uid", "batch.kubernetes.io/job-name", "controller-uid", "job-name"]
                for label in runtime_labels:
                    template_metadata.get("labels", {}).pop(label, None)

        spec = resource.get("spec")
        if spec is not None and isinstance(spec, dict):
            resource["spec"] = self._normalize_spec(resource.get("kind"), spec, for_backup=True)
            if not resource["spec"]:
                resource.pop("spec", None)

        if not resource.get("metadata"):
            logger.warning("资源缺少 metadata: %s", resource)
        spec_required_kinds = ["Deployment", "StatefulSet", "DaemonSet", "Service", "Job", "CronJob", "Ingress", "PersistentVolumeClaim"]
        if resource.get("kind") in spec_required_kinds and not resource.get("spec"):
            logger.warning("%s 缺少 spec: %s", resource.get('kind'), resource)
        if resource.get("kind") == "Role" and not resource.get("rules"):
            logger.warning("Role 缺少 rules: %s", resource)
        if resource.get("kind") == "RoleBinding" and (not resource.get("subjects") or not resource.get("roleRef")):
            logger.warning("RoleBinding 缺少 subjects 或 roleRef: %s", resource)
        return resource

    def list_backups(self, cluster_name: Optional[str] = None, namespace: Optional[str] = None) -> List[Dict]:
        """列出备份文件"""
        backups = []
        search_path = get_backup_search_path(self.backup_dir, cluster_name, namespace)

        if not os.path.exists(search_path):
            return backups

        for root, dirs, files in os.walk(search_path):
            for file in files:
                if file.endswith('.json') or file.endswith('.yaml'):
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, self.backup_dir)
                    path_parts = relative_path.split(os.sep)
                    backup_info = {
                        "file_path": file_path,
                        "relative_path": relative_path,
                        "cluster_name": path_parts[0] if len(path_parts) > 0 else "unknown",
                        "namespace": None,
                        "resource_type": None,
                        "resource_name": None,
                        "timestamp": file.split('_')[-1].replace('.json', '').replace('.yaml', '') if '_' in file else "unknown"
                    }
                    if len(path_parts) > 2 and path_parts[1] == "namespaces":
                        backup_info["namespace"] = path_parts[2]
                    if len(path_parts) > 4 and path_parts[3] == "resources":
                        backup_info["resource_type"] = path_parts[4]
                        if len(path_parts) > 5:
                            backup_info["resource_name"] = path_parts[5]
                    backups.append(backup_info)
        return sorted(backups, key=lambda x: x["timestamp"], reverse=True)
