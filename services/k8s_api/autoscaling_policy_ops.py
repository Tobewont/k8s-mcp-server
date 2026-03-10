from typing import Dict, List, Any, Optional
from kubernetes import client
from kubernetes.client.exceptions import ApiException
from utils.k8s_helpers import to_local_time_str

class AutoscalingPolicyOpsMixin:
    async def list_hpas(self, namespace: str = "default", label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
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
                    "creation_timestamp": to_local_time_str(hpa.metadata.creation_timestamp) if hpa.metadata.creation_timestamp else None
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
                "creation_timestamp": to_local_time_str(hpa.metadata.creation_timestamp) if hpa.metadata.creation_timestamp else None
            }
        except Exception as e:
            raise Exception(f"获取HPA {name} 失败: {str(e)}")

    async def create_hpa(self, name: Optional[str] = None, target_ref: Optional[dict] = None, min_replicas: int = 1,
                        max_replicas: int = 10, metrics: Optional[list] = None, namespace: str = "default",
                        labels: Optional[dict] = None, annotations: Optional[dict] = None, resource: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
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

    async def update_hpa(self, name: str, namespace: str = "default", min_replicas: Optional[int] = None,
                        max_replicas: Optional[int] = None, metrics: Optional[list] = None, labels: Optional[dict] = None,
                        annotations: Optional[dict] = None, resource: Optional[Dict] = None) -> Dict[str, Any]:
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

    async def list_network_policies(self, namespace: str = "default", label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
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
                    "creation_timestamp": to_local_time_str(policy.metadata.creation_timestamp) if policy.metadata.creation_timestamp else None
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
                "creation_timestamp": to_local_time_str(policy.metadata.creation_timestamp) if policy.metadata.creation_timestamp else None
            }
        except Exception as e:
            raise Exception(f"获取NetworkPolicy {name} 失败: {str(e)}")

    async def create_network_policy(self, name: Optional[str] = None, pod_selector: Optional[dict] = None,
                                   policy_types: Optional[list] = None, ingress: Optional[list] = None, egress: Optional[list] = None,
                                   namespace: str = "default", labels: Optional[dict] = None, annotations: Optional[dict] = None,
                                   resource: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
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
                                   pod_selector: Optional[dict] = None, policy_types: Optional[list] = None,
                                   ingress: Optional[list] = None, egress: Optional[list] = None,
                                   labels: Optional[dict] = None, annotations: Optional[dict] = None,
                                   resource: Optional[Dict] = None) -> Dict[str, Any]:
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

    async def list_resource_quotas(self, namespace: str = "default", label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
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
                    "creation_timestamp": to_local_time_str(quota.metadata.creation_timestamp) if quota.metadata.creation_timestamp else None
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
                "creation_timestamp": to_local_time_str(quota.metadata.creation_timestamp) if quota.metadata.creation_timestamp else None
            }
        except Exception as e:
            raise Exception(f"获取ResourceQuota {name} 失败: {str(e)}")

    async def create_resource_quota(self, name: Optional[str] = None, hard: Optional[dict] = None, scopes: Optional[list] = None,
                                   namespace: str = "default", labels: Optional[dict] = None, annotations: Optional[dict] = None,
                                   resource: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
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
                                   hard: Optional[dict] = None, scopes: Optional[list] = None,
                                   labels: Optional[dict] = None, annotations: Optional[dict] = None,
                                   resource: Optional[Dict] = None) -> Dict[str, Any]:
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

