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
from utils.lowlevel import parse_secret_data, to_local_time_str


class KubernetesAPIService:
    """Kubernetes API 服务类"""
    
    def __init__(self):
        self.v1_api = None
        self.apps_v1_api = None
        self.networking_v1_api = None
        self.rbac_v1_api = None
        self.storage_v1_api = None
        self.extensions_v1beta1_api = None
        self.batch_v1_api = None
        self.batch_v1beta1_api = None
        
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
            # 尝试从集群管理器获取默认集群的kubeconfig
            try:
                from utils.cluster_config import ClusterConfigManager
                cluster_manager = ClusterConfigManager()
                default_cluster = cluster_manager.get_default_cluster()
                
                if default_cluster and default_cluster.kubeconfig_path:
                    # 使用默认集群的kubeconfig
                    config.load_kube_config(config_file=default_cluster.kubeconfig_path)
                else:
                    # 如果没有默认集群，尝试使用系统默认配置
                    config.load_kube_config()
            except Exception:
                # 如果获取默认集群失败，回退到系统默认配置
                config.load_kube_config()
        
        # 初始化 API 客户端
        self.v1_api = client.CoreV1Api()
        self.apps_v1_api = client.AppsV1Api()
        self.networking_v1_api = client.NetworkingV1Api()
        self.rbac_v1_api = client.RbacAuthorizationV1Api()
        self.storage_v1_api = client.StorageV1Api()
        self.batch_v1_api = client.BatchV1Api()
        try:
            self.extensions_v1beta1_api = client.ExtensionsV1beta1Api()
        except Exception:
            self.extensions_v1beta1_api = None
        # 修复新版 K8s client 无 BatchV1beta1Api 的情况
        if hasattr(client, 'BatchV1beta1Api'):
            try:
                self.batch_v1beta1_api = client.BatchV1beta1Api()
            except Exception:
                self.batch_v1beta1_api = None
        else:
            self.batch_v1beta1_api = None

    # ========================== Pod 服务层方法 ==========================

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
                    "created": to_local_time_str(pod.metadata.creation_timestamp, 8) if pod.metadata.creation_timestamp else None,
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
                    "created": to_local_time_str(pod.metadata.creation_timestamp, 8) if pod.metadata.creation_timestamp else None,
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
                    "start_time": to_local_time_str(pod.status.start_time, 8) if pod.status.start_time else None,
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
            
            # 安全地获取uid，避免details属性不存在的问题
            uid = None
            if hasattr(response, 'details') and response.details:
                uid = getattr(response.details, 'uid', None)
            elif hasattr(response, 'metadata') and response.metadata:
                uid = getattr(response.metadata, 'uid', None)
            
            return {
                "name": name,
                "namespace": namespace,
                "status": "deleted",
                "uid": uid
            }
            
        except ApiException as e:
            raise Exception(f"删除 Pod 失败: {e.reason}")

    # ========================== Deployment 服务层方法 ==========================

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
                    "created": to_local_time_str(deployment.metadata.creation_timestamp, 8) if deployment.metadata.creation_timestamp else None,
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
                    "created": to_local_time_str(deployment.metadata.creation_timestamp, 8) if deployment.metadata.creation_timestamp else None
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

    async def create_deployment(self, name: str, image: str, namespace: str = "default",
                          replicas: int = 1, labels: dict = None, env_vars: dict = None,
                          ports: list = None, resources: dict = None) -> Dict[str, Any]:
        """创建 Deployment"""
        try:
            if labels is None:
                labels = {"app": name}
            
            # 构建容器规格
            container_ports = []
            if ports:
                for port in ports:
                    container_ports.append(
                        client.V1ContainerPort(
                            name=port.get("name", "http"),
                            container_port=port.get("containerPort", 80)
                        )
                    )
            
            # 构建环境变量
            env_list = []
            if env_vars:
                for key, value in env_vars.items():
                    env_list.append(client.V1EnvVar(name=key, value=str(value)))
            
            # 构建资源限制
            resource_requirements = None
            if resources:
                resource_requirements = client.V1ResourceRequirements(
                    requests=resources.get("requests"),
                    limits=resources.get("limits")
                )
            
            # 构建容器规格
            container = client.V1Container(
                name=name,
                image=image,
                ports=container_ports,
                env=env_list,
                resources=resource_requirements
            )
            
            # 构建 Pod 模板
            pod_template = client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels=labels),
                spec=client.V1PodSpec(containers=[container])
            )
            
            # 构建 Deployment 规格
            deployment_spec = client.V1DeploymentSpec(
                replicas=replicas,
                selector=client.V1LabelSelector(match_labels=labels),
                template=pod_template
            )
            
            # 构建 Deployment
            deployment = client.V1Deployment(
                api_version="apps/v1",
                kind="Deployment",
                metadata=client.V1ObjectMeta(name=name, namespace=namespace, labels=labels),
                spec=deployment_spec
            )
            
            # 创建 Deployment
            response = self.apps_v1_api.create_namespaced_deployment(
                namespace=namespace,
                body=deployment
            )
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                "replicas": response.spec.replicas
            }
            
        except ApiException as e:
            raise Exception(f"创建 Deployment 失败: {e}")

    async def update_deployment(self, name: str, namespace: str = "default",
                          image: str = None, replicas: int = None,
                          labels: dict = None, env_vars: dict = None,
                          resources: dict = None) -> Dict[str, Any]:
        """更新 Deployment"""
        try:
            # 获取当前 deployment
            deployment = self.apps_v1_api.read_namespaced_deployment(
                name=name, namespace=namespace
            )
            
            # 更新镜像
            if image is not None:
                deployment.spec.template.spec.containers[0].image = image
            
            # 更新副本数
            if replicas is not None:
                deployment.spec.replicas = replicas

            # 更新标签
            if labels is not None:
                if deployment.metadata.labels:
                    deployment.metadata.labels.update(labels)
                else:
                    deployment.metadata.labels = labels
                # 同时更新 Pod 模板的标签
                if deployment.spec.template.metadata.labels:
                    deployment.spec.template.metadata.labels.update(labels)
                else:
                    deployment.spec.template.metadata.labels = labels
            
            # 更新环境变量
            if env_vars is not None:
                env_list = []
                for key, value in env_vars.items():
                    env_list.append(client.V1EnvVar(name=key, value=str(value)))
                deployment.spec.template.spec.containers[0].env = env_list
            
            # 更新资源限制
            if resources is not None:
                resource_requirements = client.V1ResourceRequirements(
                    requests=resources.get("requests"),
                    limits=resources.get("limits")
                )
                deployment.spec.template.spec.containers[0].resources = resource_requirements
            
            # 应用更新
            updated_deployment = self.apps_v1_api.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=deployment
            )
            
            return {
                "name": updated_deployment.metadata.name,
                "namespace": updated_deployment.metadata.namespace,
                "uid": updated_deployment.metadata.uid,
                "replicas": updated_deployment.spec.replicas,
                "image": updated_deployment.spec.template.spec.containers[0].image,
                "status": "updated"
            }
            
        except ApiException as e:
            raise Exception(f"更新 Deployment 失败: {e.reason}")

    async def delete_deployment(self, name: str, namespace: str = "default", 
                                grace_period_seconds: int = None) -> Dict[str, Any]:
        """删除 Deployment"""
        try:
            body = client.V1DeleteOptions(grace_period_seconds=grace_period_seconds) if grace_period_seconds is not None else None
            response = self.apps_v1_api.delete_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=body
            )
            
            return {
                "name": name,
                "namespace": namespace,
                "status": "deleted"
            }
            
        except ApiException as e:
            raise Exception(f"删除 Deployment 失败: {e.reason}")

    # ========================== StatefulSet 服务层方法 ==========================

    async def list_statefulsets(self, namespace: str = "default", label_selector: str = None) -> List[Dict[str, Any]]:
        """列出 StatefulSet"""
        try:
            if namespace == "all":
                response = self.apps_v1_api.list_stateful_set_for_all_namespaces(label_selector=label_selector)
            else:
                response = self.apps_v1_api.list_namespaced_stateful_set(
                    namespace=namespace,
                    label_selector=label_selector
                )
            statefulsets = []
            for item in response.items:
                statefulsets.append({
                    "name": item.metadata.name,
                    "namespace": item.metadata.namespace,
                    "uid": item.metadata.uid,
                    "creation_timestamp": to_local_time_str(item.metadata.creation_timestamp, 8) if item.metadata.creation_timestamp else None,
                    "replicas": item.spec.replicas,
                    "ready_replicas": item.status.ready_replicas or 0,
                    "current_replicas": item.status.current_replicas or 0,
                    "labels": item.metadata.labels,
                    "selector": item.spec.selector.match_labels
                })
            
            return statefulsets
            
        except ApiException as e:
            raise Exception(f"列出 StatefulSet 失败: {e}")

    async def get_statefulset(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """获取 StatefulSet 详情"""
        try:
            response = self.apps_v1_api.read_namespaced_stateful_set(
                name=name,
                namespace=namespace
            )

            # 提取容器详细信息
            containers = []
            for c in response.spec.template.spec.containers:
                containers.append({
                    "name": c.name,
                    "image": c.image,
                    "resources": {
                        "limits": c.resources.limits if c.resources and c.resources.limits else {},
                        "requests": c.resources.requests if c.resources and c.resources.requests else {}
                    },
                    "env": [
                        {"name": e.name, "value": e.value, "value_from": str(e.value_from) if e.value_from else None}
                        for e in (c.env or [])
                    ],
                    "ports": [
                        {"containerPort": p.container_port, "name": p.name} for p in (c.ports or [])
                    ],
                    "volume_mounts": [
                        {"mountPath": v.mount_path, "name": v.name, "readOnly": v.read_only} for v in (c.volume_mounts or [])
                    ]
                })

            # 提取卷信息
            volumes = []
            for v in (response.spec.template.spec.volumes or []):
                vinfo = {"name": v.name}
                if v.config_map:
                    vinfo["type"] = "ConfigMap"
                    vinfo["configMap"] = {"name": v.config_map.name, "optional": v.config_map.optional}
                if v.secret:
                    vinfo["type"] = "Secret"
                    vinfo["secret"] = {"secretName": v.secret.secret_name, "optional": v.secret.optional}
                if v.persistent_volume_claim:
                    vinfo["type"] = "PersistentVolumeClaim"
                    vinfo["claimName"] = v.persistent_volume_claim.claim_name
                volumes.append(vinfo)

            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                "replicas": response.spec.replicas,
                "ready_replicas": response.status.ready_replicas or 0,
                "current_replicas": response.status.current_replicas or 0,
                "labels": response.metadata.labels,
                "selector": response.spec.selector.match_labels,
                "containers": containers,
                "volumes": volumes,
                "volume_claim_templates": [
                    {
                        "name": vct.metadata.name,
                        "access_modes": vct.spec.access_modes,
                        "storage": vct.spec.resources.requests.get("storage", ""),
                        "storage_class": vct.spec.storage_class_name
                    } for vct in (response.spec.volume_claim_templates or [])
                ]
            }
            
        except ApiException as e:
            raise Exception(f"获取 StatefulSet 失败: {e}")

    async def create_statefulset(self, name: str, image: str, namespace: str = "default",
                           replicas: int = 1, labels: dict = None, env_vars: dict = None,
                           ports: list = None, resources: dict = None,
                           volume_claims: list = None) -> Dict[str, Any]:
        """创建 StatefulSet"""
        try:
            if labels is None:
                labels = {"app": name}
            
            # 构建容器规格
            container_ports = []
            if ports:
                for port in ports:
                    container_ports.append(
                        client.V1ContainerPort(
                            name=port.get("name", "http"),
                            container_port=port.get("containerPort", 80)
                        )
                    )
            
            # 构建环境变量
            env_list = []
            if env_vars:
                for key, value in env_vars.items():
                    env_list.append(client.V1EnvVar(name=key, value=str(value)))
            
            # 构建资源限制
            resource_requirements = None
            if resources:
                resource_requirements = client.V1ResourceRequirements(
                    requests=resources.get("requests"),
                    limits=resources.get("limits")
                )
            
            # 构建容器规格
            container = client.V1Container(
                name=name,
                image=image,
                ports=container_ports,
                env=env_list,
                resources=resource_requirements
            )
            
            # 构建卷声明模板
            volume_claim_templates = []
            if volume_claims:
                for vc in volume_claims:
                    volume_claim_templates.append(
                        client.V1PersistentVolumeClaim(
                            metadata=client.V1ObjectMeta(name=vc.get("name", "data")),
                            spec=client.V1PersistentVolumeClaimSpec(
                                access_modes=vc.get("access_modes", ["ReadWriteOnce"]),
                                resources=client.V1ResourceRequirements(
                                    requests={"storage": vc.get("size", "1Gi")}
                                ),
                                storage_class_name=vc.get("storage_class")
                            )
                        )
                    )
            
            # 构建 Pod 模板
            pod_template = client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels=labels),
                spec=client.V1PodSpec(containers=[container])
            )
            
            # 构建 StatefulSet 规格
            statefulset_spec = client.V1StatefulSetSpec(
                replicas=replicas,
                selector=client.V1LabelSelector(match_labels=labels),
                template=pod_template,
                service_name=name,
                volume_claim_templates=volume_claim_templates
            )
            
            # 构建 StatefulSet
            statefulset = client.V1StatefulSet(
                api_version="apps/v1",
                kind="StatefulSet",
                metadata=client.V1ObjectMeta(name=name, namespace=namespace, labels=labels),
                spec=statefulset_spec
            )
            
            # 创建 StatefulSet
            response = self.apps_v1_api.create_namespaced_stateful_set(
                namespace=namespace,
                body=statefulset
            )
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                "replicas": response.spec.replicas
            }
            
        except ApiException as e:
            raise Exception(f"创建 StatefulSet 失败: {e}")

    async def update_statefulset(self, name: str, namespace: str = "default",
                           image: str = None, replicas: int = None,
                           labels: dict = None, env_vars: dict = None) -> Dict[str, Any]:
        """更新 StatefulSet"""
        try:
            # 获取现有的 StatefulSet
            statefulset = self.apps_v1_api.read_namespaced_stateful_set(
                name=name,
                namespace=namespace
            )
            
            # 更新副本数
            if replicas is not None:
                statefulset.spec.replicas = replicas
            
            # 更新镜像
            if image is not None:
                statefulset.spec.template.spec.containers[0].image = image
            
            # 更新标签
            if labels is not None:
                statefulset.metadata.labels.update(labels)
                statefulset.spec.template.metadata.labels.update(labels)
            
            # 更新环境变量
            if env_vars is not None:
                env_list = []
                for key, value in env_vars.items():
                    env_list.append(client.V1EnvVar(name=key, value=str(value)))
                statefulset.spec.template.spec.containers[0].env = env_list
            
            # 应用更新
            response = self.apps_v1_api.patch_namespaced_stateful_set(
                name=name,
                namespace=namespace,
                body=statefulset
            )
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "replicas": response.spec.replicas
            }
            
        except ApiException as e:
            raise Exception(f"更新 StatefulSet 失败: {e}")

    async def delete_statefulset(self, name: str, namespace: str = "default",
                                 grace_period_seconds: int = None) -> Dict[str, Any]:
        """删除 StatefulSet"""
        try:
            body = client.V1DeleteOptions(grace_period_seconds=grace_period_seconds) if grace_period_seconds is not None else None
            response = self.apps_v1_api.delete_namespaced_stateful_set(
                name=name,
                namespace=namespace,
                body=body
            )
            
            uid = None
            if hasattr(response, 'details') and response.details:
                uid = getattr(response.details, 'uid', None)
            elif hasattr(response, 'metadata') and response.metadata:
                uid = getattr(response.metadata, 'uid', None)
            
            return {
                "name": name,
                "namespace": namespace,
                "status": "deleted",
                "uid": uid
            }
            
        except ApiException as e:
            raise Exception(f"删除 StatefulSet 失败: {e}")

    # ========================== DaemonSet 服务层方法 ==========================

    async def list_daemonsets(self, namespace: str = "default", label_selector: str = None) -> List[Dict[str, Any]]:
        """列出 DaemonSet"""
        try:
            if namespace == "all":
                response = self.apps_v1_api.list_daemon_set_for_all_namespaces(label_selector=label_selector)
            else:
                response = self.apps_v1_api.list_namespaced_daemon_set(
                    namespace=namespace,
                    label_selector=label_selector
                )
            daemonsets = []
            for item in response.items:
                daemonsets.append({
                    "name": item.metadata.name,
                    "namespace": item.metadata.namespace,
                    "uid": item.metadata.uid,
                    "creation_timestamp": to_local_time_str(item.metadata.creation_timestamp, 8) if item.metadata.creation_timestamp else None,
                    "desired_number_scheduled": item.status.desired_number_scheduled or 0,
                    "current_number_scheduled": item.status.current_number_scheduled or 0,
                    "number_ready": item.status.number_ready or 0,
                    "labels": item.metadata.labels,
                    "selector": item.spec.selector.match_labels
                })
            
            return daemonsets
            
        except ApiException as e:
            raise Exception(f"列出 DaemonSet 失败: {e}")

    async def get_daemonset(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """获取 DaemonSet 详情"""
        try:
            response = self.apps_v1_api.read_namespaced_daemon_set(
                name=name,
                namespace=namespace
            )

            # 提取容器详细信息
            containers = []
            for c in response.spec.template.spec.containers:
                containers.append({
                    "name": c.name,
                    "image": c.image,
                    "resources": {
                        "limits": c.resources.limits if c.resources and c.resources.limits else {},
                        "requests": c.resources.requests if c.resources and c.resources.requests else {}
                    },
                    "env": [
                        {"name": e.name, "value": e.value, "value_from": str(e.value_from) if e.value_from else None}
                        for e in (c.env or [])
                    ],
                    "ports": [
                        {"containerPort": p.container_port, "name": p.name} for p in (c.ports or [])
                    ],
                    "volume_mounts": [
                        {"mountPath": v.mount_path, "name": v.name, "readOnly": v.read_only} for v in (c.volume_mounts or [])
                    ]
                })

            # 提取卷信息
            volumes = []
            for v in (response.spec.template.spec.volumes or []):
                vinfo = {"name": v.name}
                if v.config_map:
                    vinfo["type"] = "ConfigMap"
                    vinfo["configMap"] = {"name": v.config_map.name, "optional": v.config_map.optional}
                if v.secret:
                    vinfo["type"] = "Secret"
                    vinfo["secret"] = {"secretName": v.secret.secret_name, "optional": v.secret.optional}
                if v.persistent_volume_claim:
                    vinfo["type"] = "PersistentVolumeClaim"
                    vinfo["claimName"] = v.persistent_volume_claim.claim_name
                volumes.append(vinfo)

            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                "desired_number_scheduled": response.status.desired_number_scheduled or 0,
                "current_number_scheduled": response.status.current_number_scheduled or 0,
                "number_ready": response.status.number_ready or 0,
                "labels": response.metadata.labels,
                "selector": response.spec.selector.match_labels,
                "containers": containers,
                "volumes": volumes
            }
            
        except ApiException as e:
            raise Exception(f"获取 DaemonSet 失败: {e}")

    async def create_daemonset(self, name: str, image: str, namespace: str = "default",
                         labels: dict = None, env_vars: dict = None,
                         ports: list = None, resources: dict = None,
                         volumes: list = None) -> Dict[str, Any]:
        """创建 DaemonSet"""
        try:
            if labels is None:
                labels = {"app": name}
            
            # 构建容器规格
            container_ports = []
            if ports:
                for port in ports:
                    container_ports.append(
                        client.V1ContainerPort(
                            name=port.get("name", "http"),
                            container_port=port.get("containerPort", 80)
                        )
                    )
            
            # 构建环境变量
            env_list = []
            if env_vars:
                for key, value in env_vars.items():
                    env_list.append(client.V1EnvVar(name=key, value=str(value)))
            
            # 构建资源限制
            resource_requirements = None
            if resources:
                resource_requirements = client.V1ResourceRequirements(
                    requests=resources.get("requests"),
                    limits=resources.get("limits")
                )
            
            # 构建容器规格
            container = client.V1Container(
                name=name,
                image=image,
                ports=container_ports,
                env=env_list,
                resources=resource_requirements
            )
            
            # 构建卷配置
            volume_list = []
            volume_mounts = []
            if volumes:
                for volume in volumes:
                    volume_list.append(
                        client.V1Volume(
                            name=volume.get("name", "volume"),
                            host_path=client.V1HostPathVolumeSource(
                                path=volume.get("host_path", "/tmp")
                            ) if volume.get("host_path") else None
                        )
                    )
                    volume_mounts.append(
                        client.V1VolumeMount(
                            name=volume.get("name", "volume"),
                            mount_path=volume.get("mount_path", "/mnt")
                        )
                    )
            
            if volume_mounts:
                container.volume_mounts = volume_mounts
            
            # 构建 Pod 模板
            pod_template = client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels=labels),
                spec=client.V1PodSpec(containers=[container], volumes=volume_list)
            )
            
            # 构建 DaemonSet 规格
            daemonset_spec = client.V1DaemonSetSpec(
                selector=client.V1LabelSelector(match_labels=labels),
                template=pod_template
            )
            
            # 构建 DaemonSet
            daemonset = client.V1DaemonSet(
                api_version="apps/v1",
                kind="DaemonSet",
                metadata=client.V1ObjectMeta(name=name, namespace=namespace, labels=labels),
                spec=daemonset_spec
            )
            
            # 创建 DaemonSet
            response = self.apps_v1_api.create_namespaced_daemon_set(
                namespace=namespace,
                body=daemonset
            )
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None
            }
            
        except ApiException as e:
            raise Exception(f"创建 DaemonSet 失败: {e}")

    async def update_daemonset(self, name: str, namespace: str = "default",
                         image: str = None, labels: dict = None,
                         env_vars: dict = None) -> Dict[str, Any]:
        """更新 DaemonSet"""
        try:
            # 获取现有的 DaemonSet
            daemonset = self.apps_v1_api.read_namespaced_daemon_set(
                name=name,
                namespace=namespace
            )
            
            # 更新镜像
            if image is not None:
                daemonset.spec.template.spec.containers[0].image = image
            
            # 更新标签
            if labels is not None:
                daemonset.metadata.labels.update(labels)
                daemonset.spec.template.metadata.labels.update(labels)
            
            # 更新环境变量
            if env_vars is not None:
                env_list = []
                for key, value in env_vars.items():
                    env_list.append(client.V1EnvVar(name=key, value=str(value)))
                daemonset.spec.template.spec.containers[0].env = env_list
            
            # 应用更新
            response = self.apps_v1_api.patch_namespaced_daemon_set(
                name=name,
                namespace=namespace,
                body=daemonset
            )
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid
            }
            
        except ApiException as e:
            raise Exception(f"更新 DaemonSet 失败: {e}")

    async def delete_daemonset(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除 DaemonSet"""
        try:
            response = self.apps_v1_api.delete_namespaced_daemon_set(
                name=name,
                namespace=namespace
            )
            
            uid = None
            if hasattr(response, 'details') and response.details:
                uid = getattr(response.details, 'uid', None)
            elif hasattr(response, 'metadata') and response.metadata:
                uid = getattr(response.metadata, 'uid', None)
            
            return {
                "name": name,
                "namespace": namespace,
                "status": "deleted",
                "uid": uid
            }
            
        except ApiException as e:
            raise Exception(f"删除 DaemonSet 失败: {e}")

    # ========================== Service 服务层方法 ==========================

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
                    "external_ips": getattr(service.spec, 'external_i_ps', None) or [],
                    "ports": ports,
                    "selector": service.spec.selector or {},
                    "created": to_local_time_str(service.metadata.creation_timestamp, 8) if service.metadata.creation_timestamp else None,
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
                    "created": to_local_time_str(service.metadata.creation_timestamp, 8) if service.metadata.creation_timestamp else None,
                    "uid": service.metadata.uid
                },
                "spec": {
                    "type": service.spec.type,
                    "cluster_ip": service.spec.cluster_ip,
                    "external_ips": getattr(service.spec, 'external_i_ps', None) or [],
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

    async def create_service(self, name: str, selector: dict, ports: list,
                       namespace: str = "default", service_type: str = "ClusterIP") -> Dict[str, Any]:
        """创建 Service"""
        try:
            # 构建端口规格
            service_ports = []
            for port in ports:
                service_ports.append(
                    client.V1ServicePort(
                        name=port.get("name", "http"),
                        port=port.get("port", 80),
                        target_port=port.get("targetPort", 80),
                        protocol=port.get("protocol", "TCP")
                    )
                )
            
            # 构建 Service 规格
            service_spec = client.V1ServiceSpec(
                selector=selector,
                ports=service_ports,
                type=service_type
            )
            
            # 构建 Service
            service = client.V1Service(
                api_version="v1",
                kind="Service",
                metadata=client.V1ObjectMeta(name=name, namespace=namespace),
                spec=service_spec
            )
            
            # 创建 Service
            response = self.v1_api.create_namespaced_service(
                namespace=namespace,
                body=service
            )
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                "type": response.spec.type,
                "cluster_ip": response.spec.cluster_ip
            }
            
        except ApiException as e:
            raise Exception(f"创建 Service 失败: {e}")

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

    # ========================== ConfigMap 服务层方法 ==========================

    async def list_configmaps(self, namespace: str = "default", 
                       label_selector: str = None) -> List[Dict[str, Any]]:
        """列出 ConfigMap"""
        try:
            if namespace == "all":
                configmaps = self.v1_api.list_config_map_for_all_namespaces(label_selector=label_selector)
            else:
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
                    "created": to_local_time_str(configmap.metadata.creation_timestamp, 8) if configmap.metadata.creation_timestamp else None,
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
                    "created": to_local_time_str(configmap.metadata.creation_timestamp, 8) if configmap.metadata.creation_timestamp else None,
                    "uid": configmap.metadata.uid
                },
                "data": configmap.data or {},
                "binary_data": configmap.binary_data or {}
            }
            
        except ApiException as e:
            raise Exception(f"获取 ConfigMap 详情失败: {e.reason}")

    async def create_configmap(self, name: str, data: dict, namespace: str = "default",
                         labels: dict = None) -> Dict[str, Any]:
        """创建 ConfigMap"""
        try:
            # 构建 ConfigMap
            configmap = client.V1ConfigMap(
                api_version="v1",
                kind="ConfigMap",
                metadata=client.V1ObjectMeta(name=name, namespace=namespace, labels=labels),
                data=data
            )
            
            # 创建 ConfigMap
            response = self.v1_api.create_namespaced_config_map(
                namespace=namespace,
                body=configmap
            )
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                "data_keys": list(response.data.keys()) if response.data else []
            }
            
        except ApiException as e:
            raise Exception(f"创建 ConfigMap 失败: {e}")

    async def update_configmap(self, name: str, data: dict, namespace: str = "default",
                         labels: dict = None) -> Dict[str, Any]:
        """更新 ConfigMap"""
        try:
            # 获取现有的 ConfigMap
            configmap = self.v1_api.read_namespaced_config_map(
                name=name,
                namespace=namespace
            )
            
            # 更新数据
            configmap.data = data
            
            # 更新标签
            if labels is not None:
                if configmap.metadata.labels:
                    configmap.metadata.labels.update(labels)
                else:
                    configmap.metadata.labels = labels
            
            # 应用更新
            response = self.v1_api.patch_namespaced_config_map(
                name=name,
                namespace=namespace,
                body=configmap
            )
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "data_keys": list(response.data.keys()) if response.data else []
            }
            
        except ApiException as e:
            raise Exception(f"更新 ConfigMap 失败: {e}")

    async def delete_configmap(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除 ConfigMap"""
        try:
            response = self.v1_api.delete_namespaced_config_map(
                name=name,
                namespace=namespace
            )
            
            uid = None
            if hasattr(response, 'details') and response.details:
                uid = getattr(response.details, 'uid', None)
            elif hasattr(response, 'metadata') and response.metadata:
                uid = getattr(response.metadata, 'uid', None)
            
            return {
                "name": name,
                "namespace": namespace,
                "status": "deleted",
                "uid": uid
            }
            
        except ApiException as e:
            raise Exception(f"删除 ConfigMap 失败: {e}")

    # ========================== Secret 服务层方法 ==========================

    async def list_secrets(self, namespace: str = "default", 
                    label_selector: str = None) -> List[Dict[str, Any]]:
        """列出 Secret (不显示敏感数据)"""
        try:
            if namespace == "all":
                secrets = self.v1_api.list_secret_for_all_namespaces(label_selector=label_selector)
            else:
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
                    "created": to_local_time_str(secret.metadata.creation_timestamp, 8) if secret.metadata.creation_timestamp else None,
                    "labels": secret.metadata.labels or {}
                }
                secret_list.append(secret_info)
            
            return secret_list
            
        except ApiException as e:
            raise Exception(f"获取 Secret 列表失败: {e.reason}")

    async def get_secret(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """获取 Secret 详情"""
        try:
            response = self.v1_api.read_namespaced_secret(
                name=name,
                namespace=namespace
            )
            decoded_data = parse_secret_data(response.data) if response.data else {}
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                "type": response.type,
                "data_keys": list(response.data.keys()) if response.data else [],
                "labels": response.metadata.labels,
                "decoded_data": decoded_data
            }
        except ApiException as e:
            raise Exception(f"获取 Secret 失败: {e}") 

    async def create_secret(self, name: str, data: dict, namespace: str = "default",
                      secret_type: str = "Opaque", labels: dict = None) -> Dict[str, Any]:
        """创建 Secret"""
        try:
            import base64
            
            # 对数据进行 base64 编码
            encoded_data = {}
            for key, value in data.items():
                if isinstance(value, str):
                    encoded_data[key] = base64.b64encode(value.encode()).decode()
                else:
                    encoded_data[key] = base64.b64encode(str(value).encode()).decode()
            
            # 构建 Secret
            secret = client.V1Secret(
                api_version="v1",
                kind="Secret",
                metadata=client.V1ObjectMeta(name=name, namespace=namespace, labels=labels),
                type=secret_type,
                data=encoded_data
            )
            
            # 创建 Secret
            response = self.v1_api.create_namespaced_secret(
                namespace=namespace,
                body=secret
            )
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                "type": response.type,
                "data_keys": list(response.data.keys()) if response.data else []
            }
            
        except ApiException as e:
            raise Exception(f"创建 Secret 失败: {e}")

    async def update_secret(self, name: str, data: dict, namespace: str = "default",
                      labels: dict = None) -> Dict[str, Any]:
        """更新 Secret"""
        try:
            import base64
            
            # 获取现有的 Secret
            secret = self.v1_api.read_namespaced_secret(
                name=name,
                namespace=namespace
            )
            
            # 对数据进行 base64 编码
            encoded_data = {}
            for key, value in data.items():
                if isinstance(value, str):
                    encoded_data[key] = base64.b64encode(value.encode()).decode()
                else:
                    encoded_data[key] = base64.b64encode(str(value).encode()).decode()
            
            # 更新数据
            secret.data = encoded_data
            
            # 更新标签
            if labels is not None:
                if secret.metadata.labels:
                    secret.metadata.labels.update(labels)
                else:
                    secret.metadata.labels = labels
            
            # 应用更新
            response = self.v1_api.patch_namespaced_secret(
                name=name,
                namespace=namespace,
                body=secret
            )
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "data_keys": list(response.data.keys()) if response.data else []
            }
            
        except ApiException as e:
            raise Exception(f"更新 Secret 失败: {e}")

    async def delete_secret(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除 Secret"""
        try:
            response = self.v1_api.delete_namespaced_secret(
                name=name,
                namespace=namespace
            )
            
            uid = None
            if hasattr(response, 'details') and response.details:
                uid = getattr(response.details, 'uid', None)
            elif hasattr(response, 'metadata') and response.metadata:
                uid = getattr(response.metadata, 'uid', None)
            
            return {
                "name": name,
                "namespace": namespace,
                "status": "deleted",
                "uid": uid
            }
            
        except ApiException as e:
            raise Exception(f"删除 Secret 失败: {e}")

    # ========================== Job 服务层方法 ==========================

    async def list_jobs(self, namespace: str = "default", label_selector: str = None) -> List[Dict[str, Any]]:
        """列出 Job"""
        try:
            if namespace == "all":
                response = self.batch_v1_api.list_job_for_all_namespaces(label_selector=label_selector)
            else:
                response = self.batch_v1_api.list_namespaced_job(
                    namespace=namespace,
                    label_selector=label_selector
                )
            jobs = []
            for item in response.items:
                jobs.append({
                    "name": item.metadata.name,
                    "namespace": item.metadata.namespace,
                    "uid": item.metadata.uid,
                    "creation_timestamp": to_local_time_str(item.metadata.creation_timestamp, 8) if item.metadata.creation_timestamp else None,
                    "completions": item.spec.completions,
                    "parallelism": item.spec.parallelism,
                    "active": item.status.active or 0,
                    "succeeded": item.status.succeeded or 0,
                    "failed": item.status.failed or 0,
                    "labels": item.metadata.labels,
                    "completion_time": to_local_time_str(item.status.completion_time, 8) if item.status.completion_time else None,
                    "start_time": to_local_time_str(item.status.start_time, 8) if item.status.start_time else None
                })
            
            return jobs
            
        except ApiException as e:
            raise Exception(f"列出 Job 失败: {e}")

    async def get_job(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """获取 Job 详情"""
        try:
            response = self.batch_v1_api.read_namespaced_job(
                name=name,
                namespace=namespace
            )
            
            # 提取 Pod 模板详细信息
            pod_template = response.spec.template
            containers = []
            for c in pod_template.spec.containers:
                containers.append({
                    "name": c.name,
                    "image": c.image,
                    "command": c.command,
                    "args": c.args,
                    "env": [{"name": e.name, "value": e.value} for e in (c.env or [])],
                    "resources": {
                        "limits": c.resources.limits if c.resources and c.resources.limits else {},
                        "requests": c.resources.requests if c.resources and c.resources.requests else {}
                    }
                })
            # 其他 Pod 级别信息
            pod_spec = pod_template.spec
            pod_info = {
                "restart_policy": pod_spec.restart_policy,
                "service_account": pod_spec.service_account_name,
                "node_selector": pod_spec.node_selector,
                "volumes": [v.name for v in (pod_spec.volumes or [])]
            }
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                "completions": response.spec.completions,
                "parallelism": response.spec.parallelism,
                "active": response.status.active or 0,
                "succeeded": response.status.succeeded or 0,
                "failed": response.status.failed or 0,
                "labels": response.metadata.labels,
                "completion_time": to_local_time_str(response.status.completion_time, 8) if response.status.completion_time else None,
                "start_time": to_local_time_str(response.status.start_time, 8) if response.status.start_time else None,
                "backoff_limit": response.spec.backoff_limit,
                "containers": containers,
                "pod_template": pod_info
            }
        
        except ApiException as e:
            raise Exception(f"获取 Job 失败: {e}")

    async def create_job(self, name: str, image: str, namespace: str = "default",
                   command: list = None, args: list = None, labels: dict = None,
                   env_vars: dict = None, resources: dict = None,
                   restart_policy: str = "Never", backoff_limit: int = 6) -> Dict[str, Any]:
        """创建 Job"""
        try:
            if labels is None:
                labels = {"app": name}
            
            # 构建环境变量
            env_list = []
            if env_vars:
                for key, value in env_vars.items():
                    env_list.append(client.V1EnvVar(name=key, value=str(value)))
            
            # 构建资源限制
            resource_requirements = None
            if resources:
                resource_requirements = client.V1ResourceRequirements(
                    requests=resources.get("requests"),
                    limits=resources.get("limits")
                )
            
            # 构建容器规格
            container = client.V1Container(
                name=name,
                image=image,
                command=command,
                args=args,
                env=env_list,
                resources=resource_requirements
            )
            
            # 构建 Pod 模板
            pod_template = client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels=labels),
                spec=client.V1PodSpec(
                    containers=[container],
                    restart_policy=restart_policy
                )
            )
            
            # 构建 Job 规格
            job_spec = client.V1JobSpec(
                template=pod_template,
                backoff_limit=backoff_limit
            )
            
            # 构建 Job
            job = client.V1Job(
                api_version="batch/v1",
                kind="Job",
                metadata=client.V1ObjectMeta(name=name, namespace=namespace, labels=labels),
                spec=job_spec
            )
            
            # 创建 Job
            response = self.batch_v1_api.create_namespaced_job(
                namespace=namespace,
                body=job
            )
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None
            }
            
        except ApiException as e:
            raise Exception(f"创建 Job 失败: {e}")

    async def delete_job(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除 Job"""
        try:
            response = self.batch_v1_api.delete_namespaced_job(
                name=name,
                namespace=namespace
            )
            
            uid = None
            if hasattr(response, 'details') and response.details:
                uid = getattr(response.details, 'uid', None)
            elif hasattr(response, 'metadata') and response.metadata:
                uid = getattr(response.metadata, 'uid', None)
            
            return {
                "name": name,
                "namespace": namespace,
                "status": "deleted",
                "uid": uid
            }
            
        except ApiException as e:
            raise Exception(f"删除 Job 失败: {e}")

    # ========================== CronJob 服务层方法 ==========================

    async def list_cronjobs(self, namespace: str = "default", label_selector: str = None) -> List[Dict[str, Any]]:
        """列出 CronJob"""
        try:
            # 尝试使用 batch/v1 API（Kubernetes 1.21+）
            try:
                if namespace == "all":
                    response = self.batch_v1_api.list_cron_job_for_all_namespaces(label_selector=label_selector)
                else:
                    response = self.batch_v1_api.list_namespaced_cron_job(
                        namespace=namespace,
                        label_selector=label_selector
                    )
            except Exception:
                if not self.batch_v1beta1_api:
                    raise Exception("集群不支持 batch/v1beta1 CronJob API，且 batch/v1 API 查询失败")
                if namespace == "all":
                    response = self.batch_v1beta1_api.list_cron_job_for_all_namespaces(label_selector=label_selector)
                else:
                    response = self.batch_v1beta1_api.list_namespaced_cron_job(
                        namespace=namespace,
                        label_selector=label_selector
                    )
            cronjobs = []
            for item in response.items:
                cronjobs.append({
                    "name": item.metadata.name,
                    "namespace": item.metadata.namespace,
                    "uid": item.metadata.uid,
                    "creation_timestamp": to_local_time_str(item.metadata.creation_timestamp, 8) if item.metadata.creation_timestamp else None,
                    "schedule": item.spec.schedule,
                    "suspend": item.spec.suspend or False,
                    "active_jobs": len(item.status.active) if item.status.active else 0,
                    "last_schedule_time": to_local_time_str(item.status.last_schedule_time, 8) if item.status.last_schedule_time else None,
                    "labels": item.metadata.labels
                })
    
            return cronjobs
            
        except ApiException as e:
            raise Exception(f"列出 CronJob 失败: {e}")

    async def get_cronjob(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """获取 CronJob 详情"""
        try:
            # 尝试使用 batch/v1 API（Kubernetes 1.21+）
            try:
                response = self.batch_v1_api.read_namespaced_cron_job(
                    name=name,
                    namespace=namespace
                )
            except Exception:
                if not self.batch_v1beta1_api:
                    raise Exception("集群不支持 batch/v1beta1 CronJob API，且 batch/v1 API 查询失败")
                response = self.batch_v1beta1_api.read_namespaced_cron_job(
                    name=name,
                    namespace=namespace
                )

            # 提取 Job 模板中的 Pod 模板详细信息
            pod_template = response.spec.job_template.spec.template
            containers = []
            for c in pod_template.spec.containers:
                containers.append({
                    "name": c.name,
                    "image": c.image,
                    "command": c.command,
                    "args": c.args,
                    "env": [{"name": e.name, "value": e.value} for e in (c.env or [])],
                    "resources": {
                        "limits": c.resources.limits if c.resources and c.resources.limits else {},
                        "requests": c.resources.requests if c.resources and c.resources.requests else {}
                    }
                })
            # 其他 Pod 级别信息
            pod_spec = pod_template.spec
            pod_info = {
                "restart_policy": pod_spec.restart_policy,
                "service_account": pod_spec.service_account_name,
                "node_selector": pod_spec.node_selector,
                "volumes": [v.name for v in (pod_spec.volumes or [])]
            }
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                "schedule": response.spec.schedule,
                "suspend": response.spec.suspend or False,
                "active_jobs": len(response.status.active) if response.status.active else 0,
                "last_schedule_time": to_local_time_str(response.status.last_schedule_time, 8) if response.status.last_schedule_time else None,
                "labels": response.metadata.labels,
                "concurrency_policy": response.spec.concurrency_policy,
                "starting_deadline_seconds": response.spec.starting_deadline_seconds,
                "containers": containers,
                "pod_template": pod_info
            }

        except ApiException as e:
            raise Exception(f"获取 CronJob 失败: {e}")

    async def create_cronjob(self, name: str, image: str, schedule: str,
                       namespace: str = "default", command: list = None,
                       args: list = None, labels: dict = None,
                       env_vars: dict = None, resources: dict = None,
                       restart_policy: str = "Never", suspend: bool = False) -> Dict[str, Any]:
        """创建 CronJob"""
        try:
            if labels is None:
                labels = {"app": name}
            
            # 构建环境变量
            env_list = []
            if env_vars:
                for key, value in env_vars.items():
                    env_list.append(client.V1EnvVar(name=key, value=str(value)))
            
            # 构建资源限制
            resource_requirements = None
            if resources:
                resource_requirements = client.V1ResourceRequirements(
                    requests=resources.get("requests"),
                    limits=resources.get("limits")
                )
            
            # 构建容器规格
            container = client.V1Container(
                name=name,
                image=image,
                command=command,
                args=args,
                env=env_list,
                resources=resource_requirements
            )
            
            # 构建 Pod 模板
            pod_template = client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels=labels),
                spec=client.V1PodSpec(
                    containers=[container],
                    restart_policy=restart_policy
                )
            )
            
            # 构建 Job 模板
            job_template = client.V1JobTemplateSpec(
                metadata=client.V1ObjectMeta(labels=labels),
                spec=client.V1JobSpec(template=pod_template)
            )
            
            # 构建 CronJob 规格
            cronjob_spec = client.V1CronJobSpec(
                schedule=schedule,
                job_template=job_template,
                suspend=suspend
            )
            
            # 构建 CronJob
            cronjob = client.V1CronJob(
                api_version="batch/v1",
                kind="CronJob",
                metadata=client.V1ObjectMeta(name=name, namespace=namespace, labels=labels),
                spec=cronjob_spec
            )
            
            # 创建 CronJob
            try:
                response = self.batch_v1_api.create_namespaced_cron_job(
                    namespace=namespace,
                    body=cronjob
                )
            except:
                # 回退到 batch/v1beta1 API
                cronjob.api_version = "batch/v1beta1"
                response = self.batch_v1beta1_api.create_namespaced_cron_job(
                    namespace=namespace,
                    body=cronjob
                )
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                "schedule": response.spec.schedule
            }
            
        except ApiException as e:
            raise Exception(f"创建 CronJob 失败: {e}")

    async def update_cronjob(self, name: str, namespace: str = "default",
                       schedule: str = None, suspend: bool = None,
                       image: str = None, labels: dict = None) -> Dict[str, Any]:
        """更新 CronJob"""
        try:
            # 获取现有的 CronJob
            try:
                cronjob = self.batch_v1_api.read_namespaced_cron_job(
                    name=name,
                    namespace=namespace
                )
                api_version = "batch/v1"
            except:
                cronjob = self.batch_v1beta1_api.read_namespaced_cron_job(
                    name=name,
                    namespace=namespace
                )
                api_version = "batch/v1beta1"
            
            # 更新调度
            if schedule is not None:
                cronjob.spec.schedule = schedule
            
            # 更新暂停状态
            if suspend is not None:
                cronjob.spec.suspend = suspend
            
            # 更新镜像
            if image is not None:
                cronjob.spec.job_template.spec.template.spec.containers[0].image = image
            
            # 更新标签
            if labels is not None:
                cronjob.metadata.labels.update(labels)
            
            # 应用更新
            if api_version == "batch/v1":
                response = self.batch_v1_api.patch_namespaced_cron_job(
                    name=name,
                    namespace=namespace,
                    body=cronjob
                )
            else:
                response = self.batch_v1beta1_api.patch_namespaced_cron_job(
                    name=name,
                    namespace=namespace,
                    body=cronjob
                )
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "schedule": response.spec.schedule,
                "suspend": response.spec.suspend
            }
            
        except ApiException as e:
            raise Exception(f"更新 CronJob 失败: {e}")

    async def delete_cronjob(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除 CronJob"""
        try:
            # 尝试使用 batch/v1 API
            try:
                response = self.batch_v1_api.delete_namespaced_cron_job(
                    name=name,
                    namespace=namespace
                )
            except:
                # 回退到 batch/v1beta1 API
                response = self.batch_v1beta1_api.delete_namespaced_cron_job(
                    name=name,
                    namespace=namespace
                )
            
            uid = None
            if hasattr(response, 'details') and response.details:
                uid = getattr(response.details, 'uid', None)
            elif hasattr(response, 'metadata') and response.metadata:
                uid = getattr(response.metadata, 'uid', None)
            
            return {
                "name": name,
                "namespace": namespace,
                "status": "deleted",
                "uid": uid
            }
            
        except ApiException as e:
            raise Exception(f"删除 CronJob 失败: {e}") 

    # ========================== Ingress 服务层方法 ==========================

    async def list_ingresses(self, namespace: str = "default", label_selector: str = None) -> List[Dict[str, Any]]:
        """列出 Ingress"""
        try:
            if namespace == "all":
                response = self.networking_v1_api.list_ingress_for_all_namespaces(label_selector=label_selector)
            else:
                response = self.networking_v1_api.list_namespaced_ingress(
                    namespace=namespace,
                    label_selector=label_selector
                )
            ingresses = []
            for item in response.items:
                ingresses.append({
                    "name": item.metadata.name,
                    "namespace": item.metadata.namespace,
                    "uid": item.metadata.uid,
                    "creation_timestamp": to_local_time_str(item.metadata.creation_timestamp, 8) if item.metadata.creation_timestamp else None,
                    "labels": item.metadata.labels or {},
                    "annotations": item.metadata.annotations or {},
                    "class_name": item.spec.ingress_class_name,
                    "rules": [
                        {
                            "host": rule.host,
                            "paths": [
                                {
                                    "path": path.path,
                                    "path_type": path.path_type,
                                    "service_name": path.backend.service.name,
                                    "service_port": path.backend.service.port.number
                                }
                                for path in (rule.http.paths or [])
                            ] if rule.http else []
                        }
                        for rule in (item.spec.rules or [])
                    ],
                    "tls": [
                        {
                            "secret_name": tls.secret_name,
                            "hosts": tls.hosts or []
                        }
                        for tls in (item.spec.tls or [])
                    ]
                })
            
            return ingresses
            
        except ApiException as e:
            raise Exception(f"列出 Ingress 失败: {e}")

    async def get_ingress(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """获取 Ingress 详情"""
        try:
            response = self.networking_v1_api.read_namespaced_ingress(
                name=name,
                namespace=namespace
            )
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                "labels": response.metadata.labels or {},
                "annotations": response.metadata.annotations or {},
                "class_name": response.spec.ingress_class_name,
                "rules": [
                    {
                        "host": rule.host,
                        "paths": [
                            {
                                "path": path.path,
                                "path_type": path.path_type,
                                "service_name": path.backend.service.name,
                                "service_port": path.backend.service.port.number
                            }
                            for path in (rule.http.paths or [])
                        ] if rule.http else []
                    }
                    for rule in (response.spec.rules or [])
                ],
                "tls": [
                    {
                        "secret_name": tls.secret_name,
                        "hosts": tls.hosts or []
                    }
                    for tls in (response.spec.tls or [])
                ],
                "load_balancer": {
                    "ingress": [
                        {
                            "ip": lb.ip,
                            "hostname": lb.hostname
                        }
                        for lb in (response.status.load_balancer.ingress or [])
                    ] if response.status.load_balancer else []
                }
            }
            
        except ApiException as e:
            raise Exception(f"获取 Ingress 失败: {e}")

    async def create_ingress(self, name: str, rules: list, namespace: str = "default",
                       annotations: dict = None, tls: list = None,
                       ingress_class_name: str = None, labels: dict = None) -> Dict[str, Any]:
        """创建 Ingress"""
        try:
            # 构建 Ingress 规则
            ingress_rules = []
            for rule in rules:
                paths = []
                for path in rule.get("paths", []):
                    paths.append(
                        client.V1HTTPIngressPath(
                            path=path.get("path", "/"),
                            path_type=path.get("path_type", "Prefix"),
                            backend=client.V1IngressBackend(
                                service=client.V1IngressServiceBackend(
                                    name=path.get("service_name"),
                                    port=client.V1ServiceBackendPort(
                                        number=path.get("service_port", 80)
                                    )
                                )
                            )
                        )
                    )
                
                ingress_rules.append(
                    client.V1IngressRule(
                        host=rule.get("host"),
                        http=client.V1HTTPIngressRuleValue(paths=paths)
                    )
                )
            
            # 构建 TLS 配置
            tls_config = []
            if tls:
                for tls_item in tls:
                    tls_config.append(
                        client.V1IngressTLS(
                            secret_name=tls_item.get("secret_name"),
                            hosts=tls_item.get("hosts", [])
                        )
                    )
            
            # 构建 Ingress 规格
            ingress_spec = client.V1IngressSpec(
                rules=ingress_rules,
                tls=tls_config if tls_config else None,
                ingress_class_name=ingress_class_name
            )
            
            # 构建 Ingress
            ingress = client.V1Ingress(
                api_version="networking.k8s.io/v1",
                kind="Ingress",
                metadata=client.V1ObjectMeta(
                    name=name,
                    namespace=namespace,
                    labels=labels,
                    annotations=annotations
                ),
                spec=ingress_spec
            )
            
            # 创建 Ingress
            response = self.networking_v1_api.create_namespaced_ingress(
                namespace=namespace,
                body=ingress
            )
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                "class_name": response.spec.ingress_class_name
            }
            
        except ApiException as e:
            raise Exception(f"创建 Ingress 失败: {e}")

    async def update_ingress(self, name: str, namespace: str = "default",
                       rules: list = None, annotations: dict = None,
                       tls: list = None, ingress_class_name: str = None,
                       labels: dict = None) -> Dict[str, Any]:
        """更新 Ingress"""
        try:
            # 获取现有的 Ingress
            ingress = self.networking_v1_api.read_namespaced_ingress(
                name=name,
                namespace=namespace
            )
            
            # 更新规则
            if rules is not None:
                ingress_rules = []
                for rule in rules:
                    paths = []
                    for path in rule.get("paths", []):
                        paths.append(
                            client.V1HTTPIngressPath(
                                path=path.get("path", "/"),
                                path_type=path.get("path_type", "Prefix"),
                                backend=client.V1IngressBackend(
                                    service=client.V1IngressServiceBackend(
                                        name=path.get("service_name"),
                                        port=client.V1ServiceBackendPort(
                                            number=path.get("service_port", 80)
                                        )
                                    )
                                )
                            )
                        )
                    
                    ingress_rules.append(
                        client.V1IngressRule(
                            host=rule.get("host"),
                            http=client.V1HTTPIngressRuleValue(paths=paths)
                        )
                    )
                
                ingress.spec.rules = ingress_rules
            
            # 更新 TLS 配置
            if tls is not None:
                tls_config = []
                for tls_item in tls:
                    tls_config.append(
                        client.V1IngressTLS(
                            secret_name=tls_item.get("secret_name"),
                            hosts=tls_item.get("hosts", [])
                        )
                    )
                ingress.spec.tls = tls_config
            
            # 更新 Ingress Class
            if ingress_class_name is not None:
                ingress.spec.ingress_class_name = ingress_class_name
            
            # 更新标签
            if labels is not None:
                if ingress.metadata.labels:
                    ingress.metadata.labels.update(labels)
                else:
                    ingress.metadata.labels = labels
            
            # 更新注解
            if annotations is not None:
                if ingress.metadata.annotations:
                    ingress.metadata.annotations.update(annotations)
                else:
                    ingress.metadata.annotations = annotations
            
            # 应用更新
            response = self.networking_v1_api.patch_namespaced_ingress(
                name=name,
                namespace=namespace,
                body=ingress
            )
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "class_name": response.spec.ingress_class_name
            }
            
        except ApiException as e:
            raise Exception(f"更新 Ingress 失败: {e}")

    async def delete_ingress(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除 Ingress"""
        try:
            response = self.networking_v1_api.delete_namespaced_ingress(
                name=name,
                namespace=namespace
            )
            
            uid = None
            if hasattr(response, 'details') and response.details:
                uid = getattr(response.details, 'uid', None)
            elif hasattr(response, 'metadata') and response.metadata:
                uid = getattr(response.metadata, 'uid', None)
            
            return {
                "name": name,
                "namespace": namespace,
                "status": "deleted",
                "uid": uid
            }
            
        except ApiException as e:
            raise Exception(f"删除 Ingress 失败: {e}")

    # ========================== StorageClass 服务层方法 ==========================

    async def list_storageclasses(self, label_selector: str = None) -> List[Dict[str, Any]]:
        """列出 StorageClass"""
        try:
            response = self.storage_v1_api.list_storage_class(
                label_selector=label_selector
            )
            
            storage_classes = []
            for item in response.items:
                storage_classes.append({
                    "name": item.metadata.name,
                    "uid": item.metadata.uid,
                    "creation_timestamp": to_local_time_str(item.metadata.creation_timestamp, 8) if item.metadata.creation_timestamp else None,
                    "labels": item.metadata.labels or {},
                    "annotations": item.metadata.annotations or {},
                    "provisioner": item.provisioner,
                    "reclaim_policy": item.reclaim_policy,
                    "volume_binding_mode": item.volume_binding_mode,
                    "allow_volume_expansion": item.allow_volume_expansion,
                    "parameters": item.parameters or {}
                })
            
            return storage_classes
            
        except ApiException as e:
            raise Exception(f"列出 StorageClass 失败: {e}")

    async def get_storageclass(self, name: str) -> Dict[str, Any]:
        """获取 StorageClass 详情"""
        try:
            response = self.storage_v1_api.read_storage_class(name=name)
            
            return {
                "name": response.metadata.name,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                "labels": response.metadata.labels or {},
                "annotations": response.metadata.annotations or {},
                "provisioner": response.provisioner,
                "reclaim_policy": response.reclaim_policy,
                "volume_binding_mode": response.volume_binding_mode,
                "allow_volume_expansion": response.allow_volume_expansion,
                "parameters": response.parameters or {},
                "allowed_topologies": [
                    {
                        "match_label_expressions": [
                            {
                                "key": expr.key,
                                "values": expr.values
                            }
                            for expr in (topology.match_label_expressions or [])
                        ]
                    }
                    for topology in (response.allowed_topologies or [])
                ]
            }
            
        except ApiException as e:
            raise Exception(f"获取 StorageClass 失败: {e}")

    async def create_storageclass(self, name: str, provisioner: str,
                            reclaim_policy: str = "Delete",
                            volume_binding_mode: str = "Immediate",
                            allow_volume_expansion: bool = False,
                            parameters: dict = None,
                            labels: dict = None,
                            annotations: dict = None) -> Dict[str, Any]:
        """创建 StorageClass"""
        try:
            # 构建 StorageClass
            storage_class = client.V1StorageClass(
                api_version="storage.k8s.io/v1",
                kind="StorageClass",
                metadata=client.V1ObjectMeta(
                    name=name,
                    labels=labels,
                    annotations=annotations
                ),
                provisioner=provisioner,
                reclaim_policy=reclaim_policy,
                volume_binding_mode=volume_binding_mode,
                allow_volume_expansion=allow_volume_expansion,
                parameters=parameters
            )
            
            # 创建 StorageClass
            response = self.storage_v1_api.create_storage_class(body=storage_class)
            
            return {
                "name": response.metadata.name,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                "provisioner": response.provisioner,
                "reclaim_policy": response.reclaim_policy,
                "volume_binding_mode": response.volume_binding_mode
            }
            
        except ApiException as e:
            raise Exception(f"创建 StorageClass 失败: {e}")

    async def update_storageclass(self, name: str, provisioner: str = None,
                            reclaim_policy: str = None,
                            volume_binding_mode: str = None,
                            allow_volume_expansion: bool = None,
                            parameters: dict = None,
                            labels: dict = None,
                            annotations: dict = None) -> Dict[str, Any]:
        """更新 StorageClass"""
        try:
            # 获取现有的 StorageClass
            storage_class = self.storage_v1_api.read_storage_class(name=name)
            
            # 更新字段
            if provisioner is not None:
                storage_class.provisioner = provisioner
            if reclaim_policy is not None:
                storage_class.reclaim_policy = reclaim_policy
            if volume_binding_mode is not None:
                storage_class.volume_binding_mode = volume_binding_mode
            if allow_volume_expansion is not None:
                storage_class.allow_volume_expansion = allow_volume_expansion
            if parameters is not None:
                storage_class.parameters = parameters
            
            # 更新标签
            if labels is not None:
                if storage_class.metadata.labels:
                    storage_class.metadata.labels.update(labels)
                else:
                    storage_class.metadata.labels = labels
            
            # 更新注解
            if annotations is not None:
                if storage_class.metadata.annotations:
                    storage_class.metadata.annotations.update(annotations)
                else:
                    storage_class.metadata.annotations = annotations
            
            # 应用更新
            response = self.storage_v1_api.patch_storage_class(
                name=name,
                body=storage_class
            )
            
            return {
                "name": response.metadata.name,
                "uid": response.metadata.uid,
                "provisioner": response.provisioner,
                "reclaim_policy": response.reclaim_policy,
                "volume_binding_mode": response.volume_binding_mode
            }
            
        except ApiException as e:
            raise Exception(f"更新 StorageClass 失败: {e}")

    async def delete_storageclass(self, name: str) -> Dict[str, Any]:
        """删除 StorageClass"""
        try:
            response = self.storage_v1_api.delete_storage_class(name=name)
            
            uid = None
            if hasattr(response, 'details') and response.details:
                uid = getattr(response.details, 'uid', None)
            elif hasattr(response, 'metadata') and response.metadata:
                uid = getattr(response.metadata, 'uid', None)
            
            return {
                "name": name,
                "status": "deleted",
                "uid": uid
            }
            
        except ApiException as e:
            raise Exception(f"删除 StorageClass 失败: {e}")

    # ========================== PersistentVolume 服务层方法 ==========================

    async def list_persistentvolumes(self, label_selector: str = None) -> List[Dict[str, Any]]:
        """列出 PersistentVolume"""
        try:
            response = self.v1_api.list_persistent_volume(
                label_selector=label_selector
            )
            
            persistent_volumes = []
            for item in response.items:
                persistent_volumes.append({
                    "name": item.metadata.name,
                    "uid": item.metadata.uid,
                    "creation_timestamp": to_local_time_str(item.metadata.creation_timestamp, 8) if item.metadata.creation_timestamp else None,
                    "labels": item.metadata.labels or {},
                    "annotations": item.metadata.annotations or {},
                    "capacity": item.spec.capacity or {},
                    "access_modes": item.spec.access_modes or [],
                    "reclaim_policy": item.spec.persistent_volume_reclaim_policy,
                    "storage_class_name": item.spec.storage_class_name,
                    "volume_mode": item.spec.volume_mode,
                    "status": item.status.phase,
                    "claim_ref": {
                        "name": item.spec.claim_ref.name,
                        "namespace": item.spec.claim_ref.namespace,
                        "uid": item.spec.claim_ref.uid
                    } if item.spec.claim_ref else None
                })
            
            return persistent_volumes
            
        except ApiException as e:
            raise Exception(f"列出 PersistentVolume 失败: {e}")

    async def get_persistentvolume(self, name: str) -> Dict[str, Any]:
        """获取 PersistentVolume 详情"""
        try:
            response = self.v1_api.read_persistent_volume(name=name)
            
            return {
                "name": response.metadata.name,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                "labels": response.metadata.labels or {},
                "annotations": response.metadata.annotations or {},
                "capacity": response.spec.capacity or {},
                "access_modes": response.spec.access_modes or [],
                "reclaim_policy": response.spec.persistent_volume_reclaim_policy,
                "storage_class_name": response.spec.storage_class_name,
                "volume_mode": response.spec.volume_mode,
                "status": response.status.phase,
                "claim_ref": {
                    "name": response.spec.claim_ref.name,
                    "namespace": response.spec.claim_ref.namespace,
                    "uid": response.spec.claim_ref.uid
                } if response.spec.claim_ref else None,
                "host_path": {
                    "path": response.spec.host_path.path,
                    "type": response.spec.host_path.type
                } if response.spec.host_path else None,
                "nfs": {
                    "server": response.spec.nfs.server,
                    "path": response.spec.nfs.path,
                    "read_only": response.spec.nfs.read_only
                } if response.spec.nfs else None
            }
            
        except ApiException as e:
            raise Exception(f"获取 PersistentVolume 失败: {e}")

    async def create_persistentvolume(self, name: str, capacity: str,
                                access_modes: list,
                                reclaim_policy: str = "Retain",
                                storage_class_name: str = None,
                                volume_mode: str = "Filesystem",
                                host_path: str = None,
                                nfs: dict = None,
                                labels: dict = None,
                                annotations: dict = None,
                                csi: dict = None) -> Dict[str, Any]:
        """创建 PersistentVolume"""
        try:
            # 构建存储源
            volume_source = None
            if host_path:
                volume_source = client.V1HostPathVolumeSource(path=host_path)
            elif nfs:
                volume_source = client.V1NFSVolumeSource(
                    server=nfs.get("server"),
                    path=nfs.get("path"),
                    read_only=nfs.get("read_only", False)
                )
            
            # 构建 PersistentVolume 规格
            pv_spec = client.V1PersistentVolumeSpec(
                capacity={"storage": capacity},
                access_modes=access_modes,
                persistent_volume_reclaim_policy=reclaim_policy,
                storage_class_name=storage_class_name,
                volume_mode=volume_mode
            )
            
            # 根据存储类型设置相应的字段
            if host_path:
                pv_spec.host_path = volume_source
            elif nfs:
                pv_spec.nfs = volume_source
            
            # 支持 CSI 卷
            if csi:
                pv_spec.csi = client.V1CSIPersistentVolumeSource(
                    driver=csi.get("driver"),
                    fs_type=csi.get("fsType"),
                    volume_handle=csi.get("volumeHandle"),
                    read_only=csi.get("readOnly", False),
                    volume_attributes=csi.get("volumeAttributes")
                )
            
            # 构建 PersistentVolume
            pv = client.V1PersistentVolume(
                api_version="v1",
                kind="PersistentVolume",
                metadata=client.V1ObjectMeta(
                    name=name,
                    labels=labels,
                    annotations=annotations
                ),
                spec=pv_spec
            )
            
            # 创建 PersistentVolume
            response = self.v1_api.create_persistent_volume(body=pv)
            
            return {
                "name": response.metadata.name,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                "capacity": response.spec.capacity,
                "access_modes": response.spec.access_modes,
                "reclaim_policy": response.spec.persistent_volume_reclaim_policy,
                "storage_class_name": response.spec.storage_class_name
            }
            
        except ApiException as e:
            raise Exception(f"创建 PersistentVolume 失败: {e}")

    async def update_persistentvolume(self, name: str,
                                capacity: str = None,
                                access_modes: list = None,
                                reclaim_policy: str = None,
                                storage_class_name: str = None,
                                labels: dict = None,
                                annotations: dict = None) -> Dict[str, Any]:
        """更新 PersistentVolume"""
        try:
            # 获取现有的 PersistentVolume
            pv = self.v1_api.read_persistent_volume(name=name)
            
            # 更新字段
            if capacity is not None:
                pv.spec.capacity = {"storage": capacity}
            if access_modes is not None:
                pv.spec.access_modes = access_modes
            if reclaim_policy is not None:
                pv.spec.persistent_volume_reclaim_policy = reclaim_policy
            if storage_class_name is not None:
                pv.spec.storage_class_name = storage_class_name
            
            # 更新标签
            if labels is not None:
                if pv.metadata.labels:
                    pv.metadata.labels.update(labels)
                else:
                    pv.metadata.labels = labels
            
            # 更新注解
            if annotations is not None:
                if pv.metadata.annotations:
                    pv.metadata.annotations.update(annotations)
                else:
                    pv.metadata.annotations = annotations
            
            # 应用更新
            response = self.v1_api.patch_persistent_volume(
                name=name,
                body=pv
            )
            
            return {
                "name": response.metadata.name,
                "uid": response.metadata.uid,
                "capacity": response.spec.capacity,
                "access_modes": response.spec.access_modes,
                "reclaim_policy": response.spec.persistent_volume_reclaim_policy
            }
            
        except ApiException as e:
            raise Exception(f"更新 PersistentVolume 失败: {e}")

    async def delete_persistentvolume(self, name: str) -> Dict[str, Any]:
        """删除 PersistentVolume"""
        try:
            response = self.v1_api.delete_persistent_volume(name=name)
            
            uid = None
            if hasattr(response, 'details') and response.details:
                uid = getattr(response.details, 'uid', None)
            elif hasattr(response, 'metadata') and response.metadata:
                uid = getattr(response.metadata, 'uid', None)
            
            return {
                "name": name,
                "status": "deleted",
                "uid": uid
            }
            
        except ApiException as e:
            raise Exception(f"删除 PersistentVolume 失败: {e}")

    # ========================== PersistentVolumeClaim 服务层方法 ==========================

    async def list_persistentvolumeclaims(self, namespace: str = "default",
                                    label_selector: str = None) -> List[Dict[str, Any]]:
        """列出 PersistentVolumeClaim"""
        try:
            if namespace == "all":
                response = self.v1_api.list_persistent_volume_claim_for_all_namespaces(label_selector=label_selector)
            else:
                response = self.v1_api.list_namespaced_persistent_volume_claim(
                    namespace=namespace,
                    label_selector=label_selector
                )
            pvcs = []
            for item in response.items:
                pvcs.append({
                    "name": item.metadata.name,
                    "namespace": item.metadata.namespace,
                    "uid": item.metadata.uid,
                    "creation_timestamp": to_local_time_str(item.metadata.creation_timestamp, 8) if item.metadata.creation_timestamp else None,
                    "labels": item.metadata.labels or {},
                    "annotations": item.metadata.annotations or {},
                    "access_modes": item.spec.access_modes or [],
                    "requests": item.spec.resources.requests or {} if item.spec.resources else {},
                    "storage_class_name": item.spec.storage_class_name,
                    "volume_mode": item.spec.volume_mode,
                    "volume_name": item.spec.volume_name,
                    "status": item.status.phase,
                    "capacity": item.status.capacity or {} if item.status else {}
                })
            
            return pvcs
            
        except ApiException as e:
            raise Exception(f"列出 PersistentVolumeClaim 失败: {e}")

    async def get_persistentvolumeclaim(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """获取 PersistentVolumeClaim 详情"""
        try:
            response = self.v1_api.read_namespaced_persistent_volume_claim(
                name=name,
                namespace=namespace
            )
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                "labels": response.metadata.labels or {},
                "annotations": response.metadata.annotations or {},
                "access_modes": response.spec.access_modes or [],
                "requests": response.spec.resources.requests or {} if response.spec.resources else {},
                "limits": response.spec.resources.limits or {} if response.spec.resources else {},
                "storage_class_name": response.spec.storage_class_name,
                "volume_mode": response.spec.volume_mode,
                "volume_name": response.spec.volume_name,
                "status": response.status.phase,
                "capacity": response.status.capacity or {} if response.status else {},
                "conditions": [
                    {
                        "type": condition.type,
                        "status": condition.status,
                        "reason": condition.reason,
                        "message": condition.message,
                        "last_probe_time": to_local_time_str(condition.last_probe_time, 8) if condition.last_probe_time else None,
                        "last_transition_time": to_local_time_str(condition.last_transition_time, 8) if condition.last_transition_time else None
                    }
                    for condition in (response.status.conditions or [])
                ] if response.status else []
            }
            
        except ApiException as e:
            raise Exception(f"获取 PersistentVolumeClaim 失败: {e}")

    async def create_persistentvolumeclaim(self, name: str, size: str,
                                     namespace: str = "default",
                                     access_modes: list = None,
                                     storage_class_name: str = None,
                                     volume_mode: str = "Filesystem",
                                     volume_name: str = None,
                                     labels: dict = None,
                                     annotations: dict = None) -> Dict[str, Any]:
        """创建 PersistentVolumeClaim"""
        try:
            if access_modes is None:
                access_modes = ["ReadWriteOnce"]
            
            # 构建资源要求
            resource_requirements = client.V1ResourceRequirements(
                requests={"storage": size}
            )
            
            # 构建 PersistentVolumeClaim 规格
            pvc_spec = client.V1PersistentVolumeClaimSpec(
                access_modes=access_modes,
                resources=resource_requirements,
                storage_class_name=storage_class_name,
                volume_mode=volume_mode,
                volume_name=volume_name
            )
            
            # 构建 PersistentVolumeClaim
            pvc = client.V1PersistentVolumeClaim(
                api_version="v1",
                kind="PersistentVolumeClaim",
                metadata=client.V1ObjectMeta(
                    name=name,
                    namespace=namespace,
                    labels=labels,
                    annotations=annotations
                ),
                spec=pvc_spec
            )
            
            # 创建 PersistentVolumeClaim
            response = self.v1_api.create_namespaced_persistent_volume_claim(
                namespace=namespace,
                body=pvc
            )
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                "access_modes": response.spec.access_modes,
                "requests": response.spec.resources.requests,
                "storage_class_name": response.spec.storage_class_name
            }
            
        except ApiException as e:
            raise Exception(f"创建 PersistentVolumeClaim 失败: {e}")

    async def update_persistentvolumeclaim(self, name: str, namespace: str = "default",
                                     size: str = None,
                                     access_modes: list = None,
                                     storage_class_name: str = None,
                                     labels: dict = None,
                                     annotations: dict = None) -> Dict[str, Any]:
        """更新 PersistentVolumeClaim"""
        try:
            # 获取现有的 PersistentVolumeClaim
            pvc = self.v1_api.read_namespaced_persistent_volume_claim(
                name=name,
                namespace=namespace
            )
            
            # 更新字段
            if size is not None:
                pvc.spec.resources.requests["storage"] = size
            if access_modes is not None:
                pvc.spec.access_modes = access_modes
            if storage_class_name is not None:
                pvc.spec.storage_class_name = storage_class_name
            
            # 更新标签
            if labels is not None:
                if pvc.metadata.labels:
                    pvc.metadata.labels.update(labels)
                else:
                    pvc.metadata.labels = labels
            
            # 更新注解
            if annotations is not None:
                if pvc.metadata.annotations:
                    pvc.metadata.annotations.update(annotations)
                else:
                    pvc.metadata.annotations = annotations
            
            # 应用更新
            response = self.v1_api.patch_namespaced_persistent_volume_claim(
                name=name,
                namespace=namespace,
                body=pvc
            )
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "access_modes": response.spec.access_modes,
                "requests": response.spec.resources.requests,
                "storage_class_name": response.spec.storage_class_name
            }
            
        except ApiException as e:
            raise Exception(f"更新 PersistentVolumeClaim 失败: {e}")

    async def delete_persistentvolumeclaim(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除 PersistentVolumeClaim"""
        try:
            response = self.v1_api.delete_namespaced_persistent_volume_claim(
                name=name,
                namespace=namespace
            )
            
            uid = None
            if hasattr(response, 'details') and response.details:
                uid = getattr(response.details, 'uid', None)
            elif hasattr(response, 'metadata') and response.metadata:
                uid = getattr(response.metadata, 'uid', None)
            
            return {
                "name": name,
                "namespace": namespace,
                "status": "deleted",
                "uid": uid
            }
            
        except ApiException as e:
            raise Exception(f"删除 PersistentVolumeClaim 失败: {e}") 

    # ========================== Node 服务层方法 ==========================

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
                    "age": to_local_time_str(node.metadata.creation_timestamp, 8) if node.metadata.creation_timestamp else None,
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
                    "created": to_local_time_str(node.metadata.creation_timestamp, 8) if node.metadata.creation_timestamp else None,
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

    # ========================== Namespace 服务层方法 ==========================

    async def list_namespaces(self, label_selector: str = None) -> List[Dict[str, Any]]:
        """列出 Namespace"""
        try:
            namespaces = self.v1_api.list_namespace(label_selector=label_selector)
            
            namespace_list = []
            for namespace in namespaces.items:
                namespace_info = {
                    "name": namespace.metadata.name,
                    "status": namespace.status.phase,
                    "created": to_local_time_str(namespace.metadata.creation_timestamp, 8) if namespace.metadata.creation_timestamp else None,
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

    # ========================== Event 服务层方法 ==========================

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
                    "first_timestamp": to_local_time_str(event.first_timestamp, 8) if event.first_timestamp else None,
                    "last_timestamp": to_local_time_str(event.last_timestamp, 8) if event.last_timestamp else None,
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
                "started_at": to_local_time_str(state.running.started_at, 8) if state.running.started_at else None
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
                "started_at": to_local_time_str(state.terminated.started_at, 8) if state.terminated.started_at else None,
                "finished_at": to_local_time_str(state.terminated.finished_at, 8) if state.terminated.finished_at else None,
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
