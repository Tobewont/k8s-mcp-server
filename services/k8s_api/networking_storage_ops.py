from typing import Dict, List, Any, Optional
from kubernetes import client
from kubernetes.client.exceptions import ApiException
from utils.k8s_helpers import to_local_time_str

class NetworkingStorageOpsMixin:
    async def list_ingresses(self, namespace: str = "default", label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
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
                    "creation_timestamp": to_local_time_str(item.metadata.creation_timestamp) if item.metadata.creation_timestamp else None,
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
                    "created": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None
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

    async def create_ingress(self, name: Optional[str] = None, rules: Optional[list] = None, namespace: str = "default",
                       annotations: Optional[dict] = None, tls: Optional[list] = None,
                       ingress_class_name: Optional[str] = None, labels: Optional[dict] = None, resource: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
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
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
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
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
                "class_name": response.spec.ingress_class_name
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "ingress", resource_name, namespace, resource_data, create_operation
        )

    async def update_ingress(self, name: str, namespace: str = "default",
                       rules: Optional[list] = None, annotations: Optional[dict] = None,
                       tls: Optional[list] = None, ingress_class_name: Optional[str] = None,
                       labels: Optional[dict] = None, resource: Optional[Dict] = None) -> Dict[str, Any]:
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

    async def list_storageclasses(self, label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
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
                    "creation_timestamp": to_local_time_str(item.metadata.creation_timestamp) if item.metadata.creation_timestamp else None,
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
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
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

    async def create_storageclass(self, name: Optional[str] = None, provisioner: Optional[str] = None,
                            reclaim_policy: str = "Delete",
                            volume_binding_mode: str = "Immediate",
                            allow_volume_expansion: bool = False,
                            parameters: Optional[dict] = None,
                            labels: Optional[dict] = None,
                            annotations: Optional[dict] = None, resource: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
        """创建 StorageClass"""
        try:
            # 批量操作模式，传入完整的资源定义
            if resource:
                response = self.storage_v1_api.create_storage_class(body=resource)
                
                return {
                    "name": response.metadata.name,
                    "uid": response.metadata.uid,
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
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
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
                "provisioner": response.provisioner,
                "reclaim_policy": response.reclaim_policy,
                "volume_binding_mode": response.volume_binding_mode
            }
            
        except ApiException as e:
            raise Exception(f"创建 StorageClass 失败: {e}")

    async def update_storageclass(self, name: str, provisioner: Optional[str] = None,
                            reclaim_policy: Optional[str] = None,
                            volume_binding_mode: Optional[str] = None,
                            allow_volume_expansion: Optional[bool] = None,
                            parameters: Optional[dict] = None,
                            labels: Optional[dict] = None,
                            annotations: Optional[dict] = None, resource: Optional[Dict] = None) -> Dict[str, Any]:
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

    async def list_persistentvolumes(self, label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
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
                    "creation_timestamp": to_local_time_str(item.metadata.creation_timestamp) if item.metadata.creation_timestamp else None,
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
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
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

    async def create_persistentvolume(self, name: Optional[str] = None, capacity: Optional[str] = None,
                                access_modes: Optional[list] = None,
                                reclaim_policy: str = "Retain",
                                storage_class_name: Optional[str] = None,
                                volume_mode: str = "Filesystem",
                                host_path: Optional[str] = None,
                                nfs: Optional[dict] = None,
                                labels: Optional[dict] = None,
                                annotations: Optional[dict] = None,
                                csi: Optional[dict] = None, resource: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
        """创建 PersistentVolume"""
        try:
            # 批量操作模式，传入完整的资源定义
            if resource:
                response = self.v1_api.create_persistent_volume(body=resource)
                
                return {
                    "name": response.metadata.name,
                    "uid": response.metadata.uid,
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
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
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
                "capacity": response.spec.capacity,
                "access_modes": response.spec.access_modes,
                "reclaim_policy": response.spec.persistent_volume_reclaim_policy,
                "storage_class_name": response.spec.storage_class_name
            }
            
        except ApiException as e:
            raise Exception(f"创建 PersistentVolume 失败: {e}")

    async def update_persistentvolume(self, name: str,
                                capacity: Optional[str] = None,
                                access_modes: Optional[list] = None,
                                reclaim_policy: Optional[str] = None,
                                storage_class_name: Optional[str] = None,
                                labels: Optional[dict] = None,
                                annotations: Optional[dict] = None, resource: Optional[Dict] = None) -> Dict[str, Any]:
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
                                    label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
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
                    "creation_timestamp": to_local_time_str(item.metadata.creation_timestamp) if item.metadata.creation_timestamp else None,
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
                    "created": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None
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
                        "last_probe_time": to_local_time_str(condition.last_probe_time) if condition.last_probe_time else None,
                        "last_transition_time": to_local_time_str(condition.last_transition_time) if condition.last_transition_time else None
                    }
                    for condition in (response.status.conditions or [])
                ] if response.status else []
                }
            }
            
        except ApiException as e:
            raise Exception(f"获取 PersistentVolumeClaim 失败: {e}")

    async def create_persistentvolumeclaim(self, name: Optional[str] = None, size: Optional[str] = None,
                                     namespace: str = "default",
                                     access_modes: Optional[list] = None,
                                     storage_class_name: Optional[str] = None,
                                     volume_mode: str = "Filesystem",
                                     volume_name: Optional[str] = None,
                                     labels: Optional[dict] = None,
                                     annotations: Optional[dict] = None, resource: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
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
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
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
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
                "access_modes": response.spec.access_modes,
                "requests": response.spec.resources.requests,
                "storage_class_name": response.spec.storage_class_name
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "persistentvolumeclaim", resource_name, namespace, resource_data, create_operation
        )

    async def update_persistentvolumeclaim(self, name: str, namespace: str = "default",
                                     size: Optional[str] = None,
                                     access_modes: Optional[list] = None,
                                     storage_class_name: Optional[str] = None,
                                     labels: Optional[dict] = None,
                                     annotations: Optional[dict] = None, resource: Optional[Dict] = None) -> Dict[str, Any]:
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

