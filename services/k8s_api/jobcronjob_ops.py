import copy
from typing import Dict, List, Any, Optional
from kubernetes import client
from kubernetes.client.exceptions import ApiException
from utils.k8s_helpers import to_local_time_str

class JobCronJobOpsMixin:
    """Job 与 CronJob 资源操作 Mixin"""
    async def list_jobs(self, namespace: str = "default", label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
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
                    "creation_timestamp": to_local_time_str(item.metadata.creation_timestamp) if item.metadata.creation_timestamp else None,
                    "completions": item.spec.completions,
                    "parallelism": item.spec.parallelism,
                    "active": item.status.active or 0,
                    "succeeded": item.status.succeeded or 0,
                    "failed": item.status.failed or 0,
                    "labels": item.metadata.labels,
                    "completion_time": to_local_time_str(item.status.completion_time) if item.status.completion_time else None,
                    "start_time": to_local_time_str(item.status.start_time) if item.status.start_time else None
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
                    "created": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None
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
                "completion_time": to_local_time_str(response.status.completion_time) if response.status.completion_time else None,
                    "start_time": to_local_time_str(response.status.start_time) if response.status.start_time else None
                }
            }
        
        except ApiException as e:
            raise Exception(f"获取 Job 失败: {e}")

    async def create_job(self, name: Optional[str] = None, image: Optional[str] = None, namespace: str = "default",
                   command: Optional[list] = None, args: Optional[list] = None, labels: Optional[dict] = None,
                   env_vars: Optional[dict] = None, resources: Optional[dict] = None,
                   restart_policy: str = "Never", backoff_limit: int = 6, resource: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
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
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None
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
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "job", resource_name, namespace, resource_data, create_operation
        )

    async def update_job(self, name: str, namespace: str = "default",
                        labels: Optional[dict] = None, annotations: Optional[dict] = None, 
                        resource: Optional[Dict] = None) -> Dict[str, Any]:
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

    async def list_cronjobs(self, namespace: str = "default", label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
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
                    "creation_timestamp": to_local_time_str(item.metadata.creation_timestamp) if item.metadata.creation_timestamp else None,
                    "schedule": item.spec.schedule,
                    "suspend": item.spec.suspend or False,
                    "active_jobs": len(item.status.active) if item.status.active else 0,
                    "last_schedule_time": to_local_time_str(item.status.last_schedule_time) if item.status.last_schedule_time else None,
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
                    "created": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None
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
                    "last_schedule_time": to_local_time_str(response.status.last_schedule_time) if response.status.last_schedule_time else None
                }
            }

        except ApiException as e:
            raise Exception(f"获取 CronJob 失败: {e}")

    async def create_cronjob(self, name: Optional[str] = None, image: Optional[str] = None, schedule: Optional[str] = None,
                       namespace: str = "default", command: Optional[list] = None,
                       args: Optional[list] = None, labels: Optional[dict] = None,
                       env_vars: Optional[dict] = None, resources: Optional[dict] = None,
                       restart_policy: str = "Never", suspend: bool = False, resource: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
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
                except ApiException as e:
                    # 部分集群仅在 batch/v1beta1 暴露 CronJob（batch/v1 无 cronjobs 资源会 404）
                    if e.status != 404 or not self.batch_v1beta1_api:
                        raise
                    resource_copy = copy.deepcopy(resource)
                    resource_copy["apiVersion"] = "batch/v1beta1"
                    spec = resource_copy.get("spec") or {}
                    spec.pop("timeZone", None)
                    resource_copy["spec"] = spec
                    response = self.batch_v1beta1_api.create_namespaced_cron_job(
                        namespace=namespace,
                        body=resource_copy
                    )
                
                return {
                    "name": response.metadata.name,
                    "namespace": response.metadata.namespace,
                    "uid": response.metadata.uid,
                    "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
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
                "creation_timestamp": to_local_time_str(response.metadata.creation_timestamp) if response.metadata.creation_timestamp else None,
                "schedule": response.spec.schedule
            }
            
        # 使用统一的验证和执行方法
        return await self._execute_with_validation_and_preview(
            "create", "cronjob", resource_name, namespace, resource_data, create_operation
        )

    async def update_cronjob(self, name: str, namespace: str = "default",
                       schedule: Optional[str] = None, suspend: Optional[bool] = None,
                       image: Optional[str] = None, labels: Optional[dict] = None, resource: Optional[Dict] = None) -> Dict[str, Any]:
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

