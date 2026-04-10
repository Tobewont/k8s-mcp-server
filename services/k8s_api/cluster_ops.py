from typing import Dict, List, Any, Optional
from kubernetes import client
from kubernetes.client.exceptions import ApiException
from utils.k8s_helpers import to_local_time_str

class ClusterOpsMixin:
    async def list_nodes(self, label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出 Node"""
        try:
            nodes = self.v1_api.list_node(label_selector=label_selector)
            
            node_list = []
            for node in nodes.items:
                node_info = {
                    "name": node.metadata.name,
                    "status": self._get_node_status(node),
                    "roles": self._get_node_roles(node),
                    "age": to_local_time_str(node.metadata.creation_timestamp) if node.metadata.creation_timestamp else None,
                    "version": node.status.node_info.kubelet_version if node.status.node_info else None,
                    "internal_ip": self._get_node_internal_ip(node),
                    "external_ip": self._get_node_external_ip(node),
                    "os_image": node.status.node_info.os_image if node.status.node_info else None,
                    "kernel_version": node.status.node_info.kernel_version if node.status.node_info else None,
                    "container_runtime": node.status.node_info.container_runtime_version if node.status.node_info else None,
                    "labels": node.metadata.labels or {},
                    "capacity": dict(node.status.capacity) if node.status.capacity else {},
                    "allocatable": dict(node.status.allocatable) if node.status.allocatable else {},
                }
                node_list.append(node_info)
            
            return node_list
            
        except ApiException as e:
            raise Exception(f"获取 Node 列表失败: {e.reason}")

    def _node_obj_to_dict(self, node) -> Dict[str, Any]:
        """将 V1Node 对象转换为 get_node 格式的字典（避免 N+1 查询时重复逻辑）"""
        return {
            "metadata": {
                "name": node.metadata.name,
                "labels": dict(node.metadata.labels) if node.metadata.labels else {},
                "annotations": dict(node.metadata.annotations) if node.metadata.annotations else {},
                "created": to_local_time_str(node.metadata.creation_timestamp) if node.metadata.creation_timestamp else None,
                "uid": node.metadata.uid
            },
            "spec": {
                "pod_cidr": node.spec.pod_cidr if node.spec else None,
                "provider_id": node.spec.provider_id if node.spec else None,
                "unschedulable": (node.spec.unschedulable or False) if node.spec else False,
                "taints": [
                    {"key": taint.key, "value": taint.value, "effect": taint.effect}
                    for taint in (node.spec.taints or [])
                ] if node.spec else []
            },
            "status": {
                "capacity": dict(node.status.capacity) if node.status and node.status.capacity else {},
                "allocatable": dict(node.status.allocatable) if node.status and node.status.allocatable else {},
                "conditions": [
                    {"type": c.type, "status": c.status, "reason": c.reason, "message": c.message}
                    for c in (node.status.conditions or [])
                ] if node.status else [],
                "addresses": [
                    {"type": a.type, "address": a.address}
                    for a in (node.status.addresses or [])
                ] if node.status else [],
                "node_info": {
                    "machine_id": node.status.node_info.machine_id,
                    "system_uuid": node.status.node_info.system_uuid,
                    "boot_id": node.status.node_info.boot_id,
                    "kernel_version": node.status.node_info.kernel_version,
                    "os_image": node.status.node_info.os_image,
                    "container_runtime_version": node.status.node_info.container_runtime_version,
                    "kubelet_version": node.status.node_info.kubelet_version,
                    "kube_proxy_version": node.status.node_info.kube_proxy_version,
                    "operating_system": node.status.node_info.operating_system,
                    "architecture": node.status.node_info.architecture
                } if node.status and node.status.node_info else {}
            }
        }

    async def get_node(self, name: str) -> Dict[str, Any]:
        """获取单个 Node 详情"""
        try:
            node = self.v1_api.read_node(name=name)
            return self._node_obj_to_dict(node)
        except ApiException as e:
            raise Exception(f"获取 Node 详情失败: {e.reason}")

    async def list_nodes_detailed(self, label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出所有 Node 的完整详情（单次 API 调用，避免 N+1）"""
        try:
            nodes = self.v1_api.list_node(label_selector=label_selector)
            return [self._node_obj_to_dict(n) for n in nodes.items]
        except ApiException as e:
            raise Exception(f"获取 Node 列表失败: {e.reason}")

    async def evict_pod(self, name: str, namespace: str = "default",
                        delete_options: Optional[client.V1DeleteOptions] = None) -> Dict[str, Any]:
        """驱逐 Pod（使用 Eviction API，尊重 PDB）"""
        try:
            body = client.V1Eviction(
                metadata=client.V1ObjectMeta(name=name, namespace=namespace),
                delete_options=delete_options
            )
            response = self.v1_api.create_namespaced_pod_eviction(
                name=name, namespace=namespace, body=body
            )
            return {
                "name": name,
                "namespace": namespace,
                "status": "evicted",
                "message": getattr(response, "message", None) or "Eviction initiated"
            }
        except ApiException as e:
            raise Exception(f"驱逐 Pod {namespace}/{name} 失败: {e.reason}")

    async def cordon_node(self, node_name: str) -> Dict[str, Any]:
        """标记节点为不可调度（cordon），不驱逐现有 Pod"""
        try:
            node = self.v1_api.read_node(name=node_name)
            was_unschedulable = bool(node.spec.unschedulable)
            if not was_unschedulable:
                self.v1_api.patch_node(name=node_name, body={"spec": {"unschedulable": True}})
            return {
                "node": node_name,
                "action": "cordon",
                "unschedulable": True,
                "was_already_cordoned": was_unschedulable,
            }
        except ApiException as e:
            raise Exception(f"Cordon 节点失败: {e.reason}")

    async def uncordon_node(self, node_name: str) -> Dict[str, Any]:
        """恢复节点为可调度（uncordon）"""
        try:
            node = self.v1_api.read_node(name=node_name)
            was_unschedulable = bool(node.spec.unschedulable)
            if was_unschedulable:
                self.v1_api.patch_node(name=node_name, body={"spec": {"unschedulable": False}})
            return {
                "node": node_name,
                "action": "uncordon",
                "unschedulable": False,
                "was_already_schedulable": not was_unschedulable,
            }
        except ApiException as e:
            raise Exception(f"Uncordon 节点失败: {e.reason}")

    async def drain_node(self, node_name: str, ignore_daemonset: bool = True,
                         ignore_mirror_pods: bool = True) -> Dict[str, Any]:
        """节点排水：cordon 后驱逐该节点上所有可驱逐的 Pod"""
        try:
            node = self.v1_api.read_node(name=node_name)
            if not node.spec.unschedulable:
                self.v1_api.patch_node(name=node_name, body={"spec": {"unschedulable": True}})

            # 2. 列出该节点上的所有 Pod
            pods = self.v1_api.list_pod_for_all_namespaces(
                field_selector=f"spec.nodeName={node_name}"
            )

            evicted = []
            skipped = []
            failed = []

            for pod in pods.items:
                ns = pod.metadata.namespace
                name = pod.metadata.name

                # 跳过 DaemonSet Pod
                if ignore_daemonset and pod.metadata.owner_references:
                    if any(r.kind == "DaemonSet" for r in pod.metadata.owner_references):
                        skipped.append({"name": name, "namespace": ns, "reason": "DaemonSet"})
                        continue

                # 跳过 mirror pod（静态 Pod 的镜像）
                if ignore_mirror_pods and pod.metadata.annotations:
                    if "kubernetes.io/config.mirror" in pod.metadata.annotations:
                        skipped.append({"name": name, "namespace": ns, "reason": "mirror pod"})
                        continue

                # 跳过无控制器的 Pod（静态 Pod 等）
                if not pod.metadata.owner_references or len(pod.metadata.owner_references) == 0:
                    skipped.append({"name": name, "namespace": ns, "reason": "no controller"})
                    continue

                # 驱逐
                try:
                    body = client.V1Eviction(
                        metadata=client.V1ObjectMeta(name=name, namespace=ns)
                    )
                    self.v1_api.create_namespaced_pod_eviction(name=name, namespace=ns, body=body)
                    evicted.append({"name": name, "namespace": ns})
                except ApiException as e:
                    failed.append({"name": name, "namespace": ns, "error": str(e.reason)})

            return {
                "node": node_name,
                "cordoned": True,
                "evicted": evicted,
                "skipped": skipped,
                "failed": failed,
                "summary": {
                    "evicted_count": len(evicted),
                    "skipped_count": len(skipped),
                    "failed_count": len(failed)
                }
            }
        except ApiException as e:
            raise Exception(f"节点排水失败: {e.reason}")

    # ========================== Namespace 服务层方法 ==========================

    async def list_namespaces(self, label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出 Namespace"""
        try:
            namespaces = self.v1_api.list_namespace(label_selector=label_selector)
            
            namespace_list = []
            for namespace in namespaces.items:
                namespace_info = {
                    "name": namespace.metadata.name,
                    "status": namespace.status.phase,
                    "created": to_local_time_str(namespace.metadata.creation_timestamp) if namespace.metadata.creation_timestamp else None,
                    "labels": namespace.metadata.labels or {},
                    "annotations": namespace.metadata.annotations or {}
                }
                namespace_list.append(namespace_info)
            
            return namespace_list
            
        except ApiException as e:
            raise Exception(f"获取 Namespace 列表失败: {e.reason}")

    async def get_namespace(self, name: str) -> Dict[str, Any]:
        """获取 Namespace 详情"""
        try:
            namespace = self.v1_api.read_namespace(name=name)
            
            return {
                "name": namespace.metadata.name,
                "uid": namespace.metadata.uid,
                "status": namespace.status.phase,
                "created": to_local_time_str(namespace.metadata.creation_timestamp) if namespace.metadata.creation_timestamp else None,
                "labels": namespace.metadata.labels or {},
                "annotations": namespace.metadata.annotations or {},
                "conditions": [
                    {
                        "type": condition.type,
                        "status": condition.status,
                        "reason": condition.reason,
                        "message": condition.message,
                        "last_transition_time": to_local_time_str(condition.last_transition_time) if condition.last_transition_time else None
                    }
                    for condition in (namespace.status.conditions or [])
                ]
            }
            
        except ApiException as e:
            raise Exception(f"获取 Namespace 详情失败: {e.reason}")

    async def create_namespace(self, name: Optional[str] = None, labels: Optional[Dict[str, str]] = None,
                        annotations: Optional[Dict[str, str]] = None, resource: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
        """创建 Namespace"""
        try:
            # 批量操作模式，传入完整的资源定义
            if resource:
                response = self.v1_api.create_namespace(body=resource)
                
                return {
                    "name": response.metadata.name,
                    "status": "created",
                    "uid": response.metadata.uid
                }
            
            # 单体操作模式，使用简化参数创建
            if not name:
                raise ValueError("name参数是必需的")
            
            namespace = client.V1Namespace(
                metadata=client.V1ObjectMeta(
                    name=name,
                    labels=labels,
                    annotations=annotations
                )
            )
            
            response = self.v1_api.create_namespace(body=namespace)
            
            return {
                "name": response.metadata.name,
                "status": "created",
                "uid": response.metadata.uid
            }
            
        except ApiException as e:
            raise Exception(f"创建 Namespace 失败: {e.reason}")

    async def update_namespace(self, name: str, labels: Optional[Dict[str, str]] = None,
                           annotations: Optional[Dict[str, str]] = None, resource: Optional[Dict] = None) -> Dict[str, Any]:
        """更新 Namespace
        
        Args:
            name: Namespace名称
            labels: 标签
            annotations: 注解
            resource: 完整的资源定义
            
        Returns:
            更新后的Namespace对象
        """
        try:
            if resource is not None:
                # 批量操作模式，传入完整的资源定义
                body = resource
                # 确保metadata中有正确的name
                if 'metadata' not in body:
                    body['metadata'] = {}
                body['metadata']['name'] = name
                
                response = self.v1_api.patch_namespace(
                    name=name,
                    body=body
                )
            else:
                # 单体操作模式，使用简化参数更新
                # 获取当前Namespace
                current_namespace = self.v1_api.read_namespace(name=name)
                
                # 更新标签
                if labels is not None:
                    if current_namespace.metadata.labels is None:
                        current_namespace.metadata.labels = {}
                    current_namespace.metadata.labels.update(labels)
                
                # 更新注解
                if annotations is not None:
                    if current_namespace.metadata.annotations is None:
                        current_namespace.metadata.annotations = {}
                    current_namespace.metadata.annotations.update(annotations)
                
                # 更新Namespace
                response = self.v1_api.replace_namespace(
                name=name,
                body=current_namespace
            )
            
            return {
                "name": response.metadata.name,
                "uid": response.metadata.uid,
                "labels": response.metadata.labels,
                "annotations": response.metadata.annotations,
                "status": response.status.phase,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None
            }
            
        except ApiException as e:
            raise Exception(f"更新Namespace失败: {e}")
        except Exception as e:
            raise Exception(f"更新Namespace时发生错误: {e}")

    async def delete_namespace(self, name: str) -> Dict[str, Any]:
        """删除 Namespace"""
        try:
            response = self.v1_api.delete_namespace(name=name)
            
            return {
                "name": name,
                "status": "deleted"
            }
            
        except ApiException as e:
            raise Exception(f"删除 Namespace 失败: {e.reason}")

    # ========================== Event 服务层方法 ==========================

    async def list_events(self, namespace: str = "default",
                   field_selector: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出 Event"""
        try:
            if namespace == "all":
                events = self.v1_api.list_event_for_all_namespaces(
                    field_selector=field_selector
                )
            else:
                events = self.v1_api.list_namespaced_event(
                    namespace=namespace,
                    field_selector=field_selector
                )
            
            event_list = []
            for event in events.items:
                event_info = {
                    "name": event.metadata.name,
                    "namespace": event.metadata.namespace,
                    "type": event.type,
                    "reason": event.reason,
                    "message": event.message,
                    "source": f"{event.source.component}/{event.source.host}" if event.source else None,
                    "first_timestamp": to_local_time_str(event.first_timestamp) if event.first_timestamp else None,
                    "last_timestamp": to_local_time_str(event.last_timestamp) if event.last_timestamp else None,
                    "count": event.count,
                    "object": {
                        "kind": event.involved_object.kind,
                        "name": event.involved_object.name,
                        "namespace": event.involved_object.namespace
                    } if event.involved_object else None
                }
                event_list.append(event_info)
            
            return event_list
            
        except ApiException as e:
            raise Exception(f"获取 Event 列表失败: {e.reason}")

    # ========================== 辅助方法 ==========================

    def _get_node_status(self, node) -> str:
        """获取节点状态"""
        if not node.status.conditions:
            return "Unknown"
        
        for condition in node.status.conditions:
            if condition.type == "Ready":
                return "Ready" if condition.status == "True" else "NotReady"
        return "Unknown"

    def _get_node_roles(self, node) -> List[str]:
        """获取节点角色"""
        roles = []
        labels = node.metadata.labels or {}
        
        for label_key in labels:
            if label_key.startswith("node-role.kubernetes.io/"):
                role = label_key.split("/", 1)[1]
                if role:
                    roles.append(role)
        
        return roles if roles else ["worker"]

    def _get_node_internal_ip(self, node) -> str:
        """获取节点内部IP"""
        if node.status.addresses:
            for address in node.status.addresses:
                if address.type == "InternalIP":
                    return address.address
        return "unknown"

    def _get_node_external_ip(self, node) -> str:
        """获取节点外部IP"""
        if node.status.addresses:
            for address in node.status.addresses:
                if address.type == "ExternalIP":
                    return address.address
        return "none"

    async def check_api_health(self) -> Dict[str, Any]:
        """检查 API 服务器健康状态"""
        try:
            version_api = client.VersionApi(api_client=self._api_client)
            version_info = version_api.get_code()
            
            return {
                "status": "healthy",
                "version": {
                    "major": version_info.major,
                    "minor": version_info.minor,
                    "git_version": version_info.git_version,
                    "git_commit": version_info.git_commit,
                    "platform": version_info.platform
                }
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    async def get_cluster_info(self) -> Dict[str, Any]:
        """获取集群信息（按权限级别优雅降级：无集群级权限时返回部分结果）"""
        result: Dict[str, Any] = {"api_version": "v1", "cluster_name": "unknown"}

        try:
            nodes = self.v1_api.list_node()
            result["node_count"] = len(nodes.items)
            if nodes.items and nodes.items[0].metadata.labels:
                result["cluster_name"] = nodes.items[0].metadata.labels.get(
                    "kubernetes.io/hostname", "unknown"
                )
        except ApiException as e:
            if e.status == 403:
                result["node_count_error"] = "权限不足：需要集群级 nodes list 权限"
            else:
                result["node_count_error"] = f"获取节点信息失败: {e.reason}"
        except Exception as e:
            result["node_count_error"] = str(e)

        try:
            namespaces = self.v1_api.list_namespace()
            result["namespace_count"] = len(namespaces.items)
        except ApiException as e:
            if e.status == 403:
                result["namespace_count_error"] = "权限不足：需要集群级 namespaces list 权限"
            else:
                result["namespace_count_error"] = f"获取命名空间信息失败: {e.reason}"
        except Exception as e:
            result["namespace_count_error"] = str(e)

        return result

    async def get_node_metrics(self) -> List[Dict[str, Any]]:
        """获取所有节点的 CPU、内存使用（依赖 metrics-server）"""
        try:
            co_api = client.CustomObjectsApi(self._api_client)
            resp = co_api.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes")
            items = resp.get("items", [])
            result = []
            for item in items:
                meta = item.get("metadata", {})
                usage = item.get("usage", {})
                result.append({
                    "name": meta.get("name", ""),
                    "cpu": usage.get("cpu", "0"),
                    "memory": usage.get("memory", "0"),
                    "timestamp": item.get("timestamp", ""),
                    "window": item.get("window", ""),
                })
            return result
        except ApiException as e:
            if e.status == 404 or "metrics.k8s.io" in str(e):
                raise Exception("集群未部署 metrics-server，无法获取节点资源使用")
            raise Exception(f"获取节点 metrics 失败: {str(e)}")

    async def get_pod_metrics(self, namespace: str = "default") -> List[Dict[str, Any]]:
        """获取指定命名空间下所有 Pod 的 CPU、内存使用（依赖 metrics-server）"""
        try:
            co_api = client.CustomObjectsApi(self._api_client)
            resp = co_api.list_namespaced_custom_object(
                "metrics.k8s.io", "v1beta1", namespace, "pods"
            )
            items = resp.get("items", [])
            result = []
            for item in items:
                meta = item.get("metadata", {})
                containers = item.get("containers", [])
                container_list = [
                    {"name": c.get("name", ""), "cpu": c.get("usage", {}).get("cpu", "0"),
                     "memory": c.get("usage", {}).get("memory", "0")}
                    for c in containers
                ]
                cpu = container_list[0]["cpu"] if container_list else "0"
                memory = container_list[0]["memory"] if container_list else "0"
                result.append({
                    "name": meta.get("name", ""),
                    "namespace": meta.get("namespace", namespace),
                    "cpu": cpu,
                    "memory": memory,
                    "containers": container_list,
                    "timestamp": item.get("timestamp", ""),
                    "window": item.get("window", ""),
                })
            return result
        except ApiException as e:
            if e.status == 404 or "metrics.k8s.io" in str(e):
                raise Exception("集群未部署 metrics-server，无法获取 Pod 资源使用")
            raise Exception(f"获取 Pod metrics 失败: {str(e)}")

    def get_dynamic_client(self):
        """获取 DynamicClient，用于动态操作任意 API 资源"""
        if self._api_client is None:
            raise RuntimeError("API 客户端未初始化，请先调用 load_config()")
        from kubernetes.dynamic import DynamicClient
        return DynamicClient(self._api_client)
