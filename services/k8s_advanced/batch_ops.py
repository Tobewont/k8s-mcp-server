"""
Kubernetes 进阶服务 - 批量操作
"""
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class BatchOpsMixin:
    """批量操作 Mixin"""

    def _get_resource_operation(self, resource_type: str, operation: str, namespace: str = "default"):
        """获取资源操作方法的统一接口"""
        resource_type = resource_type.lower()

        resource_type_normalization = {
            "hpa": "horizontalpodautoscalers", "pvc": "persistentvolumeclaims", "pv": "persistentvolumes",
            "sc": "storageclasses", "sa": "serviceaccounts", "cm": "configmaps", "svc": "services",
            "deploy": "deployments", "sts": "statefulsets", "ds": "daemonsets", "rs": "replicasets",
            "rc": "replicationcontrollers", "ep": "endpoints", "ev": "events", "ns": "namespaces",
            "no": "nodes", "po": "pods",
            "deployment": "deployments", "statefulset": "statefulsets", "daemonset": "daemonsets",
            "service": "services", "configmap": "configmaps", "secret": "secrets", "job": "jobs",
            "cronjob": "cronjobs", "ingress": "ingresses", "storageclass": "storageclasses",
            "persistentvolume": "persistentvolumes", "persistentvolumeclaim": "persistentvolumeclaims",
            "role": "roles", "clusterrole": "clusterroles", "rolebinding": "rolebindings",
            "clusterrolebinding": "clusterrolebindings", "serviceaccount": "serviceaccounts",
            "namespace": "namespaces", "pod": "pods", "node": "nodes",
            "horizontalpodautoscaler": "horizontalpodautoscalers", "networkpolicy": "networkpolicies",
            "resourcequota": "resourcequotas"
        }
        resource_type = resource_type_normalization.get(resource_type, resource_type)

        list_operations = {
            "deployments": lambda: self.k8s_service.list_deployments(namespace=namespace),
            "statefulsets": lambda: self.k8s_service.list_statefulsets(namespace=namespace),
            "daemonsets": lambda: self.k8s_service.list_daemonsets(namespace=namespace),
            "services": lambda: self.k8s_service.list_services(namespace=namespace),
            "configmaps": lambda: self.k8s_service.list_configmaps(namespace=namespace),
            "secrets": lambda: self.k8s_service.list_secrets(namespace=namespace),
            "jobs": lambda: self.k8s_service.list_jobs(namespace=namespace),
            "cronjobs": lambda: self.k8s_service.list_cronjobs(namespace=namespace),
            "ingresses": lambda: self.k8s_service.list_ingresses(namespace=namespace),
            "storageclasses": lambda: self.k8s_service.list_storageclasses(),
            "persistentvolumes": lambda: self.k8s_service.list_persistentvolumes(),
            "persistentvolumeclaims": lambda: self.k8s_service.list_persistentvolumeclaims(namespace=namespace),
            "roles": lambda: self.k8s_service.list_roles(namespace=namespace),
            "clusterroles": lambda: self.k8s_service.list_cluster_roles(),
            "rolebindings": lambda: self.k8s_service.list_role_bindings(namespace=namespace),
            "clusterrolebindings": lambda: self.k8s_service.list_cluster_role_bindings(),
            "serviceaccounts": lambda: self.k8s_service.list_serviceaccounts(namespace=namespace),
            "namespaces": lambda: self.k8s_service.list_namespaces(),
            "pods": lambda: self.k8s_service.list_pods(namespace=namespace),
            "nodes": lambda: self.k8s_service.list_nodes(),
            "horizontalpodautoscalers": lambda: self.k8s_service.list_hpas(namespace=namespace),
            "networkpolicies": lambda: self.k8s_service.list_network_policies(namespace=namespace),
            "resourcequotas": lambda: self.k8s_service.list_resource_quotas(namespace=namespace),
        }

        create_operations = {
            "deployments": lambda resource: self.k8s_service.create_deployment(resource=resource, namespace=namespace),
            "statefulsets": lambda resource: self.k8s_service.create_statefulset(resource=resource, namespace=namespace),
            "daemonsets": lambda resource: self.k8s_service.create_daemonset(resource=resource, namespace=namespace),
            "services": lambda resource: self.k8s_service.create_service(resource=resource, namespace=namespace),
            "configmaps": lambda resource: self.k8s_service.create_configmap(resource=resource, namespace=namespace),
            "secrets": lambda resource: self.k8s_service.create_secret(resource=resource, namespace=namespace),
            "jobs": lambda resource: self.k8s_service.create_job(resource=resource, namespace=namespace),
            "cronjobs": lambda resource: self.k8s_service.create_cronjob(resource=resource, namespace=namespace),
            "ingresses": lambda resource: self.k8s_service.create_ingress(resource=resource, namespace=namespace),
            "storageclasses": lambda resource: self.k8s_service.create_storageclass(resource=resource),
            "persistentvolumes": lambda resource: self.k8s_service.create_persistentvolume(resource=resource),
            "persistentvolumeclaims": lambda resource: self.k8s_service.create_persistentvolumeclaim(resource=resource, namespace=namespace),
            "roles": lambda resource: self.k8s_service.create_role(resource=resource, namespace=namespace),
            "clusterroles": lambda resource: self.k8s_service.create_cluster_role(resource=resource),
            "rolebindings": lambda resource: self.k8s_service.create_role_binding(resource=resource, namespace=namespace),
            "clusterrolebindings": lambda resource: self.k8s_service.create_cluster_role_binding(resource=resource),
            "serviceaccounts": lambda resource: self.k8s_service.create_serviceaccount(resource=resource, namespace=namespace),
            "namespaces": lambda resource: self.k8s_service.create_namespace(resource=resource),
            "horizontalpodautoscalers": lambda resource: self.k8s_service.create_hpa(resource=resource, namespace=namespace),
            "networkpolicies": lambda resource: self.k8s_service.create_network_policy(resource=resource, namespace=namespace),
            "resourcequotas": lambda resource: self.k8s_service.create_resource_quota(resource=resource, namespace=namespace),
        }

        update_operations = {
            "deployments": lambda name, resource: self.k8s_service.update_deployment(name=name, namespace=namespace, resource=resource),
            "statefulsets": lambda name, resource: self.k8s_service.update_statefulset(name=name, namespace=namespace, resource=resource),
            "daemonsets": lambda name, resource: self.k8s_service.update_daemonset(name=name, namespace=namespace, resource=resource),
            "services": lambda name, resource: self.k8s_service.update_service(name=name, namespace=namespace, resource=resource),
            "configmaps": lambda name, resource: self.k8s_service.update_configmap(name=name, namespace=namespace, resource=resource),
            "secrets": lambda name, resource: self.k8s_service.update_secret(name=name, namespace=namespace, resource=resource),
            "jobs": lambda name, resource: self.k8s_service.update_job(name=name, namespace=namespace, resource=resource),
            "cronjobs": lambda name, resource: self.k8s_service.update_cronjob(name=name, namespace=namespace, resource=resource),
            "ingresses": lambda name, resource: self.k8s_service.update_ingress(name=name, namespace=namespace, resource=resource),
            "storageclasses": lambda name, resource: self.k8s_service.update_storageclass(name=name, resource=resource),
            "persistentvolumes": lambda name, resource: self.k8s_service.update_persistentvolume(name=name, resource=resource),
            "persistentvolumeclaims": lambda name, resource: self.k8s_service.update_persistentvolumeclaim(name=name, namespace=namespace, resource=resource),
            "roles": lambda name, resource: self.k8s_service.update_role(name=name, namespace=namespace, resource=resource),
            "clusterroles": lambda name, resource: self.k8s_service.update_cluster_role(name=name, resource=resource),
            "rolebindings": lambda name, resource: self.k8s_service.update_role_binding(name=name, namespace=namespace, resource=resource),
            "clusterrolebindings": lambda name, resource: self.k8s_service.update_cluster_role_binding(name=name, resource=resource),
            "serviceaccounts": lambda name, resource: self.k8s_service.update_serviceaccount(name=name, namespace=namespace, resource=resource),
            "namespaces": lambda name, resource: self.k8s_service.update_namespace(name=name, resource=resource),
            "horizontalpodautoscalers": lambda name, resource: self.k8s_service.update_hpa(name=name, namespace=namespace, resource=resource),
            "networkpolicies": lambda name, resource: self.k8s_service.update_network_policy(name=name, namespace=namespace, resource=resource),
            "resourcequotas": lambda name, resource: self.k8s_service.update_resource_quota(name=name, namespace=namespace, resource=resource),
        }

        get_operations = {
            "deployments": lambda name: self.k8s_service.get_deployment(name=name, namespace=namespace),
            "statefulsets": lambda name: self.k8s_service.get_statefulset(name=name, namespace=namespace),
            "daemonsets": lambda name: self.k8s_service.get_daemonset(name=name, namespace=namespace),
            "services": lambda name: self.k8s_service.get_service(name=name, namespace=namespace),
            "configmaps": lambda name: self.k8s_service.get_configmap(name=name, namespace=namespace),
            "secrets": lambda name: self.k8s_service.get_secret(name=name, namespace=namespace),
            "jobs": lambda name: self.k8s_service.get_job(name=name, namespace=namespace),
            "cronjobs": lambda name: self.k8s_service.get_cronjob(name=name, namespace=namespace),
            "ingresses": lambda name: self.k8s_service.get_ingress(name=name, namespace=namespace),
            "storageclasses": lambda name: self.k8s_service.get_storageclass(name=name),
            "persistentvolumes": lambda name: self.k8s_service.get_persistentvolume(name=name),
            "persistentvolumeclaims": lambda name: self.k8s_service.get_persistentvolumeclaim(name=name, namespace=namespace),
            "roles": lambda name: self.k8s_service.get_role(name=name, namespace=namespace),
            "clusterroles": lambda name: self.k8s_service.get_cluster_role(name=name),
            "rolebindings": lambda name: self.k8s_service.get_role_binding(name=name, namespace=namespace),
            "clusterrolebindings": lambda name: self.k8s_service.get_cluster_role_binding(name=name),
            "serviceaccounts": lambda name: self.k8s_service.get_serviceaccount(name=name, namespace=namespace),
            "namespaces": lambda name: self.k8s_service.get_namespace(name=name),
            "pods": lambda name: self.k8s_service.get_pod(name=name, namespace=namespace),
            "nodes": lambda name: self.k8s_service.get_node(name=name),
            "horizontalpodautoscalers": lambda name: self.k8s_service.get_hpa(name=name, namespace=namespace),
            "networkpolicies": lambda name: self.k8s_service.get_network_policy(name=name, namespace=namespace),
            "resourcequotas": lambda name: self.k8s_service.get_resource_quota(name=name, namespace=namespace),
        }

        delete_operations = {
            "deployments": lambda name, grace: self.k8s_service.delete_deployment(name=name, namespace=namespace, grace_period_seconds=grace),
            "statefulsets": lambda name, grace: self.k8s_service.delete_statefulset(name=name, namespace=namespace, grace_period_seconds=grace),
            "daemonsets": lambda name, grace: self.k8s_service.delete_daemonset(name=name, namespace=namespace),
            "services": lambda name, grace: self.k8s_service.delete_service(name=name, namespace=namespace),
            "configmaps": lambda name, grace: self.k8s_service.delete_configmap(name=name, namespace=namespace),
            "secrets": lambda name, grace: self.k8s_service.delete_secret(name=name, namespace=namespace),
            "jobs": lambda name, grace: self.k8s_service.delete_job(name=name, namespace=namespace),
            "cronjobs": lambda name, grace: self.k8s_service.delete_cronjob(name=name, namespace=namespace),
            "ingresses": lambda name, grace: self.k8s_service.delete_ingress(name=name, namespace=namespace),
            "storageclasses": lambda name, grace: self.k8s_service.delete_storageclass(name=name),
            "persistentvolumes": lambda name, grace: self.k8s_service.delete_persistentvolume(name=name),
            "persistentvolumeclaims": lambda name, grace: self.k8s_service.delete_persistentvolumeclaim(name=name, namespace=namespace),
            "roles": lambda name, grace: self.k8s_service.delete_role(name=name, namespace=namespace),
            "clusterroles": lambda name, grace: self.k8s_service.delete_cluster_role(name=name),
            "rolebindings": lambda name, grace: self.k8s_service.delete_role_binding(name=name, namespace=namespace),
            "clusterrolebindings": lambda name, grace: self.k8s_service.delete_cluster_role_binding(name=name),
            "serviceaccounts": lambda name, grace: self.k8s_service.delete_serviceaccount(name=name, namespace=namespace, grace_period_seconds=grace),
            "namespaces": lambda name, grace: self.k8s_service.delete_namespace(name=name),
            "pods": lambda name, grace: self.k8s_service.delete_pod(name=name, namespace=namespace, grace_period_seconds=grace),
            "horizontalpodautoscalers": lambda name, grace: self.k8s_service.delete_hpa(name=name, namespace=namespace),
            "networkpolicies": lambda name, grace: self.k8s_service.delete_network_policy(name=name, namespace=namespace),
            "resourcequotas": lambda name, grace: self.k8s_service.delete_resource_quota(name=name, namespace=namespace),
        }

        operations_map = {
            "list": list_operations,
            "get": get_operations,
            "create": create_operations,
            "update": update_operations,
            "delete": delete_operations
        }

        if operation not in operations_map:
            raise ValueError(f"不支持的操作类型: {operation}")
        if resource_type not in operations_map[operation]:
            raise ValueError(f"资源类型 {resource_type} 不支持 {operation} 操作")
        return operations_map[operation][resource_type]

    async def _resolve_to_api_version_kind(self, resource_type: str) -> tuple:
        rt = resource_type.lower().strip()
        kind = self._resource_type_to_kind.get(rt)
        if kind:
            api_version = self._api_version_map.get(kind, "v1")
            return (api_version, kind)
        for r in await self._dynamic_service.list_available_resources_async():
            if r["name"].lower() == rt or r["kind"].lower() == rt:
                return (r["group_version"], r["kind"])
        raise ValueError(f"无法解析资源类型: {resource_type}，请使用 batch_list_resources(resource_types='all') 查看可用资源")

    async def list_available_api_resources(self) -> List[Dict[str, Any]]:
        """列出集群中所有可发现的 API 资源"""
        return await self._dynamic_service.list_available_resources_async()

    async def batch_list_resources(self, resource_types: List[str], namespace: str = "default") -> Dict:
        """批量查看资源"""
        if len(resource_types) == 1 and resource_types[0].lower() in ("all", "__all__", "__discover__"):
            try:
                resources = await self.list_available_api_resources()
                return {
                    "success": [{"resource_type": "__discover__", "available_resources": resources, "count": len(resources)}],
                    "failed": [],
                    "total": 1
                }
            except Exception as e:
                return {"success": [], "failed": [{"resource_type": "__discover__", "error": str(e)}], "total": 1}

        results = {"success": [], "failed": [], "total": len(resource_types)}
        for resource_type in resource_types:
            try:
                resource_type = resource_type.lower()
                try:
                    operation_func = self._get_resource_operation(resource_type, "list", namespace)
                    result = await operation_func()
                except ValueError:
                    api_version, kind = await self._resolve_to_api_version_kind(resource_type)
                    result = await self._dynamic_service.list_resources_async(api_version, kind, namespace)
                results["success"].append({
                    "resource_type": resource_type,
                    "count": len(result) if isinstance(result, list) else 0,
                    "items": result
                })
            except Exception as e:
                results["failed"].append({"resource_type": resource_type, "error": str(e)})
        return results

    async def batch_describe_resources(self, resource_specs: List[Dict], namespace: str = "default") -> Dict:
        """批量获取资源详细信息"""
        results = {"success": [], "failed": [], "total": len(resource_specs)}
        for spec in resource_specs:
            try:
                kind = spec["kind"]
                name = spec["name"]
                api_version = spec.get("apiVersion") or self._api_version_map.get(kind, "v1")
                try:
                    resource_type = self._kind_to_resource_type(kind)
                    operation_func = self._get_resource_operation(resource_type, "get", namespace)
                    result = await operation_func(name)
                except ValueError:
                    result = await self._dynamic_service.get_resource_async(api_version, kind, name, namespace)
                results["success"].append({"kind": kind, "name": name, "namespace": namespace, "details": result})
            except Exception as e:
                results["failed"].append({"kind": spec.get("kind", "Unknown"), "name": spec.get("name", "Unknown"), "error": str(e)})
        return results

    def _kind_to_resource_type(self, kind: str) -> str:
        kind_mapping = {
            "Pod": "pods", "Deployment": "deployments", "StatefulSet": "statefulsets", "DaemonSet": "daemonsets",
            "Service": "services", "ConfigMap": "configmaps", "Secret": "secrets", "Job": "jobs",
            "CronJob": "cronjobs", "Ingress": "ingresses", "PersistentVolumeClaim": "persistentvolumeclaims",
            "ServiceAccount": "serviceaccounts", "Role": "roles", "RoleBinding": "rolebindings",
            "Node": "nodes", "Namespace": "namespaces", "HorizontalPodAutoscaler": "horizontalpodautoscalers",
            "HPA": "horizontalpodautoscalers", "NetworkPolicy": "networkpolicies", "ResourceQuota": "resourcequotas"
        }
        resource_type = kind_mapping.get(kind)
        if not resource_type:
            raise ValueError(f"不支持的资源类型: {kind}")
        return resource_type

    async def batch_create_resources(self, resources: List[Dict], namespace: str = "default") -> Dict:
        """批量创建k8s资源"""
        logger.info("开始批量创建 %d 个资源", len(resources))
        results = {"success": [], "failed": [], "total": len(resources)}
        for resource in resources:
            resource_type = resource.get("kind", "").lower()
            resource_name = resource.get("metadata", {}).get("name", "unknown")
            try:
                try:
                    operation_func = self._get_resource_operation(resource_type, "create", namespace)
                    result = await operation_func(resource)
                except ValueError:
                    result = await self._dynamic_service.create_resource_async(resource, namespace)
                results["success"].append({"name": resource_name, "kind": resource_type, "result": result})
            except Exception as e:
                results["failed"].append({"name": resource_name, "kind": resource_type, "error": str(e)})
        logger.info("批量创建完成: %d 成功, %d 失败", len(results['success']), len(results['failed']))
        return results

    async def batch_update_resources(self, resources: List[Dict], namespace: str = "default") -> Dict:
        """批量更新资源"""
        logger.info("开始批量更新 %d 个资源", len(resources))
        results = {"success": [], "failed": [], "total": len(resources)}
        for resource in resources:
            resource_type = resource.get("kind", "").lower()
            resource_name = resource.get("metadata", {}).get("name", "unknown")
            try:
                try:
                    operation_func = self._get_resource_operation(resource_type, "update", namespace)
                    result = await operation_func(resource_name, resource)
                except ValueError:
                    result = await self._dynamic_service.update_resource_async(resource, namespace)
                results["success"].append({"name": resource_name, "kind": resource_type, "result": result})
            except Exception as e:
                results["failed"].append({"name": resource_name, "kind": resource_type, "error": str(e)})
        logger.info("批量更新完成: %d 成功, %d 失败", len(results['success']), len(results['failed']))
        return results

    async def batch_rollout_resources(self, operations: List[Dict], namespace: str = "default") -> Dict:
        """批量发布操作"""
        results = {"success": [], "failed": [], "total": len(operations)}
        supported_kinds = ["deployment", "statefulset", "daemonset"]
        for op in operations:
            kind = (op.get("kind") or "").lower()
            name = op.get("name", "")
            action = (op.get("action") or "status").lower()
            ns = op.get("namespace") or namespace
            try:
                if kind not in supported_kinds:
                    raise ValueError(f"不支持的资源类型: {kind}")
                if not name:
                    raise ValueError("必须指定 name")
                if action == "status":
                    result = await self.k8s_service.rollout_status(kind, name, ns)
                elif action == "undo":
                    result = await self.k8s_service.rollout_undo(kind, name, ns, op.get("revision"))
                elif action == "pause":
                    result = await self.k8s_service.rollout_pause(kind, name, ns)
                elif action == "resume":
                    result = await self.k8s_service.rollout_resume(kind, name, ns)
                else:
                    raise ValueError(f"不支持的操作: {action}，支持 status/undo/pause/resume")
                results["success"].append({"kind": kind, "name": name, "action": action, "result": result})
            except Exception as e:
                results["failed"].append({"kind": kind, "name": name, "action": action, "error": str(e)})
        return results

    async def batch_top_resources(self, resource_types: List[str], namespace: str = "default") -> Dict:
        """批量获取 Node/Pod 的 CPU、内存使用"""
        results = {"nodes": [], "pods": [], "error": None}
        try:
            if "nodes" in resource_types or "node" in resource_types:
                results["nodes"] = await self.k8s_service.get_node_metrics()
            if "pods" in resource_types or "pod" in resource_types:
                results["pods"] = await self.k8s_service.get_pod_metrics(namespace)
        except Exception as e:
            results["error"] = str(e)
        return results

    async def batch_delete_resources(self, resources: List[Dict], namespace: str = "default",
                                     grace_period_seconds: Optional[int] = None) -> Dict:
        """批量删除资源"""
        logger.info("开始批量删除 %d 个资源", len(resources))
        results = {"success": [], "failed": [], "total": len(resources)}
        for resource in resources:
            resource_type = resource.get("kind", "").lower()
            resource_name = resource.get("metadata", {}).get("name", "unknown")
            try:
                try:
                    operation_func = self._get_resource_operation(resource_type, "delete", namespace)
                    result = await operation_func(resource_name, grace_period_seconds)
                except ValueError:
                    kind = resource.get("kind", "Unknown")
                    api_version = resource.get("apiVersion") or self._api_version_map.get(kind, "v1")
                    result = await self._dynamic_service.delete_resource_async(
                        api_version, kind, resource_name, namespace, grace_period_seconds
                    )
                results["success"].append({"name": resource_name, "kind": resource_type, "result": result})
            except Exception as e:
                results["failed"].append({"name": resource_name, "kind": resource_type, "error": str(e)})
        logger.info("批量删除完成: %d 成功, %d 失败", len(results['success']), len(results['failed']))
        return results
