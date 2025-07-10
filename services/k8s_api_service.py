"""
Kubernetes API 服务层
提供所有 Kubernetes API 操作的封装
"""

from typing import Dict, List, Any, Optional, Union
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
import yaml
import tempfile
import os


class KubernetesAPIService:
    """Kubernetes API 服务类"""
    
    def __init__(self):
        self.v1_api = None
        self.apps_v1_api = None
        self.networking_v1_api = None
        self.rbac_v1_api = None
        self.storage_v1_api = None
        self.extensions_v1beta1_api = None
        
    def load_config(self, kubeconfig_content: str = None, kubeconfig_path: str = None):
        """
        加载 Kubernetes 配置
        
        Args:
            kubeconfig_content: kubeconfig 文件内容
            kubeconfig_path: kubeconfig 文件路径
        """
        if kubeconfig_content:
            # 从内容加载配置
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write(kubeconfig_content)
                temp_path = f.name
            
            try:
                config.load_kube_config(config_file=temp_path)
            finally:
                os.unlink(temp_path)
                
        elif kubeconfig_path:
            # 从文件路径加载配置
            config.load_kube_config(config_file=kubeconfig_path)
        else:
            # 使用默认配置
            config.load_kube_config()
        
        # 初始化 API 客户端
        self.v1_api = client.CoreV1Api()
        self.apps_v1_api = client.AppsV1Api()
        self.networking_v1_api = client.NetworkingV1Api()
        self.rbac_v1_api = client.RbacAuthorizationV1Api()
        self.storage_v1_api = client.StorageV1Api()
        try:
            self.extensions_v1beta1_api = client.ExtensionsV1beta1Api()
        except:
            self.extensions_v1beta1_api = None

    # Pod 相关操作
    async def list_pods(self, namespace: str = "default", label_selector: str = None, 
                  field_selector: str = None) -> List[Dict[str, Any]]:
        """列出 Pod"""
        try:
            if namespace == "all":
                pods = self.v1_api.list_pod_for_all_namespaces(
                    label_selector=label_selector,
                    field_selector=field_selector
                )
            else:
                pods = self.v1_api.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=label_selector,
                    field_selector=field_selector
                )
            
            pod_list = []
            for pod in pods.items:
                pod_info = {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "status": pod.status.phase,
                    "created": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None,
                    "node": pod.spec.node_name,
                    "ready": self._get_pod_ready_status(pod),
                    "restarts": self._get_pod_restart_count(pod),
                    "pod_ip": pod.status.pod_ip,
                    "labels": pod.metadata.labels or {}
                }
                pod_list.append(pod_info)
            
            return pod_list
            
        except ApiException as e:
            raise Exception(f"获取 Pod 列表失败: {e.reason}")

    async def get_pod(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """获取单个 Pod 详情"""
        try:
            pod = self.v1_api.read_namespaced_pod(name=name, namespace=namespace)
            
            return {
                "metadata": {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "labels": pod.metadata.labels or {},
                    "annotations": pod.metadata.annotations or {},
                    "created": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None,
                    "uid": pod.metadata.uid
                },
                "spec": {
                    "node_name": pod.spec.node_name,
                    "restart_policy": pod.spec.restart_policy,
                    "service_account": pod.spec.service_account,
                    "containers": [
                        {
                            "name": container.name,
                            "image": container.image,
                            "ports": [
                                {"containerPort": port.container_port, "protocol": port.protocol}
                                for port in (container.ports or [])
                            ],
                            "resources": {
                                "requests": container.resources.requests or {} if container.resources else {},
                                "limits": container.resources.limits or {} if container.resources else {}
                            },
                            "env": [
                                {"name": env.name, "value": env.value or ""}
                                for env in (container.env or [])
                            ]
                        }
                        for container in pod.spec.containers
                    ]
                },
                "status": {
                    "phase": pod.status.phase,
                    "pod_ip": pod.status.pod_ip,
                    "start_time": pod.status.start_time.isoformat() if pod.status.start_time else None,
                    "conditions": [
                        {
                            "type": condition.type,
                            "status": condition.status,
                            "reason": condition.reason,
                            "message": condition.message
                        }
                        for condition in (pod.status.conditions or [])
                    ],
                    "container_statuses": [
                        {
                            "name": status.name,
                            "ready": status.ready,
                            "restart_count": status.restart_count,
                            "image": status.image,
                            "state": self._extract_container_state(status.state)
                        }
                        for status in (pod.status.container_statuses or [])
                    ]
                }
            }
            
        except ApiException as e:
            raise Exception(f"获取 Pod 详情失败: {e.reason}")

    async def get_pod_logs(self, name: str, namespace: str = "default", 
                     container: str = None, lines: int = 100, 
                     since_seconds: int = None, follow: bool = False) -> str:
        """获取 Pod 日志"""
        try:
            logs = self.v1_api.read_namespaced_pod_log(
                name=name,
                namespace=namespace,
                container=container,
                tail_lines=lines,
                since_seconds=since_seconds,
                follow=follow
            )
            return logs
            
        except ApiException as e:
            raise Exception(f"获取 Pod 日志失败: {e.reason}")

    async def delete_pod(self, name: str, namespace: str = "default", 
                   grace_period_seconds: int = None) -> Dict[str, Any]:
        """删除 Pod"""
        try:
            body = client.V1DeleteOptions(grace_period_seconds=grace_period_seconds)
            response = self.v1_api.delete_namespaced_pod(
                name=name,
                namespace=namespace,
                body=body
            )
            
            return {
                "name": name,
                "namespace": namespace,
                "status": "deleted",
                "uid": response.details.uid if response.details else None
            }
            
        except ApiException as e:
            raise Exception(f"删除 Pod 失败: {e.reason}")

    # Deployment 相关操作
    async def list_deployments(self, namespace: str = "default", 
                        label_selector: str = None) -> List[Dict[str, Any]]:
        """列出 Deployment"""
        try:
            if namespace == "all":
                deployments = self.apps_v1_api.list_deployment_for_all_namespaces(
                    label_selector=label_selector
                )
            else:
                deployments = self.apps_v1_api.list_namespaced_deployment(
                    namespace=namespace,
                    label_selector=label_selector
                )
            
            deployment_list = []
            for deployment in deployments.items:
                deployment_info = {
                    "name": deployment.metadata.name,
                    "namespace": deployment.metadata.namespace,
                    "replicas": deployment.spec.replicas,
                    "ready_replicas": deployment.status.ready_replicas or 0,
                    "available_replicas": deployment.status.available_replicas or 0,
                    "updated_replicas": deployment.status.updated_replicas or 0,
                    "created": deployment.metadata.creation_timestamp.isoformat() if deployment.metadata.creation_timestamp else None,
                    "labels": deployment.metadata.labels or {},
                    "selector": deployment.spec.selector.match_labels or {}
                }
                deployment_list.append(deployment_info)
            
            return deployment_list
            
        except ApiException as e:
            raise Exception(f"获取 Deployment 列表失败: {e.reason}")

    async def get_deployment(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """获取单个 Deployment 详情"""
        try:
            deployment = self.apps_v1_api.read_namespaced_deployment(
                name=name, namespace=namespace
            )
            
            return {
                "metadata": {
                    "name": deployment.metadata.name,
                    "namespace": deployment.metadata.namespace,
                    "labels": deployment.metadata.labels or {},
                    "annotations": deployment.metadata.annotations or {},
                    "created": deployment.metadata.creation_timestamp.isoformat() if deployment.metadata.creation_timestamp else None
                },
                "spec": {
                    "replicas": deployment.spec.replicas,
                    "selector": deployment.spec.selector.match_labels or {},
                    "strategy": deployment.spec.strategy.type if deployment.spec.strategy else None,
                    "template": {
                        "containers": [
                            {
                                "name": container.name,
                                "image": container.image,
                                "ports": [
                                    {"containerPort": port.container_port}
                                    for port in (container.ports or [])
                                ]
                            }
                            for container in deployment.spec.template.spec.containers
                        ]
                    }
                },
                "status": {
                    "replicas": deployment.status.replicas or 0,
                    "ready_replicas": deployment.status.ready_replicas or 0,
                    "available_replicas": deployment.status.available_replicas or 0,
                    "updated_replicas": deployment.status.updated_replicas or 0,
                    "conditions": [
                        {
                            "type": condition.type,
                            "status": condition.status,
                            "reason": condition.reason,
                            "message": condition.message
                        }
                        for condition in (deployment.status.conditions or [])
                    ]
                }
            }
            
        except ApiException as e:
            raise Exception(f"获取 Deployment 详情失败: {e.reason}")

    async def scale_deployment(self, name: str, namespace: str = "default", 
                        replicas: int = 1) -> Dict[str, Any]:
        """扩缩容 Deployment"""
        try:
            # 获取当前 deployment
            deployment = self.apps_v1_api.read_namespaced_deployment(
                name=name, namespace=namespace
            )
            
            # 更新副本数
            deployment.spec.replicas = replicas
            
            # 应用更新
            updated_deployment = self.apps_v1_api.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=deployment
            )
            
            return {
                "name": name,
                "namespace": namespace,
                "old_replicas": deployment.spec.replicas,
                "new_replicas": replicas,
                "status": "scaling"
            }
            
        except ApiException as e:
            raise Exception(f"扩缩容 Deployment 失败: {e.reason}")

    async def delete_deployment(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除 Deployment"""
        try:
            response = self.apps_v1_api.delete_namespaced_deployment(
                name=name,
                namespace=namespace
            )
            
            return {
                "name": name,
                "namespace": namespace,
                "status": "deleted"
            }
            
        except ApiException as e:
            raise Exception(f"删除 Deployment 失败: {e.reason}")

    # Service 相关操作
    async def list_services(self, namespace: str = "default", 
                     label_selector: str = None) -> List[Dict[str, Any]]:
        """列出 Service"""
        try:
            if namespace == "all":
                services = self.v1_api.list_service_for_all_namespaces(
                    label_selector=label_selector
                )
            else:
                services = self.v1_api.list_namespaced_service(
                    namespace=namespace,
                    label_selector=label_selector
                )
            
            service_list = []
            for service in services.items:
                # 获取端口信息
                ports = []
                for port in (service.spec.ports or []):
                    port_info = {
                        "name": port.name,
                        "port": port.port,
                        "target_port": str(port.target_port) if port.target_port else None,
                        "protocol": port.protocol,
                        "node_port": port.node_port
                    }
                    ports.append(port_info)
                
                service_info = {
                    "name": service.metadata.name,
                    "namespace": service.metadata.namespace,
                    "type": service.spec.type,
                    "cluster_ip": service.spec.cluster_ip,
                    "external_ips": service.spec.external_ips or [],
                    "ports": ports,
                    "selector": service.spec.selector or {},
                    "created": service.metadata.creation_timestamp.isoformat() if service.metadata.creation_timestamp else None,
                    "labels": service.metadata.labels or {}
                }
                service_list.append(service_info)
            
            return service_list
            
        except ApiException as e:
            raise Exception(f"获取 Service 列表失败: {e.reason}")

    async def get_service(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """获取单个 Service 详情"""
        try:
            service = self.v1_api.read_namespaced_service(name=name, namespace=namespace)
            
            # 获取端口信息
            ports = []
            for port in (service.spec.ports or []):
                port_info = {
                    "name": port.name,
                    "port": port.port,
                    "target_port": str(port.target_port) if port.target_port else None,
                    "protocol": port.protocol,
                    "node_port": port.node_port
                }
                ports.append(port_info)
            
            return {
                "metadata": {
                    "name": service.metadata.name,
                    "namespace": service.metadata.namespace,
                    "labels": service.metadata.labels or {},
                    "annotations": service.metadata.annotations or {},
                    "created": service.metadata.creation_timestamp.isoformat() if service.metadata.creation_timestamp else None,
                    "uid": service.metadata.uid
                },
                "spec": {
                    "type": service.spec.type,
                    "cluster_ip": service.spec.cluster_ip,
                    "external_ips": service.spec.external_ips or [],
                    "load_balancer_ip": service.spec.load_balancer_ip,
                    "ports": ports,
                    "selector": service.spec.selector or {},
                    "session_affinity": service.spec.session_affinity
                },
                "status": {
                    "load_balancer": {
                        "ingress": [
                            {
                                "ip": ingress.ip,
                                "hostname": ingress.hostname
                            }
                            for ingress in (service.status.load_balancer.ingress or [])
                        ] if service.status.load_balancer and service.status.load_balancer.ingress else []
                    }
                }
            }
            
        except ApiException as e:
            raise Exception(f"获取 Service 详情失败: {e.reason}")

    async def delete_service(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除 Service"""
        try:
            response = self.v1_api.delete_namespaced_service(
                name=name,
                namespace=namespace
            )
            
            return {
                "name": name,
                "namespace": namespace,
                "status": "deleted"
            }
            
        except ApiException as e:
            raise Exception(f"删除 Service 失败: {e.reason}")

    # Node 相关操作
    async def list_nodes(self, label_selector: str = None) -> List[Dict[str, Any]]:
        """列出 Node"""
        try:
            nodes = self.v1_api.list_node(label_selector=label_selector)
            
            node_list = []
            for node in nodes.items:
                node_info = {
                    "name": node.metadata.name,
                    "status": self._get_node_status(node),
                    "roles": self._get_node_roles(node),
                    "age": node.metadata.creation_timestamp.isoformat() if node.metadata.creation_timestamp else None,
                    "version": node.status.node_info.kubelet_version if node.status.node_info else None,
                    "internal_ip": self._get_node_internal_ip(node),
                    "external_ip": self._get_node_external_ip(node),
                    "os_image": node.status.node_info.os_image if node.status.node_info else None,
                    "kernel_version": node.status.node_info.kernel_version if node.status.node_info else None,
                    "container_runtime": node.status.node_info.container_runtime_version if node.status.node_info else None,
                    "labels": node.metadata.labels or {}
                }
                node_list.append(node_info)
            
            return node_list
            
        except ApiException as e:
            raise Exception(f"获取 Node 列表失败: {e.reason}")

    async def get_node(self, name: str) -> Dict[str, Any]:
        """获取单个 Node 详情"""
        try:
            node = self.v1_api.read_node(name=name)
            
            return {
                "metadata": {
                    "name": node.metadata.name,
                    "labels": node.metadata.labels or {},
                    "annotations": node.metadata.annotations or {},
                    "created": node.metadata.creation_timestamp.isoformat() if node.metadata.creation_timestamp else None,
                    "uid": node.metadata.uid
                },
                "spec": {
                    "pod_cidr": node.spec.pod_cidr,
                    "provider_id": node.spec.provider_id,
                    "unschedulable": node.spec.unschedulable or False,
                    "taints": [
                        {
                            "key": taint.key,
                            "value": taint.value,
                            "effect": taint.effect
                        }
                        for taint in (node.spec.taints or [])
                    ]
                },
                "status": {
                    "capacity": node.status.capacity or {},
                    "allocatable": node.status.allocatable or {},
                    "conditions": [
                        {
                            "type": condition.type,
                            "status": condition.status,
                            "reason": condition.reason,
                            "message": condition.message
                        }
                        for condition in (node.status.conditions or [])
                    ],
                    "addresses": [
                        {
                            "type": address.type,
                            "address": address.address
                        }
                        for address in (node.status.addresses or [])
                    ],
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
                    } if node.status.node_info else {}
                }
            }
            
        except ApiException as e:
            raise Exception(f"获取 Node 详情失败: {e.reason}")

    # Namespace 相关操作
    async def list_namespaces(self, label_selector: str = None) -> List[Dict[str, Any]]:
        """列出 Namespace"""
        try:
            namespaces = self.v1_api.list_namespace(label_selector=label_selector)
            
            namespace_list = []
            for namespace in namespaces.items:
                namespace_info = {
                    "name": namespace.metadata.name,
                    "status": namespace.status.phase,
                    "created": namespace.metadata.creation_timestamp.isoformat() if namespace.metadata.creation_timestamp else None,
                    "labels": namespace.metadata.labels or {},
                    "annotations": namespace.metadata.annotations or {}
                }
                namespace_list.append(namespace_info)
            
            return namespace_list
            
        except ApiException as e:
            raise Exception(f"获取 Namespace 列表失败: {e.reason}")

    async def create_namespace(self, name: str, labels: Dict[str, str] = None, 
                        annotations: Dict[str, str] = None) -> Dict[str, Any]:
        """创建 Namespace"""
        try:
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

    # ConfigMap 相关操作
    async def list_configmaps(self, namespace: str = "default", 
                       label_selector: str = None) -> List[Dict[str, Any]]:
        """列出 ConfigMap"""
        try:
            configmaps = self.v1_api.list_namespaced_config_map(
                namespace=namespace,
                label_selector=label_selector
            )
            
            configmap_list = []
            for configmap in configmaps.items:
                configmap_info = {
                    "name": configmap.metadata.name,
                    "namespace": configmap.metadata.namespace,
                    "data_count": len(configmap.data or {}),
                    "created": configmap.metadata.creation_timestamp.isoformat() if configmap.metadata.creation_timestamp else None,
                    "labels": configmap.metadata.labels or {}
                }
                configmap_list.append(configmap_info)
            
            return configmap_list
            
        except ApiException as e:
            raise Exception(f"获取 ConfigMap 列表失败: {e.reason}")

    async def get_configmap(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """获取单个 ConfigMap 详情"""
        try:
            configmap = self.v1_api.read_namespaced_config_map(name=name, namespace=namespace)
            
            return {
                "metadata": {
                    "name": configmap.metadata.name,
                    "namespace": configmap.metadata.namespace,
                    "labels": configmap.metadata.labels or {},
                    "annotations": configmap.metadata.annotations or {},
                    "created": configmap.metadata.creation_timestamp.isoformat() if configmap.metadata.creation_timestamp else None,
                    "uid": configmap.metadata.uid
                },
                "data": configmap.data or {},
                "binary_data": configmap.binary_data or {}
            }
            
        except ApiException as e:
            raise Exception(f"获取 ConfigMap 详情失败: {e.reason}")

    # Secret 相关操作 (不返回敏感数据)
    async def list_secrets(self, namespace: str = "default", 
                    label_selector: str = None) -> List[Dict[str, Any]]:
        """列出 Secret (不显示敏感数据)"""
        try:
            secrets = self.v1_api.list_namespaced_secret(
                namespace=namespace,
                label_selector=label_selector
            )
            
            secret_list = []
            for secret in secrets.items:
                secret_info = {
                    "name": secret.metadata.name,
                    "namespace": secret.metadata.namespace,
                    "type": secret.type,
                    "data_count": len(secret.data or {}),
                    "created": secret.metadata.creation_timestamp.isoformat() if secret.metadata.creation_timestamp else None,
                    "labels": secret.metadata.labels or {}
                }
                secret_list.append(secret_info)
            
            return secret_list
            
        except ApiException as e:
            raise Exception(f"获取 Secret 列表失败: {e.reason}")

    # Event 相关操作
    async def list_events(self, namespace: str = "default", 
                   field_selector: str = None) -> List[Dict[str, Any]]:
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
                    "first_timestamp": event.first_timestamp.isoformat() if event.first_timestamp else None,
                    "last_timestamp": event.last_timestamp.isoformat() if event.last_timestamp else None,
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

    # 辅助方法保持同步
    def _get_pod_ready_status(self, pod) -> str:
        """获取 Pod 就绪状态"""
        if not pod.status.conditions:
            return "Unknown"
        
        for condition in pod.status.conditions:
            if condition.type == "Ready":
                return "Ready" if condition.status == "True" else "NotReady"
        return "Unknown"

    def _get_pod_restart_count(self, pod) -> int:
        """获取 Pod 重启次数"""
        if not pod.status.container_statuses:
            return 0
        
        return sum(status.restart_count for status in pod.status.container_statuses)

    def _extract_container_state(self, state) -> Dict[str, Any]:
        """提取容器状态"""
        if state.running:
            return {
                "state": "running",
                "started_at": state.running.started_at.isoformat() if state.running.started_at else None
            }
        elif state.waiting:
            return {
                "state": "waiting",
                "reason": state.waiting.reason,
                "message": state.waiting.message
            }
        elif state.terminated:
            return {
                "state": "terminated",
                "reason": state.terminated.reason,
                "message": state.terminated.message,
                "started_at": state.terminated.started_at.isoformat() if state.terminated.started_at else None,
                "finished_at": state.terminated.finished_at.isoformat() if state.terminated.finished_at else None,
                "exit_code": state.terminated.exit_code
            }
        else:
            return {"state": "unknown"}

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
            # 尝试获取版本信息来测试连接
            version_api = client.VersionApi()
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
        """获取集群信息"""
        try:
            # 获取版本信息
            version_api = client.VersionApi()
            version_info = version_api.get_code()
            
            # 获取节点数量
            nodes = await self.list_nodes()
            
            return {
                "version": {
                    "kubernetes": version_info.git_version,
                    "platform": version_info.platform
                },
                "node_count": len(nodes),
                "ready_nodes": len([node for node in nodes if node["status"] == "Ready"]),
                "api_server": "accessible"
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "api_server": "inaccessible"
            } 