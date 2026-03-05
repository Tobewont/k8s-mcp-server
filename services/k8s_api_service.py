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
        
        # 验证服务
        self._advanced_service = None
    
    def set_validation_service(self, advanced_service):
        """设置验证服务"""
        self._advanced_service = advanced_service
    
    async def _execute_with_validation_and_preview(self, operation_type: str, resource_type: str, 
                                                 resource_name: str, namespace: str = "default", 
                                                 resource_data: Dict = None, original_operation=None, **kwargs):
        """统一的验证、预览和执行方法"""
        if not self._advanced_service:
            # 如果没有验证服务，直接执行原始操作
            if original_operation:
                return await original_operation()
            else:
                raise Exception("验证服务未初始化且未提供原始操作方法")
        
        # 执行验证和预览
        print(f"\n🔍 {operation_type.upper()} {resource_type}/{resource_name}")
        
        if operation_type in ["update", "delete"]:
            validation_result = await self._advanced_service.validate_and_preview_operation(
                resource_type, resource_name, operation_type, namespace, resource_data
            )
            
            if not validation_result["valid"]:
                print(validation_result["message"])
                return {"error": validation_result["message"]}
            
            print(validation_result["message"])
            
            # 显示变化预览
            if validation_result["changes"]:
                print("📋 预览变化:")
                for change in validation_result["changes"]:
                    print(change)
                print()  # 空行分隔
            
            # 显示警告
            for warning in validation_result["warnings"]:
                print(warning)
        
        elif operation_type == "create":
            # 创建操作只需要基本验证
            validation_result = await self._advanced_service.validate_and_preview_operation(
                resource_type, resource_name, operation_type, namespace, resource_data
            )
            
            if not validation_result["valid"]:
                print(validation_result["message"])
                return {"error": validation_result["message"]}
            
            print(validation_result["message"])
        
        print(f"🚀 执行操作...")
        
        # 执行实际操作
        try:
            result = await original_operation()
            print(f"✅ 操作成功完成\n")
            return result
        except Exception as e:
            print(f"❌ 操作失败: {e}\n")
            raise
    
    def _build_resource_data_for_validation(self, resource_type: str, name: str, namespace: str, 
                                          resource: Dict = None, **params) -> Dict:
        """为验证构建资源数据的通用方法"""
        if resource:
            return resource
        
        # 根据资源类型构建基础资源数据
        kind_mapping = {
            "horizontalpodautoscaler": "HorizontalPodAutoscaler",
            "networkpolicy": "NetworkPolicy", 
            "resourcequota": "ResourceQuota"
        }
        
        base_resource = {
            "apiVersion": self._get_api_version_for_resource(resource_type),
            "kind": kind_mapping.get(resource_type.lower(), resource_type.capitalize()),
            "metadata": {"name": name, "namespace": namespace}
        }
        
        # 根据资源类型添加特定字段
        if resource_type == "deployment":
            labels = params.get("labels", {"app": name})
            base_resource.update({
                "spec": {
                    "replicas": params.get("replicas", 1),
                    "selector": {"matchLabels": labels},
                    "template": {
                        "metadata": {"labels": labels},
                        "spec": {
                            "containers": [{
                                "name": name,
                                "image": params.get("image", ""),
                                "ports": params.get("ports", []),
                                "env": [{"name": k, "value": str(v)} for k, v in (params.get("env_vars", {})).items()],
                                "resources": params.get("resources", {})
                            }]
                        }
                    }
                }
            })
        elif resource_type == "statefulset":
            labels = params.get("labels", {"app": name})
            base_resource.update({
                "spec": {
                    "replicas": params.get("replicas", 1),
                    "serviceName": params.get("service_name", name),
                    "selector": {"matchLabels": labels},
                    "template": {
                        "metadata": {"labels": labels},
                        "spec": {
                            "containers": [{
                                "name": name,
                                "image": params.get("image", ""),
                                "ports": params.get("ports", []),
                                "env": [{"name": k, "value": str(v)} for k, v in (params.get("env_vars", {})).items()],
                                "resources": params.get("resources", {})
                            }]
                        }
                    },
                    "volumeClaimTemplates": params.get("volume_claims", [])
                }
            })
        elif resource_type == "daemonset":
            labels = params.get("labels", {"app": name})
            base_resource.update({
                "spec": {
                    "selector": {"matchLabels": labels},
                    "template": {
                        "metadata": {"labels": labels},
                        "spec": {
                            "containers": [{
                                "name": name,
                                "image": params.get("image", ""),
                                "ports": params.get("ports", []),
                                "env": [{"name": k, "value": str(v)} for k, v in (params.get("env_vars", {})).items()],
                                "resources": params.get("resources", {})
                            }]
                        }
                    }
                }
            })
        elif resource_type == "service":
            base_resource.update({
                "spec": {
                    "type": params.get("service_type", "ClusterIP"),
                    "ports": params.get("ports", []),
                    "selector": params.get("selector", {})
                }
            })
        elif resource_type == "configmap":
            base_resource.update({
                "data": params.get("data", {})
            })
        elif resource_type == "secret":
            base_resource.update({
                "type": params.get("secret_type", "Opaque"),
                "data": params.get("data", {})
            })
        elif resource_type == "job":
            base_resource.update({
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [{
                                "name": name,
                                "image": params.get("image", ""),
                                "command": params.get("command", []),
                                "args": params.get("args", [])
                            }],
                            "restartPolicy": params.get("restart_policy", "Never")
                        }
                    },
                    "backoffLimit": params.get("backoff_limit", 6)
                }
            })
        elif resource_type == "cronjob":
            base_resource.update({
                "spec": {
                    "schedule": params.get("schedule", ""),
                    "jobTemplate": {
                        "spec": {
                            "template": {
                                "spec": {
                                    "containers": [{
                                        "name": name,
                                        "image": params.get("image", ""),
                                        "command": params.get("command", []),
                                        "args": params.get("args", [])
                                    }],
                                    "restartPolicy": params.get("restart_policy", "Never")
                                }
                            }
                        }
                    },
                    "suspend": params.get("suspend", False)
                }
            })
        elif resource_type == "ingress":
            base_resource.update({
                "spec": {
                    "rules": params.get("rules", []),
                    "tls": params.get("tls", []),
                    "ingressClassName": params.get("ingress_class_name")
                }
            })
        elif resource_type == "persistentvolumeclaim":
            base_resource.update({
                "spec": {
                    "accessModes": params.get("access_modes", ["ReadWriteOnce"]),
                    "resources": {
                        "requests": {
                            "storage": params.get("size", "1Gi")
                        }
                    },
                    "storageClassName": params.get("storage_class_name")
                }
            })
        elif resource_type == "serviceaccount":
            if params.get("automount_service_account_token") is not None:
                base_resource["automountServiceAccountToken"] = params.get("automount_service_account_token")
        elif resource_type == "role":
            base_resource.update({
                "rules": params.get("rules", [])
            })
        elif resource_type == "rolebinding":
            base_resource.update({
                "subjects": params.get("subjects", []),
                "roleRef": params.get("role_ref", {})
            })
        elif resource_type == "horizontalpodautoscaler":
            base_resource.update({
                "spec": {
                    "scaleTargetRef": params.get("target_ref", {}),
                    "minReplicas": params.get("min_replicas", 1),
                    "maxReplicas": params.get("max_replicas", 10),
                    "metrics": params.get("metrics", [])
                }
            })
        elif resource_type == "networkpolicy":
            base_resource.update({
                "spec": {
                    "podSelector": params.get("pod_selector", {}),
                    "policyTypes": params.get("policy_types", ["Ingress"]),
                    "ingress": params.get("ingress", []),
                    "egress": params.get("egress", [])
                }
            })
        elif resource_type == "resourcequota":
            base_resource.update({
                "spec": {
                    "hard": params.get("hard", {}),
                    "scopes": params.get("scopes", [])
                }
            })
        
        return base_resource
    
    def _get_api_version_for_resource(self, resource_type: str) -> str:
        """获取资源类型的API版本"""
        api_versions = {
            "deployment": "apps/v1",
            "statefulset": "apps/v1", 
            "daemonset": "apps/v1",
            "service": "v1",
            "configmap": "v1",
            "secret": "v1",
            "job": "batch/v1",
            "cronjob": "batch/v1",
            "ingress": "networking.k8s.io/v1",
            "persistentvolumeclaim": "v1",
            "serviceaccount": "v1",
            "role": "rbac.authorization.k8s.io/v1",
            "rolebinding": "rbac.authorization.k8s.io/v1",
            "clusterrole": "rbac.authorization.k8s.io/v1",
            "clusterrolebinding": "rbac.authorization.k8s.io/v1",
            "namespace": "v1",
            "horizontalpodautoscaler": "autoscaling/v2",
            "networkpolicy": "networking.k8s.io/v1",
            "resourcequota": "v1"
        }
        return api_versions.get(resource_type.lower(), "v1")
        
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
                            "key": env.value_from.secret_key_ref.key
                        } if env.value_from and env.value_from.secret_key_ref else None,
                        "configMapKeyRef": {
                            "name": env.value_from.config_map_key_ref.name,
                            "key": env.value_from.config_map_key_ref.key
                        } if env.value_from and env.value_from.config_map_key_ref else None
                    } if env.value_from else None
                }
                for env in (container.env or [])
            ],
            "resources": {
                "requests": {
                    "memory": container.resources.requests.get("memory") if container.resources and container.resources.requests else None,
                    "cpu": container.resources.requests.get("cpu") if container.resources and container.resources.requests else None
                } if container.resources and container.resources.requests else {},
                "limits": {
                    "memory": container.resources.limits.get("memory") if container.resources and container.resources.limits else None,
                    "cpu": container.resources.limits.get("cpu") if container.resources and container.resources.limits else None
                } if container.resources and container.resources.limits else {}
            } if container.resources else {},
            "livenessProbe": {
                "httpGet": {
                    "path": container.liveness_probe.http_get.path,
                    "port": container.liveness_probe.http_get.port
                } if container.liveness_probe and container.liveness_probe.http_get else None,
                "initialDelaySeconds": container.liveness_probe.initial_delay_seconds,
                "periodSeconds": container.liveness_probe.period_seconds,
                "successThreshold": container.liveness_probe.success_threshold,
                "failureThreshold": container.liveness_probe.failure_threshold
            } if container.liveness_probe else None,
            "readinessProbe": {
                "httpGet": {
                    "path": container.readiness_probe.http_get.path,
                    "port": container.readiness_probe.http_get.port
                } if container.readiness_probe and container.readiness_probe.http_get else None,
                "initialDelaySeconds": container.readiness_probe.initial_delay_seconds,
                "periodSeconds": container.readiness_probe.period_seconds,
                "successThreshold": container.readiness_probe.success_threshold,
                "failureThreshold": container.readiness_probe.failure_threshold
            } if container.readiness_probe else None,
            "volumeMounts": [
                {"mountPath": v.mount_path, "name": v.name, "readOnly": v.read_only} 
                for v in (container.volume_mounts or [])
            ]
        }
        
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
        # 修复新版 K8s client 无 BatchV1beta1Api 的情况
        if hasattr(client, 'BatchV1beta1Api'):
            try:
                self.batch_v1beta1_api = client.BatchV1beta1Api()
            except Exception:
                self.batch_v1beta1_api = None
        else:
            self.batch_v1beta1_api = None
        
        # 验证所有必需的 API 客户端是否已初始化
        self._validate_api_clients()

    def _validate_api_clients(self):
        """验证所有需要的 API 客户端是否已初始化"""
        required_apis = [
            'v1_api', 'apps_v1_api', 'networking_v1_api', 
            'rbac_v1_api', 'storage_v1_api', 'batch_v1_api',
            'autoscaling_v2_api'
        ]
        
        for api_name in required_apis:
            if not hasattr(self, api_name) or getattr(self, api_name) is None:
                raise AttributeError(f"API 客户端 {api_name} 未正确初始化")

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
                     since_seconds: int = None, follow: bool = False,
                     previous: bool = False) -> str:
        """获取 Pod 日志，previous=True 时获取上一实例（崩溃容器）的日志"""
        try:
            logs = self.v1_api.read_namespaced_pod_log(
                name=name,
                namespace=namespace,
                container=container,
                tail_lines=lines,
                since_seconds=since_seconds,
                follow=follow,
                previous=previous
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
            
            # 提取容器和卷信息
            containers = [self._extract_container_info(c) for c in deployment.spec.template.spec.containers]
            volumes = [self._extract_volume_info(v) for v in (deployment.spec.template.spec.volumes or [])]
            
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
                        "metadata": {
                            "labels": deployment.spec.template.metadata.labels or {}
                        },
                        "spec": {
                            "containers": containers,
                            "volumes": volumes
                        }
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

    async def create_deployment(self, name: str = None, image: str = None, namespace: str = "default",
                          replicas: int = 1, labels: dict = None, env_vars: dict = None,
                          ports: list = None, resources: dict = None, resource: Dict = None, **kwargs) -> Dict[str, Any]:
        """创建 Deployment"""
        
        # 准备资源数据用于验证
        resource_name = resource.get("metadata", {}).get("name") if resource else name
        resource_data = self._build_resource_data_for_validation(
            "deployment", name, namespace, resource,
            labels=labels, replicas=replicas, image=image, ports=ports, 
            env_vars=env_vars, resources=resources
        )
        
        # 定义实际的创建操作
        async def create_operation():
            # 批量操作模式，传入完整的资源定义
            if resource:
                # 创建 Deployment
                response = self.apps_v1_api.create_namespaced_deployment(
                    namespace=namespace,
                    body=resource
                )
                
                return {
                    "name": response.metadata.name,
                    "namespace": response.metadata.namespace,
                    "uid": response.metadata.uid,
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                    "replicas": response.spec.replicas
                }
            
            # 单体操作模式，使用简化参数创建
            if not name or not image:
                raise ValueError("name和image参数是必需的")
            
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
        
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "deployment", resource_name, namespace, resource_data, create_operation
        )

    async def update_deployment(self, name: str, namespace: str = "default",
                          image: str = None, replicas: int = None,
                          labels: dict = None, env_vars: dict = None,
                          resources: dict = None, resource: Dict = None) -> Dict[str, Any]:
        """更新 Deployment"""
        
        # 准备资源数据用于验证和预览
        resource_data = resource if resource else {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": name, "namespace": namespace},
            "spec": {}
        }
        
        # 如果有简化参数，构建完整的资源数据用于预览
        if not resource:
            # 获取当前资源状态来构建完整的更新数据
            current = await self.get_deployment(name, namespace)
            if current.get("error"):
                return {"error": current["error"]}
            
            # 基于当前状态构建更新后的资源数据
            resource_data = {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": current.get("metadata", {}),
                "spec": current.get("spec", {})
            }
            
            # 应用更新参数
            if image is not None:
                if "template" in resource_data["spec"] and "spec" in resource_data["spec"]["template"]:
                    containers = resource_data["spec"]["template"]["spec"].get("containers", [])
                    if containers:
                        containers[0]["image"] = image
            
            if replicas is not None:
                resource_data["spec"]["replicas"] = replicas
                
            if labels is not None:
                resource_data["metadata"]["labels"] = {**(resource_data["metadata"].get("labels", {})), **labels}
                if "template" in resource_data["spec"] and "metadata" in resource_data["spec"]["template"]:
                    resource_data["spec"]["template"]["metadata"]["labels"] = {**(resource_data["spec"]["template"]["metadata"].get("labels", {})), **labels}
        
        # 定义实际的更新操作
        async def update_operation():
            if resource is not None:
                # 批量操作模式，传入完整的资源定义
                body = resource
                # 确保metadata中有正确的name和namespace
                if 'metadata' not in body:
                    body['metadata'] = {}
                body['metadata']['name'] = name
                body['metadata']['namespace'] = namespace
                
                response = self.apps_v1_api.patch_namespaced_deployment(
                    name=name,
                    namespace=namespace,
                    body=body
                )
            else:
                # 单体操作模式，使用简化参数更新
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
                response = self.apps_v1_api.patch_namespaced_deployment(
                    name=name,
                    namespace=namespace,
                    body=deployment
                )
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "replicas": response.spec.replicas,
                "image": response.spec.template.spec.containers[0].image,
                "status": "updated"
            }
        
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "update", "deployment", name, namespace, resource_data, update_operation
        )

    async def delete_deployment(self, name: str, namespace: str = "default", 
                                grace_period_seconds: int = None) -> Dict[str, Any]:
        """删除 Deployment"""
        
        # 定义实际的删除操作
        async def delete_operation():
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
        
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "delete", "deployment", name, namespace, None, delete_operation
        )

    async def rollout_status(self, kind: str, name: str, namespace: str = "default") -> Dict[str, Any]:
        """获取 Deployment/StatefulSet/DaemonSet 发布状态"""
        try:
            kind = kind.lower()
            if kind == "deployment":
                obj = self.apps_v1_api.read_namespaced_deployment_status(name=name, namespace=namespace)
                return {
                    "kind": "Deployment",
                    "name": name,
                    "namespace": namespace,
                    "replicas": obj.spec.replicas,
                    "ready_replicas": obj.status.ready_replicas or 0,
                    "updated_replicas": obj.status.updated_replicas or 0,
                    "available_replicas": obj.status.available_replicas or 0,
                    "paused": getattr(obj.spec, "paused", False) or False,
                    "conditions": [
                        {"type": c.type, "status": c.status, "reason": c.reason, "message": c.message}
                        for c in (obj.status.conditions or [])
                    ]
                }
            elif kind == "statefulset":
                obj = self.apps_v1_api.read_namespaced_stateful_set_status(name=name, namespace=namespace)
                return {
                    "kind": "StatefulSet",
                    "name": name,
                    "namespace": namespace,
                    "replicas": obj.spec.replicas,
                    "ready_replicas": obj.status.ready_replicas or 0,
                    "current_replicas": obj.status.current_replicas or 0,
                    "updated_replicas": obj.status.updated_replicas or 0,
                    "conditions": [
                        {"type": c.type, "status": c.status, "reason": c.reason, "message": c.message}
                        for c in (obj.status.conditions or [])
                    ]
                }
            elif kind == "daemonset":
                obj = self.apps_v1_api.read_namespaced_daemon_set_status(name=name, namespace=namespace)
                return {
                    "kind": "DaemonSet",
                    "name": name,
                    "namespace": namespace,
                    "desired_number_scheduled": obj.status.desired_number_scheduled or 0,
                    "current_number_scheduled": obj.status.current_number_scheduled or 0,
                    "number_ready": obj.status.number_ready or 0,
                    "updated_number_scheduled": obj.status.updated_number_scheduled or 0,
                    "conditions": [
                        {"type": c.type, "status": c.status, "reason": c.reason, "message": c.message}
                        for c in (obj.status.conditions or [])
                    ]
                }
            else:
                raise ValueError(f"不支持的资源类型: {kind}，支持 Deployment/StatefulSet/DaemonSet")
        except ApiException as e:
            raise Exception(f"获取发布状态失败: {e.reason}")

    async def rollout_undo(self, kind: str, name: str, namespace: str = "default",
                          revision: int = None) -> Dict[str, Any]:
        """回滚 Deployment/StatefulSet/DaemonSet 到上一版本"""
        try:
            kind = kind.lower()
            if kind == "deployment":
                deployment = self.apps_v1_api.read_namespaced_deployment(name=name, namespace=namespace)
                label_selector = ",".join(f"{k}={v}" for k, v in (deployment.spec.selector.match_labels or {}).items())
                rs_list = self.apps_v1_api.list_namespaced_replica_set(
                    namespace=namespace, label_selector=label_selector
                )
                def _rev_key(r):
                    rev = r.metadata.annotations.get("deployment.kubernetes.io/revision", "0")
                    return int(rev) if str(rev).isdigit() else 0
                rs_sorted = sorted(rs_list.items, key=_rev_key, reverse=True)
                if revision is not None:
                    target_rs = next((r for r in rs_sorted if _rev_key(r) == revision), None)
                    if not target_rs:
                        raise Exception(f"未找到 revision {revision}")
                    prev_rs = target_rs
                elif len(rs_sorted) < 2:
                    raise Exception("没有可回滚的版本")
                else:
                    prev_rs = rs_sorted[1]
                template = prev_rs.spec.template
                api_client = self.apps_v1_api.api_client
                template_dict = api_client.sanitize_for_serialization(template) if template else {}
                if not template_dict:
                    raise Exception("无法获取上一版本的 Pod 模板")
                if isinstance(template_dict.get("metadata", {}).get("labels"), dict):
                    template_dict["metadata"]["labels"].pop("pod-template-hash", None)
                patch = [{"op": "replace", "path": "/spec/template", "value": template_dict}]
                self.apps_v1_api.patch_namespaced_deployment(name=name, namespace=namespace, body=patch)
                return {"kind": "Deployment", "name": name, "namespace": namespace, "status": "rolled_back"}
            elif kind == "statefulset":
                sts = self.apps_v1_api.read_namespaced_stateful_set(name=name, namespace=namespace)
                revisions = self.apps_v1_api.list_namespaced_controller_revision(
                    namespace=namespace,
                    label_selector=f"controller.kubernetes.io/name={name}"
                )
                rev_sorted = sorted(revisions.items, key=lambda r: getattr(r, "revision", 0) or 0, reverse=True)
                if len(rev_sorted) < 2:
                    raise Exception("没有可回滚的版本")
                prev_rev = rev_sorted[1]
                rev_data = prev_rev.data if hasattr(prev_rev, "data") else {}
                if isinstance(rev_data, dict):
                    template = rev_data.get("spec", {}).get("template") or rev_data.get("template")
                else:
                    template = getattr(getattr(rev_data, "spec", None), "template", None) or getattr(rev_data, "template", None)
                if not template:
                    raise Exception("无法解析上一版本的模板")
                patch = {"spec": {"template": template}}
                self.apps_v1_api.patch_namespaced_stateful_set(name=name, namespace=namespace, body=patch)
                return {"kind": "StatefulSet", "name": name, "namespace": namespace, "status": "rolled_back"}
            elif kind == "daemonset":
                revisions = self.apps_v1_api.list_namespaced_controller_revision(
                    namespace=namespace,
                    label_selector=f"controller.kubernetes.io/name={name}"
                )
                rev_sorted = sorted(revisions.items, key=lambda r: getattr(r, "revision", 0) or 0, reverse=True)
                if len(rev_sorted) < 2:
                    raise Exception("没有可回滚的版本")
                prev_rev = rev_sorted[1]
                rev_data = prev_rev.data if hasattr(prev_rev, "data") else {}
                if isinstance(rev_data, dict):
                    template = rev_data.get("spec", {}).get("template") or rev_data.get("template")
                else:
                    template = getattr(getattr(rev_data, "spec", None), "template", None) or getattr(rev_data, "template", None)
                if not template:
                    raise Exception("无法解析上一版本的模板")
                patch = {"spec": {"template": template}}
                self.apps_v1_api.patch_namespaced_daemon_set(name=name, namespace=namespace, body=patch)
                return {"kind": "DaemonSet", "name": name, "namespace": namespace, "status": "rolled_back"}
            else:
                raise ValueError(f"不支持的资源类型: {kind}")
        except ApiException as e:
            raise Exception(f"回滚失败: {e.reason}")

    async def rollout_pause(self, kind: str, name: str, namespace: str = "default") -> Dict[str, Any]:
        """暂停 Deployment 发布（仅 Deployment 支持）"""
        if kind.lower() != "deployment":
            raise ValueError("仅 Deployment 支持暂停发布")
        try:
            patch = {"spec": {"paused": True}}
            self.apps_v1_api.patch_namespaced_deployment(name=name, namespace=namespace, body=patch)
            return {"kind": "Deployment", "name": name, "namespace": namespace, "status": "paused"}
        except ApiException as e:
            raise Exception(f"暂停发布失败: {e.reason}")

    async def rollout_resume(self, kind: str, name: str, namespace: str = "default") -> Dict[str, Any]:
        """恢复 Deployment 发布（仅 Deployment 支持）"""
        if kind.lower() != "deployment":
            raise ValueError("仅 Deployment 支持恢复发布")
        try:
            patch = {"spec": {"paused": False}}
            self.apps_v1_api.patch_namespaced_deployment(name=name, namespace=namespace, body=patch)
            return {"kind": "Deployment", "name": name, "namespace": namespace, "status": "resumed"}
        except ApiException as e:
            raise Exception(f"恢复发布失败: {e.reason}")

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
                    "imagePullPolicy": c.image_pull_policy,
                    "ports": [
                        {
                            "containerPort": port.container_port,
                            "name": port.name,
                            "protocol": port.protocol
                        }
                        for port in (c.ports or [])
                    ],
                    "env": [
                        {
                            "name": env.name,
                            "value": env.value,
                            "valueFrom": {
                                "secretKeyRef": {
                                    "name": env.value_from.secret_key_ref.name,
                                    "key": env.value_from.secret_key_ref.key
                                } if env.value_from and env.value_from.secret_key_ref else None,
                                "configMapKeyRef": {
                                    "name": env.value_from.config_map_key_ref.name,
                                    "key": env.value_from.config_map_key_ref.key
                                } if env.value_from and env.value_from.config_map_key_ref else None
                            } if env.value_from else None
                        }
                        for env in (c.env or [])
                    ],
                    "resources": {
                        "requests": {
                            "memory": c.resources.requests.get("memory") if c.resources and c.resources.requests else None,
                            "cpu": c.resources.requests.get("cpu") if c.resources and c.resources.requests else None
                        } if c.resources and c.resources.requests else {},
                        "limits": {
                            "memory": c.resources.limits.get("memory") if c.resources and c.resources.limits else None,
                            "cpu": c.resources.limits.get("cpu") if c.resources and c.resources.limits else None
                        } if c.resources and c.resources.limits else {}
                    } if c.resources else {},
                    "livenessProbe": {
                        "httpGet": {
                            "path": c.liveness_probe.http_get.path,
                            "port": c.liveness_probe.http_get.port
                        } if c.liveness_probe and c.liveness_probe.http_get else None,
                        "initialDelaySeconds": c.liveness_probe.initial_delay_seconds,
                        "periodSeconds": c.liveness_probe.period_seconds,
                        "successThreshold": c.liveness_probe.success_threshold,
                        "failureThreshold": c.liveness_probe.failure_threshold
                    } if c.liveness_probe else None,
                    "readinessProbe": {
                        "httpGet": {
                            "path": c.readiness_probe.http_get.path,
                            "port": c.readiness_probe.http_get.port
                        } if c.readiness_probe and c.readiness_probe.http_get else None,
                        "initialDelaySeconds": c.readiness_probe.initial_delay_seconds,
                        "periodSeconds": c.readiness_probe.period_seconds,
                        "successThreshold": c.readiness_probe.success_threshold,
                        "failureThreshold": c.readiness_probe.failure_threshold
                    } if c.readiness_probe else None,
                    "volumeMounts": [
                        {"mountPath": v.mount_path, "name": v.name, "readOnly": v.read_only} 
                        for v in (c.volume_mounts or [])
                    ]
                })

            # 提取卷信息
            volumes = []
            for v in (response.spec.template.spec.volumes or []):
                vinfo = {"name": v.name}
                if v.config_map:
                    vinfo["type"] = "ConfigMap"
                    config_map_info = {"name": v.config_map.name}
                    if v.config_map.optional:
                        config_map_info["optional"] = v.config_map.optional
                    vinfo["configMap"] = config_map_info
                elif v.secret:
                    vinfo["type"] = "Secret"
                    secret_info = {"secretName": v.secret.secret_name}
                    if v.secret.optional:
                        secret_info["optional"] = v.secret.optional
                    vinfo["secret"] = secret_info
                elif v.persistent_volume_claim:
                    vinfo["type"] = "PersistentVolumeClaim"
                    vinfo["persistentVolumeClaim"] = {"claimName": v.persistent_volume_claim.claim_name}
                elif v.host_path:
                    vinfo["type"] = "HostPath"
                    vinfo["hostPath"] = {"path": v.host_path.path}
                    if v.host_path.type:
                        vinfo["hostPath"]["type"] = v.host_path.type
                elif v.empty_dir:
                    vinfo["type"] = "EmptyDir"
                    vinfo["emptyDir"] = {}
                    if v.empty_dir.size_limit:
                        vinfo["emptyDir"]["sizeLimit"] = v.empty_dir.size_limit
                volumes.append(vinfo)

            return {
                "metadata": {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                    "labels": response.metadata.labels or {},
                    "annotations": response.metadata.annotations or {},
                    "created": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None
                },
                "spec": {
                "replicas": response.spec.replicas,
                    "selector": response.spec.selector.match_labels or {},
                    "serviceName": response.spec.service_name,
                    "template": {
                        "metadata": {
                            "labels": response.spec.template.metadata.labels or {}
                        },
                        "spec": {
                "containers": containers,
                            "volumes": volumes
                        }
                    },
                    "volumeClaimTemplates": [
                        {
                            "metadata": {"name": vct.metadata.name},
                            "spec": {
                                "accessModes": vct.spec.access_modes,
                                "resources": {"requests": {"storage": vct.spec.resources.requests.get("storage", "")}},
                                "storageClassName": vct.spec.storage_class_name
                            }
                    } for vct in (response.spec.volume_claim_templates or [])
                ]
                },
                "status": {
                    "replicas": response.status.replicas or 0,
                    "ready_replicas": response.status.ready_replicas or 0,
                    "current_replicas": response.status.current_replicas or 0
                }
            }
            
        except ApiException as e:
            raise Exception(f"获取 StatefulSet 失败: {e}")

    async def create_statefulset(self, name: str = None, image: str = None, namespace: str = "default",
                           replicas: int = 1, labels: dict = None, env_vars: dict = None,
                           ports: list = None, resources: dict = None,
                           volume_claims: list = None, resource: Dict = None, **kwargs) -> Dict[str, Any]:
        """创建 StatefulSet"""
        
        # 准备资源数据用于验证
        resource_name = resource.get("metadata", {}).get("name") if resource else name
        resource_data = self._build_resource_data_for_validation(
            "statefulset", name, namespace, resource,
            labels=labels, replicas=replicas, image=image, ports=ports, 
            env_vars=env_vars, resources=resources, volume_claims=volume_claims
        )
        
        # 定义实际的创建操作
        async def create_operation():
            # 批量操作模式，传入完整的资源定义
            if resource:
                response = self.apps_v1_api.create_namespaced_stateful_set(
                    namespace=namespace,
                    body=resource
                )
                
                return {
                    "name": response.metadata.name,
                    "namespace": response.metadata.namespace,
                    "uid": response.metadata.uid,
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                    "replicas": response.spec.replicas
                }
            
            # 单体操作模式，使用简化参数创建
            if not name or not image:
                raise ValueError("name和image参数是必需的")
            
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "statefulset", resource_name, namespace, resource_data, create_operation
        )

    async def update_statefulset(self, name: str, namespace: str = "default",
                           image: str = None, replicas: int = None,
                           labels: dict = None, env_vars: dict = None, resource: Dict = None) -> Dict[str, Any]:
        """更新 StatefulSet"""
        
        # 准备资源数据用于验证
        resource_data = self._build_resource_data_for_validation(
            "statefulset", name, namespace, resource,
            labels=labels, replicas=replicas, image=image, env_vars=env_vars
        )
        
        # 定义实际的更新操作
        async def update_operation():
            if resource is not None:
                # 批量操作模式，传入完整的资源定义
                body = resource
                # 确保metadata中有正确的name和namespace
                if 'metadata' not in body:
                    body['metadata'] = {}
                body['metadata']['name'] = name
                body['metadata']['namespace'] = namespace
                
                response = self.apps_v1_api.patch_namespaced_stateful_set(
                    name=name,
                    namespace=namespace,
                    body=body
                )
            else:
                # 单体操作模式，使用简化参数更新
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "update", "statefulset", name, namespace, resource_data, update_operation
        )

    async def delete_statefulset(self, name: str, namespace: str = "default",
                                 grace_period_seconds: int = None) -> Dict[str, Any]:
        """删除 StatefulSet"""
        
        # 定义实际的删除操作
        async def delete_operation():
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "delete", "statefulset", name, namespace, None, delete_operation
        )

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
                    "imagePullPolicy": c.image_pull_policy,
                    "ports": [
                        {
                            "containerPort": port.container_port,
                            "name": port.name,
                            "protocol": port.protocol
                        }
                        for port in (c.ports or [])
                    ],
                    "env": [
                        {
                            "name": env.name,
                            "value": env.value,
                            "valueFrom": {
                                "secretKeyRef": {
                                    "name": env.value_from.secret_key_ref.name,
                                    "key": env.value_from.secret_key_ref.key
                                } if env.value_from and env.value_from.secret_key_ref else None,
                                "configMapKeyRef": {
                                    "name": env.value_from.config_map_key_ref.name,
                                    "key": env.value_from.config_map_key_ref.key
                                } if env.value_from and env.value_from.config_map_key_ref else None
                            } if env.value_from else None
                        }
                        for env in (c.env or [])
                    ],
                    "resources": {
                        "requests": {
                            "memory": c.resources.requests.get("memory") if c.resources and c.resources.requests else None,
                            "cpu": c.resources.requests.get("cpu") if c.resources and c.resources.requests else None
                        } if c.resources and c.resources.requests else {},
                        "limits": {
                            "memory": c.resources.limits.get("memory") if c.resources and c.resources.limits else None,
                            "cpu": c.resources.limits.get("cpu") if c.resources and c.resources.limits else None
                        } if c.resources and c.resources.limits else {}
                    } if c.resources else {},
                    "livenessProbe": {
                        "httpGet": {
                            "path": c.liveness_probe.http_get.path,
                            "port": c.liveness_probe.http_get.port
                        } if c.liveness_probe and c.liveness_probe.http_get else None,
                        "initialDelaySeconds": c.liveness_probe.initial_delay_seconds,
                        "periodSeconds": c.liveness_probe.period_seconds,
                        "successThreshold": c.liveness_probe.success_threshold,
                        "failureThreshold": c.liveness_probe.failure_threshold
                    } if c.liveness_probe else None,
                    "readinessProbe": {
                        "httpGet": {
                            "path": c.readiness_probe.http_get.path,
                            "port": c.readiness_probe.http_get.port
                        } if c.readiness_probe and c.readiness_probe.http_get else None,
                        "initialDelaySeconds": c.readiness_probe.initial_delay_seconds,
                        "periodSeconds": c.readiness_probe.period_seconds,
                        "successThreshold": c.readiness_probe.success_threshold,
                        "failureThreshold": c.readiness_probe.failure_threshold
                    } if c.readiness_probe else None,
                    "volumeMounts": [
                        {"mountPath": v.mount_path, "name": v.name, "readOnly": v.read_only} 
                        for v in (c.volume_mounts or [])
                    ]
                })

            # 提取卷信息
            volumes = []
            for v in (response.spec.template.spec.volumes or []):
                vinfo = {"name": v.name}
                if v.config_map:
                    vinfo["type"] = "ConfigMap"
                    config_map_info = {"name": v.config_map.name}
                    if v.config_map.optional:
                        config_map_info["optional"] = v.config_map.optional
                    vinfo["configMap"] = config_map_info
                elif v.secret:
                    vinfo["type"] = "Secret"
                    secret_info = {"secretName": v.secret.secret_name}
                    if v.secret.optional:
                        secret_info["optional"] = v.secret.optional
                    vinfo["secret"] = secret_info
                elif v.persistent_volume_claim:
                    vinfo["type"] = "PersistentVolumeClaim"
                    vinfo["persistentVolumeClaim"] = {"claimName": v.persistent_volume_claim.claim_name}
                elif v.host_path:
                    vinfo["type"] = "HostPath"
                    vinfo["hostPath"] = {"path": v.host_path.path}
                    if v.host_path.type:
                        vinfo["hostPath"]["type"] = v.host_path.type
                elif v.empty_dir:
                    vinfo["type"] = "EmptyDir"
                    vinfo["emptyDir"] = {}
                    if v.empty_dir.size_limit:
                        vinfo["emptyDir"]["sizeLimit"] = v.empty_dir.size_limit
                volumes.append(vinfo)

            return {
                "metadata": {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                    "labels": response.metadata.labels or {},
                    "annotations": response.metadata.annotations or {},
                    "created": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None
                },
                "spec": {
                    "selector": response.spec.selector.match_labels or {},
                    "template": {
                        "metadata": {
                            "labels": response.spec.template.metadata.labels or {}
                        },
                        "spec": {
                "containers": containers,
                "volumes": volumes
                        }
                    }
                },
                "status": {
                    "desired_number_scheduled": response.status.desired_number_scheduled or 0,
                    "current_number_scheduled": response.status.current_number_scheduled or 0,
                    "number_ready": response.status.number_ready or 0
                }
            }
            
        except ApiException as e:
            raise Exception(f"获取 DaemonSet 失败: {e}")

    async def create_daemonset(self, name: str = None, image: str = None, namespace: str = "default",
                         labels: dict = None, env_vars: dict = None,
                         ports: list = None, resources: dict = None,
                         volumes: list = None, resource: Dict = None, **kwargs) -> Dict[str, Any]:
        """创建 DaemonSet"""
        
        # 准备资源数据用于验证
        resource_name = resource.get("metadata", {}).get("name") if resource else name
        resource_data = self._build_resource_data_for_validation(
            "daemonset", name, namespace, resource,
            labels=labels, image=image, ports=ports, env_vars=env_vars, resources=resources
        )
        
        # 定义实际的创建操作
        async def create_operation():
            # 批量操作模式，传入完整的资源定义
            if resource:
                response = self.apps_v1_api.create_namespaced_daemon_set(
                    namespace=namespace,
                    body=resource
                )
                
                return {
                    "name": response.metadata.name,
                    "namespace": response.metadata.namespace,
                    "uid": response.metadata.uid,
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None
                }
            
            # 单体操作模式，使用简化参数创建
            if not name or not image:
                raise ValueError("name和image参数是必需的")
            
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "daemonset", resource_name, namespace, resource_data, create_operation
        )

    async def update_daemonset(self, name: str, namespace: str = "default",
                         image: str = None, labels: dict = None,
                         env_vars: dict = None, resource: Dict = None) -> Dict[str, Any]:
        """更新 DaemonSet"""
        
        # 准备资源数据用于验证
        resource_data = self._build_resource_data_for_validation(
            "daemonset", name, namespace, resource,
            labels=labels, image=image, env_vars=env_vars
        )
        
        # 定义实际的更新操作
        async def update_operation():
            if resource is not None:
                # 批量操作模式，传入完整的资源定义
                body = resource
                # 确保metadata中有正确的name和namespace
                if 'metadata' not in body:
                    body['metadata'] = {}
                body['metadata']['name'] = name
                body['metadata']['namespace'] = namespace
                
                response = self.apps_v1_api.patch_namespaced_daemon_set(
                    name=name,
                    namespace=namespace,
                    body=body
                )
            else:
                # 单体操作模式，使用简化参数更新
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "update", "daemonset", name, namespace, resource_data, update_operation
        )

    async def delete_daemonset(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除 DaemonSet"""
        
        # 定义实际的删除操作
        async def delete_operation():
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "delete", "daemonset", name, namespace, None, delete_operation
        )

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

    async def create_service(self, name: str = None, selector: dict = None, ports: list = None,
                       namespace: str = "default", service_type: str = "ClusterIP", resource: Dict = None, **kwargs) -> Dict[str, Any]:
        """创建 Service"""
        
        # 准备资源数据用于验证
        resource_name = resource.get("metadata", {}).get("name") if resource else name
        resource_data = self._build_resource_data_for_validation(
            "service", name, namespace, resource,
            selector=selector, ports=ports, service_type=service_type
        )
        
        # 定义实际的创建操作
        async def create_operation():
            # 批量操作模式，传入完整的资源定义
            if resource:
                # 创建 Service
                response = self.v1_api.create_namespaced_service(
                    namespace=namespace,
                    body=resource
                )
                
                return {
                    "name": response.metadata.name,
                    "namespace": response.metadata.namespace,
                    "uid": response.metadata.uid,
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                    "type": response.spec.type,
                    "cluster_ip": response.spec.cluster_ip
                }
            
            # 单体操作模式，使用简化参数创建
            if not name or not selector or not ports:
                raise ValueError("name、selector和ports参数是必需的")
            
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "service", resource_name, namespace, resource_data, create_operation
        )

    async def update_service(self, name: str, namespace: str = "default",
                       service_type: str = None, ports: list = None,
                       selector: dict = None, labels: dict = None, 
                       annotations: dict = None, resource: Dict = None) -> Dict[str, Any]:
        """更新 Service
        
        Args:
            name: Service名称
            namespace: 命名空间
            service_type: 服务类型 (ClusterIP, NodePort, LoadBalancer)
            ports: 端口列表
            selector: 选择器
            labels: 标签
            annotations: 注解
            resource: 完整的资源定义
            
        Returns:
            更新后的Service对象
        """
        
        # 准备资源数据用于验证
        resource_data = self._build_resource_data_for_validation(
            "service", name, namespace, resource,
            service_type=service_type, ports=ports, selector=selector
        )
        
        # 定义实际的更新操作
        async def update_operation():
            if resource is not None:
                # 批量操作模式，传入完整的资源定义
                # 获取当前Service以保持完整性
                current_service = self.v1_api.read_namespaced_service(name, namespace)
                
                # 更新指定的字段
                if 'metadata' in resource:
                    if 'labels' in resource['metadata']:
                        if current_service.metadata.labels is None:
                            current_service.metadata.labels = {}
                        current_service.metadata.labels.update(resource['metadata']['labels'])
                    if 'annotations' in resource['metadata']:
                        if current_service.metadata.annotations is None:
                            current_service.metadata.annotations = {}
                        current_service.metadata.annotations.update(resource['metadata']['annotations'])
                
                if 'spec' in resource:
                    if 'ports' in resource['spec']:
                        # 替换端口配置
                        current_service.spec.ports = []
                        for i, port in enumerate(resource['spec']['ports']):
                            service_port = client.V1ServicePort(
                                port=port.get("port"),
                                target_port=port.get("targetPort") or port.get("target_port"),
                                protocol=port.get("protocol", "TCP"),
                                name=port.get("name") or f"port-{port.get('port', i)}"
                            )
                            if port.get("nodePort") or port.get("node_port"):
                                service_port.node_port = port.get("nodePort") or port.get("node_port")
                            current_service.spec.ports.append(service_port)
                    
                    if 'selector' in resource['spec']:
                        current_service.spec.selector = resource['spec']['selector']
                    
                    if 'type' in resource['spec']:
                        current_service.spec.type = resource['spec']['type']
                
                response = self.v1_api.replace_namespaced_service(
                    name=name,
                    namespace=namespace,
                    body=current_service
                )
            else:
                # 单体操作模式，使用简化参数更新
                # 获取当前Service
                current_service = self.v1_api.read_namespaced_service(name, namespace)
                
                # 更新字段
                if service_type is not None:
                    current_service.spec.type = service_type
                    
                if ports is not None:
                    current_service.spec.ports = []
                    for port in ports:
                        service_port = client.V1ServicePort(
                            port=port.get("port"),
                            target_port=port.get("target_port"),
                            protocol=port.get("protocol", "TCP"),
                            name=port.get("name", f"port-{port.get('port')}")
                        )
                        if port.get("node_port") and (service_type == "NodePort" or current_service.spec.type == "NodePort"):
                            service_port.node_port = port.get("node_port")
                        current_service.spec.ports.append(service_port)
                        
                if selector is not None:
                    current_service.spec.selector = selector
                    
                if labels is not None:
                    if current_service.metadata.labels is None:
                        current_service.metadata.labels = {}
                    current_service.metadata.labels.update(labels)
                    
                if annotations is not None:
                    if current_service.metadata.annotations is None:
                        current_service.metadata.annotations = {}
                    current_service.metadata.annotations.update(annotations)
                
                # 更新Service
                response = self.v1_api.replace_namespaced_service(
                    name=name,
                namespace=namespace,
                body=current_service
            )
            
            # 转换为字典并返回
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                "type": response.spec.type,
                "cluster_ip": response.spec.cluster_ip,
                "selector": response.spec.selector,
                "labels": response.metadata.labels or {},
                "annotations": response.metadata.annotations or {}
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "update", "service", name, namespace, resource_data, update_operation
        )
    
    async def delete_service(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除 Service"""
        
        # 定义实际的删除操作
        async def delete_operation():
            response = self.v1_api.delete_namespaced_service(
                name=name,
                namespace=namespace
            )
            
            return {
                "name": name,
                "namespace": namespace,
                "status": "deleted"
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "delete", "service", name, namespace, None, delete_operation
        )

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

    async def create_configmap(self, name: str = None, data: dict = None, namespace: str = "default",
                         labels: dict = None, resource: Dict = None, **kwargs) -> Dict[str, Any]:
        """创建 ConfigMap"""
        
        # 准备资源数据用于验证
        resource_name = resource.get("metadata", {}).get("name") if resource else name
        resource_data = self._build_resource_data_for_validation(
            "configmap", name, namespace, resource,
            data=data, labels=labels
        )
        
        # 定义实际的创建操作
        async def create_operation():
            # 批量操作模式，传入完整的资源定义
            if resource:
                # 创建 ConfigMap
                response = self.v1_api.create_namespaced_config_map(
                    namespace=namespace,
                    body=resource
                )
                
                return {
                    "name": response.metadata.name,
                    "namespace": response.metadata.namespace,
                    "uid": response.metadata.uid,
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                    "data_keys": list(response.data.keys()) if response.data else []
                }
            
            # 单体操作模式，使用简化参数创建
            if not name or not data:
                raise ValueError("name和data参数是必需的")
            
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "configmap", resource_name, namespace, resource_data, create_operation
        )

    async def update_configmap(self, name: str, data: dict = None, namespace: str = "default",
                         labels: dict = None, resource: Dict = None) -> Dict[str, Any]:
        """更新 ConfigMap"""
        
        # 准备资源数据用于验证
        resource_data = self._build_resource_data_for_validation(
            "configmap", name, namespace, resource,
            data=data, labels=labels
        )
        
        # 定义实际的更新操作
        async def update_operation():
            if resource is not None:
                # 批量操作模式，传入完整的资源定义
                body = resource
                # 确保metadata中有正确的name和namespace
                if 'metadata' not in body:
                    body['metadata'] = {}
                body['metadata']['name'] = name
                body['metadata']['namespace'] = namespace
                
                response = self.v1_api.patch_namespaced_config_map(
                    name=name,
                    namespace=namespace,
                    body=body
                )
            else:
                # 单体操作模式，使用简化参数更新
                # 获取现有的 ConfigMap
                configmap = self.v1_api.read_namespaced_config_map(
                    name=name,
                    namespace=namespace
                )
                
                # 更新数据
                if data is not None:
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "update", "configmap", name, namespace, resource_data, update_operation
        )

    async def delete_configmap(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除 ConfigMap"""
        
        # 定义实际的删除操作
        async def delete_operation():
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "delete", "configmap", name, namespace, None, delete_operation
        )

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

    async def create_secret(self, name: str = None, data: dict = None, namespace: str = "default",
                      secret_type: str = "Opaque", labels: dict = None, resource: Dict = None, **kwargs) -> Dict[str, Any]:
        """创建 Secret"""
        
        # 准备资源数据用于验证
        resource_name = resource.get("metadata", {}).get("name") if resource else name
        resource_data = self._build_resource_data_for_validation(
            "secret", name, namespace, resource,
            data=data, secret_type=secret_type, labels=labels
        )
        
        # 定义实际的创建操作
        async def create_operation():
            # 批量操作模式，传入完整的资源定义
            if resource:
                # 创建 Secret
                response = self.v1_api.create_namespaced_secret(
                    namespace=namespace,
                    body=resource
                )
                
                return {
                    "name": response.metadata.name,
                    "namespace": response.metadata.namespace,
                    "uid": response.metadata.uid,
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                    "type": response.type,
                    "data_keys": list(response.data.keys()) if response.data else []
                }
            
            # 单体操作模式，使用简化参数创建
            if not name or not data:
                raise ValueError("name和data参数是必需的")
            
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "secret", resource_name, namespace, resource_data, create_operation
        )

    async def update_secret(self, name: str, data: dict = None, namespace: str = "default",
                      labels: dict = None, resource: Dict = None) -> Dict[str, Any]:
        """更新 Secret"""
        
        # 准备资源数据用于验证
        resource_data = self._build_resource_data_for_validation(
            "secret", name, namespace, resource,
            data=data, labels=labels
        )
        
        # 定义实际的更新操作
        async def update_operation():
            import base64
            
            if resource is not None:
                # 批量操作模式，传入完整的资源定义
                body = resource
                # 确保metadata中有正确的name和namespace
                if 'metadata' not in body:
                    body['metadata'] = {}
                body['metadata']['name'] = name
                body['metadata']['namespace'] = namespace
                
                response = self.v1_api.patch_namespaced_secret(
                    name=name,
                    namespace=namespace,
                    body=body
                )
            else:
                # 单体操作模式，使用简化参数更新
                # 获取现有的 Secret
                secret = self.v1_api.read_namespaced_secret(
                    name=name,
                    namespace=namespace
                )
                
                # 对数据进行 base64 编码
                if data is not None:
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "update", "secret", name, namespace, resource_data, update_operation
        )

    async def delete_secret(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除 Secret"""
        
        # 定义实际的删除操作
        async def delete_operation():
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "delete", "secret", name, namespace, None, delete_operation
        )

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
                    "imagePullPolicy": c.image_pull_policy,
                    "command": c.command,
                    "args": c.args,
                    "env": [
                        {
                            "name": env.name,
                            "value": env.value,
                            "valueFrom": {
                                "secretKeyRef": {
                                    "name": env.value_from.secret_key_ref.name,
                                    "key": env.value_from.secret_key_ref.key
                                } if env.value_from and env.value_from.secret_key_ref else None,
                                "configMapKeyRef": {
                                    "name": env.value_from.config_map_key_ref.name,
                                    "key": env.value_from.config_map_key_ref.key
                                } if env.value_from and env.value_from.config_map_key_ref else None
                            } if env.value_from else None
                        }
                        for env in (c.env or [])
                    ],
                    "resources": {
                        "requests": {
                            "memory": c.resources.requests.get("memory") if c.resources and c.resources.requests else None,
                            "cpu": c.resources.requests.get("cpu") if c.resources and c.resources.requests else None
                        } if c.resources and c.resources.requests else {},
                        "limits": {
                            "memory": c.resources.limits.get("memory") if c.resources and c.resources.limits else None,
                            "cpu": c.resources.limits.get("cpu") if c.resources and c.resources.limits else None
                        } if c.resources and c.resources.limits else {}
                    } if c.resources else {}
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
                "metadata": {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                    "labels": response.metadata.labels or {},
                    "annotations": response.metadata.annotations or {},
                    "created": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None
                },
                "spec": {
                "completions": response.spec.completions,
                "parallelism": response.spec.parallelism,
                    "backoffLimit": response.spec.backoff_limit,
                    "template": {
                        "metadata": {
                            "labels": pod_template.metadata.labels or {}
                        } if pod_template.metadata else {},
                        "spec": {
                            "containers": containers,
                            "restartPolicy": pod_spec.restart_policy
                        }
                    }
                },
                "status": {
                "active": response.status.active or 0,
                "succeeded": response.status.succeeded or 0,
                "failed": response.status.failed or 0,
                "completion_time": to_local_time_str(response.status.completion_time, 8) if response.status.completion_time else None,
                    "start_time": to_local_time_str(response.status.start_time, 8) if response.status.start_time else None
                }
            }
        
        except ApiException as e:
            raise Exception(f"获取 Job 失败: {e}")

    async def create_job(self, name: str = None, image: str = None, namespace: str = "default",
                   command: list = None, args: list = None, labels: dict = None,
                   env_vars: dict = None, resources: dict = None,
                   restart_policy: str = "Never", backoff_limit: int = 6, resource: Dict = None, **kwargs) -> Dict[str, Any]:
        """创建 Job"""
        
        # 准备资源数据用于验证
        resource_name = resource.get("metadata", {}).get("name") if resource else name
        resource_data = self._build_resource_data_for_validation(
            "job", name, namespace, resource,
            image=image, command=command, args=args, restart_policy=restart_policy, backoff_limit=backoff_limit
        )
        
        # 定义实际的创建操作
        async def create_operation():
            # 批量操作模式，传入完整的资源定义
            if resource:
                response = self.batch_v1_api.create_namespaced_job(
                    namespace=namespace,
                    body=resource
                )
                
                return {
                    "name": response.metadata.name,
                    "namespace": response.metadata.namespace,
                    "uid": response.metadata.uid,
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None
                }
            
            # 单体操作模式，使用简化参数创建
            if not name or not image:
                raise ValueError("name和image参数是必需的")
            
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "job", resource_name, namespace, resource_data, create_operation
        )

    async def update_job(self, name: str, namespace: str = "default",
                        labels: dict = None, annotations: dict = None, 
                        resource: Dict = None) -> Dict[str, Any]:
        """更新 Job（Job的spec字段大多不可变，仅支持labels和annotations）"""
        
        # 准备资源数据用于验证
        resource_data = self._build_resource_data_for_validation(
            "job", name, namespace, resource,
            labels=labels, annotations=annotations
        )
        
        # 定义实际的更新操作
        async def update_operation():
            if resource is not None:
                # 批量操作模式，传入完整的资源定义
                # 确保metadata中包含name和namespace
                if 'metadata' not in resource:
                    resource['metadata'] = {}
                resource['metadata']['name'] = name
                resource['metadata']['namespace'] = namespace
                
                response = self.batch_v1_api.patch_namespaced_job(
                    name=name,
                    namespace=namespace,
                    body=resource
                )
            else:
                # 单体操作模式，使用简化参数更新
                # 获取当前Job
                current_job = self.batch_v1_api.read_namespaced_job(name=name, namespace=namespace)
                
                # 更新metadata
                if labels:
                    if not current_job.metadata.labels:
                        current_job.metadata.labels = {}
                    current_job.metadata.labels.update(labels)
                    
                if annotations:
                    if not current_job.metadata.annotations:
                        current_job.metadata.annotations = {}
                    current_job.metadata.annotations.update(annotations)
                
                # 执行更新
                response = self.batch_v1_api.patch_namespaced_job(
                    name=name,
                    namespace=namespace,
                    body=current_job
                )
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "labels": dict(response.metadata.labels or {}),
                "annotations": dict(response.metadata.annotations or {}),
                "creation_timestamp": response.metadata.creation_timestamp.strftime("%Y-%m-%d %H:%M:%S") if response.metadata.creation_timestamp else None
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "update", "job", name, namespace, resource_data, update_operation
        )

    async def delete_job(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除 Job"""
        
        # 定义实际的删除操作
        async def delete_operation():
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "delete", "job", name, namespace, None, delete_operation
        )

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
                    "imagePullPolicy": c.image_pull_policy,
                    "command": c.command,
                    "args": c.args,
                    "env": [
                        {
                            "name": env.name,
                            "value": env.value,
                            "valueFrom": {
                                "secretKeyRef": {
                                    "name": env.value_from.secret_key_ref.name,
                                    "key": env.value_from.secret_key_ref.key
                                } if env.value_from and env.value_from.secret_key_ref else None,
                                "configMapKeyRef": {
                                    "name": env.value_from.config_map_key_ref.name,
                                    "key": env.value_from.config_map_key_ref.key
                                } if env.value_from and env.value_from.config_map_key_ref else None
                            } if env.value_from else None
                        }
                        for env in (c.env or [])
                    ],
                    "resources": {
                        "requests": {
                            "memory": c.resources.requests.get("memory") if c.resources and c.resources.requests else None,
                            "cpu": c.resources.requests.get("cpu") if c.resources and c.resources.requests else None
                        } if c.resources and c.resources.requests else {},
                        "limits": {
                            "memory": c.resources.limits.get("memory") if c.resources and c.resources.limits else None,
                            "cpu": c.resources.limits.get("cpu") if c.resources and c.resources.limits else None
                        } if c.resources and c.resources.limits else {}
                    } if c.resources else {}
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
                "metadata": {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                    "labels": response.metadata.labels or {},
                    "annotations": response.metadata.annotations or {},
                    "created": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None
                },
                "spec": {
                "schedule": response.spec.schedule,
                "suspend": response.spec.suspend or False,
                    "concurrencyPolicy": response.spec.concurrency_policy,
                    "startingDeadlineSeconds": response.spec.starting_deadline_seconds,
                    "jobTemplate": {
                        "spec": {
                            "template": {
                                "metadata": {
                                    "labels": pod_template.metadata.labels or {}
                                } if pod_template.metadata else {},
                                "spec": {
                "containers": containers,
                                    "restartPolicy": pod_spec.restart_policy
                                }
                            }
                        }
                    }
                },
                "status": {
                    "active_jobs": len(response.status.active) if response.status.active else 0,
                    "last_schedule_time": to_local_time_str(response.status.last_schedule_time, 8) if response.status.last_schedule_time else None
                }
            }

        except ApiException as e:
            raise Exception(f"获取 CronJob 失败: {e}")

    async def create_cronjob(self, name: str = None, image: str = None, schedule: str = None,
                       namespace: str = "default", command: list = None,
                       args: list = None, labels: dict = None,
                       env_vars: dict = None, resources: dict = None,
                       restart_policy: str = "Never", suspend: bool = False, resource: Dict = None, **kwargs) -> Dict[str, Any]:
        """创建 CronJob"""
        
        # 准备资源数据用于验证
        resource_name = resource.get("metadata", {}).get("name") if resource else name
        resource_data = self._build_resource_data_for_validation(
            "cronjob", name, namespace, resource,
            image=image, schedule=schedule, command=command, args=args, 
            restart_policy=restart_policy, suspend=suspend
        )
        
        # 定义实际的创建操作
        async def create_operation():
            # 批量操作模式，传入完整的资源定义
            if resource:
                try:
                    response = self.batch_v1_api.create_namespaced_cron_job(
                        namespace=namespace,
                        body=resource
                    )
                except:
                    # 回退到 batch/v1beta1 API
                    resource_copy = resource.copy()
                    resource_copy["apiVersion"] = "batch/v1beta1"
                    response = self.batch_v1beta1_api.create_namespaced_cron_job(
                        namespace=namespace,
                        body=resource_copy
                    )
                
                return {
                    "name": response.metadata.name,
                    "namespace": response.metadata.namespace,
                    "uid": response.metadata.uid,
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                    "schedule": response.spec.schedule
                }
            
            # 单体操作模式，使用简化参数创建
            if not name or not image or not schedule:
                raise ValueError("name、image和schedule参数是必需的")
            
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "cronjob", resource_name, namespace, resource_data, create_operation
        )

    async def update_cronjob(self, name: str, namespace: str = "default",
                       schedule: str = None, suspend: bool = None,
                       image: str = None, labels: dict = None, resource: Dict = None) -> Dict[str, Any]:
        """更新 CronJob"""
        
        # 准备资源数据用于验证
        resource_data = self._build_resource_data_for_validation(
            "cronjob", name, namespace, resource,
            schedule=schedule, suspend=suspend, image=image
        )
        
        # 定义实际的更新操作
        async def update_operation():
            if resource is not None:
                # 批量操作模式，传入完整的资源定义
                body = resource
                # 确保metadata中有正确的name和namespace
                if 'metadata' not in body:
                    body['metadata'] = {}
                body['metadata']['name'] = name
                body['metadata']['namespace'] = namespace
                
                # 尝试使用batch/v1 API
                try:
                    response = self.batch_v1_api.patch_namespaced_cron_job(
                        name=name,
                        namespace=namespace,
                        body=body
                    )
                except:
                    # 如果失败，尝试使用batch/v1beta1 API
                    response = self.batch_v1beta1_api.patch_namespaced_cron_job(
                        name=name,
                        namespace=namespace,
                        body=body
                    )
            else:
                # 单体操作模式，使用简化参数更新
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "update", "cronjob", name, namespace, resource_data, update_operation
        )

    async def delete_cronjob(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除 CronJob"""
        
        # 定义实际的删除操作
        async def delete_operation():
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "delete", "cronjob", name, namespace, None, delete_operation
        ) 

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
                "metadata": {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "labels": response.metadata.labels or {},
                "annotations": response.metadata.annotations or {},
                    "created": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None
                },
                "spec": {
                    "ingressClassName": response.spec.ingress_class_name,
                "rules": [
                    {
                        "host": rule.host,
                            "http": {
                        "paths": [
                            {
                                "path": path.path,
                                        "pathType": path.path_type,
                                        "backend": {
                                            "service": {
                                                "name": path.backend.service.name,
                                                "port": {"number": path.backend.service.port.number}
                                            }
                                        }
                            }
                            for path in (rule.http.paths or [])
                                ]
                            } if rule.http else {}
                    }
                    for rule in (response.spec.rules or [])
                ],
                "tls": [
                    {
                            "secretName": tls.secret_name,
                        "hosts": tls.hosts or []
                    }
                    for tls in (response.spec.tls or [])
                    ]
                },
                "status": {
                    "loadBalancer": {
                    "ingress": [
                        {
                            "ip": lb.ip,
                            "hostname": lb.hostname
                        }
                        for lb in (response.status.load_balancer.ingress or [])
                    ] if response.status.load_balancer else []
                    }
                }
            }
            
        except ApiException as e:
            raise Exception(f"获取 Ingress 失败: {e}")

    async def create_ingress(self, name: str = None, rules: list = None, namespace: str = "default",
                       annotations: dict = None, tls: list = None,
                       ingress_class_name: str = None, labels: dict = None, resource: Dict = None, **kwargs) -> Dict[str, Any]:
        """创建 Ingress"""
        
        # 准备资源数据用于验证
        resource_name = resource.get("metadata", {}).get("name") if resource else name
        resource_data = self._build_resource_data_for_validation(
            "ingress", name, namespace, resource,
            rules=rules, tls=tls, ingress_class_name=ingress_class_name
        )
        
        # 定义实际的创建操作
        async def create_operation():
            # 批量操作模式，传入完整的资源定义
            if resource:
                response = self.networking_v1_api.create_namespaced_ingress(
                    namespace=namespace,
                    body=resource
                )
                
                return {
                    "name": response.metadata.name,
                    "namespace": response.metadata.namespace,
                    "uid": response.metadata.uid,
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                    "class_name": response.spec.ingress_class_name
                }
            
            # 单体操作模式，使用简化参数创建
            if not name or not rules:
                raise ValueError("name和rules参数是必需的")
            
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "ingress", resource_name, namespace, resource_data, create_operation
        )

    async def update_ingress(self, name: str, namespace: str = "default",
                       rules: list = None, annotations: dict = None,
                       tls: list = None, ingress_class_name: str = None,
                       labels: dict = None, resource: Dict = None) -> Dict[str, Any]:
        """更新 Ingress"""
        
        # 准备资源数据用于验证
        resource_data = self._build_resource_data_for_validation(
            "ingress", name, namespace, resource,
            rules=rules, tls=tls, ingress_class_name=ingress_class_name
        )
        
        # 定义实际的更新操作
        async def update_operation():
            if resource is not None:
                # 批量操作模式，传入完整的资源定义
                body = resource
                # 确保metadata中有正确的name和namespace
                if 'metadata' not in body:
                    body['metadata'] = {}
                body['metadata']['name'] = name
                body['metadata']['namespace'] = namespace
                
                response = self.networking_v1_api.patch_namespaced_ingress(
                    name=name,
                    namespace=namespace,
                    body=body
                )
            else:
                # 单体操作模式，使用简化参数更新
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "update", "ingress", name, namespace, resource_data, update_operation
        )

    async def delete_ingress(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除 Ingress"""
        
        # 定义实际的删除操作
        async def delete_operation():
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "delete", "ingress", name, namespace, None, delete_operation
        )

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

    async def create_storageclass(self, name: str = None, provisioner: str = None,
                            reclaim_policy: str = "Delete",
                            volume_binding_mode: str = "Immediate",
                            allow_volume_expansion: bool = False,
                            parameters: dict = None,
                            labels: dict = None,
                            annotations: dict = None, resource: Dict = None, **kwargs) -> Dict[str, Any]:
        """创建 StorageClass"""
        try:
            # 批量操作模式，传入完整的资源定义
            if resource:
                response = self.storage_v1_api.create_storage_class(body=resource)
                
                return {
                    "name": response.metadata.name,
                    "uid": response.metadata.uid,
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                    "provisioner": response.provisioner,
                    "reclaim_policy": response.reclaim_policy,
                    "volume_binding_mode": response.volume_binding_mode
                }
            
            # 单体操作模式，使用简化参数创建
            if not name or not provisioner:
                raise ValueError("name和provisioner参数是必需的")
            
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
                            annotations: dict = None, resource: Dict = None) -> Dict[str, Any]:
        """更新 StorageClass"""
        try:
            if resource is not None:
                # 批量操作模式，传入完整的资源定义
                body = resource
                # 确保metadata中有正确的name
                if 'metadata' not in body:
                    body['metadata'] = {}
                body['metadata']['name'] = name
                
                response = self.storage_v1_api.patch_storage_class(
                    name=name,
                    body=body
                )
            else:
                # 单体操作模式，使用简化参数更新
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

    async def create_persistentvolume(self, name: str = None, capacity: str = None,
                                access_modes: list = None,
                                reclaim_policy: str = "Retain",
                                storage_class_name: str = None,
                                volume_mode: str = "Filesystem",
                                host_path: str = None,
                                nfs: dict = None,
                                labels: dict = None,
                                annotations: dict = None,
                                csi: dict = None, resource: Dict = None, **kwargs) -> Dict[str, Any]:
        """创建 PersistentVolume"""
        try:
            # 批量操作模式，传入完整的资源定义
            if resource:
                response = self.v1_api.create_persistent_volume(body=resource)
                
                return {
                    "name": response.metadata.name,
                    "uid": response.metadata.uid,
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None,
                    "capacity": response.spec.capacity,
                    "access_modes": response.spec.access_modes,
                    "reclaim_policy": response.spec.persistent_volume_reclaim_policy,
                    "storage_class_name": response.spec.storage_class_name
                }
            
            # 单体操作模式，使用简化参数创建
            if not name or not capacity or not access_modes:
                raise ValueError("name、capacity和access_modes参数是必需的")
            
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
                                annotations: dict = None, resource: Dict = None) -> Dict[str, Any]:
        """更新 PersistentVolume"""
        try:
            if resource is not None:
                # 批量操作模式，传入完整的资源定义
                body = resource
                # 确保metadata中有正确的name
                if 'metadata' not in body:
                    body['metadata'] = {}
                body['metadata']['name'] = name
                
                response = self.v1_api.patch_persistent_volume(
                    name=name,
                    body=body
                )
            else:
                # 单体操作模式，使用简化参数更新
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
                "metadata": {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "labels": response.metadata.labels or {},
                "annotations": response.metadata.annotations or {},
                    "created": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None
                },
                "spec": {
                    "accessModes": response.spec.access_modes or [],
                    "resources": {
                        "requests": response.spec.resources.requests or {} if response.spec.resources else {}
                    } if response.spec.resources else {"requests": {}},
                    "storageClassName": response.spec.storage_class_name,
                    "volumeMode": response.spec.volume_mode,
                    "volumeName": response.spec.volume_name
                },
                "status": {
                    "phase": response.status.phase,
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
            }
            
        except ApiException as e:
            raise Exception(f"获取 PersistentVolumeClaim 失败: {e}")

    async def create_persistentvolumeclaim(self, name: str = None, size: str = None,
                                     namespace: str = "default",
                                     access_modes: list = None,
                                     storage_class_name: str = None,
                                     volume_mode: str = "Filesystem",
                                     volume_name: str = None,
                                     labels: dict = None,
                                     annotations: dict = None, resource: Dict = None, **kwargs) -> Dict[str, Any]:
        """创建 PersistentVolumeClaim"""
        
        # 准备资源数据用于验证
        resource_name = resource.get("metadata", {}).get("name") if resource else name
        resource_data = self._build_resource_data_for_validation(
            "persistentvolumeclaim", name, namespace, resource,
            size=size, access_modes=access_modes, storage_class_name=storage_class_name
        )
        
        # 定义实际的创建操作
        async def create_operation():
            # 批量操作模式，传入完整的资源定义
            if resource:
                response = self.v1_api.create_namespaced_persistent_volume_claim(
                    namespace=namespace,
                    body=resource
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
            
            # 单体操作模式，使用简化参数创建
            if not name or not size:
                raise ValueError("name和size参数是必需的")
            
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "persistentvolumeclaim", resource_name, namespace, resource_data, create_operation
        )

    async def update_persistentvolumeclaim(self, name: str, namespace: str = "default",
                                     size: str = None,
                                     access_modes: list = None,
                                     storage_class_name: str = None,
                                     labels: dict = None,
                                     annotations: dict = None, resource: Dict = None) -> Dict[str, Any]:
        """更新 PersistentVolumeClaim"""
        
        # 准备资源数据用于验证
        resource_data = self._build_resource_data_for_validation(
            "persistentvolumeclaim", name, namespace, resource,
            size=size, access_modes=access_modes, storage_class_name=storage_class_name
        )
        
        # 定义实际的更新操作
        async def update_operation():
            if resource is not None:
                # 批量操作模式，传入完整的资源定义
                body = resource
                # 确保metadata中有正确的name和namespace
                if 'metadata' not in body:
                    body['metadata'] = {}
                body['metadata']['name'] = name
                body['metadata']['namespace'] = namespace
                
                response = self.v1_api.patch_namespaced_persistent_volume_claim(
                    name=name,
                    namespace=namespace,
                    body=body
                )
            else:
                # 单体操作模式，使用简化参数更新
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "update", "persistentvolumeclaim", name, namespace, resource_data, update_operation
        )

    async def delete_persistentvolumeclaim(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除 PersistentVolumeClaim"""
        
        # 定义实际的删除操作
        async def delete_operation():
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
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "delete", "persistentvolumeclaim", name, namespace, None, delete_operation
        ) 

    # ==================== ServiceAccount 相关方法 ====================

    async def list_serviceaccounts(self, namespace: str = "default") -> List[Dict[str, Any]]:
        """列出ServiceAccount"""
        try:
            response = self.v1_api.list_namespaced_service_account(namespace=namespace)
            
            serviceaccounts = []
            for item in response.items:
                serviceaccount_info = {
                    "name": item.metadata.name,
                    "namespace": item.metadata.namespace,
                    "uid": item.metadata.uid,
                    "creation_timestamp": to_local_time_str(item.metadata.creation_timestamp),
                    "labels": item.metadata.labels or {},
                    "annotations": item.metadata.annotations or {},
                    "secrets": [secret.name for secret in (item.secrets or [])],
                    "image_pull_secrets": [secret.name for secret in (item.image_pull_secrets or [])],
                    "automount_service_account_token": item.automount_service_account_token
                }
                serviceaccounts.append(serviceaccount_info)
            
            return serviceaccounts
            
        except ApiException as e:
            raise Exception(f"获取ServiceAccount列表失败: {e.reason}")

    async def get_serviceaccount(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """获取ServiceAccount详情"""
        try:
            response = self.v1_api.read_namespaced_service_account(name=name, namespace=namespace)
            
            return {
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "uid": response.metadata.uid,
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp),
                "labels": response.metadata.labels or {},
                "annotations": response.metadata.annotations or {},
                "secrets": [secret.name for secret in (response.secrets or [])],
                "image_pull_secrets": [secret.name for secret in (response.image_pull_secrets or [])],
                "automount_service_account_token": response.automount_service_account_token
            }
            
        except ApiException as e:
            if e.status == 404:
                raise Exception(f"ServiceAccount {name} 在命名空间 {namespace} 中不存在")
            raise Exception(f"获取ServiceAccount失败: {e.reason}")

    async def create_serviceaccount(self, name: str = None, namespace: str = "default", 
                                  labels: Dict[str, str] = None,
                                  annotations: Dict[str, str] = None,
                                  secrets: List[str] = None,
                                  image_pull_secrets: List[str] = None,
                                  automount_service_account_token: bool = None, resource: Dict = None, **kwargs) -> Dict[str, Any]:
        """创建ServiceAccount"""
        
        # 准备资源数据用于验证
        resource_name = resource.get("metadata", {}).get("name") if resource else name
        resource_data = self._build_resource_data_for_validation(
            "serviceaccount", name, namespace, resource,
            automount_service_account_token=automount_service_account_token
        )
        
        # 定义实际的创建操作
        async def create_operation():
            # 批量操作模式，传入完整的资源定义
            if resource:
                response = self.v1_api.create_namespaced_service_account(namespace=namespace, body=resource)
                
                return {
                    "success": True,
                    "message": f"ServiceAccount {resource.get('metadata', {}).get('name', 'unknown')} 创建成功",
                    "serviceaccount": {
                        "name": response.metadata.name,
                        "namespace": response.metadata.namespace,
                        "uid": response.metadata.uid,
                        "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp)
                    }
                }
            
            # 单体操作模式，使用简化参数创建
            if not name:
                raise ValueError("name参数是必需的")
            
            # 构建ServiceAccount对象
            body = client.V1ServiceAccount(
                metadata=client.V1ObjectMeta(
                    name=name,
                    namespace=namespace,
                    labels=labels,
                    annotations=annotations
                )
            )
            
            # 设置secrets
            if secrets:
                body.secrets = [client.V1ObjectReference(name=secret_name) for secret_name in secrets]
            
            # 设置image_pull_secrets
            if image_pull_secrets:
                body.image_pull_secrets = [client.V1LocalObjectReference(name=secret_name) for secret_name in image_pull_secrets]
            
            # 设置automount_service_account_token
            if automount_service_account_token is not None:
                body.automount_service_account_token = automount_service_account_token
            
            response = self.v1_api.create_namespaced_service_account(namespace=namespace, body=body)
            
            return {
                "success": True,
                "message": f"ServiceAccount {name} 创建成功",
                "serviceaccount": {
                    "name": response.metadata.name,
                    "namespace": response.metadata.namespace,
                    "uid": response.metadata.uid,
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp)
                }
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "serviceaccount", resource_name, namespace, resource_data, create_operation
        )

    async def update_serviceaccount(self, name: str, namespace: str = "default",
                                  labels: Dict[str, str] = None,
                                  annotations: Dict[str, str] = None,
                                  secrets: List[str] = None,
                                  image_pull_secrets: List[str] = None,
                                  automount_service_account_token: bool = None, resource: Dict = None) -> Dict[str, Any]:
        """更新ServiceAccount"""
        
        # 准备资源数据用于验证
        resource_data = self._build_resource_data_for_validation(
            "serviceaccount", name, namespace, resource,
            automount_service_account_token=automount_service_account_token
        )
        
        # 定义实际的更新操作
        async def update_operation():
            if resource is not None:
                # 批量操作模式，传入完整的资源定义
                body = resource
                # 确保metadata中有正确的name和namespace
                if 'metadata' not in body:
                    body['metadata'] = {}
                body['metadata']['name'] = name
                body['metadata']['namespace'] = namespace
                
                response = self.v1_api.patch_namespaced_service_account(
                    name=name,
                    namespace=namespace,
                    body=body
                )
            else:
                # 单体操作模式，使用简化参数更新
                # 获取现有的ServiceAccount
                current = self.v1_api.read_namespaced_service_account(name=name, namespace=namespace)
                
                # 更新metadata
                if labels is not None:
                    if current.metadata.labels is None:
                        current.metadata.labels = {}
                    current.metadata.labels.update(labels)
                if annotations is not None:
                    if current.metadata.annotations is None:
                        current.metadata.annotations = {}
                    current.metadata.annotations.update(annotations)
                
                # 更新secrets
                if secrets is not None:
                    current.secrets = [client.V1ObjectReference(name=secret_name) for secret_name in secrets]
                
                # 更新image_pull_secrets
                if image_pull_secrets is not None:
                    current.image_pull_secrets = [client.V1LocalObjectReference(name=secret_name) for secret_name in image_pull_secrets]
                
                # 更新automount_service_account_token
                if automount_service_account_token is not None:
                    current.automount_service_account_token = automount_service_account_token
                
                response = self.v1_api.replace_namespaced_service_account(
                    name=name,
                    namespace=namespace,
                    body=current
                )
            
            return {
                "success": True,
                "message": f"ServiceAccount {name} 更新成功",
                "serviceaccount": {
                    "name": response.metadata.name,
                    "namespace": response.metadata.namespace,
                    "uid": response.metadata.uid
                }
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "update", "serviceaccount", name, namespace, resource_data, update_operation
        )

    async def delete_serviceaccount(self, name: str, namespace: str = "default",
                                  grace_period_seconds: int = None) -> Dict[str, Any]:
        """删除ServiceAccount"""
        
        # 定义实际的删除操作
        async def delete_operation():
            delete_options = client.V1DeleteOptions()
            if grace_period_seconds is not None:
                delete_options.grace_period_seconds = grace_period_seconds
            
            self.v1_api.delete_namespaced_service_account(
                name=name,
                namespace=namespace,
                body=delete_options
            )
            
            return {
                "success": True,
                "message": f"ServiceAccount {name} 删除成功"
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "delete", "serviceaccount", name, namespace, None, delete_operation
        )

    # ========================== RBAC 服务层方法 ==========================

    async def list_roles(self, namespace: str = "default", label_selector: str = None) -> List[Dict[str, Any]]:
        """列出Role"""
        try:
            roles = self.rbac_v1_api.list_namespaced_role(
                namespace=namespace,
                label_selector=label_selector
            )
            
            result = []
            for role in roles.items:
                role_dict = {
                    "name": role.metadata.name,
                    "namespace": role.metadata.namespace,
                    "rules": [],
                    "labels": role.metadata.labels,
                    "annotations": role.metadata.annotations,
                    "creation_timestamp": to_local_time_str(role.metadata.creation_timestamp),
                    "uid": role.metadata.uid
                }
                
                # 转换规则
                for rule in role.rules:
                    rule_dict = {
                        "api_groups": rule.api_groups,
                        "resources": rule.resources,
                        "verbs": rule.verbs,
                        "resource_names": rule.resource_names,
                        "non_resource_urls": getattr(rule, 'non_resource_urls', [])
                    }
                    role_dict["rules"].append(rule_dict)
                
                result.append(role_dict)
            
            return result
        except ApiException as e:
            raise Exception(f"获取Role列表失败: {e.reason}")

    async def get_role(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """获取Role详情"""
        try:
            role = self.rbac_v1_api.read_namespaced_role(name=name, namespace=namespace)
            
            role_dict = {
                "name": role.metadata.name,
                "namespace": role.metadata.namespace,
                "rules": [],
                "labels": role.metadata.labels,
                "annotations": role.metadata.annotations,
                "creation_timestamp": to_local_time_str(role.metadata.creation_timestamp),
                "uid": role.metadata.uid
            }
            
            # 转换规则
            for rule in role.rules:
                rule_dict = {
                    "api_groups": rule.api_groups or [],
                    "resources": rule.resources or [],
                    "verbs": rule.verbs or []
                }
                # 只有当这些字段有值时才添加
                if rule.resource_names:
                    rule_dict["resource_names"] = rule.resource_names
                if getattr(rule, 'non_resource_urls', None):
                    rule_dict["non_resource_urls"] = rule.non_resource_urls
                role_dict["rules"].append(rule_dict)
            
            return role_dict
        except ApiException as e:
            raise Exception(f"获取Role详情失败: {e.reason}")

    async def create_role(self, name: str = None, namespace: str = "default", rules: list = None,
                         labels: dict = None, annotations: dict = None, resource: Dict = None, **kwargs) -> Dict[str, Any]:
        """创建Role"""
        
        # 准备资源数据用于验证
        resource_name = resource.get("metadata", {}).get("name") if resource else name
        resource_data = self._build_resource_data_for_validation(
            "role", name, namespace, resource,
            rules=rules
        )
        
        # 定义实际的创建操作
        async def create_operation():
            # 批量操作模式，传入完整的资源定义
            if resource:
                created_role = self.rbac_v1_api.create_namespaced_role(
                    namespace=namespace,
                    body=resource
                )
                
                return {
                    "success": True,
                    "name": created_role.metadata.name,
                    "namespace": created_role.metadata.namespace,
                    "message": f"Role {created_role.metadata.name} 创建成功"
                }
            
            # 单体操作模式，使用简化参数创建
            if not name:
                raise ValueError("name参数是必需的")
            
            # 转换规则
            role_rules = []
            if rules:
                for rule in rules:
                    role_rule = client.V1PolicyRule(
                        api_groups=rule.get("api_groups", []),
                        resources=rule.get("resources", []),
                        verbs=rule.get("verbs", []),
                        resource_names=rule.get("resource_names", []),
                    )
                    role_rules.append(role_rule)
            
            role = client.V1Role(
                metadata=client.V1ObjectMeta(
                    name=name,
                    namespace=namespace,
                    labels=labels,
                    annotations=annotations
                ),
                rules=role_rules
            )
            
            created_role = self.rbac_v1_api.create_namespaced_role(
                namespace=namespace,
                body=role
            )
            
            return {
                "success": True,
                "name": created_role.metadata.name,
                "namespace": created_role.metadata.namespace,
                "message": f"Role {name} 创建成功"
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "role", resource_name, namespace, resource_data, create_operation
        )

    async def update_role(self, name: str, namespace: str = "default", rules: list = None,
                         labels: dict = None, annotations: dict = None, resource: Dict = None) -> Dict[str, Any]:
        """更新Role"""
        
        # 准备资源数据用于验证
        resource_data = self._build_resource_data_for_validation(
            "role", name, namespace, resource,
            rules=rules
        )
        
        # 定义实际的更新操作
        async def update_operation():
            if resource is not None:
                # 批量操作模式，传入完整的资源定义
                body = resource
                # 确保metadata中有正确的name和namespace
                if 'metadata' not in body:
                    body['metadata'] = {}
                body['metadata']['name'] = name
                body['metadata']['namespace'] = namespace
                
                response = self.rbac_v1_api.patch_namespaced_role(
                    name=name,
                    namespace=namespace,
                    body=body
                )
            else:
                # 单体操作模式，使用简化参数更新
                # 获取现有Role
                existing_role = self.rbac_v1_api.read_namespaced_role(name=name, namespace=namespace)
                
                # 更新规则
                if rules is not None:
                    role_rules = []
                    for rule in rules:
                        role_rule = client.V1PolicyRule(
                            api_groups=rule.get("api_groups", []),
                            resources=rule.get("resources", []),
                            verbs=rule.get("verbs", []),
                            resource_names=rule.get("resource_names", []),
                        )
                        role_rules.append(role_rule)
                    existing_role.rules = role_rules
                
                # 更新标签和注解
                if labels is not None:
                    existing_role.metadata.labels = labels
                if annotations is not None:
                    existing_role.metadata.annotations = annotations
                
                response = self.rbac_v1_api.replace_namespaced_role(
                    name=name,
                    namespace=namespace,
                    body=existing_role
            )
            
            return {
                "success": True,
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "message": f"Role {name} 更新成功"
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "update", "role", name, namespace, resource_data, update_operation
        )

    async def delete_role(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除Role"""
        
        # 定义实际的删除操作
        async def delete_operation():
            self.rbac_v1_api.delete_namespaced_role(name=name, namespace=namespace)
            
            return {
                "success": True,
                "message": f"Role {name} 删除成功"
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "delete", "role", name, namespace, None, delete_operation
        )

    async def list_cluster_roles(self, label_selector: str = None) -> List[Dict[str, Any]]:
        """列出ClusterRole"""
        try:
            cluster_roles = self.rbac_v1_api.list_cluster_role(label_selector=label_selector)
            
            result = []
            for role in cluster_roles.items:
                role_dict = {
                    "name": role.metadata.name,
                    "rules": [],
                    "labels": role.metadata.labels,
                    "annotations": role.metadata.annotations,
                    "creation_timestamp": to_local_time_str(role.metadata.creation_timestamp),
                    "uid": role.metadata.uid
                }
                
                # 转换规则
                for rule in role.rules:
                    rule_dict = {
                        "api_groups": rule.api_groups,
                        "resources": rule.resources,
                        "verbs": rule.verbs,
                        "resource_names": rule.resource_names,
                        "non_resource_urls": getattr(rule, 'non_resource_urls', [])
                    }
                    role_dict["rules"].append(rule_dict)
                
                result.append(role_dict)
            
            return result
        except ApiException as e:
            raise Exception(f"获取ClusterRole列表失败: {e.reason}")

    async def get_cluster_role(self, name: str) -> Dict[str, Any]:
        """获取ClusterRole详情"""
        try:
            role = self.rbac_v1_api.read_cluster_role(name=name)
            
            role_dict = {
                "name": role.metadata.name,
                "rules": [],
                "labels": role.metadata.labels,
                "annotations": role.metadata.annotations,
                "creation_timestamp": to_local_time_str(role.metadata.creation_timestamp),
                "uid": role.metadata.uid
            }
            
            # 转换规则
            for rule in role.rules:
                rule_dict = {
                    "api_groups": rule.api_groups,
                    "resources": rule.resources,
                    "verbs": rule.verbs,
                    "resource_names": rule.resource_names,
                    "non_resource_urls": getattr(rule, 'non_resource_urls', [])
                }
                role_dict["rules"].append(rule_dict)
            
            return role_dict
        except ApiException as e:
            raise Exception(f"获取ClusterRole详情失败: {e.reason}")

    async def create_cluster_role(self, name: str = None, rules: list = None,
                                labels: dict = None, annotations: dict = None, resource: Dict = None, **kwargs) -> Dict[str, Any]:
        """创建ClusterRole"""
        
        # 准备资源数据用于验证
        resource_name = resource.get("metadata", {}).get("name") if resource else name
        resource_data = self._build_resource_data_for_validation(
            "clusterrole", name, None, resource,  # ClusterRole 没有 namespace
            rules=rules
        )
        
        # 定义实际的创建操作
        async def create_operation():
            # 批量操作模式，传入完整的资源定义
            if resource:
                created_role = self.rbac_v1_api.create_cluster_role(body=resource)
                
                return {
                    "success": True,
                    "name": created_role.metadata.name,
                    "message": f"ClusterRole {created_role.metadata.name} 创建成功"
                }
            
            # 单体操作模式，使用简化参数创建
            if not name:
                raise ValueError("name参数是必需的")
            
            # 转换规则
            role_rules = []
            if rules:
                for rule in rules:
                    role_rule = client.V1PolicyRule(
                        api_groups=rule.get("api_groups", []),
                        resources=rule.get("resources", []),
                        verbs=rule.get("verbs", []),
                        resource_names=rule.get("resource_names", []),
                    )
                    role_rules.append(role_rule)
            
            cluster_role = client.V1ClusterRole(
                metadata=client.V1ObjectMeta(
                    name=name,
                    labels=labels,
                    annotations=annotations
                ),
                rules=role_rules
            )
            
            created_role = self.rbac_v1_api.create_cluster_role(body=cluster_role)
            
            return {
                "success": True,
                "name": created_role.metadata.name,
                "message": f"ClusterRole {name} 创建成功"
            }
            
        # 使用统一的验证和执行方法 (ClusterRole 是集群级资源，没有 namespace)
        return await self._execute_with_validation_and_preview(
            "create", "clusterrole", resource_name, None, resource_data, create_operation
        )

    async def update_cluster_role(self, name: str, rules: list = None,
                                labels: dict = None, annotations: dict = None, resource: Dict = None) -> Dict[str, Any]:
        """更新ClusterRole"""
        
        # 准备资源数据用于验证
        resource_data = self._build_resource_data_for_validation(
            "clusterrole", name, None, resource,  # ClusterRole 没有 namespace
            rules=rules
        )
        
        # 定义实际的更新操作
        async def update_operation():
            if resource is not None:
                # 批量操作模式，传入完整的资源定义
                body = resource
                # 确保metadata中有正确的name
                if 'metadata' not in body:
                    body['metadata'] = {}
                body['metadata']['name'] = name
                
                response = self.rbac_v1_api.patch_cluster_role(
                    name=name,
                    body=body
                )
            else:
                # 单体操作模式，使用简化参数更新
                # 获取现有ClusterRole
                existing_role = self.rbac_v1_api.read_cluster_role(name=name)
                
                # 更新规则
                if rules is not None:
                    role_rules = []
                    for rule in rules:
                        role_rule = client.V1PolicyRule(
                            api_groups=rule.get("api_groups", []),
                            resources=rule.get("resources", []),
                            verbs=rule.get("verbs", []),
                            resource_names=rule.get("resource_names", []),
                        )
                        role_rules.append(role_rule)
                    existing_role.rules = role_rules
                
                # 更新标签和注解
                if labels is not None:
                    existing_role.metadata.labels = labels
                if annotations is not None:
                    existing_role.metadata.annotations = annotations
                
                response = self.rbac_v1_api.replace_cluster_role(
                    name=name,
                    body=existing_role
            )
            
            return {
                "success": True,
                "name": response.metadata.name,
                "message": f"ClusterRole {name} 更新成功"
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "update", "clusterrole", name, None, resource_data, update_operation
        )

    async def delete_cluster_role(self, name: str) -> Dict[str, Any]:
        """删除ClusterRole"""
        
        # 定义实际的删除操作
        async def delete_operation():
            self.rbac_v1_api.delete_cluster_role(name=name)
            
            return {
                "success": True,
                "message": f"ClusterRole {name} 删除成功"
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "delete", "clusterrole", name, None, None, delete_operation
        )

    async def list_role_bindings(self, namespace: str = "default", label_selector: str = None) -> List[Dict[str, Any]]:
        """列出RoleBinding"""
        try:
            role_bindings = self.rbac_v1_api.list_namespaced_role_binding(
                namespace=namespace,
                label_selector=label_selector
            )
            
            result = []
            for rb in role_bindings.items:
                rb_dict = {
                    "name": rb.metadata.name,
                    "namespace": rb.metadata.namespace,
                    "role_ref": {
                        "api_group": rb.role_ref.api_group,
                        "kind": rb.role_ref.kind,
                        "name": rb.role_ref.name
                    },
                    "subjects": [],
                    "labels": rb.metadata.labels,
                    "annotations": rb.metadata.annotations,
                    "creation_timestamp": to_local_time_str(rb.metadata.creation_timestamp),
                    "uid": rb.metadata.uid
                }
                
                # 转换subjects
                for subject in rb.subjects:
                    subject_dict = {
                        "kind": subject.kind,
                        "name": subject.name,
                        "api_group": subject.api_group,
                        "namespace": subject.namespace
                    }
                    rb_dict["subjects"].append(subject_dict)
                
                result.append(rb_dict)
            
            return result
        except ApiException as e:
            raise Exception(f"获取RoleBinding列表失败: {e.reason}")

    async def get_role_binding(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """获取RoleBinding详情"""
        try:
            rb = self.rbac_v1_api.read_namespaced_role_binding(name=name, namespace=namespace)
            
            rb_dict = {
                "name": rb.metadata.name,
                "namespace": rb.metadata.namespace,
                "role_ref": {
                    "api_group": rb.role_ref.api_group,
                    "kind": rb.role_ref.kind,
                    "name": rb.role_ref.name
                },
                "subjects": [],
                "labels": rb.metadata.labels,
                "annotations": rb.metadata.annotations,
                "creation_timestamp": to_local_time_str(rb.metadata.creation_timestamp),
                "uid": rb.metadata.uid
            }
            
            # 转换subjects
            for subject in rb.subjects:
                subject_dict = {
                    "kind": subject.kind,
                    "name": subject.name
                }
                # 只有当apiGroup不为空且不为None时才添加
                if subject.api_group:
                    subject_dict["api_group"] = subject.api_group
                # 只有当namespace不为空且不为None时才添加
                if subject.namespace:
                    subject_dict["namespace"] = subject.namespace
                rb_dict["subjects"].append(subject_dict)
            
            return rb_dict
        except ApiException as e:
            raise Exception(f"获取RoleBinding详情失败: {e.reason}")

    async def create_role_binding(self, name: str = None, namespace: str = "default", 
                                role_ref: dict = None, subjects: list = None,
                                labels: dict = None, annotations: dict = None, resource: Dict = None, **kwargs) -> Dict[str, Any]:
        """创建RoleBinding"""
        
        # 准备资源数据用于验证
        resource_name = resource.get("metadata", {}).get("name") if resource else name
        resource_data = self._build_resource_data_for_validation(
            "rolebinding", name, namespace, resource,
            role_ref=role_ref, subjects=subjects
        )
        
        # 定义实际的创建操作
        async def create_operation():
            # 批量操作模式，传入完整的资源定义
            if resource:
                created_rb = self.rbac_v1_api.create_namespaced_role_binding(
                    namespace=namespace,
                    body=resource
                )
                
                return {
                    "success": True,
                    "name": created_rb.metadata.name,
                    "namespace": created_rb.metadata.namespace,
                    "message": f"RoleBinding {created_rb.metadata.name} 创建成功"
                }
            
            # 单体操作模式，使用简化参数创建
            if not name:
                raise ValueError("name参数是必需的")
            
            # 转换role_ref
            role_ref_obj = None
            if role_ref:
                role_ref_obj = client.V1RoleRef(
                    api_group=role_ref.get("api_group", "rbac.authorization.k8s.io"),
                    kind=role_ref.get("kind", "Role"),
                    name=role_ref.get("name")
                )
            
            # 转换subjects
            subjects_list = []
            if subjects:
                for subject in subjects:
                    subject_obj = client.RbacV1Subject(
                        kind=subject.get("kind"),
                        name=subject.get("name"),
                        api_group=subject.get("api_group", "rbac.authorization.k8s.io"),
                        namespace=subject.get("namespace")
                    )
                    subjects_list.append(subject_obj)
            
            role_binding = client.V1RoleBinding(
                metadata=client.V1ObjectMeta(
                    name=name,
                    namespace=namespace,
                    labels=labels,
                    annotations=annotations
                ),
                role_ref=role_ref_obj,
                subjects=subjects_list
            )
            
            created_rb = self.rbac_v1_api.create_namespaced_role_binding(
                namespace=namespace,
                body=role_binding
            )
            
            return {
                "success": True,
                "name": created_rb.metadata.name,
                "namespace": created_rb.metadata.namespace,
                "message": f"RoleBinding {name} 创建成功"
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "rolebinding", resource_name, namespace, resource_data, create_operation
        )

    async def update_role_binding(self, name: str, namespace: str = "default",
                                role_ref: dict = None, subjects: list = None,
                                labels: dict = None, annotations: dict = None, resource: Dict = None) -> Dict[str, Any]:
        """更新RoleBinding"""
        
        # 准备资源数据用于验证
        resource_data = self._build_resource_data_for_validation(
            "rolebinding", name, namespace, resource,
            role_ref=role_ref, subjects=subjects
        )
        
        # 定义实际的更新操作
        async def update_operation():
            if resource is not None:
                # 批量操作模式，传入完整的资源定义
                body = resource
                # 确保metadata中有正确的name和namespace
                if 'metadata' not in body:
                    body['metadata'] = {}
                body['metadata']['name'] = name
                body['metadata']['namespace'] = namespace
                
                response = self.rbac_v1_api.patch_namespaced_role_binding(
                    name=name,
                    namespace=namespace,
                    body=body
                )
            else:
                # 单体操作模式，使用简化参数更新
                # 获取现有RoleBinding
                existing_rb = self.rbac_v1_api.read_namespaced_role_binding(name=name, namespace=namespace)
                
                # 更新role_ref
                if role_ref is not None:
                    role_ref_obj = client.V1RoleRef(
                        api_group=role_ref.get("api_group", "rbac.authorization.k8s.io"),
                        kind=role_ref.get("kind", "Role"),
                        name=role_ref.get("name")
                    )
                    existing_rb.role_ref = role_ref_obj
                
                # 更新subjects
                if subjects is not None:
                    subjects_list = []
                    for subject in subjects:
                        subject_obj = client.RbacV1Subject(
                            kind=subject.get("kind"),
                            name=subject.get("name"),
                            api_group=subject.get("api_group", "rbac.authorization.k8s.io"),
                            namespace=subject.get("namespace")
                        )
                        subjects_list.append(subject_obj)
                    existing_rb.subjects = subjects_list
                
                # 更新标签和注解
                if labels is not None:
                    existing_rb.metadata.labels = labels
                if annotations is not None:
                    existing_rb.metadata.annotations = annotations
                
                response = self.rbac_v1_api.replace_namespaced_role_binding(
                    name=name,
                    namespace=namespace,
                    body=existing_rb
            )
            
            return {
                "success": True,
                "name": response.metadata.name,
                "namespace": response.metadata.namespace,
                "message": f"RoleBinding {name} 更新成功"
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "update", "rolebinding", name, namespace, resource_data, update_operation
        )

    async def delete_role_binding(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除RoleBinding"""
        
        # 定义实际的删除操作
        async def delete_operation():
            self.rbac_v1_api.delete_namespaced_role_binding(name=name, namespace=namespace)
            
            return {
                "success": True,
                "message": f"RoleBinding {name} 删除成功"
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "delete", "rolebinding", name, namespace, None, delete_operation
        )

    async def list_cluster_role_bindings(self, label_selector: str = None) -> List[Dict[str, Any]]:
        """列出ClusterRoleBinding"""
        try:
            cluster_role_bindings = self.rbac_v1_api.list_cluster_role_binding(label_selector=label_selector)
            
            result = []
            for crb in cluster_role_bindings.items:
                crb_dict = {
                    "name": crb.metadata.name,
                    "role_ref": {
                        "api_group": crb.role_ref.api_group,
                        "kind": crb.role_ref.kind,
                        "name": crb.role_ref.name
                    },
                    "subjects": [],
                    "labels": crb.metadata.labels,
                    "annotations": crb.metadata.annotations,
                    "creation_timestamp": to_local_time_str(crb.metadata.creation_timestamp),
                    "uid": crb.metadata.uid
                }
                
                # 转换subjects
                if crb.subjects:
                    for subject in crb.subjects:
                        subject_dict = {
                            "kind": subject.kind,
                            "name": subject.name,
                            "api_group": subject.api_group,
                            "namespace": subject.namespace
                        }
                        crb_dict["subjects"].append(subject_dict)
                
                result.append(crb_dict)
            
            return result
        except ApiException as e:
            raise Exception(f"获取ClusterRoleBinding列表失败: {e.reason}")

    async def get_cluster_role_binding(self, name: str) -> Dict[str, Any]:
        """获取ClusterRoleBinding详情"""
        try:
            crb = self.rbac_v1_api.read_cluster_role_binding(name=name)
            
            crb_dict = {
                "name": crb.metadata.name,
                "role_ref": {
                    "api_group": crb.role_ref.api_group,
                    "kind": crb.role_ref.kind,
                    "name": crb.role_ref.name
                },
                "subjects": [],
                "labels": crb.metadata.labels,
                "annotations": crb.metadata.annotations,
                "creation_timestamp": to_local_time_str(crb.metadata.creation_timestamp),
                "uid": crb.metadata.uid
            }
            
            # 转换subjects
            for subject in crb.subjects:
                subject_dict = {
                    "kind": subject.kind,
                    "name": subject.name,
                    "api_group": subject.api_group,
                    "namespace": subject.namespace
                }
                crb_dict["subjects"].append(subject_dict)
            
            return crb_dict
        except ApiException as e:
            raise Exception(f"获取ClusterRoleBinding详情失败: {e.reason}")

    async def create_cluster_role_binding(self, name: str = None, role_ref: dict = None, 
                                        subjects: list = None,
                                        labels: dict = None, annotations: dict = None, resource: Dict = None, **kwargs) -> Dict[str, Any]:
        """创建ClusterRoleBinding"""
        
        # 准备资源数据用于验证
        resource_name = resource.get("metadata", {}).get("name") if resource else name
        resource_data = self._build_resource_data_for_validation(
            "clusterrolebinding", name, None, resource,  # ClusterRoleBinding 没有 namespace
            role_ref=role_ref, subjects=subjects
        )
        
        # 定义实际的创建操作
        async def create_operation():
            # 批量操作模式，传入完整的资源定义
            if resource:
                created_crb = self.rbac_v1_api.create_cluster_role_binding(body=resource)
                
                return {
                    "success": True,
                    "name": created_crb.metadata.name,
                    "message": f"ClusterRoleBinding {created_crb.metadata.name} 创建成功"
                }
            
            # 单体操作模式，使用简化参数创建
            if not name:
                raise ValueError("name参数是必需的")
            
            # 转换role_ref
            role_ref_obj = None
            if role_ref:
                role_ref_obj = client.V1RoleRef(
                    api_group=role_ref.get("api_group", "rbac.authorization.k8s.io"),
                    kind=role_ref.get("kind", "ClusterRole"),
                    name=role_ref.get("name")
                )
            
            # 转换subjects
            subjects_list = []
            if subjects:
                for subject in subjects:
                    subject_obj = client.RbacV1Subject(
                        kind=subject.get("kind"),
                        name=subject.get("name"),
                        api_group=subject.get("api_group", "rbac.authorization.k8s.io"),
                        namespace=subject.get("namespace")
                    )
                    subjects_list.append(subject_obj)
            
            cluster_role_binding = client.V1ClusterRoleBinding(
                metadata=client.V1ObjectMeta(
                    name=name,
                    labels=labels,
                    annotations=annotations
                ),
                role_ref=role_ref_obj,
                subjects=subjects_list
            )
            
            created_crb = self.rbac_v1_api.create_cluster_role_binding(body=cluster_role_binding)
            
            return {
                "success": True,
                "name": created_crb.metadata.name,
                "message": f"ClusterRoleBinding {name} 创建成功"
            }
            
        # 使用统一的验证和执行方法 (ClusterRoleBinding 是集群级资源，没有 namespace)
        return await self._execute_with_validation_and_preview(
            "create", "clusterrolebinding", resource_name, None, resource_data, create_operation
        )

    async def update_cluster_role_binding(self, name: str, role_ref: dict = None,
                                        subjects: list = None,
                                        labels: dict = None, annotations: dict = None, resource: Dict = None) -> Dict[str, Any]:
        """更新ClusterRoleBinding"""
        
        # 准备资源数据用于验证
        resource_data = self._build_resource_data_for_validation(
            "clusterrolebinding", name, None, resource,  # ClusterRoleBinding 没有 namespace
            role_ref=role_ref, subjects=subjects
        )
        
        # 定义实际的更新操作
        async def update_operation():
            if resource is not None:
                # 批量操作模式，传入完整的资源定义
                body = resource
                # 确保metadata中有正确的name
                if 'metadata' not in body:
                    body['metadata'] = {}
                body['metadata']['name'] = name
                
                response = self.rbac_v1_api.patch_cluster_role_binding(
                    name=name,
                    body=body
                )
            else:
                # 单体操作模式，使用简化参数更新
                # 获取现有ClusterRoleBinding
                existing_crb = self.rbac_v1_api.read_cluster_role_binding(name=name)
                
                # 更新role_ref
                if role_ref is not None:
                    role_ref_obj = client.V1RoleRef(
                        api_group=role_ref.get("api_group", "rbac.authorization.k8s.io"),
                        kind=role_ref.get("kind", "ClusterRole"),
                        name=role_ref.get("name")
                    )
                    existing_crb.role_ref = role_ref_obj
                
                # 更新subjects
                if subjects is not None:
                    subjects_list = []
                    for subject in subjects:
                        subject_obj = client.RbacV1Subject(
                            kind=subject.get("kind"),
                            name=subject.get("name"),
                            api_group=subject.get("api_group", "rbac.authorization.k8s.io"),
                            namespace=subject.get("namespace")
                        )
                        subjects_list.append(subject_obj)
                    existing_crb.subjects = subjects_list
                
                # 更新标签和注解
                if labels is not None:
                    existing_crb.metadata.labels = labels
                if annotations is not None:
                    existing_crb.metadata.annotations = annotations
                
                response = self.rbac_v1_api.replace_cluster_role_binding(
                    name=name,
                    body=existing_crb
            )
            
            return {
                "success": True,
                "name": response.metadata.name,
                "message": f"ClusterRoleBinding {name} 更新成功"
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "update", "clusterrolebinding", name, None, resource_data, update_operation
        )

    async def delete_cluster_role_binding(self, name: str) -> Dict[str, Any]:
        """删除ClusterRoleBinding"""
        
        # 定义实际的删除操作
        async def delete_operation():
            self.rbac_v1_api.delete_cluster_role_binding(name=name)
            
            return {
                "success": True,
                "message": f"ClusterRoleBinding {name} 删除成功"
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "delete", "clusterrolebinding", name, None, None, delete_operation
        )

    # ==================== HPA (Horizontal Pod Autoscaler) 管理 ====================

    async def list_hpas(self, namespace: str = "default", label_selector: str = None) -> List[Dict[str, Any]]:
        """列出 HPA"""
        try:
            if label_selector:
                hpas = self.autoscaling_v2_api.list_namespaced_horizontal_pod_autoscaler(
                    namespace=namespace, label_selector=label_selector
                )
            else:
                hpas = self.autoscaling_v2_api.list_namespaced_horizontal_pod_autoscaler(namespace=namespace)
            
            return [
                {
                    "name": hpa.metadata.name,
                    "namespace": hpa.metadata.namespace,
                    "target_ref": {
                        "kind": hpa.spec.scale_target_ref.kind,
                        "name": hpa.spec.scale_target_ref.name
                    },
                    "min_replicas": hpa.spec.min_replicas,
                    "max_replicas": hpa.spec.max_replicas,
                    "current_replicas": hpa.status.current_replicas if hpa.status else None,
                    "desired_replicas": hpa.status.desired_replicas if hpa.status else None,
                    "creation_timestamp": to_local_time_str(hpa.metadata.creation_timestamp, 8) if hpa.metadata.creation_timestamp else None
                }
                for hpa in hpas.items
            ]
        except Exception as e:
            raise Exception(f"获取HPA列表失败: {str(e)}")

    async def get_hpa(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """获取 HPA 详细信息"""
        try:
            hpa = self.autoscaling_v2_api.read_namespaced_horizontal_pod_autoscaler(name=name, namespace=namespace)
            
            return {
                "name": hpa.metadata.name,
                "namespace": hpa.metadata.namespace,
                "uid": hpa.metadata.uid,
                "labels": dict(hpa.metadata.labels) if hpa.metadata.labels else {},
                "annotations": dict(hpa.metadata.annotations) if hpa.metadata.annotations else {},
                "target_ref": {
                    "kind": hpa.spec.scale_target_ref.kind,
                    "name": hpa.spec.scale_target_ref.name,
                    "api_version": hpa.spec.scale_target_ref.api_version
                },
                "min_replicas": hpa.spec.min_replicas,
                "max_replicas": hpa.spec.max_replicas,
                "metrics": [
                    {
                        "type": metric.type,
                        "resource": metric.resource.to_dict() if metric.resource else None,
                        "pods": metric.pods.to_dict() if metric.pods else None,
                        "object": metric.object.to_dict() if metric.object else None
                    }
                    for metric in (hpa.spec.metrics or [])
                ],
                "status": {
                    "current_replicas": hpa.status.current_replicas,
                    "desired_replicas": hpa.status.desired_replicas,
                    "current_metrics": [
                        {
                            "type": metric.type,
                            "resource": metric.resource.to_dict() if metric.resource else None
                        }
                        for metric in (hpa.status.current_metrics or [])
                    ] if hpa.status else []
                } if hpa.status else {},
                "creation_timestamp": to_local_time_str(hpa.metadata.creation_timestamp, 8) if hpa.metadata.creation_timestamp else None
            }
        except Exception as e:
            raise Exception(f"获取HPA {name} 失败: {str(e)}")

    async def create_hpa(self, name: str = None, target_ref: dict = None, min_replicas: int = 1,
                        max_replicas: int = 10, metrics: list = None, namespace: str = "default",
                        labels: dict = None, annotations: dict = None, resource: Dict = None, **kwargs) -> Dict[str, Any]:
        """创建 HPA"""
        
        # 准备资源数据用于验证
        resource_name = resource.get("metadata", {}).get("name") if resource else name
        resource_data = self._build_resource_data_for_validation(
            "horizontalpodautoscaler", name, namespace, resource,
            target_ref=target_ref, min_replicas=min_replicas, max_replicas=max_replicas, metrics=metrics
        )
        
        # 定义实际的创建操作
        async def create_operation():
            # 批量操作模式，传入完整的资源定义
            if resource:
                created_hpa = self.autoscaling_v2_api.create_namespaced_horizontal_pod_autoscaler(
                    namespace=namespace, body=resource
                )
                
                return {
                    "success": True,
                    "name": created_hpa.metadata.name,
                    "namespace": created_hpa.metadata.namespace,
                    "message": f"HPA {created_hpa.metadata.name} 创建成功"
                }
            
            # 单体操作模式，使用简化参数创建
            if not name or not target_ref:
                raise ValueError("name和target_ref参数是必需的")
            
            # 构建 HPA 规格
            hpa_spec = client.V2HorizontalPodAutoscalerSpec(
                scale_target_ref=client.V2CrossVersionObjectReference(
                    kind=target_ref.get("kind"),
                    name=target_ref.get("name"),
                    api_version=target_ref.get("api_version", "apps/v1")
                ),
                min_replicas=min_replicas,
                max_replicas=max_replicas,
                metrics=[
                    client.V2MetricSpec(
                        type=metric.get("type"),
                        resource=client.V2ResourceMetricSource(
                            name=metric.get("resource", {}).get("name"),
                            target=client.V2MetricTarget(
                                type=metric.get("resource", {}).get("target", {}).get("type"),
                                average_utilization=metric.get("resource", {}).get("target", {}).get("average_utilization")
                            )
                        ) if metric.get("resource") else None
                    )
                    for metric in (metrics or [])
                ] if metrics else [
                    client.V2MetricSpec(
                        type="Resource",
                        resource=client.V2ResourceMetricSource(
                            name="cpu",
                            target=client.V2MetricTarget(
                                type="Utilization",
                                average_utilization=80
                            )
                        )
                    )
                ]
            )
            
            # 构建 HPA
            hpa = client.V2HorizontalPodAutoscaler(
                api_version="autoscaling/v2",
                kind="HorizontalPodAutoscaler",
                metadata=client.V1ObjectMeta(
                    name=name,
                    namespace=namespace,
                    labels=labels,
                    annotations=annotations
                ),
                spec=hpa_spec
            )
            
            # 创建 HPA
            created_hpa = self.autoscaling_v2_api.create_namespaced_horizontal_pod_autoscaler(
                namespace=namespace, body=hpa
            )
            
            return {
                "success": True,
                "name": created_hpa.metadata.name,
                "namespace": created_hpa.metadata.namespace,
                "message": f"HPA {name} 创建成功"
            }
        
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "horizontalpodautoscaler", resource_name, namespace, resource_data, create_operation
        )

    async def update_hpa(self, name: str, namespace: str = "default", min_replicas: int = None,
                        max_replicas: int = None, metrics: list = None, labels: dict = None,
                        annotations: dict = None, resource: Dict = None) -> Dict[str, Any]:
        """更新 HPA"""
        
        # 准备资源数据用于验证
        resource_name = resource.get("metadata", {}).get("name") if resource else name
        resource_data = self._build_resource_data_for_validation(
            "horizontalpodautoscaler", name, namespace, resource,
            min_replicas=min_replicas, max_replicas=max_replicas, metrics=metrics
        )
        
        # 定义实际的更新操作
        async def update_operation():
            # 批量操作模式，传入完整的资源定义
            if resource:
                updated_hpa = self.autoscaling_v2_api.replace_namespaced_horizontal_pod_autoscaler(
                    name=name, namespace=namespace, body=resource
                )
                
                return {
                    "success": True,
                    "name": updated_hpa.metadata.name,
                    "namespace": updated_hpa.metadata.namespace,
                    "message": f"HPA {updated_hpa.metadata.name} 更新成功"
                }
            
            # 单体操作模式，获取现有HPA并更新
            current_hpa = self.autoscaling_v2_api.read_namespaced_horizontal_pod_autoscaler(
                name=name, namespace=namespace
            )
            
            # 更新字段
            if min_replicas is not None:
                current_hpa.spec.min_replicas = min_replicas
            if max_replicas is not None:
                current_hpa.spec.max_replicas = max_replicas
            if metrics is not None:
                current_hpa.spec.metrics = [
                    client.V2MetricSpec(
                        type=metric.get("type"),
                        resource=client.V2ResourceMetricSource(
                            name=metric.get("resource", {}).get("name"),
                            target=client.V2MetricTarget(
                                type=metric.get("resource", {}).get("target", {}).get("type"),
                                average_utilization=metric.get("resource", {}).get("target", {}).get("average_utilization")
                            )
                        ) if metric.get("resource") else None
                    )
                    for metric in metrics
                ]
            if labels:
                if current_hpa.metadata.labels:
                    current_hpa.metadata.labels.update(labels)
                else:
                    current_hpa.metadata.labels = labels
            if annotations:
                if current_hpa.metadata.annotations:
                    current_hpa.metadata.annotations.update(annotations)
                else:
                    current_hpa.metadata.annotations = annotations
            
            # 更新 HPA
            updated_hpa = self.autoscaling_v2_api.replace_namespaced_horizontal_pod_autoscaler(
                name=name, namespace=namespace, body=current_hpa
            )
            
            return {
                "success": True,
                "name": updated_hpa.metadata.name,
                "namespace": updated_hpa.metadata.namespace,
                "message": f"HPA {name} 更新成功"
            }
        
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "update", "horizontalpodautoscaler", resource_name, namespace, resource_data, update_operation
        )

    async def delete_hpa(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除 HPA"""
        
        # 定义实际的删除操作
        async def delete_operation():
            self.autoscaling_v2_api.delete_namespaced_horizontal_pod_autoscaler(
                name=name, namespace=namespace
            )
            
            return {
                "success": True,
                "name": name,
                "namespace": namespace,
                "message": f"HPA {name} 删除成功"
            }
        
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "delete", "horizontalpodautoscaler", name, namespace, {}, delete_operation
        )

    # ==================== NetworkPolicy 管理 ====================

    async def list_network_policies(self, namespace: str = "default", label_selector: str = None) -> List[Dict[str, Any]]:
        """列出 NetworkPolicy"""
        try:
            if label_selector:
                policies = self.networking_v1_api.list_namespaced_network_policy(
                    namespace=namespace, label_selector=label_selector
                )
            else:
                policies = self.networking_v1_api.list_namespaced_network_policy(namespace=namespace)
            
            return [
                {
                    "name": policy.metadata.name,
                    "namespace": policy.metadata.namespace,
                    "pod_selector": policy.spec.pod_selector.to_dict() if policy.spec.pod_selector else {},
                    "policy_types": policy.spec.policy_types or [],
                    "ingress_rules": len(policy.spec.ingress or []),
                    "egress_rules": len(policy.spec.egress or []),
                    "creation_timestamp": to_local_time_str(policy.metadata.creation_timestamp, 8) if policy.metadata.creation_timestamp else None
                }
                for policy in policies.items
            ]
        except Exception as e:
            raise Exception(f"获取NetworkPolicy列表失败: {str(e)}")

    async def get_network_policy(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """获取 NetworkPolicy 详细信息"""
        try:
            policy = self.networking_v1_api.read_namespaced_network_policy(name=name, namespace=namespace)
            
            return {
                "name": policy.metadata.name,
                "namespace": policy.metadata.namespace,
                "uid": policy.metadata.uid,
                "labels": dict(policy.metadata.labels) if policy.metadata.labels else {},
                "annotations": dict(policy.metadata.annotations) if policy.metadata.annotations else {},
                "spec": {
                    "pod_selector": policy.spec.pod_selector.to_dict() if policy.spec.pod_selector else {},
                    "policy_types": policy.spec.policy_types or [],
                    "ingress": [rule.to_dict() for rule in (policy.spec.ingress or [])],
                    "egress": [rule.to_dict() for rule in (policy.spec.egress or [])]
                },
                "creation_timestamp": to_local_time_str(policy.metadata.creation_timestamp, 8) if policy.metadata.creation_timestamp else None
            }
        except Exception as e:
            raise Exception(f"获取NetworkPolicy {name} 失败: {str(e)}")

    async def create_network_policy(self, name: str = None, pod_selector: dict = None,
                                   policy_types: list = None, ingress: list = None, egress: list = None,
                                   namespace: str = "default", labels: dict = None, annotations: dict = None,
                                   resource: Dict = None, **kwargs) -> Dict[str, Any]:
        """创建 NetworkPolicy"""
        
        # 准备资源数据用于验证
        resource_name = resource.get("metadata", {}).get("name") if resource else name
        resource_data = self._build_resource_data_for_validation(
            "networkpolicy", name, namespace, resource,
            pod_selector=pod_selector, policy_types=policy_types, ingress=ingress, egress=egress
        )
        
        # 定义实际的创建操作
        async def create_operation():
            # 批量操作模式，传入完整的资源定义
            if resource:
                created_policy = self.networking_v1_api.create_namespaced_network_policy(
                    namespace=namespace, body=resource
                )
                
                return {
                    "success": True,
                    "name": created_policy.metadata.name,
                    "namespace": created_policy.metadata.namespace,
                    "message": f"NetworkPolicy {created_policy.metadata.name} 创建成功"
                }
            
            # 单体操作模式，使用简化参数创建
            if not name:
                raise ValueError("name参数是必需的")
            
            # 构建 NetworkPolicy 规格
            policy_spec = client.V1NetworkPolicySpec(
                pod_selector=client.V1LabelSelector(
                    match_labels=pod_selector or {}
                ),
                policy_types=policy_types or ["Ingress"],
                ingress=[
                    client.V1NetworkPolicyIngressRule(
                        _from=[
                            client.V1NetworkPolicyPeer(
                                pod_selector=client.V1LabelSelector(
                                    match_labels=rule.get("from", {}).get("pod_selector", {})
                                ) if rule.get("from", {}).get("pod_selector") else None,
                                namespace_selector=client.V1LabelSelector(
                                    match_labels=rule.get("from", {}).get("namespace_selector", {})
                                ) if rule.get("from", {}).get("namespace_selector") else None
                            )
                        ] if rule.get("from") else None,
                        ports=[
                            client.V1NetworkPolicyPort(
                                port=port.get("port"),
                                protocol=port.get("protocol", "TCP")
                            )
                            for port in rule.get("ports", [])
                        ] if rule.get("ports") else None
                    )
                    for rule in (ingress or [])
                ] if ingress else None,
                egress=[
                    client.V1NetworkPolicyEgressRule(
                        to=[
                            client.V1NetworkPolicyPeer(
                                pod_selector=client.V1LabelSelector(
                                    match_labels=rule.get("to", {}).get("pod_selector", {})
                                ) if rule.get("to", {}).get("pod_selector") else None,
                                namespace_selector=client.V1LabelSelector(
                                    match_labels=rule.get("to", {}).get("namespace_selector", {})
                                ) if rule.get("to", {}).get("namespace_selector") else None
                            )
                        ] if rule.get("to") else None,
                        ports=[
                            client.V1NetworkPolicyPort(
                                port=port.get("port"),
                                protocol=port.get("protocol", "TCP")
                            )
                            for port in rule.get("ports", [])
                        ] if rule.get("ports") else None
                    )
                    for rule in (egress or [])
                ] if egress else None
            )
            
            # 构建 NetworkPolicy
            network_policy = client.V1NetworkPolicy(
                api_version="networking.k8s.io/v1",
                kind="NetworkPolicy",
                metadata=client.V1ObjectMeta(
                    name=name,
                    namespace=namespace,
                    labels=labels,
                    annotations=annotations
                ),
                spec=policy_spec
            )
            
            # 创建 NetworkPolicy
            created_policy = self.networking_v1_api.create_namespaced_network_policy(
                namespace=namespace, body=network_policy
            )
            
            return {
                "success": True,
                "name": created_policy.metadata.name,
                "namespace": created_policy.metadata.namespace,
                "message": f"NetworkPolicy {name} 创建成功"
            }
        
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "networkpolicy", resource_name, namespace, resource_data, create_operation
        )

    async def update_network_policy(self, name: str, namespace: str = "default",
                                   pod_selector: dict = None, policy_types: list = None,
                                   ingress: list = None, egress: list = None,
                                   labels: dict = None, annotations: dict = None,
                                   resource: Dict = None) -> Dict[str, Any]:
        """更新 NetworkPolicy"""
        
        # 准备资源数据用于验证
        resource_name = resource.get("metadata", {}).get("name") if resource else name
        resource_data = self._build_resource_data_for_validation(
            "networkpolicy", name, namespace, resource,
            pod_selector=pod_selector, policy_types=policy_types, ingress=ingress, egress=egress
        )
        
        # 定义实际的更新操作
        async def update_operation():
            # 批量操作模式，传入完整的资源定义
            if resource:
                updated_policy = self.networking_v1_api.replace_namespaced_network_policy(
                    name=name, namespace=namespace, body=resource
                )
                
                return {
                    "success": True,
                    "name": updated_policy.metadata.name,
                    "namespace": updated_policy.metadata.namespace,
                    "message": f"NetworkPolicy {updated_policy.metadata.name} 更新成功"
                }
            
            # 单体操作模式，获取现有NetworkPolicy并更新
            current_policy = self.networking_v1_api.read_namespaced_network_policy(
                name=name, namespace=namespace
            )
            
            # 更新字段
            if pod_selector is not None:
                current_policy.spec.pod_selector = client.V1LabelSelector(match_labels=pod_selector)
            if policy_types is not None:
                current_policy.spec.policy_types = policy_types
            if labels:
                if current_policy.metadata.labels:
                    current_policy.metadata.labels.update(labels)
                else:
                    current_policy.metadata.labels = labels
            if annotations:
                if current_policy.metadata.annotations:
                    current_policy.metadata.annotations.update(annotations)
                else:
                    current_policy.metadata.annotations = annotations
            
            # 更新 NetworkPolicy
            updated_policy = self.networking_v1_api.replace_namespaced_network_policy(
                name=name, namespace=namespace, body=current_policy
            )
            
            return {
                "success": True,
                "name": updated_policy.metadata.name,
                "namespace": updated_policy.metadata.namespace,
                "message": f"NetworkPolicy {name} 更新成功"
            }
        
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "update", "networkpolicy", resource_name, namespace, resource_data, update_operation
        )

    async def delete_network_policy(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除 NetworkPolicy"""
        
        # 定义实际的删除操作
        async def delete_operation():
            self.networking_v1_api.delete_namespaced_network_policy(
                name=name, namespace=namespace
            )
            
            return {
                "success": True,
                "name": name,
                "namespace": namespace,
                "message": f"NetworkPolicy {name} 删除成功"
            }
        
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "delete", "networkpolicy", name, namespace, {}, delete_operation
        )

    # ==================== ResourceQuota 管理 ====================

    async def list_resource_quotas(self, namespace: str = "default", label_selector: str = None) -> List[Dict[str, Any]]:
        """列出 ResourceQuota"""
        try:
            if label_selector:
                quotas = self.v1_api.list_namespaced_resource_quota(
                    namespace=namespace, label_selector=label_selector
                )
            else:
                quotas = self.v1_api.list_namespaced_resource_quota(namespace=namespace)
            
            return [
                {
                    "name": quota.metadata.name,
                    "namespace": quota.metadata.namespace,
                    "hard": dict(quota.spec.hard) if quota.spec.hard else {},
                    "used": dict(quota.status.used) if quota.status and quota.status.used else {},
                    "creation_timestamp": to_local_time_str(quota.metadata.creation_timestamp, 8) if quota.metadata.creation_timestamp else None
                }
                for quota in quotas.items
            ]
        except Exception as e:
            raise Exception(f"获取ResourceQuota列表失败: {str(e)}")

    async def get_resource_quota(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """获取 ResourceQuota 详细信息"""
        try:
            quota = self.v1_api.read_namespaced_resource_quota(name=name, namespace=namespace)
            
            return {
                "name": quota.metadata.name,
                "namespace": quota.metadata.namespace,
                "uid": quota.metadata.uid,
                "labels": dict(quota.metadata.labels) if quota.metadata.labels else {},
                "annotations": dict(quota.metadata.annotations) if quota.metadata.annotations else {},
                "spec": {
                    "hard": dict(quota.spec.hard) if quota.spec.hard else {},
                    "scopes": quota.spec.scopes or []
                },
                "status": {
                    "hard": dict(quota.status.hard) if quota.status and quota.status.hard else {},
                    "used": dict(quota.status.used) if quota.status and quota.status.used else {}
                } if quota.status else {},
                "creation_timestamp": to_local_time_str(quota.metadata.creation_timestamp, 8) if quota.metadata.creation_timestamp else None
            }
        except Exception as e:
            raise Exception(f"获取ResourceQuota {name} 失败: {str(e)}")

    async def create_resource_quota(self, name: str = None, hard: dict = None, scopes: list = None,
                                   namespace: str = "default", labels: dict = None, annotations: dict = None,
                                   resource: Dict = None, **kwargs) -> Dict[str, Any]:
        """创建 ResourceQuota"""
        
        # 准备资源数据用于验证
        resource_name = resource.get("metadata", {}).get("name") if resource else name
        resource_data = self._build_resource_data_for_validation(
            "resourcequota", name, namespace, resource,
            hard=hard, scopes=scopes
        )
        
        # 定义实际的创建操作
        async def create_operation():
            # 批量操作模式，传入完整的资源定义
            if resource:
                created_quota = self.v1_api.create_namespaced_resource_quota(
                    namespace=namespace, body=resource
                )
                
                return {
                    "success": True,
                    "name": created_quota.metadata.name,
                    "namespace": created_quota.metadata.namespace,
                    "message": f"ResourceQuota {created_quota.metadata.name} 创建成功"
                }
            
            # 单体操作模式，使用简化参数创建
            if not name or not hard:
                raise ValueError("name和hard参数是必需的")
            
            # 构建 ResourceQuota 规格
            quota_spec = client.V1ResourceQuotaSpec(
                hard=hard,
                scopes=scopes
            )
            
            # 构建 ResourceQuota
            resource_quota = client.V1ResourceQuota(
                api_version="v1",
                kind="ResourceQuota",
                metadata=client.V1ObjectMeta(
                    name=name,
                    namespace=namespace,
                    labels=labels,
                    annotations=annotations
                ),
                spec=quota_spec
            )
            
            # 创建 ResourceQuota
            created_quota = self.v1_api.create_namespaced_resource_quota(
                namespace=namespace, body=resource_quota
            )
            
            return {
                "success": True,
                "name": created_quota.metadata.name,
                "namespace": created_quota.metadata.namespace,
                "message": f"ResourceQuota {name} 创建成功"
            }
        
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "resourcequota", resource_name, namespace, resource_data, create_operation
        )

    async def update_resource_quota(self, name: str, namespace: str = "default",
                                   hard: dict = None, scopes: list = None,
                                   labels: dict = None, annotations: dict = None,
                                   resource: Dict = None) -> Dict[str, Any]:
        """更新 ResourceQuota"""
        
        # 准备资源数据用于验证
        resource_name = resource.get("metadata", {}).get("name") if resource else name
        resource_data = self._build_resource_data_for_validation(
            "resourcequota", name, namespace, resource,
            hard=hard, scopes=scopes
        )
        
        # 定义实际的更新操作
        async def update_operation():
            # 批量操作模式，传入完整的资源定义
            if resource:
                updated_quota = self.v1_api.replace_namespaced_resource_quota(
                    name=name, namespace=namespace, body=resource
                )
                
                return {
                    "success": True,
                    "name": updated_quota.metadata.name,
                    "namespace": updated_quota.metadata.namespace,
                    "message": f"ResourceQuota {updated_quota.metadata.name} 更新成功"
                }
            
            # 单体操作模式，获取现有ResourceQuota并更新
            current_quota = self.v1_api.read_namespaced_resource_quota(
                name=name, namespace=namespace
            )
            
            # 更新字段
            if hard is not None:
                current_quota.spec.hard = hard
            if scopes is not None:
                current_quota.spec.scopes = scopes
            if labels:
                if current_quota.metadata.labels:
                    current_quota.metadata.labels.update(labels)
                else:
                    current_quota.metadata.labels = labels
            if annotations:
                if current_quota.metadata.annotations:
                    current_quota.metadata.annotations.update(annotations)
                else:
                    current_quota.metadata.annotations = annotations
            
            # 更新 ResourceQuota
            updated_quota = self.v1_api.replace_namespaced_resource_quota(
                name=name, namespace=namespace, body=current_quota
            )
            
            return {
                "success": True,
                "name": updated_quota.metadata.name,
                "namespace": updated_quota.metadata.namespace,
                "message": f"ResourceQuota {name} 更新成功"
            }
        
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "update", "resourcequota", resource_name, namespace, resource_data, update_operation
        )

    async def delete_resource_quota(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """删除 ResourceQuota"""
        
        # 定义实际的删除操作
        async def delete_operation():
            self.v1_api.delete_namespaced_resource_quota(
                name=name, namespace=namespace
            )
            
            return {
                "success": True,
                "name": name,
                "namespace": namespace,
                "message": f"ResourceQuota {name} 删除成功"
            }
        
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "delete", "resourcequota", name, namespace, {}, delete_operation
        )

    # ==================== 交互式操作方法 ====================

    async def exec_pod_command(self, pod_name: str, command: list, namespace: str = "default",
                              container: str = None) -> str:
        """在Pod中执行命令"""
        try:
            from kubernetes.stream import stream
            
            # 构建exec命令
            exec_command = ['/bin/sh', '-c', ' '.join(command)] if isinstance(command, list) else ['/bin/sh', '-c', command]
            
            # 执行命令
            resp = stream(
                self.v1_api.connect_get_namespaced_pod_exec,
                pod_name,
                namespace,
                command=exec_command,
                container=container,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False
            )
            
            return resp
            
        except Exception as e:
            raise Exception(f"执行Pod命令失败: {str(e)}")

    async def copy_from_pod(self, pod_name: str, pod_path: str, local_path: str,
                            namespace: str = "default", container: str = None) -> str:
        """从 Pod 拷贝文件/目录到本地（使用 tar + stream，需 Pod 内有 tar）"""
        import os
        import tarfile
        import asyncio
        from io import BytesIO
        from kubernetes.stream import stream

        def _do_copy():
            parent = os.path.dirname(pod_path)
            base = os.path.basename(pod_path)
            if not parent:
                parent = "."
            cmd = ['tar', 'cf', '-', '-C', parent, base]
            resp = stream(
                self.v1_api.connect_get_namespaced_pod_exec,
                pod_name, namespace,
                command=cmd,
                container=container,
                stderr=True, stdin=False, stdout=True, tty=False,
                _preload_content=False,
                binary=True
            )
            tar_data = BytesIO()
            while resp.is_open():
                resp.update(timeout=2)
                if resp.peek_stdout():
                    out = resp.read_stdout()
                    if isinstance(out, str):
                        out = out.encode('latin1')
                    tar_data.write(out)
            resp.close()
            tar_data.seek(0)
            # 解压到 local_path 的父目录，使 tar 内的 base 目录（如 apt）落在 local_path 下
            # 例如 pod /var/log/apt -> tar 含 apt/<files>，解压到 dirname(local_path) 得到 local_path/<files>
            dest_dir = os.path.dirname(local_path) or "."
            os.makedirs(dest_dir, exist_ok=True)
            with tarfile.open(fileobj=tar_data, mode='r:') as tar:
                tar.extractall(path=dest_dir)
            return local_path

        await asyncio.to_thread(_do_copy)
        return local_path

    async def copy_to_pod(self, pod_name: str, local_path: str, pod_path: str,
                          namespace: str = "default", container: str = None) -> str:
        """从本地拷贝文件/目录到 Pod（使用 tar + stream，需 Pod 内有 tar）"""
        import os
        import tarfile
        import asyncio
        from io import BytesIO
        from kubernetes.stream import stream

        def _do_copy():
            if not os.path.exists(local_path):
                raise FileNotFoundError(f"本地路径不存在: {local_path}")
            tar_buffer = BytesIO()
            arcname = os.path.basename(pod_path.rstrip('/')) or os.path.basename(local_path)
            with tarfile.open(fileobj=tar_buffer, mode='w') as tar:
                tar.add(local_path, arcname=arcname)
            tar_buffer.seek(0)
            tar_bytes = tar_buffer.read()
            dest_dir = os.path.dirname(pod_path)
            if not dest_dir:
                dest_dir = "/"
            cmd = ['tar', 'xf', '-', '-C', dest_dir]
            resp = stream(
                self.v1_api.connect_get_namespaced_pod_exec,
                pod_name, namespace,
                command=cmd,
                container=container,
                stderr=True, stdin=True, stdout=True, tty=False,
                _preload_content=False,
                binary=True
            )
            chunk_size = 1024 * 64
            for i in range(0, len(tar_bytes), chunk_size):
                resp.write_stdin(tar_bytes[i:i + chunk_size])
            resp.close()
            return pod_path

        await asyncio.to_thread(_do_copy)
        return pod_path

    async def port_forward(self, pod_name: str, local_port: int, pod_port: int,
                          namespace: str = "default") -> Dict[str, Any]:
        """Pod端口转发 - 在本地端口与Pod端口之间建立真实转发"""
        import threading
        import socket
        import select
        from kubernetes.stream import portforward

        def _bridge_sockets(local_sock, remote_sock):
            """双向转发两个 socket 之间的数据"""
            try:
                while True:
                    rlist, _, xlist = select.select([local_sock, remote_sock], [], [local_sock, remote_sock], 60)
                    if xlist:
                        break
                    for sock in rlist:
                        try:
                            data = sock.recv(65536)
                            if not data:
                                return
                            other = remote_sock if sock is local_sock else local_sock
                            other.sendall(data)
                        except (ConnectionResetError, BrokenPipeError, OSError):
                            return
            finally:
                try:
                    local_sock.close()
                except Exception:
                    pass
                try:
                    remote_sock.close()
                except Exception:
                    pass

        def _handle_connection(client_socket):
            """处理单个连接：建立 portforward 并桥接数据"""
            try:
                pf = portforward(
                    self.v1_api.connect_get_namespaced_pod_portforward,
                    pod_name,
                    namespace,
                    ports=str(pod_port),
                )
                remote_sock = pf.socket(pod_port)
                remote_sock.setblocking(True)
                _bridge_sockets(client_socket, remote_sock)
            except Exception:
                pass
            finally:
                try:
                    client_socket.close()
                except Exception:
                    pass

        run_flag = {"running": True}

        def _run_forward_server():
            """在后台运行 TCP 服务器，将本地端口流量转发到 Pod"""
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                server.bind(("127.0.0.1", local_port))
                server.listen(5)
                server.settimeout(1.0)
                while run_flag["running"]:
                    try:
                        client_sock, _ = server.accept()
                        t = threading.Thread(target=_handle_connection, args=(client_sock,), daemon=True)
                        t.start()
                    except socket.timeout:
                        continue
                    except OSError:
                        break
            finally:
                try:
                    server.close()
                except Exception:
                    pass

        # 启动后台转发线程
        server_thread = threading.Thread(target=_run_forward_server, daemon=True)
        server_thread.start()

        return {
            "pod_name": pod_name,
            "namespace": namespace,
            "local_port": local_port,
            "pod_port": pod_port,
            "status": "running",
            "message": f"端口转发已启动: localhost:{local_port} -> {pod_name}:{pod_port}",
            "note": "转发在后台运行，访问 http://127.0.0.1:{local_port} 可访问 Pod 服务。进程退出时自动停止。".format(local_port=local_port),
        }

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

    async def evict_pod(self, name: str, namespace: str = "default",
                        delete_options: client.V1DeleteOptions = None) -> Dict[str, Any]:
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

    async def drain_node(self, node_name: str, ignore_daemonset: bool = True,
                         ignore_mirror_pods: bool = True) -> Dict[str, Any]:
        """节点排水：cordon 后驱逐该节点上所有可驱逐的 Pod"""
        try:
            # 1. Cordon 节点
            node = self.v1_api.read_node(name=node_name)
            if not node.spec.unschedulable:
                node.spec.unschedulable = True
                self.v1_api.replace_node(name=node_name, body=node)

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

    async def get_namespace(self, name: str) -> Dict[str, Any]:
        """获取 Namespace 详情"""
        try:
            namespace = self.v1_api.read_namespace(name=name)
            
            return {
                "name": namespace.metadata.name,
                "uid": namespace.metadata.uid,
                "status": namespace.status.phase,
                "created": to_local_time_str(namespace.metadata.creation_timestamp, 8) if namespace.metadata.creation_timestamp else None,
                "labels": namespace.metadata.labels or {},
                "annotations": namespace.metadata.annotations or {},
                "conditions": [
                    {
                        "type": condition.type,
                        "status": condition.status,
                        "reason": condition.reason,
                        "message": condition.message,
                        "last_transition_time": to_local_time_str(condition.last_transition_time, 8) if condition.last_transition_time else None
                    }
                    for condition in (namespace.status.conditions or [])
                ]
            }
            
        except ApiException as e:
            raise Exception(f"获取 Namespace 详情失败: {e.reason}")

    async def create_namespace(self, name: str = None, labels: Dict[str, str] = None, 
                        annotations: Dict[str, str] = None, resource: Dict = None, **kwargs) -> Dict[str, Any]:
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

    async def update_namespace(self, name: str, labels: Dict[str, str] = None, 
                           annotations: Dict[str, str] = None, resource: Dict = None) -> Dict[str, Any]:
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
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp, 8) if response.metadata.creation_timestamp else None
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
            # 获取API服务器版本
            version = self.v1_api.get_api_resources()
            
            # 获取节点信息
            nodes = self.v1_api.list_node()
            node_count = len(nodes.items)
            
            # 获取命名空间信息
            namespaces = self.v1_api.list_namespace()
            namespace_count = len(namespaces.items)
            
            # 获取集群名称（从第一个节点的cluster-name标签获取）
            cluster_name = "unknown"
            if nodes.items:
                first_node = nodes.items[0]
                if first_node.metadata.labels:
                    cluster_name = first_node.metadata.labels.get("kubernetes.io/hostname", "unknown")
            
            return {
                "cluster_name": cluster_name,
                "node_count": node_count,
                "namespace_count": namespace_count,
                "api_version": "v1"
            }
        except Exception as e:
            return {"error": str(e)}

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
