from typing import Dict, List, Any, Optional
from kubernetes import client
from kubernetes.client.exceptions import ApiException
from utils.k8s_helpers import to_local_time_str

class WorkloadOpsMixin:
    async def list_deployments(self, namespace: str = "default", 
                        label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
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
                    "created": to_local_time_str(deployment.metadata.creation_timestamp) if deployment.metadata.creation_timestamp else None,
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
                    "created": to_local_time_str(deployment.metadata.creation_timestamp) if deployment.metadata.creation_timestamp else None
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

    async def create_deployment(self, name: Optional[str] = None, image: Optional[str] = None, namespace: str = "default",
                          replicas: int = 1, labels: Optional[dict] = None, env_vars: Optional[dict] = None,
                          ports: Optional[list] = None, resources: Optional[dict] = None, resource: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
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
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
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
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
                "replicas": response.spec.replicas
            }
        
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "deployment", resource_name, namespace, resource_data, create_operation
        )

    async def update_deployment(self, name: str, namespace: str = "default",
                          image: Optional[str] = None, replicas: Optional[int] = None,
                          labels: Optional[dict] = None, env_vars: Optional[dict] = None,
                          resources: Optional[dict] = None, resource: Optional[Dict] = None) -> Dict[str, Any]:
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
                                grace_period_seconds: Optional[int] = None) -> Dict[str, Any]:
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
                          revision: Optional[int] = None) -> Dict[str, Any]:
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

    async def list_statefulsets(self, namespace: str = "default", label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
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
                    "creation_timestamp": to_local_time_str(item.metadata.creation_timestamp) if item.metadata.creation_timestamp else None,
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
                    "created": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None
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

    async def create_statefulset(self, name: Optional[str] = None, image: Optional[str] = None, namespace: str = "default",
                           replicas: int = 1, labels: Optional[dict] = None, env_vars: Optional[dict] = None,
                           ports: Optional[list] = None, resources: Optional[dict] = None,
                           volume_claims: Optional[list] = None, resource: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
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
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
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
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
                "replicas": response.spec.replicas
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "statefulset", resource_name, namespace, resource_data, create_operation
        )

    async def update_statefulset(self, name: str, namespace: str = "default",
                           image: Optional[str] = None, replicas: Optional[int] = None,
                           labels: Optional[dict] = None, env_vars: Optional[dict] = None, resource: Optional[Dict] = None) -> Dict[str, Any]:
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
                                 grace_period_seconds: Optional[int] = None) -> Dict[str, Any]:
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

    async def list_daemonsets(self, namespace: str = "default", label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
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
                    "creation_timestamp": to_local_time_str(item.metadata.creation_timestamp) if item.metadata.creation_timestamp else None,
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
                    "created": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None
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

    async def create_daemonset(self, name: Optional[str] = None, image: Optional[str] = None, namespace: str = "default",
                         labels: Optional[dict] = None, env_vars: Optional[dict] = None,
                         ports: Optional[list] = None, resources: Optional[dict] = None,
                         volumes: Optional[list] = None, resource: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
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
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None
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
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "daemonset", resource_name, namespace, resource_data, create_operation
        )

    async def update_daemonset(self, name: str, namespace: str = "default",
                         image: Optional[str] = None, labels: Optional[dict] = None,
                         env_vars: Optional[dict] = None, resource: Optional[Dict] = None) -> Dict[str, Any]:
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

