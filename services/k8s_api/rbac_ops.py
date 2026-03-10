from typing import Dict, List, Any, Optional
from kubernetes import client
from kubernetes.client.exceptions import ApiException
from utils.k8s_helpers import to_local_time_str

class RbacOpsMixin:
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

    async def create_serviceaccount(self, name: Optional[str] = None, namespace: str = "default", 
                                  labels: Optional[Dict[str, str]] = None,
                                  annotations: Optional[Dict[str, str]] = None,
                                  secrets: Optional[List[str]] = None,
                                  image_pull_secrets: Optional[List[str]] = None,
                                  automount_service_account_token: Optional[bool] = None, resource: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
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
                                  labels: Optional[Dict[str, str]] = None,
                                  annotations: Optional[Dict[str, str]] = None,
                                  secrets: Optional[List[str]] = None,
                                  image_pull_secrets: Optional[List[str]] = None,
                                  automount_service_account_token: Optional[bool] = None, resource: Optional[Dict] = None) -> Dict[str, Any]:
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
                                  grace_period_seconds: Optional[int] = None) -> Dict[str, Any]:
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

    async def list_roles(self, namespace: str = "default", label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
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

    async def create_role(self, name: Optional[str] = None, namespace: str = "default", rules: Optional[list] = None,
                         labels: Optional[dict] = None, annotations: Optional[dict] = None, resource: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
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

    async def update_role(self, name: str, namespace: str = "default", rules: Optional[list] = None,
                         labels: Optional[dict] = None, annotations: Optional[dict] = None, resource: Optional[Dict] = None) -> Dict[str, Any]:
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

    async def list_cluster_roles(self, label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
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

    async def create_cluster_role(self, name: Optional[str] = None, rules: Optional[list] = None,
                                labels: Optional[dict] = None, annotations: Optional[dict] = None, resource: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
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

    async def update_cluster_role(self, name: str, rules: Optional[list] = None,
                                labels: Optional[dict] = None, annotations: Optional[dict] = None, resource: Optional[Dict] = None) -> Dict[str, Any]:
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

    async def list_role_bindings(self, namespace: str = "default", label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
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

    async def create_role_binding(self, name: Optional[str] = None, namespace: str = "default",
                                role_ref: Optional[dict] = None, subjects: Optional[list] = None,
                                labels: Optional[dict] = None, annotations: Optional[dict] = None, resource: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
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
                                role_ref: Optional[dict] = None, subjects: Optional[list] = None,
                                labels: Optional[dict] = None, annotations: Optional[dict] = None, resource: Optional[Dict] = None) -> Dict[str, Any]:
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

    async def list_cluster_role_bindings(self, label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
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

    async def create_cluster_role_binding(self, name: Optional[str] = None, role_ref: Optional[dict] = None,
                                        subjects: Optional[list] = None,
                                        labels: Optional[dict] = None, annotations: Optional[dict] = None, resource: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
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

    async def update_cluster_role_binding(self, name: str, role_ref: Optional[dict] = None,
                                        subjects: Optional[list] = None,
                                        labels: Optional[dict] = None, annotations: Optional[dict] = None, resource: Optional[Dict] = None) -> Dict[str, Any]:
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

