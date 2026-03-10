"""
Kubernetes 进阶服务 - 资源验证与预览
"""
from typing import Any, Callable, Dict, List, Optional, Tuple

# 资源类型 -> (是否需要 namespace, 获取方法名)
_RESOURCE_GET_MAP: Dict[str, Tuple[bool, str]] = {
    "deployment": (True, "get_deployment"),
    "statefulset": (True, "get_statefulset"),
    "daemonset": (True, "get_daemonset"),
    "service": (True, "get_service"),
    "configmap": (True, "get_configmap"),
    "secret": (True, "get_secret"),
    "job": (True, "get_job"),
    "cronjob": (True, "get_cronjob"),
    "ingress": (True, "get_ingress"),
    "storageclass": (False, "get_storageclass"),
    "persistentvolume": (False, "get_persistentvolume"),
    "persistentvolumeclaim": (True, "get_persistentvolumeclaim"),
    "serviceaccount": (True, "get_serviceaccount"),
    "role": (True, "get_role"),
    "clusterrole": (False, "get_cluster_role"),
    "rolebinding": (True, "get_role_binding"),
    "clusterrolebinding": (False, "get_cluster_role_binding"),
    "pod": (True, "get_pod"),
    "node": (False, "get_node"),
    "horizontalpodautoscaler": (True, "get_hpa"),
    "networkpolicy": (True, "get_network_policy"),
    "resourcequota": (True, "get_resource_quota"),
}


class ValidationMixin:
    """资源验证与预览 Mixin"""

    async def get_resource_before_operation(self, resource_type: str, resource_name: str,
                                            namespace: str = "default") -> Dict:
        """获取操作前的资源状态"""
        try:
            if resource_type == "namespace":
                namespaces = await self.k8s_service.list_namespaces()
                for ns in namespaces:
                    if ns["name"] == resource_name:
                        return ns
                return {"error": f"命名空间 {resource_name} 不存在"}
            entry = _RESOURCE_GET_MAP.get(resource_type)
            if not entry:
                raise ValueError(f"不支持的资源类型: {resource_type}")

            needs_ns, method_name = entry
            get_method: Callable = getattr(self.k8s_service, method_name)
            if needs_ns:
                return await get_method(resource_name, namespace)
            return await get_method(resource_name)
        except Exception as e:
            return {"error": str(e)}

    async def get_resource_after_operation(self, resource_type: str, resource_name: str,
                                           namespace: str = "default") -> Dict:
        """获取操作后的资源状态"""
        return await self.get_resource_before_operation(resource_type, resource_name, namespace)

    def _compare_resource_fields(self, before: Dict, after: Dict, field_configs: Dict) -> Dict:
        """通用的资源字段比较方法"""
        changes = {}
        if before.get("error") or after.get("error"):
            return {"error": "无法获取资源状态"}
        for field_name, config in field_configs.items():
            if callable(config):
                before_value = config(before)
                after_value = config(after)
            elif isinstance(config, str):
                before_value = self._get_nested_value(before, config)
                after_value = self._get_nested_value(after, config)
            else:
                before_path, after_path = config
                before_value = self._get_nested_value(before, before_path)
                after_value = self._get_nested_value(after, after_path)
            if before_value != after_value:
                changes[field_name] = {"before": before_value, "after": after_value}
                if isinstance(before_value, (str, int, bool)) and isinstance(after_value, (str, int, bool)):
                    changes[field_name]["change"] = f"{before_value} -> {after_value}"
        return changes

    def _get_nested_value(self, data: Dict, path: str, default=None):
        """从嵌套字典中获取值"""
        keys = path.split(".")
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current

    def _get_resource_field_configs(self, resource_type: str) -> Dict:
        """获取资源类型的字段配置"""
        configs = {
            "deployment": {
                "replicas": "spec.replicas", "labels": "metadata.labels", "annotations": "metadata.annotations",
                "image": lambda r: self._get_first_container_field(r, "image"),
                "resources": lambda r: self._get_first_container_field(r, "resources"),
                "env_vars": lambda r: self._get_first_container_field(r, "env")
            },
            "statefulset": {
                "replicas": "spec.replicas", "labels": "metadata.labels", "annotations": "metadata.annotations",
                "image": lambda r: self._get_first_container_field(r, "image"),
                "resources": lambda r: self._get_first_container_field(r, "resources"),
                "env_vars": lambda r: self._get_first_container_field(r, "env"),
                "volume_claims": "spec.volumeClaimTemplates"
            },
            "daemonset": {
                "labels": "metadata.labels", "annotations": "metadata.annotations",
                "image": lambda r: self._get_first_container_field(r, "image"),
                "resources": lambda r: self._get_first_container_field(r, "resources"),
                "env_vars": lambda r: self._get_first_container_field(r, "env")
            },
            "service": {
                "service_type": "spec.type", "ports": "spec.ports", "selector": "spec.selector",
                "labels": "metadata.labels", "annotations": "metadata.annotations"
            },
            "configmap": {
                "data": "data", "binary_data": "binaryData",
                "labels": "metadata.labels", "annotations": "metadata.annotations"
            },
            "secret": {
                "data": lambda r: list(r.get("data", {}).keys()),
                "type": "type", "labels": "metadata.labels", "annotations": "metadata.annotations"
            },
            "job": {
                "parallelism": "spec.parallelism", "completions": "spec.completions",
                "active_deadline_seconds": "spec.activeDeadlineSeconds", "backoff_limit": "spec.backoffLimit",
                "labels": "metadata.labels", "annotations": "metadata.annotations"
            },
            "cronjob": {
                "schedule": "spec.schedule", "suspend": "spec.suspend",
                "labels": "metadata.labels", "annotations": "metadata.annotations"
            },
            "ingress": {
                "rules": "spec.rules", "tls": "spec.tls", "ingress_class": "spec.ingressClassName",
                "labels": "metadata.labels", "annotations": "metadata.annotations"
            },
            "persistentvolumeclaim": {
                "size": "spec.resources.requests.storage", "access_modes": "spec.accessModes",
                "storage_class": "spec.storageClassName",
                "labels": "metadata.labels", "annotations": "metadata.annotations"
            },
            "persistentvolume": {
                "capacity": "capacity.storage", "access_modes": "access_modes",
                "reclaim_policy": "reclaim_policy", "storage_class": "storage_class_name",
                "labels": "metadata.labels", "annotations": "metadata.annotations"
            },
            "storageclass": {
                "provisioner": "provisioner", "parameters": "parameters",
                "allow_volume_expansion": "allow_volume_expansion",
                "labels": "metadata.labels", "annotations": "metadata.annotations"
            },
            "serviceaccount": {
                "labels": "labels", "annotations": "annotations", "secrets": "secrets",
                "image_pull_secrets": "image_pull_secrets",
                "automount_service_account_token": "automount_service_account_token"
            },
            "role": {"rules": "rules", "labels": "metadata.labels", "annotations": "metadata.annotations"},
            "clusterrole": {"rules": "rules", "labels": "metadata.labels", "annotations": "metadata.annotations"},
            "rolebinding": {
                "role_ref": "role_ref", "subjects": "subjects",
                "labels": "metadata.labels", "annotations": "metadata.annotations"
            },
            "clusterrolebinding": {
                "role_ref": "role_ref", "subjects": "subjects",
                "labels": "metadata.labels", "annotations": "metadata.annotations"
            },
            "namespace": {"status": "status.phase", "labels": "metadata.labels", "annotations": "metadata.annotations"},
            "pod": {
                "phase": "phase", "ready": "ready", "restart_count": "restart_count", "node_name": "node_name",
                "labels": "labels", "annotations": "annotations",
                "containers": lambda r: [c.get("name") for c in r.get("containers", [])]
            },
            "node": {
                "status": "status", "roles": "roles", "version": "version", "os_image": "os_image",
                "labels": "labels", "annotations": "annotations"
            }
        }
        return configs.get(resource_type, {})

    def _get_first_container_field(self, resource: Dict, field: str):
        """获取第一个容器的字段值"""
        containers = resource.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        return containers[0].get(field) if containers else None

    def compare_resource_changes(self, resource_type: str, before: Dict, after: Dict) -> Dict:
        """统一的资源变化比较方法"""
        field_configs = self._get_resource_field_configs(resource_type)
        if not field_configs:
            return {"error": f"不支持的资源类型: {resource_type}"}
        return self._compare_resource_fields(before, after, field_configs)

    def _is_cluster_resource(self, resource_type: str) -> bool:
        """判断是否为集群级别资源"""
        return resource_type.lower() in ["persistentvolume", "storageclass", "clusterrole", "clusterrolebinding", "namespace", "node"]

    def _validate_operation_support(self, resource_type: str, operation: str) -> tuple:
        """验证操作是否支持"""
        unsupported_operations = {
            "persistentvolume": ["update"],
            "storageclass": ["update"],
            "namespace": ["update"]
        }
        if resource_type in unsupported_operations and operation in unsupported_operations[resource_type]:
            return False, f"{resource_type} 不支持 {operation} 操作"
        return True, ""

    def _format_change_output(self, field: str, before_value: Any, after_value: Any) -> List[str]:
        """格式化变化输出"""
        if before_value == after_value:
            return []
        changes = []
        if isinstance(before_value, (str, int, float, bool)) and isinstance(after_value, (str, int, float, bool)):
            changes.append(f"   • {field}: {before_value} → {after_value}")
        elif isinstance(before_value, list) and isinstance(after_value, list):
            if before_value and isinstance(before_value[0], dict):
                changes.extend(self._format_complex_list_changes(field, before_value, after_value))
            else:
                before_set = set(str(item) for item in before_value) if before_value else set()
                after_set = set(str(item) for item in after_value) if after_value else set()
                for item in sorted(after_set - before_set):
                    changes.append(f"   • {field}: 新增 {item}")
                for item in sorted(before_set - after_set):
                    changes.append(f"   • {field}: 删除 {item}")
                if not (after_set - before_set or before_set - after_set) and before_value != after_value:
                    changes.append(f"   • {field}: 顺序或内容已更新")
        elif isinstance(before_value, dict) and isinstance(after_value, dict):
            before_dict = before_value if before_value else {}
            after_dict = after_value if after_value else {}
            before_keys, after_keys = set(before_dict.keys()), set(after_dict.keys())
            for key in sorted(after_keys - before_keys):
                changes.append(f"   • {field}.{key}: 新增 = {after_dict[key]}")
            for key in sorted(before_keys - after_keys):
                changes.append(f"   • {field}.{key}: 删除 = {before_dict[key]}")
            for key in sorted(before_keys & after_keys):
                if before_dict[key] != after_dict[key]:
                    changes.append(f"   • {field}.{key}: {before_dict[key]} → {after_dict[key]}")
        elif before_value is None and after_value is not None:
            if isinstance(after_value, list) and after_value and isinstance(after_value[0], dict):
                changes.append(f"   • {field}: 新增 {len(after_value)} 项配置")
                for i, item in enumerate(after_value):
                    changes.append(f"     [{i+1}] {self._format_dict_summary(item)}")
            else:
                changes.append(f"   • {field}: 未设置 → {after_value}")
        elif before_value is not None and after_value is None:
            changes.append(f"   • {field}: {before_value} → 未设置")
        else:
            changes.append(f"   • {field}: 类型变化 {type(before_value).__name__} → {type(after_value).__name__}")
        return changes

    def _format_complex_list_changes(self, field: str, before_list: List[Any], after_list: List[Any]) -> List[str]:
        """格式化复杂列表的变化"""
        def get_item_key(item):
            if isinstance(item, dict):
                if 'resources' in item and 'verbs' in item:
                    resources = ','.join(sorted(item.get('resources', [])))
                    verbs = ','.join(sorted(item.get('verbs', [])))
                    api_groups = ','.join(sorted(item.get('apiGroups', item.get('api_groups', []))))
                    return f"{api_groups}:{resources}:{verbs}"
                elif 'port' in item:
                    return f"{item.get('port')}:{item.get('protocol', 'TCP')}"
                return str(sorted(item.items()))
            return str(item)

        changes = []
        before_dict = {get_item_key(item): item for item in before_list}
        after_dict = {get_item_key(item): item for item in after_list}
        before_keys, after_keys = set(before_dict.keys()), set(after_dict.keys())
        for key in after_keys - before_keys:
            changes.append(f"   • {field}: 新增规则 {self._format_dict_summary(after_dict[key])}")
        for key in before_keys - after_keys:
            changes.append(f"   • {field}: 删除规则 {self._format_dict_summary(before_dict[key])}")
        for key in before_keys & after_keys:
            if before_dict[key] != after_dict[key]:
                changes.append(f"   • {field}: 修改规则")
                changes.append(f"     原: {self._format_dict_summary(before_dict[key])}")
                changes.append(f"     新: {self._format_dict_summary(after_dict[key])}")
        return changes

    def _format_dict_summary(self, item: dict) -> str:
        """格式化字典为简洁的摘要"""
        if not isinstance(item, dict):
            return str(item)
        if 'resources' in item and 'verbs' in item:
            api_groups = item.get('apiGroups', item.get('api_groups', ['']))
            resources = item.get('resources', [])
            verbs = item.get('verbs', [])
            api_groups_str = ','.join(api_groups) if api_groups != [''] else 'core'
            return f"[{api_groups_str}] {','.join(resources)} -> {','.join(verbs)}"
        elif 'port' in item:
            port = item.get('port')
            target_port = item.get('targetPort', item.get('target_port'))
            protocol = item.get('protocol', 'TCP')
            name = item.get('name', '')
            if target_port and target_port != port:
                return f"{name}:{port}->{target_port}/{protocol}" if name else f"{port}->{target_port}/{protocol}"
            return f"{name}:{port}/{protocol}" if name else f"{port}/{protocol}"
        else:
            key_values = [f"{k}={type(v).__name__}" if isinstance(v, (list, dict)) else f"{k}={v}" for k, v in item.items()]
            return "{" + ", ".join(key_values[:3]) + ("..." if len(key_values) > 3 else "") + "}"

    async def validate_and_preview_operation(self, resource_type: str, name: str,
                                            operation: str, namespace: str = "default",
                                            new_resource: Optional[Dict] = None) -> Dict:
        """统一的操作验证和预览方法"""
        result = {"valid": False, "message": "", "changes": [], "warnings": []}
        try:
            supported, reason = self._validate_operation_support(resource_type, operation)
            if not supported:
                result["message"] = f"❌ {reason}"
                return result

            if operation in ["update", "delete"]:
                if self._is_cluster_resource(resource_type):
                    current_state = await self.get_resource_before_operation(resource_type, name)
                else:
                    current_state = await self.get_resource_before_operation(resource_type, name, namespace)
                if current_state.get("error"):
                    result["message"] = f"❌ 资源不存在: {current_state['error']}"
                    return result

            if operation == "update" and new_resource:
                changes = self.compare_resource_changes(resource_type, current_state, new_resource)
                if changes and not changes.get("error"):
                    change_list = []
                    for field, change in changes.items():
                        if change is not None and not (isinstance(change, dict) and change.get('error')):
                            if isinstance(change, dict) and 'before' in change and 'after' in change:
                                change_list.extend(self._format_change_output(field, change['before'], change['after']))
                    result["changes"] = change_list

            if operation == "delete":
                result["warnings"] = [f"⚠️  将删除资源 {resource_type}/{name}，此操作不可逆"]

            result["valid"] = True
            result["message"] = "✅ 操作内容验证通过"
            return result
        except Exception as e:
            result["message"] = f"❌ 验证失败: {str(e)}"
            return result
