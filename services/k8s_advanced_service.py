"""
Kubernetes 进阶服务层
整合批量操作、备份恢复、资源验证等功能
"""

import json
import yaml
import os
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
from services.k8s_api_service import KubernetesAPIService
from config import DATA_DIR, BACKUP_DIR_NAME


class KubernetesAdvancedService:
    """Kubernetes 进阶服务类
    整合批量操作、备份恢复、资源验证等功能
    """
    
    def __init__(self):
        self.k8s_service = KubernetesAPIService()
        self.k8s_service.load_config()
        self.backup_dir = os.path.join(DATA_DIR, BACKUP_DIR_NAME)
        os.makedirs(self.backup_dir, exist_ok=True)
        self.operation_history = []
    
    # ==================== 批量操作相关方法 ====================
    
    def _get_resource_operation(self, resource_type: str, operation: str, namespace: str = "default"):
        """获取资源操作方法的统一接口"""
        resource_type = resource_type.lower()
        
        # 列表操作映射
        list_operations = {
            "deployment": lambda: self.k8s_service.list_deployments(namespace=namespace),
            "statefulset": lambda: self.k8s_service.list_statefulsets(namespace=namespace),
            "daemonset": lambda: self.k8s_service.list_daemonsets(namespace=namespace),
            "service": lambda: self.k8s_service.list_services(namespace=namespace),
            "configmap": lambda: self.k8s_service.list_configmaps(namespace=namespace),
            "secret": lambda: self.k8s_service.list_secrets(namespace=namespace),
            "job": lambda: self.k8s_service.list_jobs(namespace=namespace),
            "cronjob": lambda: self.k8s_service.list_cronjobs(namespace=namespace),
            "ingress": lambda: self.k8s_service.list_ingresses(namespace=namespace),
            "storageclass": lambda: self.k8s_service.list_storageclasses(),
            "persistentvolume": lambda: self.k8s_service.list_persistentvolumes(),
            "persistentvolumeclaim": lambda: self.k8s_service.list_persistentvolumeclaims(namespace=namespace),
            "role": lambda: self.k8s_service.list_roles(namespace=namespace),
            "clusterrole": lambda: self.k8s_service.list_cluster_roles(),
            "rolebinding": lambda: self.k8s_service.list_role_bindings(namespace=namespace),
            "clusterrolebinding": lambda: self.k8s_service.list_cluster_role_bindings(),
            "serviceaccount": lambda: self.k8s_service.list_serviceaccounts(namespace=namespace),
            "namespace": lambda: self.k8s_service.list_namespaces(),
            "pod": lambda: self.k8s_service.list_pods(namespace=namespace),
            "node": lambda: self.k8s_service.list_nodes(),
        }
        
        # 创建操作映射
        create_operations = {
            "deployment": lambda resource: self.k8s_service.create_deployment(resource=resource, namespace=namespace),
            "statefulset": lambda resource: self.k8s_service.create_statefulset(resource=resource, namespace=namespace),
            "daemonset": lambda resource: self.k8s_service.create_daemonset(resource=resource, namespace=namespace),
            "service": lambda resource: self.k8s_service.create_service(resource=resource, namespace=namespace),
            "configmap": lambda resource: self.k8s_service.create_configmap(resource=resource, namespace=namespace),
            "secret": lambda resource: self.k8s_service.create_secret(resource=resource, namespace=namespace),
            "job": lambda resource: self.k8s_service.create_job(resource=resource, namespace=namespace),
            "cronjob": lambda resource: self.k8s_service.create_cronjob(resource=resource, namespace=namespace),
            "ingress": lambda resource: self.k8s_service.create_ingress(resource=resource, namespace=namespace),
            "storageclass": lambda resource: self.k8s_service.create_storageclass(resource=resource),
            "persistentvolume": lambda resource: self.k8s_service.create_persistentvolume(resource=resource),
            "persistentvolumeclaim": lambda resource: self.k8s_service.create_persistentvolumeclaim(resource=resource, namespace=namespace),
            "role": lambda resource: self.k8s_service.create_role(resource=resource, namespace=namespace),
            "clusterrole": lambda resource: self.k8s_service.create_cluster_role(resource=resource),
            "rolebinding": lambda resource: self.k8s_service.create_role_binding(resource=resource, namespace=namespace),
            "clusterrolebinding": lambda resource: self.k8s_service.create_cluster_role_binding(resource=resource),
            "serviceaccount": lambda resource: self.k8s_service.create_serviceaccount(resource=resource, namespace=namespace),
            "namespace": lambda resource: self.k8s_service.create_namespace(resource=resource),
        }
        
        # 更新操作映射
        update_operations = {
            "deployment": lambda name, resource: self.k8s_service.update_deployment(name=name, namespace=namespace, resource=resource),
            "statefulset": lambda name, resource: self.k8s_service.update_statefulset(name=name, namespace=namespace, resource=resource),
            "daemonset": lambda name, resource: self.k8s_service.update_daemonset(name=name, namespace=namespace, resource=resource),
            "service": lambda name, resource: self.k8s_service.update_service(name=name, namespace=namespace, resource=resource),
            "configmap": lambda name, resource: self.k8s_service.update_configmap(name=name, namespace=namespace, resource=resource),
            "secret": lambda name, resource: self.k8s_service.update_secret(name=name, namespace=namespace, resource=resource),
            "job": lambda name, resource: self.k8s_service.update_job(name=name, namespace=namespace, resource=resource),
            "cronjob": lambda name, resource: self.k8s_service.update_cronjob(name=name, namespace=namespace, resource=resource),
            "ingress": lambda name, resource: self.k8s_service.update_ingress(name=name, namespace=namespace, resource=resource),
            "storageclass": lambda name, resource: self.k8s_service.update_storageclass(name=name, resource=resource),
            "persistentvolume": lambda name, resource: self.k8s_service.update_persistentvolume(name=name, resource=resource),
            "persistentvolumeclaim": lambda name, resource: self.k8s_service.update_persistentvolumeclaim(name=name, namespace=namespace, resource=resource),
            "role": lambda name, resource: self.k8s_service.update_role(name=name, namespace=namespace, resource=resource),
            "clusterrole": lambda name, resource: self.k8s_service.update_cluster_role(name=name, resource=resource),
            "rolebinding": lambda name, resource: self.k8s_service.update_role_binding(name=name, namespace=namespace, resource=resource),
            "clusterrolebinding": lambda name, resource: self.k8s_service.update_cluster_role_binding(name=name, resource=resource),
            "serviceaccount": lambda name, resource: self.k8s_service.update_serviceaccount(name=name, namespace=namespace, resource=resource),
            "namespace": lambda name, resource: self.k8s_service.update_namespace(name=name, resource=resource),
        }
        
        # 删除操作映射（带grace_period_seconds支持）
        delete_operations = {
            "deployment": lambda name, grace: self.k8s_service.delete_deployment(name=name, namespace=namespace, grace_period_seconds=grace),
            "statefulset": lambda name, grace: self.k8s_service.delete_statefulset(name=name, namespace=namespace, grace_period_seconds=grace),
            "daemonset": lambda name, grace: self.k8s_service.delete_daemonset(name=name, namespace=namespace),
            "service": lambda name, grace: self.k8s_service.delete_service(name=name, namespace=namespace),
            "configmap": lambda name, grace: self.k8s_service.delete_configmap(name=name, namespace=namespace),
            "secret": lambda name, grace: self.k8s_service.delete_secret(name=name, namespace=namespace),
            "job": lambda name, grace: self.k8s_service.delete_job(name=name, namespace=namespace),
            "cronjob": lambda name, grace: self.k8s_service.delete_cronjob(name=name, namespace=namespace),
            "ingress": lambda name, grace: self.k8s_service.delete_ingress(name=name, namespace=namespace),
            "storageclass": lambda name, grace: self.k8s_service.delete_storageclass(name=name),
            "persistentvolume": lambda name, grace: self.k8s_service.delete_persistentvolume(name=name),
            "persistentvolumeclaim": lambda name, grace: self.k8s_service.delete_persistentvolumeclaim(name=name, namespace=namespace),
            "role": lambda name, grace: self.k8s_service.delete_role(name=name, namespace=namespace),
            "clusterrole": lambda name, grace: self.k8s_service.delete_cluster_role(name=name),
            "rolebinding": lambda name, grace: self.k8s_service.delete_role_binding(name=name, namespace=namespace),
            "clusterrolebinding": lambda name, grace: self.k8s_service.delete_cluster_role_binding(name=name),
            "serviceaccount": lambda name, grace: self.k8s_service.delete_serviceaccount(name=name, namespace=namespace, grace_period_seconds=grace),
            "namespace": lambda name, grace: self.k8s_service.delete_namespace(name=name),
            "pod": lambda name, grace: self.k8s_service.delete_pod(name=name, namespace=namespace, grace_period_seconds=grace),
        }
        
        operations_map = {
            "list": list_operations,
            "create": create_operations,
            "update": update_operations,
            "delete": delete_operations
        }
        
        if operation not in operations_map:
            raise ValueError(f"不支持的操作类型: {operation}")
        
        if resource_type not in operations_map[operation]:
            raise ValueError(f"资源类型 {resource_type} 不支持 {operation} 操作")
        
        return operations_map[operation][resource_type]

    async def batch_list_resources(self, resource_types: List[str], namespace: str = "default") -> Dict:
        """批量查看资源"""
        results = {"success": [], "failed": [], "total": len(resource_types)}
        
        for resource_type in resource_types:
            try:
                resource_type = resource_type.lower()
                operation_func = self._get_resource_operation(resource_type, "list", namespace)
                result = await operation_func()
                
                results["success"].append({
                    "resource_type": resource_type,
                    "count": len(result) if isinstance(result, list) else 0,
                    "items": result
                })
                
            except Exception as e:
                results["failed"].append({
                    "resource_type": resource_type,
                    "error": str(e)
                })
        
        return results

    async def batch_create_resources(self, resources: List[Dict], namespace: str = "default") -> Dict:
        """批量创建k8s资源"""
        results = {"success": [], "failed": [], "total": len(resources)}
        
        for resource in resources:
            try:
                resource_type = resource.get("kind", "").lower()
                resource_name = resource.get("metadata", {}).get("name", "unknown")
                
                operation_func = self._get_resource_operation(resource_type, "create", namespace)
                result = await operation_func(resource)
                
                results["success"].append({
                    "name": resource_name,
                    "kind": resource_type,
                    "result": result
                })
                
            except Exception as e:
                results["failed"].append({
                    "name": resource.get("metadata", {}).get("name", "unknown"),
                    "kind": resource.get("kind", "unknown"),
                    "error": str(e)
                })
        
        return results
    
    async def batch_update_resources(self, resources: List[Dict], namespace: str = "default") -> Dict:
        """批量更新资源"""
        results = {"success": [], "failed": [], "total": len(resources)}
        
        for resource in resources:
            try:
                resource_type = resource.get("kind", "").lower()
                resource_name = resource.get("metadata", {}).get("name", "unknown")
                
                operation_func = self._get_resource_operation(resource_type, "update", namespace)
                result = await operation_func(resource_name, resource)
                
                results["success"].append({
                    "name": resource_name,
                    "kind": resource_type,
                    "result": result
                })
                
            except Exception as e:
                results["failed"].append({
                    "name": resource.get("metadata", {}).get("name", "unknown"),
                    "kind": resource.get("kind", "unknown"),
                    "error": str(e)
                })
        
        return results
    
    async def batch_delete_resources(self, resources: List[Dict], namespace: str = "default", 
                                   grace_period_seconds: Optional[int] = None) -> Dict:
        """批量删除资源"""
        results = {"success": [], "failed": [], "total": len(resources)}
        
        for resource in resources:
            try:
                resource_type = resource.get("kind", "").lower()
                resource_name = resource.get("metadata", {}).get("name", "unknown")
                
                operation_func = self._get_resource_operation(resource_type, "delete", namespace)
                result = await operation_func(resource_name, grace_period_seconds)
                
                results["success"].append({
                    "name": resource_name,
                    "kind": resource_type,
                    "result": result
                })
                
            except Exception as e:
                results["failed"].append({
                    "name": resource.get("metadata", {}).get("name", "unknown"),
                    "kind": resource.get("kind", "unknown"),
                    "error": str(e)
                })
        
        return results    
    # ==================== 备份恢复相关方法 ====================
    
    def _get_backup_path(self, cluster_name: str, namespace: str = None, 
                         resource_type: str = None, resource_name: str = None) -> str:
        """获取备份文件路径"""
        path_parts = [self.backup_dir, cluster_name]
        
        if namespace:
            path_parts.append("namespaces")
            path_parts.append(namespace)
        
        if resource_type:
            path_parts.append("resources")
            path_parts.append(resource_type)
        
        if resource_name:
            path_parts.append(resource_name)
        
        backup_path = os.path.join(*path_parts)
        os.makedirs(backup_path, exist_ok=True)
        
        return backup_path
    
    async def backup_namespace(self, namespace: str, cluster_name: str = None, 
                             include_secrets: bool = False) -> str:
        """备份整个命名空间的资源"""
        if not cluster_name:
            # 获取当前集群名称
            cluster_info = await self.k8s_service.get_cluster_info()
            cluster_name = cluster_info.get("cluster_name", "default")
        
        backup_data = {
            "metadata": {
                "cluster_name": cluster_name,
                "namespace": namespace,
                "timestamp": datetime.now().isoformat(),
                "version": "v1",
                "include_secrets": include_secrets
            },
            "resources": {}
        }
        
        # 备份各种资源
        resource_types = [
            "pods", "deployments", "statefulsets", "daemonsets",
            "services", "configmaps", "secrets", "jobs", "cronjobs", "ingresses", 
            "storageclasses", "persistentvolumes", "persistentvolumeclaims", 
            "serviceaccounts", "roles", "clusterroles", "rolebindings", "clusterrolebindings"
        ]
        
        if include_secrets:
            resource_types.append("secrets")
        
        for resource_type in resource_types:
            try:
                if resource_type == "pods":
                    resources = await self.k8s_service.list_pods(namespace=namespace)
                elif resource_type == "deployments":
                    resources = await self.k8s_service.list_deployments(namespace=namespace)
                elif resource_type == "statefulsets":
                    resources = await self.k8s_service.list_statefulsets(namespace=namespace)
                elif resource_type == "daemonsets":
                    resources = await self.k8s_service.list_daemonsets(namespace=namespace)
                elif resource_type == "services":
                    resources = await self.k8s_service.list_services(namespace=namespace)
                elif resource_type == "configmaps":
                    resources = await self.k8s_service.list_configmaps(namespace=namespace)
                elif resource_type == "secrets":
                    resources = await self.k8s_service.list_secrets(namespace=namespace)
                elif resource_type == "jobs":
                    resources = await self.k8s_service.list_jobs(namespace=namespace)
                elif resource_type == "cronjobs":
                    resources = await self.k8s_service.list_cronjobs(namespace=namespace)
                elif resource_type == "ingresses":
                    resources = await self.k8s_service.list_ingresses(namespace=namespace)
                elif resource_type == "storageclasses":
                    resources = await self.k8s_service.list_storageclasses()
                elif resource_type == "persistentvolumes":
                    resources = await self.k8s_service.list_persistentvolumes()
                elif resource_type == "persistentvolumeclaims":
                    resources = await self.k8s_service.list_persistentvolumeclaims(namespace=namespace)
                elif resource_type == "serviceaccounts":
                    resources = await self.k8s_service.list_serviceaccounts(namespace=namespace)
                elif resource_type == "roles":
                    resources = await self.k8s_service.list_roles(namespace=namespace)
                elif resource_type == "clusterroles":
                    resources = await self.k8s_service.list_cluster_roles()
                elif resource_type == "rolebindings":
                    resources = await self.k8s_service.list_role_bindings(namespace=namespace)
                elif resource_type == "clusterrolebindings":
                    resources = await self.k8s_service.list_cluster_role_bindings()
                
                backup_data["resources"][resource_type] = resources
                
            except Exception as e:
                print(f"备份 {resource_type} 失败: {e}")
                backup_data["resources"][resource_type] = {"error": str(e)}
        
        # 保存备份文件
        backup_path = self._get_backup_path(cluster_name, namespace)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_path, f"namespace_backup_{timestamp}.json")
        
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
        
        return backup_file
    
    async def backup_specific_resource(self, resource_type: str, resource_name: str, 
                                     namespace: str, cluster_name: str = None) -> str:
        """备份特定资源"""
        if not cluster_name:
            cluster_info = await self.k8s_service.get_cluster_info()
            cluster_name = cluster_info.get("cluster_name", "default")
        
        try:
            # 获取特定资源
            if resource_type == "deployment":
                resource_data = await self.k8s_service.get_deployment(resource_name, namespace)
            elif resource_type == "service":
                resource_data = await self.k8s_service.get_service(resource_name, namespace)
            elif resource_type == "configmap":
                resource_data = await self.k8s_service.get_configmap(resource_name, namespace)
            elif resource_type == "secret":
                resource_data = await self.k8s_service.get_secret(resource_name, namespace)
            elif resource_type == "persistentvolumeclaim":
                resource_data = await self.k8s_service.get_persistentvolumeclaim(resource_name, namespace)
            elif resource_type == "ingress":
                resource_data = await self.k8s_service.get_ingress(resource_name, namespace)
            else:
                raise ValueError(f"不支持的资源类型: {resource_type}")
            
            backup_data = {
                "metadata": {
                    "cluster_name": cluster_name,
                    "namespace": namespace,
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                    "timestamp": datetime.now().isoformat(),
                    "version": "v1"
                },
                "resource": resource_data
            }
            
            # 保存备份文件
            backup_path = self._get_backup_path(cluster_name, namespace, resource_type, resource_name)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(backup_path, f"{resource_name}_{timestamp}.json")
            
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
            
            return backup_file
            
        except Exception as e:
            raise Exception(f"备份资源失败: {e}")
    
    async def restore_from_backup(self, backup_file: str, target_namespace: str = None, 
                                target_cluster: str = None) -> Dict:
        """从备份文件恢复资源"""
        if not os.path.exists(backup_file):
            raise FileNotFoundError(f"备份文件不存在: {backup_file}")
        
        with open(backup_file, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
        
        metadata = backup_data["metadata"]
        original_namespace = metadata["namespace"]
        original_cluster = metadata["cluster_name"]
        
        target_namespace = target_namespace or original_namespace
        target_cluster = target_cluster or original_cluster
        
        results = {"success": [], "failed": [], "total": 0}
        
        # 如果是命名空间备份
        if "resources" in backup_data:
            for resource_type, resources in backup_data["resources"].items():
                if isinstance(resources, dict) and "error" in resources:
                    results["failed"].append({
                        "resource_type": resource_type,
                        "error": resources["error"]
                    })
                    continue
                
                for resource in resources:
                    try:
                        # 修改命名空间
                        if "metadata" in resource:
                            resource["metadata"]["namespace"] = target_namespace
                        
                        # 根据资源类型调用相应的创建方法
                        if resource_type == "deployments":
                            await self.k8s_service.create_deployment(**resource)
                        elif resource_type == "services":
                            await self.k8s_service.create_service(**resource)
                        elif resource_type == "configmaps":
                            await self.k8s_service.create_configmap(**resource)
                        elif resource_type == "secrets":
                            await self.k8s_service.create_secret(**resource)
                        elif resource_type == "persistentvolumeclaims":
                            await self.k8s_service.create_persistentvolumeclaim(**resource)
                        elif resource_type == "ingresses":
                            await self.k8s_service.create_ingress(**resource)
                        elif resource_type == "jobs":
                            await self.k8s_service.create_job(**resource)
                        elif resource_type == "cronjobs":
                            await self.k8s_service.create_cronjob(**resource)
                        
                        results["success"].append(f"{resource_type}/{resource['metadata']['name']}")
                        results["total"] += 1
                        
                    except Exception as e:
                        results["failed"].append({
                            "resource": f"{resource_type}/{resource.get('metadata', {}).get('name', 'unknown')}",
                            "error": str(e)
                        })
        
        # 如果是单个资源备份
        elif "resource" in backup_data:
            resource = backup_data["resource"]
            resource_type = metadata["resource_type"]
            
            try:
                # 修改命名空间
                if "metadata" in resource:
                    resource["metadata"]["namespace"] = target_namespace
                
                # 根据资源类型调用相应的创建方法
                if resource_type == "deployment":
                    await self.k8s_service.create_deployment(**resource)
                elif resource_type == "service":
                    await self.k8s_service.create_service(**resource)
                elif resource_type == "configmap":
                    await self.k8s_service.create_configmap(**resource)
                elif resource_type == "secret":
                    await self.k8s_service.create_secret(**resource)
                elif resource_type == "persistentvolumeclaim":
                    await self.k8s_service.create_persistentvolumeclaim(**resource)
                elif resource_type == "ingress":
                    await self.k8s_service.create_ingress(**resource)
                
                results["success"].append(f"{resource_type}/{resource['metadata']['name']}")
                results["total"] += 1
                
            except Exception as e:
                results["failed"].append({
                    "resource": f"{resource_type}/{resource.get('metadata', {}).get('name', 'unknown')}",
                    "error": str(e)
                })
        
        return results
    
    def list_backups(self, cluster_name: str = None, namespace: str = None) -> List[Dict]:
        """列出备份文件"""
        backups = []
        
        if cluster_name:
            search_path = self._get_backup_path(cluster_name, namespace)
        else:
            search_path = self.backup_dir
        
        if not os.path.exists(search_path):
            return backups
        
        for root, dirs, files in os.walk(search_path):
            for file in files:
                if file.endswith('.json'):
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, self.backup_dir)
                    
                    # 解析路径信息
                    path_parts = relative_path.split(os.sep)
                    
                    backup_info = {
                        "file_path": file_path,
                        "relative_path": relative_path,
                        "cluster_name": path_parts[0] if len(path_parts) > 0 else "unknown",
                        "namespace": None,
                        "resource_type": None,
                        "resource_name": None,
                        "timestamp": file.split('_')[-1].replace('.json', '') if '_' in file else "unknown"
                    }
                    
                    # 解析路径结构
                    if len(path_parts) > 2 and path_parts[1] == "namespaces":
                        backup_info["namespace"] = path_parts[2]
                    
                    if len(path_parts) > 4 and path_parts[3] == "resources":
                        backup_info["resource_type"] = path_parts[4]
                        if len(path_parts) > 5:
                            backup_info["resource_name"] = path_parts[5]
                    
                    backups.append(backup_info)
        
        return sorted(backups, key=lambda x: x["timestamp"], reverse=True)

    # ==================== RBAC相关方法 ====================
    
    async def create_developer_role(self, namespace: str, role_name: str = "developer") -> Dict:
        """创建开发者角色（只读权限）"""
        rules = [
            {
                "api_groups": [""],
                "resources": ["pods", "services", "configmaps", "persistentvolumeclaims"],
                "verbs": ["get", "list", "watch"]
            },
            {
                "api_groups": ["apps"],
                "resources": ["deployments", "statefulsets", "daemonsets"],
                "verbs": ["get", "list", "watch"]
            },
            {
                "api_groups": ["networking.k8s.io"],
                "resources": ["ingresses"],
                "verbs": ["get", "list", "watch"]
            },
            {
                "api_groups": ["batch"],
                "resources": ["jobs", "cronjobs"],
                "verbs": ["get", "list", "watch"]
            }
        ]
        
        return await self.k8s_service.create_role(role_name, namespace, rules)
    
    async def create_admin_role(self, namespace: str, role_name: str = "admin") -> Dict:
        """创建管理员角色（完全权限）"""
        rules = [
            {
                "api_groups": [""],
                "resources": ["*"],
                "verbs": ["*"]
            },
            {
                "api_groups": ["apps"],
                "resources": ["*"],
                "verbs": ["*"]
            },
            {
                "api_groups": ["networking.k8s.io"],
                "resources": ["*"],
                "verbs": ["*"]
            },
            {
                "api_groups": ["batch"],
                "resources": ["*"],
                "verbs": ["*"]
            },
            {
                "api_groups": ["rbac.authorization.k8s.io"],
                "resources": ["*"],
                "verbs": ["*"]
            }
        ]
        
        return await self.k8s_service.create_role(role_name, namespace, rules)
    
    async def create_operator_role(self, namespace: str, role_name: str = "operator") -> Dict:
        """创建运维角色（管理权限，但不包括RBAC）"""
        rules = [
            {
                "api_groups": [""],
                "resources": ["pods", "services", "configmaps", "secrets", "persistentvolumeclaims"],
                "verbs": ["*"]
            },
            {
                "api_groups": ["apps"],
                "resources": ["deployments", "statefulsets", "daemonsets"],
                "verbs": ["*"]
            },
            {
                "api_groups": ["networking.k8s.io"],
                "resources": ["ingresses"],
                "verbs": ["*"]
            },
            {
                "api_groups": ["batch"],
                "resources": ["jobs", "cronjobs"],
                "verbs": ["*"]
            }
        ]
        
        return await self.k8s_service.create_role(role_name, namespace, rules)

    # ==================== 资源验证相关方法 ====================
    
    async def get_resource_before_operation(self, resource_type: str, resource_name: str, 
                                           namespace: str = "default") -> Dict:
        """获取操作前的资源状态"""
        try:
            if resource_type == "deployment":
                return await self.k8s_service.get_deployment(resource_name, namespace)
            elif resource_type == "statefulset":
                return await self.k8s_service.get_statefulset(resource_name, namespace)
            elif resource_type == "daemonset":
                return await self.k8s_service.get_daemonset(resource_name, namespace)
            elif resource_type == "service":
                return await self.k8s_service.get_service(resource_name, namespace)
            elif resource_type == "configmap":
                return await self.k8s_service.get_configmap(resource_name, namespace)
            elif resource_type == "secret":
                return await self.k8s_service.get_secret(resource_name, namespace)
            elif resource_type == "job":
                return await self.k8s_service.get_job(resource_name, namespace)
            elif resource_type == "cronjob":
                return await self.k8s_service.get_cronjob(resource_name, namespace)
            elif resource_type == "ingress":
                return await self.k8s_service.get_ingress(resource_name, namespace)
            elif resource_type == "storageclass":
                return await self.k8s_service.get_storageclass(resource_name)
            elif resource_type == "persistentvolume":
                return await self.k8s_service.get_persistentvolume(resource_name)
            elif resource_type == "persistentvolumeclaim":
                return await self.k8s_service.get_persistentvolumeclaim(resource_name, namespace)
            elif resource_type == "serviceaccount":
                return await self.k8s_service.get_serviceaccount(resource_name, namespace)
            elif resource_type == "role":
                return await self.k8s_service.get_role(resource_name, namespace)
            elif resource_type == "clusterrole":
                return await self.k8s_service.get_cluster_role(resource_name)
            elif resource_type == "rolebinding":
                return await self.k8s_service.get_role_binding(resource_name, namespace)
            elif resource_type == "clusterrolebinding":
                return await self.k8s_service.get_cluster_role_binding(resource_name)
            elif resource_type == "namespace":
                # 命名空间资源不需要指定命名空间
                namespaces = await self.k8s_service.list_namespaces()
                for ns in namespaces:
                    if ns["name"] == resource_name:
                        return ns
                return {"error": f"命名空间 {resource_name} 不存在"}
            else:
                raise ValueError(f"不支持的资源类型: {resource_type}")
        except Exception as e:
            return {"error": str(e)}

    async def get_resource_after_operation(self, resource_type: str, resource_name: str, 
                                          namespace: str = "default") -> Dict:
        """获取操作后的资源状态"""
        return await self.get_resource_before_operation(resource_type, resource_name, namespace)
    
    # ==================== Deployment 比较和验证方法 ====================
    
    def compare_deployment_changes(self, before: Dict, after: Dict) -> Dict:
        """比较Deployment的变化"""
        changes = {
            "replicas": None,
            "image": None,
            "labels": None,
            "annotations": None,
            "resources": None,
            "env_vars": None
        }
        
        if before.get("error") or after.get("error"):
            return {"error": "无法获取资源状态"}
        
        # 比较副本数
        before_replicas = before.get("spec", {}).get("replicas", 0)
        after_replicas = after.get("spec", {}).get("replicas", 0)
        if before_replicas != after_replicas:
            changes["replicas"] = {
                "before": before_replicas,
                "after": after_replicas,
                "change": f"{before_replicas} -> {after_replicas}"
            }
        
        # 比较镜像
        before_containers = before.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        after_containers = after.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        
        if before_containers and after_containers:
            before_image = before_containers[0].get("image", "")
            after_image = after_containers[0].get("image", "")
            if before_image != after_image:
                changes["image"] = {
                    "before": before_image,
                    "after": after_image,
                    "change": f"{before_image} -> {after_image}"
                }
        
        # 比较标签
        before_labels = before.get("metadata", {}).get("labels", {})
        after_labels = after.get("metadata", {}).get("labels", {})
        if before_labels != after_labels:
            changes["labels"] = {
                "before": before_labels,
                "after": after_labels
            }
        
        # 比较注解
        before_annotations = before.get("metadata", {}).get("annotations", {})
        after_annotations = after.get("metadata", {}).get("annotations", {})
        if before_annotations != after_annotations:
            changes["annotations"] = {
                "before": before_annotations,
                "after": after_annotations
            }
        
        # 比较资源限制
        if before_containers and after_containers:
            before_resources = before_containers[0].get("resources", {})
            after_resources = after_containers[0].get("resources", {})
            if before_resources != after_resources:
                changes["resources"] = {
                    "before": before_resources,
                    "after": after_resources
                }
        
        # 比较环境变量
        if before_containers and after_containers:
            before_env = before_containers[0].get("env", [])
            after_env = after_containers[0].get("env", [])
            if before_env != after_env:
                changes["env_vars"] = {
                    "before": before_env,
                    "after": after_env
                }
        
        return changes

    async def validate_deployment_operation(self, name: str, namespace: str = "default",
                                          operation: str = "update", **kwargs) -> Dict:
        """验证Deployment操作"""
        try:
            # 获取操作前的状态
            before_state = await self.get_resource_before_operation("deployment", name, namespace)
            
            # 执行操作
            if operation == "update":
                if "replicas" in kwargs:
                    await self.k8s_service.update_deployment(name, namespace, replicas=kwargs["replicas"])
                if "image" in kwargs:
                    await self.k8s_service.update_deployment(name, namespace, image=kwargs["image"])
                if "labels" in kwargs:
                    await self.k8s_service.update_deployment(name, namespace, labels=kwargs["labels"])
            
            # 获取操作后的状态
            after_state = await self.get_resource_after_operation("deployment", name, namespace)
            
            # 比较变化
            changes = self.compare_deployment_changes(before_state, after_state)
            
            return {
                "success": True,
                "operation": operation,
                "resource": f"deployment/{name}",
                "namespace": namespace,
                "before": before_state,
                "after": after_state,
                "changes": changes
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "operation": operation,
                "resource": f"deployment/{name}",
                "namespace": namespace
            }
    
    # ==================== StatefulSet 比较和验证方法 ====================
    
    def compare_statefulset_changes(self, before: Dict, after: Dict) -> Dict:
        """比较StatefulSet的变化"""
        changes = {
            "replicas": None,
            "image": None,
            "labels": None,
            "annotations": None,
            "resources": None,
            "env_vars": None,
            "volume_claims": None
        }
        
        if before.get("error") or after.get("error"):
            return {"error": "无法获取资源状态"}
        
        # 比较副本数
        before_replicas = before.get("spec", {}).get("replicas", 0)
        after_replicas = after.get("spec", {}).get("replicas", 0)
        if before_replicas != after_replicas:
            changes["replicas"] = {
                "before": before_replicas,
                "after": after_replicas,
                "change": f"{before_replicas} -> {after_replicas}"
            }
        
        # 比较镜像
        before_containers = before.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        after_containers = after.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        
        if before_containers and after_containers:
            before_image = before_containers[0].get("image", "")
            after_image = after_containers[0].get("image", "")
            if before_image != after_image:
                changes["image"] = {
                    "before": before_image,
                    "after": after_image,
                    "change": f"{before_image} -> {after_image}"
                }
        
        # 比较标签
        before_labels = before.get("metadata", {}).get("labels", {})
        after_labels = after.get("metadata", {}).get("labels", {})
        if before_labels != after_labels:
            changes["labels"] = {
                "before": before_labels,
                "after": after_labels
            }
        
        # 比较注解
        before_annotations = before.get("metadata", {}).get("annotations", {})
        after_annotations = after.get("metadata", {}).get("annotations", {})
        if before_annotations != after_annotations:
            changes["annotations"] = {
                "before": before_annotations,
                "after": after_annotations
            }
        
        # 比较资源限制
        if before_containers and after_containers:
            before_resources = before_containers[0].get("resources", {})
            after_resources = after_containers[0].get("resources", {})
            if before_resources != after_resources:
                changes["resources"] = {
                    "before": before_resources,
                    "after": after_resources
                }
                
        # 比较卷声明模板
        before_vct = before.get("spec", {}).get("volumeClaimTemplates", [])
        after_vct = after.get("spec", {}).get("volumeClaimTemplates", [])
        if before_vct != after_vct:
            changes["volume_claims"] = {
                "before": before_vct,
                "after": after_vct
            }
        
        return changes
    
    async def validate_statefulset_operation(self, name: str, namespace: str = "default",
                                          operation: str = "update", **kwargs) -> Dict:
        """验证StatefulSet操作"""
        try:
            # 获取操作前的状态
            before_state = await self.get_resource_before_operation("statefulset", name, namespace)
            
            # 执行操作
            if operation == "update":
                if "replicas" in kwargs:
                    await self.k8s_service.update_statefulset(name, namespace, replicas=kwargs["replicas"])
                if "image" in kwargs:
                    await self.k8s_service.update_statefulset(name, namespace, image=kwargs["image"])
                if "labels" in kwargs:
                    await self.k8s_service.update_statefulset(name, namespace, labels=kwargs["labels"])
                if "env_vars" in kwargs:
                    await self.k8s_service.update_statefulset(name, namespace, env_vars=kwargs["env_vars"])
            
            # 获取操作后的状态
            after_state = await self.get_resource_after_operation("statefulset", name, namespace)
            
            # 比较变化
            changes = self.compare_statefulset_changes(before_state, after_state)
            
            return {
                "success": True,
                "operation": operation,
                "resource": f"statefulset/{name}",
                "namespace": namespace,
                "before": before_state,
                "after": after_state,
                "changes": changes
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "operation": operation,
                "resource": f"statefulset/{name}",
                "namespace": namespace
            }
    
    # ==================== DaemonSet 比较和验证方法 ====================
    
    def compare_daemonset_changes(self, before: Dict, after: Dict) -> Dict:
        """比较DaemonSet的变化"""
        changes = {
            "image": None,
            "labels": None,
            "annotations": None,
            "resources": None,
            "env_vars": None
        }
        
        if before.get("error") or after.get("error"):
            return {"error": "无法获取资源状态"}
        
        # 比较镜像
        before_containers = before.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        after_containers = after.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        
        if before_containers and after_containers:
            before_image = before_containers[0].get("image", "")
            after_image = after_containers[0].get("image", "")
            if before_image != after_image:
                changes["image"] = {
                    "before": before_image,
                    "after": after_image,
                    "change": f"{before_image} -> {after_image}"
                }
        
        # 比较标签
        before_labels = before.get("metadata", {}).get("labels", {})
        after_labels = after.get("metadata", {}).get("labels", {})
        if before_labels != after_labels:
            changes["labels"] = {
                "before": before_labels,
                "after": after_labels
            }
        
        # 比较注解
        before_annotations = before.get("metadata", {}).get("annotations", {})
        after_annotations = after.get("metadata", {}).get("annotations", {})
        if before_annotations != after_annotations:
            changes["annotations"] = {
                "before": before_annotations,
                "after": after_annotations
            }
        
        # 比较资源限制
        if before_containers and after_containers:
            before_resources = before_containers[0].get("resources", {})
            after_resources = after_containers[0].get("resources", {})
            if before_resources != after_resources:
                changes["resources"] = {
                    "before": before_resources,
                    "after": after_resources
                }
        
        return changes
    
    async def validate_daemonset_operation(self, name: str, namespace: str = "default",
                                         operation: str = "update", **kwargs) -> Dict:
        """验证DaemonSet操作"""
        try:
            # 获取操作前的状态
            before_state = await self.get_resource_before_operation("daemonset", name, namespace)
            
            # 执行操作
            if operation == "update":
                if "image" in kwargs:
                    await self.k8s_service.update_daemonset(name, namespace, image=kwargs["image"])
                if "labels" in kwargs:
                    await self.k8s_service.update_daemonset(name, namespace, labels=kwargs["labels"])
                if "env_vars" in kwargs:
                    await self.k8s_service.update_daemonset(name, namespace, env_vars=kwargs["env_vars"])
            
            # 获取操作后的状态
            after_state = await self.get_resource_after_operation("daemonset", name, namespace)
            
            # 比较变化
            changes = self.compare_daemonset_changes(before_state, after_state)
            
            return {
                "success": True,
                "operation": operation,
                "resource": f"daemonset/{name}",
                "namespace": namespace,
                "before": before_state,
                "after": after_state,
                "changes": changes
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "operation": operation,
                "resource": f"daemonset/{name}",
                "namespace": namespace
            }
    
    # ==================== Service 比较和验证方法 ====================
    
    def compare_service_changes(self, before: Dict, after: Dict) -> Dict:
        """比较Service的变化"""
        changes = {
            "service_type": None,
            "ports": None,
            "selector": None,
            "labels": None,
            "annotations": None
        }
        
        if before.get("error") or after.get("error"):
            return {"error": "无法获取资源状态"}
        
        # 比较服务类型
        before_type = before.get("spec", {}).get("type", "")
        after_type = after.get("spec", {}).get("type", "")
        if before_type != after_type:
            changes["service_type"] = {
                "before": before_type,
                "after": after_type,
                "change": f"{before_type} -> {after_type}"
            }
        
        # 比较端口
        before_ports = before.get("spec", {}).get("ports", [])
        after_ports = after.get("spec", {}).get("ports", [])
        if before_ports != after_ports:
            changes["ports"] = {
                "before": before_ports,
                "after": after_ports
            }
        
        # 比较选择器
        before_selector = before.get("spec", {}).get("selector", {})
        after_selector = after.get("spec", {}).get("selector", {})
        if before_selector != after_selector:
            changes["selector"] = {
                "before": before_selector,
                "after": after_selector
            }
        
        # 比较标签和注解
        before_labels = before.get("metadata", {}).get("labels", {})
        after_labels = after.get("metadata", {}).get("labels", {})
        if before_labels != after_labels:
            changes["labels"] = {
                "before": before_labels,
                "after": after_labels
            }
        
        before_annotations = before.get("metadata", {}).get("annotations", {})
        after_annotations = after.get("metadata", {}).get("annotations", {})
        if before_annotations != after_annotations:
            changes["annotations"] = {
                "before": before_annotations,
                "after": after_annotations
            }
        
        return changes

    async def validate_service_operation(self, name: str, namespace: str = "default",
                                        operation: str = "update", **kwargs) -> Dict:
        """验证Service操作"""
        try:
            # 获取操作前的状态
            before_state = await self.get_resource_before_operation("service", name, namespace)
            
            # 执行操作
            if operation == "update":
                if "service_type" in kwargs:
                    await self.k8s_service.update_service(name, namespace, service_type=kwargs["service_type"])
                if "ports" in kwargs:
                    await self.k8s_service.update_service(name, namespace, ports=kwargs["ports"])
                if "selector" in kwargs:
                    await self.k8s_service.update_service(name, namespace, selector=kwargs["selector"])
                if "labels" in kwargs:
                    await self.k8s_service.update_service(name, namespace, labels=kwargs["labels"])
                if "annotations" in kwargs:
                    await self.k8s_service.update_service(name, namespace, annotations=kwargs["annotations"])
            
            # 获取操作后的状态
            after_state = await self.get_resource_after_operation("service", name, namespace)
            
            # 比较变化
            changes = self.compare_service_changes(before_state, after_state)
            
            return {
                "success": True,
                "operation": operation,
                "resource": f"service/{name}",
                "namespace": namespace,
                "before": before_state,
                "after": after_state,
                "changes": changes
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "operation": operation,
                "resource": f"service/{name}",
                "namespace": namespace
            }
    
    # ==================== ConfigMap 比较和验证方法 ====================
    
    def compare_configmap_changes(self, before: Dict, after: Dict) -> Dict:
        """比较ConfigMap的变化"""
        changes = {
            "data": None,
            "binary_data": None,
            "labels": None,
            "annotations": None
        }
        
        if before.get("error") or after.get("error"):
            return {"error": "无法获取资源状态"}
        
        # 比较数据
        before_data = before.get("data", {})
        after_data = after.get("data", {})
        if before_data != after_data:
            changes["data"] = {
                "before": before_data,
                "after": after_data
            }
        
        # 比较二进制数据
        before_binary_data = before.get("binary_data", {})
        after_binary_data = after.get("binary_data", {})
        if before_binary_data != after_binary_data:
            changes["binary_data"] = {
                "before": before_binary_data,
                "after": after_binary_data
            }
        
        # 比较标签
        before_labels = before.get("metadata", {}).get("labels", {})
        after_labels = after.get("metadata", {}).get("labels", {})
        if before_labels != after_labels:
            changes["labels"] = {
                "before": before_labels,
                "after": after_labels
            }
        
        # 比较注解
        before_annotations = before.get("metadata", {}).get("annotations", {})
        after_annotations = after.get("metadata", {}).get("annotations", {})
        if before_annotations != after_annotations:
            changes["annotations"] = {
                "before": before_annotations,
                "after": after_annotations
            }
        
        return changes
    
    async def validate_configmap_operation(self, name: str, namespace: str = "default",
                                         operation: str = "update", **kwargs) -> Dict:
        """验证ConfigMap操作"""
        try:
            # 获取操作前的状态
            before_state = await self.get_resource_before_operation("configmap", name, namespace)
            
            # 执行操作
            if operation == "update":
                if "data" in kwargs:
                    await self.k8s_service.update_configmap(name, namespace, data=kwargs["data"])
                if "binary_data" in kwargs:
                    await self.k8s_service.update_configmap(name, namespace, binary_data=kwargs["binary_data"])
                if "labels" in kwargs:
                    await self.k8s_service.update_configmap(name, namespace, labels=kwargs["labels"])
                if "annotations" in kwargs:
                    await self.k8s_service.update_configmap(name, namespace, annotations=kwargs["annotations"])
            
            # 获取操作后的状态
            after_state = await self.get_resource_after_operation("configmap", name, namespace)
            
            # 比较变化
            changes = self.compare_configmap_changes(before_state, after_state)
            
            return {
                "success": True,
                "operation": operation,
                "resource": f"configmap/{name}",
                "namespace": namespace,
                "before": before_state,
                "after": after_state,
                "changes": changes
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "operation": operation,
                "resource": f"configmap/{name}",
                "namespace": namespace
            }
    
    # ==================== Secret 比较和验证方法 ====================
    
    def compare_secret_changes(self, before: Dict, after: Dict) -> Dict:
        """比较Secret的变化"""
        changes = {
            "data": None,
            "type": None,
            "labels": None,
            "annotations": None
        }
        
        if before.get("error") or after.get("error"):
            return {"error": "无法获取资源状态"}
        
        # 比较数据 (注意: 实际值可能是加密的)
        before_data = before.get("data", {})
        after_data = after.get("data", {})
        if before_data != after_data:
            # 只比较键名，不比较具体值
            before_keys = set(before_data.keys())
            after_keys = set(after_data.keys())
            changes["data"] = {
                "before_keys": list(before_keys),
                "after_keys": list(after_keys),
                "added_keys": list(after_keys - before_keys),
                "removed_keys": list(before_keys - after_keys)
            }
        
        # 比较类型
        before_type = before.get("type", "")
        after_type = after.get("type", "")
        if before_type != after_type:
            changes["type"] = {
                "before": before_type,
                "after": after_type,
                "change": f"{before_type} -> {after_type}"
            }
        
        # 比较标签
        before_labels = before.get("metadata", {}).get("labels", {})
        after_labels = after.get("metadata", {}).get("labels", {})
        if before_labels != after_labels:
            changes["labels"] = {
                "before": before_labels,
                "after": after_labels
            }
        
        # 比较注解
        before_annotations = before.get("metadata", {}).get("annotations", {})
        after_annotations = after.get("metadata", {}).get("annotations", {})
        if before_annotations != after_annotations:
            changes["annotations"] = {
                "before": before_annotations,
                "after": after_annotations
            }
        
        return changes
    
    async def validate_secret_operation(self, name: str, namespace: str = "default",
                                      operation: str = "update", **kwargs) -> Dict:
        """验证Secret操作"""
        try:
            # 获取操作前的状态
            before_state = await self.get_resource_before_operation("secret", name, namespace)
            
            # 执行操作
            if operation == "update":
                if "data" in kwargs:
                    await self.k8s_service.update_secret(name, namespace, data=kwargs["data"])
                if "string_data" in kwargs:
                    await self.k8s_service.update_secret(name, namespace, string_data=kwargs["string_data"])
                if "type" in kwargs:
                    await self.k8s_service.update_secret(name, namespace, type=kwargs["type"])
                if "labels" in kwargs:
                    await self.k8s_service.update_secret(name, namespace, labels=kwargs["labels"])
                if "annotations" in kwargs:
                    await self.k8s_service.update_secret(name, namespace, annotations=kwargs["annotations"])
            
            # 获取操作后的状态
            after_state = await self.get_resource_after_operation("secret", name, namespace)
            
            # 比较变化
            changes = self.compare_secret_changes(before_state, after_state)
            
            return {
                "success": True,
                "operation": operation,
                "resource": f"secret/{name}",
                "namespace": namespace,
                "before": before_state,
                "after": after_state,
                "changes": changes
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "operation": operation,
                "resource": f"secret/{name}",
                "namespace": namespace
            }
    
    # ==================== Job 比较和验证方法 ====================
    
    def compare_job_changes(self, before: Dict, after: Dict) -> Dict:
        """比较Job的变化"""
        changes = {
            "parallelism": None,
            "completions": None,
            "active_deadline_seconds": None,
            "backoff_limit": None,
            "labels": None,
            "annotations": None
        }
        
        if before.get("error") or after.get("error"):
            return {"error": "无法获取资源状态"}
        
        # 比较并行度
        before_parallelism = before.get("spec", {}).get("parallelism")
        after_parallelism = after.get("spec", {}).get("parallelism")
        if before_parallelism != after_parallelism:
            changes["parallelism"] = {
                "before": before_parallelism,
                "after": after_parallelism,
                "change": f"{before_parallelism} -> {after_parallelism}"
            }
        
        # 比较完成数
        before_completions = before.get("spec", {}).get("completions")
        after_completions = after.get("spec", {}).get("completions")
        if before_completions != after_completions:
            changes["completions"] = {
                "before": before_completions,
                "after": after_completions,
                "change": f"{before_completions} -> {after_completions}"
            }
        
        # 比较活动截止时间
        before_deadline = before.get("spec", {}).get("activeDeadlineSeconds")
        after_deadline = after.get("spec", {}).get("activeDeadlineSeconds")
        if before_deadline != after_deadline:
            changes["active_deadline_seconds"] = {
                "before": before_deadline,
                "after": after_deadline,
                "change": f"{before_deadline} -> {after_deadline}"
            }
        
        # 比较回退限制
        before_backoff = before.get("spec", {}).get("backoffLimit")
        after_backoff = after.get("spec", {}).get("backoffLimit")
        if before_backoff != after_backoff:
            changes["backoff_limit"] = {
                "before": before_backoff,
                "after": after_backoff,
                "change": f"{before_backoff} -> {after_backoff}"
            }
        
        # 比较标签
        before_labels = before.get("metadata", {}).get("labels", {})
        after_labels = after.get("metadata", {}).get("labels", {})
        if before_labels != after_labels:
            changes["labels"] = {
                "before": before_labels,
                "after": after_labels
            }
        
        # 比较注解
        before_annotations = before.get("metadata", {}).get("annotations", {})
        after_annotations = after.get("metadata", {}).get("annotations", {})
        if before_annotations != after_annotations:
            changes["annotations"] = {
                "before": before_annotations,
                "after": after_annotations
            }
        
        return changes
    
    async def validate_job_operation(self, name: str, namespace: str = "default",
                                   operation: str = "update", **kwargs) -> Dict:
        """验证Job操作"""
        try:
            # 获取操作前的状态
            before_state = await self.get_resource_before_operation("job", name, namespace)
            
            # 执行操作
            if operation == "update":
                if "parallelism" in kwargs:
                    await self.k8s_service.update_job(name, namespace, parallelism=kwargs["parallelism"])
                if "completions" in kwargs:
                    await self.k8s_service.update_job(name, namespace, completions=kwargs["completions"])
                if "active_deadline_seconds" in kwargs:
                    await self.k8s_service.update_job(name, namespace, active_deadline_seconds=kwargs["active_deadline_seconds"])
                if "backoff_limit" in kwargs:
                    await self.k8s_service.update_job(name, namespace, backoff_limit=kwargs["backoff_limit"])
                if "labels" in kwargs:
                    await self.k8s_service.update_job(name, namespace, labels=kwargs["labels"])
                if "annotations" in kwargs:
                    await self.k8s_service.update_job(name, namespace, annotations=kwargs["annotations"])
            
            # 获取操作后的状态
            after_state = await self.get_resource_after_operation("job", name, namespace)
            
            # 比较变化
            changes = self.compare_job_changes(before_state, after_state)
            
            return {
                "success": True,
                "operation": operation,
                "resource": f"job/{name}",
                "namespace": namespace,
                "before": before_state,
                "after": after_state,
                "changes": changes
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "operation": operation,
                "resource": f"job/{name}",
                "namespace": namespace
            }
    
    # ==================== CronJob 比较和验证方法 ====================
    
    def compare_cronjob_changes(self, before: Dict, after: Dict) -> Dict:
        """比较CronJob的变化"""
        changes = {
            "schedule": None,
            "suspend": None,
            "concurrency_policy": None,
            "starting_deadline_seconds": None,
            "successful_jobs_history_limit": None,
            "failed_jobs_history_limit": None,
            "job_template": None,
            "labels": None,
            "annotations": None
        }
        
        if before.get("error") or after.get("error"):
            return {"error": "无法获取资源状态"}
        
        # 比较调度表达式
        before_schedule = before.get("spec", {}).get("schedule", "")
        after_schedule = after.get("spec", {}).get("schedule", "")
        if before_schedule != after_schedule:
            changes["schedule"] = {
                "before": before_schedule,
                "after": after_schedule,
                "change": f"{before_schedule} -> {after_schedule}"
            }
        
        # 比较暂停状态
        before_suspend = before.get("spec", {}).get("suspend", False)
        after_suspend = after.get("spec", {}).get("suspend", False)
        if before_suspend != after_suspend:
            changes["suspend"] = {
                "before": before_suspend,
                "after": after_suspend,
                "change": f"{before_suspend} -> {after_suspend}"
            }
        
        # 比较标签
        before_labels = before.get("metadata", {}).get("labels", {})
        after_labels = after.get("metadata", {}).get("labels", {})
        if before_labels != after_labels:
            changes["labels"] = {
                "before": before_labels,
                "after": after_labels
            }
        
        # 比较注解
        before_annotations = before.get("metadata", {}).get("annotations", {})
        after_annotations = after.get("metadata", {}).get("annotations", {})
        if before_annotations != after_annotations:
            changes["annotations"] = {
                "before": before_annotations,
                "after": after_annotations
            }
        
        return changes
    
    async def validate_cronjob_operation(self, name: str, namespace: str = "default",
                                      operation: str = "update", **kwargs) -> Dict:
        """验证CronJob操作"""
        try:
            # 获取操作前的状态
            before_state = await self.get_resource_before_operation("cronjob", name, namespace)
            
            # 执行操作
            if operation == "update":
                if "schedule" in kwargs:
                    await self.k8s_service.update_cronjob(name, namespace, schedule=kwargs["schedule"])
                if "suspend" in kwargs:
                    await self.k8s_service.update_cronjob(name, namespace, suspend=kwargs["suspend"])
                if "image" in kwargs:
                    await self.k8s_service.update_cronjob(name, namespace, image=kwargs["image"])
                if "labels" in kwargs:
                    await self.k8s_service.update_cronjob(name, namespace, labels=kwargs["labels"])
                if "annotations" in kwargs:
                    await self.k8s_service.update_cronjob(name, namespace, annotations=kwargs["annotations"])
            
            # 获取操作后的状态
            after_state = await self.get_resource_after_operation("cronjob", name, namespace)
            
            # 比较变化
            changes = self.compare_cronjob_changes(before_state, after_state)
            
            return {
                "success": True,
                "operation": operation,
                "resource": f"cronjob/{name}",
                "namespace": namespace,
                "before": before_state,
                "after": after_state,
                "changes": changes
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "operation": operation,
                "resource": f"cronjob/{name}",
                "namespace": namespace
            }
    
    # ==================== Ingress 比较和验证方法 ====================
    
    def compare_ingress_changes(self, before: Dict, after: Dict) -> Dict:
        """比较Ingress的变化"""
        changes = {
            "rules": None,
            "tls": None,
            "ingress_class": None,
            "labels": None,
            "annotations": None
        }
        
        if before.get("error") or after.get("error"):
            return {"error": "无法获取资源状态"}
        
        # 比较规则
        before_rules = before.get("spec", {}).get("rules", [])
        after_rules = after.get("spec", {}).get("rules", [])
        if before_rules != after_rules:
            changes["rules"] = {
                "before": before_rules,
                "after": after_rules
            }
        
        # 比较TLS配置
        before_tls = before.get("spec", {}).get("tls", [])
        after_tls = after.get("spec", {}).get("tls", [])
        if before_tls != after_tls:
            changes["tls"] = {
                "before": before_tls,
                "after": after_tls
            }
        
        # 比较Ingress Class
        before_class = before.get("spec", {}).get("ingressClassName", "")
        after_class = after.get("spec", {}).get("ingressClassName", "")
        if before_class != after_class:
            changes["ingress_class"] = {
                "before": before_class,
                "after": after_class,
                "change": f"{before_class} -> {after_class}"
            }
        
        # 比较标签
        before_labels = before.get("metadata", {}).get("labels", {})
        after_labels = after.get("metadata", {}).get("labels", {})
        if before_labels != after_labels:
            changes["labels"] = {
                "before": before_labels,
                "after": after_labels
            }
        
        # 比较注解
        before_annotations = before.get("metadata", {}).get("annotations", {})
        after_annotations = after.get("metadata", {}).get("annotations", {})
        if before_annotations != after_annotations:
            changes["annotations"] = {
                "before": before_annotations,
                "after": after_annotations
            }
        
        return changes
    
    async def validate_ingress_operation(self, name: str, namespace: str = "default",
                                       operation: str = "update", **kwargs) -> Dict:
        """验证Ingress操作"""
        try:
            # 获取操作前的状态
            before_state = await self.get_resource_before_operation("ingress", name, namespace)
            
            # 执行操作
            if operation == "update":
                if "rules" in kwargs:
                    await self.k8s_service.update_ingress(name, namespace, rules=kwargs["rules"])
                if "tls" in kwargs:
                    await self.k8s_service.update_ingress(name, namespace, tls=kwargs["tls"])
                if "ingress_class" in kwargs:
                    await self.k8s_service.update_ingress(name, namespace, ingress_class=kwargs["ingress_class"])
                if "labels" in kwargs:
                    await self.k8s_service.update_ingress(name, namespace, labels=kwargs["labels"])
                if "annotations" in kwargs:
                    await self.k8s_service.update_ingress(name, namespace, annotations=kwargs["annotations"])
            
            # 获取操作后的状态
            after_state = await self.get_resource_after_operation("ingress", name, namespace)
            
            # 比较变化
            changes = self.compare_ingress_changes(before_state, after_state)
            
            return {
                "success": True,
                "operation": operation,
                "resource": f"ingress/{name}",
                "namespace": namespace,
                "before": before_state,
                "after": after_state,
                "changes": changes
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "operation": operation,
                "resource": f"ingress/{name}",
                "namespace": namespace
            }
    
    # ==================== StorageClass 比较和验证方法 ====================
    
    def compare_storageclass_changes(self, before: Dict, after: Dict) -> Dict:
        """比较StorageClass的变化"""
        changes = {
            "provisioner": None,
            "parameters": None,
            "allow_volume_expansion": None,
            "labels": None,
            "annotations": None
        }
        
        if before.get("error") or after.get("error"):
            return {"error": "无法获取资源状态"}
        
        # 比较存储供应商
        before_provisioner = before.get("provisioner", "")
        after_provisioner = after.get("provisioner", "")
        if before_provisioner != after_provisioner:
            changes["provisioner"] = {
                "before": before_provisioner,
                "after": after_provisioner,
                "change": f"{before_provisioner} -> {after_provisioner}"
            }
        
        # 比较参数
        before_parameters = before.get("parameters", {})
        after_parameters = after.get("parameters", {})
        if before_parameters != after_parameters:
            changes["parameters"] = {
                "before": before_parameters,
                "after": after_parameters
            }
        
        # 比较卷扩容
        before_expansion = before.get("allow_volume_expansion", False)
        after_expansion = after.get("allow_volume_expansion", False)
        if before_expansion != after_expansion:
            changes["allow_volume_expansion"] = {
                "before": before_expansion,
                "after": after_expansion,
                "change": f"{before_expansion} -> {after_expansion}"
            }
        
        # 比较标签
        before_labels = before.get("metadata", {}).get("labels", {})
        after_labels = after.get("metadata", {}).get("labels", {})
        if before_labels != after_labels:
            changes["labels"] = {
                "before": before_labels,
                "after": after_labels
            }
        
        # 比较注解
        before_annotations = before.get("metadata", {}).get("annotations", {})
        after_annotations = after.get("metadata", {}).get("annotations", {})
        if before_annotations != after_annotations:
            changes["annotations"] = {
                "before": before_annotations,
                "after": after_annotations
            }
        
        return changes
    
    async def validate_storageclass_operation(self, name: str, operation: str = "update", **kwargs) -> Dict:
        """验证StorageClass操作"""
        try:
            # 获取操作前的状态
            before_state = await self.get_resource_before_operation("storageclass", name)
            
            # 执行操作
            if operation == "update":
                # StorageClass的一些字段是不可变的，这里只处理可变字段
                update_params = {}
                
                if "allow_volume_expansion" in kwargs:
                    update_params["allow_volume_expansion"] = kwargs["allow_volume_expansion"]
                
                if "parameters" in kwargs:
                    update_params["parameters"] = kwargs["parameters"]
                
                if "labels" in kwargs:
                    update_params["labels"] = kwargs["labels"]
                
                if "annotations" in kwargs:
                    update_params["annotations"] = kwargs["annotations"]
                
                if update_params:
                    await self.k8s_service.update_storageclass(name, **update_params)
            
            # 获取操作后的状态
            after_state = await self.get_resource_after_operation("storageclass", name)
            
            # 比较变化
            changes = self.compare_storageclass_changes(before_state, after_state)
            
            return {
                "success": True,
                "operation": operation,
                "resource": f"storageclass/{name}",
                "before": before_state,
                "after": after_state,
                "changes": changes
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "operation": operation,
                "resource": f"storageclass/{name}"
            }
    
    # ==================== PersistentVolume 比较和验证方法 ====================
    
    def compare_persistentvolume_changes(self, before: Dict, after: Dict) -> Dict:
        """比较PersistentVolume的变化"""
        changes = {
            "capacity": None,
            "access_modes": None,
            "reclaim_policy": None,
            "storage_class": None,
            "labels": None,
            "annotations": None,
            "status": None
        }
        
        if before.get("error") or after.get("error"):
            return {"error": "无法获取资源状态"}
        
        # 比较容量
        before_capacity = before.get("capacity", {}).get("storage", "")
        after_capacity = after.get("capacity", {}).get("storage", "")
        if before_capacity != after_capacity:
            changes["capacity"] = {
                "before": before_capacity,
                "after": after_capacity,
                "change": f"{before_capacity} -> {after_capacity}"
            }
        
        # 比较访问模式
        before_access_modes = before.get("access_modes", [])
        after_access_modes = after.get("access_modes", [])
        if before_access_modes != after_access_modes:
            changes["access_modes"] = {
                "before": before_access_modes,
                "after": after_access_modes,
                "change": f"{','.join(before_access_modes)} -> {','.join(after_access_modes)}"
            }
        
        # 比较回收策略
        before_reclaim_policy = before.get("reclaim_policy", "")
        after_reclaim_policy = after.get("reclaim_policy", "")
        if before_reclaim_policy != after_reclaim_policy:
            changes["reclaim_policy"] = {
                "before": before_reclaim_policy,
                "after": after_reclaim_policy,
                "change": f"{before_reclaim_policy} -> {after_reclaim_policy}"
            }
        
        # 比较存储类
        before_storage_class = before.get("storage_class_name", "")
        after_storage_class = after.get("storage_class_name", "")
        if before_storage_class != after_storage_class:
            changes["storage_class"] = {
                "before": before_storage_class,
                "after": after_storage_class,
                "change": f"{before_storage_class} -> {after_storage_class}"
            }
        
        # 比较标签
        before_labels = before.get("metadata", {}).get("labels", {})
        after_labels = after.get("metadata", {}).get("labels", {})
        if before_labels != after_labels:
            changes["labels"] = {
                "before": before_labels,
                "after": after_labels
            }
        
        # 比较注解
        before_annotations = before.get("metadata", {}).get("annotations", {})
        after_annotations = after.get("metadata", {}).get("annotations", {})
        if before_annotations != after_annotations:
            changes["annotations"] = {
                "before": before_annotations,
                "after": after_annotations
            }
        
        return changes
    
    async def validate_persistentvolume_operation(self, name: str, operation: str = "update", **kwargs) -> Dict:
        """验证PersistentVolume操作"""
        try:
            # 获取操作前的状态
            before_state = await self.get_resource_before_operation("persistentvolume", name)
            
            # 执行操作
            if operation == "update":
                update_params = {}
                
                if "capacity" in kwargs:
                    update_params["capacity"] = kwargs["capacity"]
                
                if "access_modes" in kwargs:
                    update_params["access_modes"] = kwargs["access_modes"]
                
                if "reclaim_policy" in kwargs:
                    update_params["reclaim_policy"] = kwargs["reclaim_policy"]
                
                if "storage_class_name" in kwargs:
                    update_params["storage_class_name"] = kwargs["storage_class_name"]
                
                if "labels" in kwargs:
                    update_params["labels"] = kwargs["labels"]
                
                if "annotations" in kwargs:
                    update_params["annotations"] = kwargs["annotations"]
                
                if update_params:
                    await self.k8s_service.update_persistentvolume(name, **update_params)
            
            # 获取操作后的状态
            after_state = await self.get_resource_after_operation("persistentvolume", name)
            
            # 比较变化
            changes = self.compare_persistentvolume_changes(before_state, after_state)
            
            return {
                "success": True,
                "operation": operation,
                "resource": f"persistentvolume/{name}",
                "before": before_state,
                "after": after_state,
                "changes": changes
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "operation": operation,
                "resource": f"persistentvolume/{name}"
            }
    
    # ==================== PersistentVolumeClaim 比较和验证方法 ====================
    
    def compare_persistentvolumeclaim_changes(self, before: Dict, after: Dict) -> Dict:
        """比较PersistentVolumeClaim的变化"""
        changes = {
            "size": None,
            "access_modes": None,
            "storage_class": None,
            "labels": None,
            "annotations": None
        }
        
        if before.get("error") or after.get("error"):
            return {"error": "无法获取资源状态"}
        
        # 比较存储大小
        before_size = before.get("spec", {}).get("resources", {}).get("requests", {}).get("storage", "")
        after_size = after.get("spec", {}).get("resources", {}).get("requests", {}).get("storage", "")
        if before_size != after_size:
            changes["size"] = {
                "before": before_size,
                "after": after_size,
                "change": f"{before_size} -> {after_size}"
            }
        
        # 比较访问模式
        before_access_modes = before.get("spec", {}).get("access_modes", [])
        after_access_modes = after.get("spec", {}).get("access_modes", [])
        if before_access_modes != after_access_modes:
            changes["access_modes"] = {
                "before": before_access_modes,
                "after": after_access_modes
            }
        
        # 比较存储类
        before_storage_class = before.get("spec", {}).get("storage_class_name", "")
        after_storage_class = after.get("spec", {}).get("storage_class_name", "")
        if before_storage_class != after_storage_class:
            changes["storage_class"] = {
                "before": before_storage_class,
                "after": after_storage_class,
                "change": f"{before_storage_class} -> {after_storage_class}"
            }
        
        # 比较标签和注解
        before_labels = before.get("metadata", {}).get("labels", {})
        after_labels = after.get("metadata", {}).get("labels", {})
        if before_labels != after_labels:
            changes["labels"] = {
                "before": before_labels,
                "after": after_labels
            }
        
        before_annotations = before.get("metadata", {}).get("annotations", {})
        after_annotations = after.get("metadata", {}).get("annotations", {})
        if before_annotations != after_annotations:
            changes["annotations"] = {
                "before": before_annotations,
                "after": after_annotations
            }
        
        return changes
    
    async def validate_persistentvolumeclaim_operation(self, name: str, namespace: str = "default",
                                                      operation: str = "update", **kwargs) -> Dict:
        """验证PersistentVolumeClaim操作"""
        try:
            # 获取操作前的状态
            before_state = await self.get_resource_before_operation("persistentvolumeclaim", name, namespace)
            
            # 执行操作
            if operation == "update":
                if "size" in kwargs:
                    await self.k8s_service.update_persistentvolumeclaim(name, namespace, size=kwargs["size"])
                if "access_modes" in kwargs:
                    await self.k8s_service.update_persistentvolumeclaim(name, namespace, access_modes=kwargs["access_modes"])
                if "storage_class" in kwargs:
                    await self.k8s_service.update_persistentvolumeclaim(name, namespace, storage_class=kwargs["storage_class"])
            
            # 获取操作后的状态
            after_state = await self.get_resource_after_operation("persistentvolumeclaim", name, namespace)
            
            # 比较变化
            changes = self.compare_persistentvolumeclaim_changes(before_state, after_state)
            
            return {
                "success": True,
                "operation": operation,
                "resource": f"persistentvolumeclaim/{name}",
                "namespace": namespace,
                "before": before_state,
                "after": after_state,
                "changes": changes
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "operation": operation,
                "resource": f"persistentvolumeclaim/{name}",
                "namespace": namespace
            }
    
    # ==================== ServiceAccount 比较和验证方法 ====================
    
    def compare_serviceaccount_changes(self, before: Dict, after: Dict) -> Dict:
        """比较ServiceAccount的变化"""
        changes = {
            "labels": None,
            "annotations": None,
            "secrets": None,
            "image_pull_secrets": None,
            "automount_service_account_token": None
        }
        
        if before.get("error") or after.get("error"):
            return {"error": "无法获取资源状态"}
        
        # 比较标签
        before_labels = before.get("labels", {})
        after_labels = after.get("labels", {})
        if before_labels != after_labels:
            changes["labels"] = {
                "before": before_labels,
                "after": after_labels
            }
        
        # 比较注解
        before_annotations = before.get("annotations", {})
        after_annotations = after.get("annotations", {})
        if before_annotations != after_annotations:
            changes["annotations"] = {
                "before": before_annotations,
                "after": after_annotations
            }
        
        # 比较secrets
        before_secrets = before.get("secrets", [])
        after_secrets = after.get("secrets", [])
        if before_secrets != after_secrets:
            changes["secrets"] = {
                "before": before_secrets,
                "after": after_secrets
            }
        
        # 比较image_pull_secrets
        before_image_pull_secrets = before.get("image_pull_secrets", [])
        after_image_pull_secrets = after.get("image_pull_secrets", [])
        if before_image_pull_secrets != after_image_pull_secrets:
            changes["image_pull_secrets"] = {
                "before": before_image_pull_secrets,
                "after": after_image_pull_secrets
            }
        
        # 比较automount_service_account_token
        before_automount = before.get("automount_service_account_token")
        after_automount = after.get("automount_service_account_token")
        if before_automount != after_automount:
            changes["automount_service_account_token"] = {
                "before": before_automount,
                "after": after_automount,
                "change": f"{before_automount} -> {after_automount}"
            }
        
        return changes
    
    async def validate_serviceaccount_operation(self, name: str, namespace: str = "default",
                                              operation: str = "update", **kwargs) -> Dict:
        """验证ServiceAccount操作"""
        try:
            # 获取操作前的状态
            before_state = await self.get_resource_before_operation("serviceaccount", name, namespace)
            
            # 执行操作
            if operation == "update":
                update_params = {}
                
                if "labels" in kwargs:
                    update_params["labels"] = kwargs["labels"]
                
                if "annotations" in kwargs:
                    update_params["annotations"] = kwargs["annotations"]
                
                if "secrets" in kwargs:
                    update_params["secrets"] = kwargs["secrets"]
                
                if "image_pull_secrets" in kwargs:
                    update_params["image_pull_secrets"] = kwargs["image_pull_secrets"]
                
                if "automount_service_account_token" in kwargs:
                    update_params["automount_service_account_token"] = kwargs["automount_service_account_token"]
                
                if update_params:
                    await self.k8s_service.update_serviceaccount(name, namespace, **update_params)
            
            # 获取操作后的状态
            after_state = await self.get_resource_after_operation("serviceaccount", name, namespace)
            
            # 比较变化
            changes = self.compare_serviceaccount_changes(before_state, after_state)
            
            return {
                "success": True,
                "operation": operation,
                "resource": f"serviceaccount/{name}",
                "namespace": namespace,
                "before": before_state,
                "after": after_state,
                "changes": changes
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "operation": operation,
                "resource": f"serviceaccount/{name}",
                "namespace": namespace
            }
    
    # ==================== Role 比较和验证方法 ====================
    
    def compare_role_changes(self, before: Dict, after: Dict) -> Dict:
        """比较Role的变化"""
        changes = {
            "rules": None,
            "labels": None,
            "annotations": None
        }
        
        if before.get("error") or after.get("error"):
            return {"error": "无法获取资源状态"}
        
        # 比较规则
        before_rules = before.get("rules", [])
        after_rules = after.get("rules", [])
        if before_rules != after_rules:
            changes["rules"] = {
                "before": before_rules,
                "after": after_rules
            }
        
        # 比较标签
        before_labels = before.get("metadata", {}).get("labels", {})
        after_labels = after.get("metadata", {}).get("labels", {})
        if before_labels != after_labels:
            changes["labels"] = {
                "before": before_labels,
                "after": after_labels
            }
        
        # 比较注解
        before_annotations = before.get("metadata", {}).get("annotations", {})
        after_annotations = after.get("metadata", {}).get("annotations", {})
        if before_annotations != after_annotations:
            changes["annotations"] = {
                "before": before_annotations,
                "after": after_annotations
            }
        
        return changes
    
    async def validate_role_operation(self, name: str, namespace: str = "default",
                                    operation: str = "update", **kwargs) -> Dict:
        """验证Role操作"""
        try:
            # 获取操作前的状态
            before_state = await self.get_resource_before_operation("role", name, namespace)
            
            # 执行操作
            if operation == "update":
                update_params = {}
                
                if "rules" in kwargs:
                    update_params["rules"] = kwargs["rules"]
                
                if "labels" in kwargs:
                    update_params["labels"] = kwargs["labels"]
                
                if "annotations" in kwargs:
                    update_params["annotations"] = kwargs["annotations"]
                
                if update_params:
                    await self.k8s_service.update_role(name, namespace, **update_params)
            
            # 获取操作后的状态
            after_state = await self.get_resource_after_operation("role", name, namespace)
            
            # 比较变化
            changes = self.compare_role_changes(before_state, after_state)
            
            return {
                "success": True,
                "operation": operation,
                "resource": f"role/{name}",
                "namespace": namespace,
                "before": before_state,
                "after": after_state,
                "changes": changes
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "operation": operation,
                "resource": f"role/{name}",
                "namespace": namespace
            }
    
    # ==================== ClusterRole 比较和验证方法 ====================
    
    def compare_cluster_role_changes(self, before: Dict, after: Dict) -> Dict:
        """比较ClusterRole的变化"""
        changes = {
            "rules": None,
            "labels": None,
            "annotations": None
        }
        
        if before.get("error") or after.get("error"):
            return {"error": "无法获取资源状态"}
        
        # 比较规则
        before_rules = before.get("rules", [])
        after_rules = after.get("rules", [])
        if before_rules != after_rules:
            changes["rules"] = {
                "before": before_rules,
                "after": after_rules
            }
        
        # 比较标签
        before_labels = before.get("metadata", {}).get("labels", {})
        after_labels = after.get("metadata", {}).get("labels", {})
        if before_labels != after_labels:
            changes["labels"] = {
                "before": before_labels,
                "after": after_labels
            }
        
        # 比较注解
        before_annotations = before.get("metadata", {}).get("annotations", {})
        after_annotations = after.get("metadata", {}).get("annotations", {})
        if before_annotations != after_annotations:
            changes["annotations"] = {
                "before": before_annotations,
                "after": after_annotations
            }
        
        return changes
    
    async def validate_cluster_role_operation(self, name: str, operation: str = "update", **kwargs) -> Dict:
        """验证ClusterRole操作"""
        try:
            # 获取操作前的状态
            before_state = await self.get_resource_before_operation("clusterrole", name)
            
            # 执行操作
            if operation == "update":
                update_params = {}
                
                if "rules" in kwargs:
                    update_params["rules"] = kwargs["rules"]
                
                if "labels" in kwargs:
                    update_params["labels"] = kwargs["labels"]
                
                if "annotations" in kwargs:
                    update_params["annotations"] = kwargs["annotations"]
                
                if update_params:
                    await self.k8s_service.update_cluster_role(name, **update_params)
            
            # 获取操作后的状态
            after_state = await self.get_resource_after_operation("clusterrole", name)
            
            # 比较变化
            changes = self.compare_cluster_role_changes(before_state, after_state)
            
            return {
                "success": True,
                "operation": operation,
                "resource": f"clusterrole/{name}",
                "before": before_state,
                "after": after_state,
                "changes": changes
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "operation": operation,
                "resource": f"clusterrole/{name}"
            }
    
    # ==================== RoleBinding 比较和验证方法 ====================
    
    def compare_role_binding_changes(self, before: Dict, after: Dict) -> Dict:
        """比较RoleBinding的变化"""
        changes = {
            "role_ref": None,
            "subjects": None,
            "labels": None,
            "annotations": None
        }
        
        if before.get("error") or after.get("error"):
            return {"error": "无法获取资源状态"}
        
        # 比较角色引用
        before_role_ref = before.get("role_ref", {})
        after_role_ref = after.get("role_ref", {})
        if before_role_ref != after_role_ref:
            changes["role_ref"] = {
                "before": before_role_ref,
                "after": after_role_ref
            }
        
        # 比较主体
        before_subjects = before.get("subjects", [])
        after_subjects = after.get("subjects", [])
        if before_subjects != after_subjects:
            changes["subjects"] = {
                "before": before_subjects,
                "after": after_subjects
            }
        
        # 比较标签
        before_labels = before.get("metadata", {}).get("labels", {})
        after_labels = after.get("metadata", {}).get("labels", {})
        if before_labels != after_labels:
            changes["labels"] = {
                "before": before_labels,
                "after": after_labels
            }
        
        # 比较注解
        before_annotations = before.get("metadata", {}).get("annotations", {})
        after_annotations = after.get("metadata", {}).get("annotations", {})
        if before_annotations != after_annotations:
            changes["annotations"] = {
                "before": before_annotations,
                "after": after_annotations
            }
        
        return changes
    
    async def validate_role_binding_operation(self, name: str, namespace: str = "default",
                                           operation: str = "update", **kwargs) -> Dict:
        """验证RoleBinding操作"""
        try:
            # 获取操作前的状态
            before_state = await self.get_resource_before_operation("rolebinding", name, namespace)
            
            # 执行操作
            if operation == "update":
                update_params = {}
                
                if "role_ref" in kwargs:
                    update_params["role_ref"] = kwargs["role_ref"]
                
                if "subjects" in kwargs:
                    update_params["subjects"] = kwargs["subjects"]
                
                if "labels" in kwargs:
                    update_params["labels"] = kwargs["labels"]
                
                if "annotations" in kwargs:
                    update_params["annotations"] = kwargs["annotations"]
                
                if update_params:
                    await self.k8s_service.update_role_binding(name, namespace, **update_params)
            
            # 获取操作后的状态
            after_state = await self.get_resource_after_operation("rolebinding", name, namespace)
            
            # 比较变化
            changes = self.compare_role_binding_changes(before_state, after_state)
            
            return {
                "success": True,
                "operation": operation,
                "resource": f"rolebinding/{name}",
                "namespace": namespace,
                "before": before_state,
                "after": after_state,
                "changes": changes
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "operation": operation,
                "resource": f"rolebinding/{name}",
                "namespace": namespace
            }
    
    # ==================== ClusterRoleBinding 比较和验证方法 ====================
    
    def compare_cluster_role_binding_changes(self, before: Dict, after: Dict) -> Dict:
        """比较ClusterRoleBinding的变化"""
        changes = {
            "role_ref": None,
            "subjects": None,
            "labels": None,
            "annotations": None
        }
        
        if before.get("error") or after.get("error"):
            return {"error": "无法获取资源状态"}
        
        # 比较角色引用
        before_role_ref = before.get("role_ref", {})
        after_role_ref = after.get("role_ref", {})
        if before_role_ref != after_role_ref:
            changes["role_ref"] = {
                "before": before_role_ref,
                "after": after_role_ref
            }
        
        # 比较主体
        before_subjects = before.get("subjects", [])
        after_subjects = after.get("subjects", [])
        if before_subjects != after_subjects:
            changes["subjects"] = {
                "before": before_subjects,
                "after": after_subjects
            }
        
        # 比较标签
        before_labels = before.get("metadata", {}).get("labels", {})
        after_labels = after.get("metadata", {}).get("labels", {})
        if before_labels != after_labels:
            changes["labels"] = {
                "before": before_labels,
                "after": after_labels
            }
        
        # 比较注解
        before_annotations = before.get("metadata", {}).get("annotations", {})
        after_annotations = after.get("metadata", {}).get("annotations", {})
        if before_annotations != after_annotations:
            changes["annotations"] = {
                "before": before_annotations,
                "after": after_annotations
            }
        
        return changes
    
    async def validate_cluster_role_binding_operation(self, name: str, operation: str = "update", **kwargs) -> Dict:
        """验证ClusterRoleBinding操作"""
        try:
            # 获取操作前的状态
            before_state = await self.get_resource_before_operation("clusterrolebinding", name)
            
            # 执行操作
            if operation == "update":
                update_params = {}
                
                if "role_ref" in kwargs:
                    update_params["role_ref"] = kwargs["role_ref"]
                
                if "subjects" in kwargs:
                    update_params["subjects"] = kwargs["subjects"]
                
                if "labels" in kwargs:
                    update_params["labels"] = kwargs["labels"]
                
                if "annotations" in kwargs:
                    update_params["annotations"] = kwargs["annotations"]
                
                if update_params:
                    await self.k8s_service.update_cluster_role_binding(name, **update_params)
            
            # 获取操作后的状态
            after_state = await self.get_resource_after_operation("clusterrolebinding", name)
            
            # 比较变化
            changes = self.compare_cluster_role_binding_changes(before_state, after_state)
            
            return {
                "success": True,
                "operation": operation,
                "resource": f"clusterrolebinding/{name}",
                "before": before_state,
                "after": after_state,
                "changes": changes
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "operation": operation,
                "resource": f"clusterrolebinding/{name}"
            }
    
    # ==================== Namespace 比较和验证方法 ====================
    
    def compare_namespace_changes(self, before: Dict, after: Dict) -> Dict:
        """比较Namespace的变化"""
        changes = {
            "status": None,
            "labels": None,
            "annotations": None
        }
        
        if before.get("error") or after.get("error"):
            return {"error": "无法获取资源状态"}
        
        # 比较状态
        before_status = before.get("status", {}).get("phase", "")
        after_status = after.get("status", {}).get("phase", "")
        if before_status != after_status:
            changes["status"] = {
                "before": before_status,
                "after": after_status,
                "change": f"{before_status} -> {after_status}"
            }
        
        # 比较标签
        before_labels = before.get("metadata", {}).get("labels", {})
        after_labels = after.get("metadata", {}).get("labels", {})
        if before_labels != after_labels:
            changes["labels"] = {
                "before": before_labels,
                "after": after_labels
            }
        
        # 比较注解
        before_annotations = before.get("metadata", {}).get("annotations", {})
        after_annotations = after.get("metadata", {}).get("annotations", {})
        if before_annotations != after_annotations:
            changes["annotations"] = {
                "before": before_annotations,
                "after": after_annotations
            }
        
        return changes
    
    async def validate_namespace_operation(self, name: str, operation: str = "update", **kwargs) -> Dict:
        """验证Namespace操作"""
        try:
            # 获取操作前的状态
            before_state = await self.get_resource_before_operation("namespace", name)
            
            # 执行操作
            if operation == "update":
                if "labels" in kwargs:
                    # 目前只支持更新标签
                    await self.k8s_service.update_namespace(name, labels=kwargs["labels"])
                if "annotations" in kwargs:
                    # 支持更新注解
                    await self.k8s_service.update_namespace(name, annotations=kwargs["annotations"])
            
            # 获取操作后的状态
            after_state = await self.get_resource_after_operation("namespace", name)
            
            # 比较变化
            changes = self.compare_namespace_changes(before_state, after_state)
            
            return {
                "success": True,
                "operation": operation,
                "resource": f"namespace/{name}",
                "before": before_state,
                "after": after_state,
                "changes": changes
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "operation": operation,
                "resource": f"namespace/{name}"
            }

