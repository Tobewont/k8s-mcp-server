from typing import Dict, List, Any, Optional
from kubernetes import client
from kubernetes.client.exceptions import ApiException
from utils.k8s_helpers import parse_secret_data, to_local_time_str

class ServiceConfigOpsMixin:
    async def list_services(self, namespace: str = "default", 
                     label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
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
                    "created": to_local_time_str(service.metadata.creation_timestamp) if service.metadata.creation_timestamp else None,
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
                    "created": to_local_time_str(service.metadata.creation_timestamp) if service.metadata.creation_timestamp else None,
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

    async def create_service(self, name: Optional[str] = None, selector: Optional[dict] = None, ports: Optional[list] = None,
                       namespace: str = "default", service_type: str = "ClusterIP", resource: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
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
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
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
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
                "type": response.spec.type,
                "cluster_ip": response.spec.cluster_ip
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "service", resource_name, namespace, resource_data, create_operation
        )

    async def update_service(self, name: str, namespace: str = "default",
service_type: Optional[str] = None, ports: Optional[list] = None,
                       selector: Optional[dict] = None, labels: Optional[dict] = None,
                       annotations: Optional[dict] = None, resource: Optional[Dict] = None) -> Dict[str, Any]:
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
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
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
                       label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
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
                    "created": to_local_time_str(configmap.metadata.creation_timestamp) if configmap.metadata.creation_timestamp else None,
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
                    "created": to_local_time_str(configmap.metadata.creation_timestamp) if configmap.metadata.creation_timestamp else None,
                    "uid": configmap.metadata.uid
                },
                "data": configmap.data or {},
                "binary_data": configmap.binary_data or {}
            }
            
        except ApiException as e:
            raise Exception(f"获取 ConfigMap 详情失败: {e.reason}")

    async def create_configmap(self, name: Optional[str] = None, data: Optional[dict] = None, namespace: str = "default",
                         labels: Optional[dict] = None, resource: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
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
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
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
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
                "data_keys": list(response.data.keys()) if response.data else []
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "configmap", resource_name, namespace, resource_data, create_operation
        )

    async def update_configmap(self, name: str, data: Optional[dict] = None, namespace: str = "default",
                         labels: Optional[dict] = None, resource: Optional[Dict] = None) -> Dict[str, Any]:
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
                    label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
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
                    "created": to_local_time_str(secret.metadata.creation_timestamp) if secret.metadata.creation_timestamp else None,
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
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
                "type": response.type,
                "data_keys": list(response.data.keys()) if response.data else [],
                "labels": response.metadata.labels,
                "decoded_data": decoded_data
            }
        except ApiException as e:
            raise Exception(f"获取 Secret 失败: {e}") 

    async def create_secret(self, name: Optional[str] = None, data: Optional[dict] = None, namespace: str = "default",
                      secret_type: str = "Opaque", labels: Optional[dict] = None, resource: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
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
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
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
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
                "type": response.type,
                "data_keys": list(response.data.keys()) if response.data else []
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "secret", resource_name, namespace, resource_data, create_operation
        )

    async def update_secret(self, name: str, data: Optional[dict] = None, namespace: str = "default",
                      labels: Optional[dict] = None, resource: Optional[Dict] = None) -> Dict[str, Any]:
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

