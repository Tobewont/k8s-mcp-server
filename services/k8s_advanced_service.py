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
from services.dynamic_resource_service import DynamicResourceService
from config import DATA_DIR, BACKUP_DIR


class ResourceManager:
    """资源管理器，统一管理资源配置和操作"""
    
    def __init__(self, k8s_service):
        self.k8s_service = k8s_service
        self._resource_configs = self._init_resource_configs()
    
    def _init_resource_configs(self):
        """初始化资源配置"""
        return {
            "deployments": ResourceConfig("Deployment", "list_deployments", "get_deployment"),
            "statefulsets": ResourceConfig("StatefulSet", "list_statefulsets", "get_statefulset"),
            "daemonsets": ResourceConfig("DaemonSet", "list_daemonsets", "get_daemonset"),
            "services": ResourceConfig("Service", "list_services", "get_service"),
            "configmaps": ResourceConfig("ConfigMap", "list_configmaps", "get_configmap", 
                                       skip_condition=lambda name: name in ["kube-root-ca.crt"]),
            "secrets": ResourceConfig("Secret", "list_secrets", "get_secret",
                                    skip_condition=lambda name: name.startswith("default-token-")),
            "jobs": ResourceConfig("Job", "list_jobs", "get_job"),
            "cronjobs": ResourceConfig("CronJob", "list_cronjobs", "get_cronjob"),
            "ingresses": ResourceConfig("Ingress", "list_ingresses", "get_ingress"),
            "persistentvolumeclaims": ResourceConfig("PersistentVolumeClaim", "list_persistentvolumeclaims", "get_persistentvolumeclaim"),
            "serviceaccounts": ResourceConfig("ServiceAccount", "list_serviceaccounts", "get_serviceaccount",
                                            skip_condition=lambda name: name == "default"),
            "roles": ResourceConfig("Role", "list_roles", "get_role"),
            "rolebindings": ResourceConfig("RoleBinding", "list_role_bindings", "get_role_binding"),
            "horizontalpodautoscalers": ResourceConfig("HorizontalPodAutoscaler", "list_hpas", "get_hpa"),
            "networkpolicies": ResourceConfig("NetworkPolicy", "list_network_policies", "get_network_policy"),
            "resourcequotas": ResourceConfig("ResourceQuota", "list_resource_quotas", "get_resource_quota")
        }
    
    def get_resource_config(self, resource_type: str):
        """获取资源配置"""
        return self._resource_configs.get(resource_type)
    
    def get_operation_method(self, resource_type: str, operation: str, namespace: str = "default"):
        """获取操作方法"""
        config = self.get_resource_config(resource_type)
        if not config:
            raise ValueError(f"不支持的资源类型: {resource_type}")
        
        if operation == "list":
            return lambda: getattr(self.k8s_service, config.list_method)(namespace=namespace)
        elif operation == "get":
            return lambda name: getattr(self.k8s_service, config.get_method)(name, namespace)
        else:
            raise ValueError(f"不支持的操作类型: {operation}")


class ResourceConfig:
    """资源配置类"""
    
    def __init__(self, kind: str, list_method: str, get_method: str, skip_condition: Callable = None):
        self.kind = kind
        self.list_method = list_method
        self.get_method = get_method
        self.skip_condition = skip_condition


class BatchOperationResult:
    """批量操作结果类"""
    
    def __init__(self):
        self.success = []
        self.failed = []
        self.total = 0
    
    def add_success(self, resource_info):
        self.success.append(resource_info)
        self.total += 1
    
    def add_failure(self, resource_info, error):
        self.failed.append({"resource": resource_info, "error": str(error)})
        self.total += 1
    
    def to_dict(self):
        return {
            "success": self.success,
            "failed": self.failed,
            "total": self.total
        }


class KubernetesAdvancedService:
    """Kubernetes 进阶服务类
    整合批量操作、备份恢复、资源验证等功能
    """
    
    def __init__(self):
        self.k8s_service = KubernetesAPIService()
        self.k8s_service.load_config()
        self.backup_dir = BACKUP_DIR
        os.makedirs(self.backup_dir, exist_ok=True)
        self.operation_history = []
        
        # 初始化资源管理器
        self.resource_manager = ResourceManager(self.k8s_service)
        # 动态资源服务（支持集群中所有 API 资源）
        self._dynamic_service = DynamicResourceService(self.k8s_service)

        # 设置验证服务的循环引用
        self.k8s_service.set_validation_service(self)

        # 统一的 kind -> apiVersion 映射
        self._api_version_map: Dict[str, str] = {
            "Deployment": "apps/v1",
            "StatefulSet": "apps/v1",
            "DaemonSet": "apps/v1",
            "Service": "v1",
            "ConfigMap": "v1",
            "Secret": "v1",
            "Job": "batch/v1",
            "CronJob": "batch/v1",
            "Ingress": "networking.k8s.io/v1",
            "PersistentVolumeClaim": "v1",
            "ServiceAccount": "v1",
            "Role": "rbac.authorization.k8s.io/v1",
            "RoleBinding": "rbac.authorization.k8s.io/v1",
            "HorizontalPodAutoscaler": "autoscaling/v2",
            "NetworkPolicy": "networking.k8s.io/v1",
            "ResourceQuota": "v1",
            "Namespace": "v1",
            "Node": "v1",
            "Pod": "v1",
            "PersistentVolume": "v1",
            "StorageClass": "storage.k8s.io/v1",
            "ClusterRole": "rbac.authorization.k8s.io/v1",
            "ClusterRoleBinding": "rbac.authorization.k8s.io/v1",
        }
        # resource_type (复数) -> kind，用于动态解析
        self._resource_type_to_kind: Dict[str, str] = {
            "deployments": "Deployment", "statefulsets": "StatefulSet", "daemonsets": "DaemonSet",
            "services": "Service", "configmaps": "ConfigMap", "secrets": "Secret",
            "jobs": "Job", "cronjobs": "CronJob", "ingresses": "Ingress",
            "persistentvolumeclaims": "PersistentVolumeClaim", "persistentvolumes": "PersistentVolume",
            "serviceaccounts": "ServiceAccount", "roles": "Role", "rolebindings": "RoleBinding",
            "clusterroles": "ClusterRole", "clusterrolebindings": "ClusterRoleBinding",
            "namespaces": "Namespace", "pods": "Pod", "nodes": "Node",
            "horizontalpodautoscalers": "HorizontalPodAutoscaler", "networkpolicies": "NetworkPolicy",
            "resourcequotas": "ResourceQuota", "storageclasses": "StorageClass",
        }

    # ==================== 规格归一化（备份/恢复通用） ====================
    def _normalize_service_ports(self, ports: List[Dict], *, for_backup: bool) -> List[Dict]:
        normalized_ports: List[Dict] = []
        for port in ports or []:
            if not isinstance(port, dict):
                continue
            port = dict(port)
            # 统一字段命名
            if "target_port" in port:
                port["targetPort"] = port.pop("target_port")
            if "node_port" in port:
                port["nodePort"] = port.pop("node_port")

            # 类型纠正（targetPort 数字优先；字符串保留为命名端口）
            if "targetPort" in port and isinstance(port["targetPort"], str):
                try:
                    port["targetPort"] = int(port["targetPort"])
                except ValueError:
                    pass

            # 运行时字段移除
            for k in ["nodePort"]:
                port.pop(k, None)

            # 移除 None
            for k in [key for key, val in list(port.items()) if val is None]:
                port.pop(k, None)

            normalized_ports.append(port)
        return normalized_ports

    def _normalize_spec(self, kind: str, spec: Dict, *, for_backup: bool) -> Dict:
        if not isinstance(spec, dict):
            return spec

        normalized = json.loads(json.dumps(spec))

        # 通用运行时字段移除
        runtime_fields_common = ["finalizers"] if for_backup else []
        for f in runtime_fields_common:
            normalized.pop(f, None)

        if kind == "Service":
            # Service 运行时字段
            runtime_fields_service = ["clusterIP", "clusterIPs", "cluster_ip", "external_ips", "load_balancer_ip", "session_affinity"]
            for f in runtime_fields_service:
                normalized.pop(f, None)
            if "ports" in normalized:
                normalized["ports"] = self._normalize_service_ports(normalized.get("ports", []), for_backup=for_backup)

        elif kind == "PersistentVolumeClaim":
            # PVC 运行时字段
            normalized.pop("volumeName", None)
            if for_backup:
                normalized.pop("phase", None)

        elif kind in ["Deployment", "StatefulSet", "DaemonSet"]:
            # 工作负载类型通用处理
            # strategy 纠正
            if "strategy" in normalized and isinstance(normalized["strategy"], str):
                strategy_type = normalized["strategy"]
                normalized["strategy"] = {
                    "type": strategy_type,
                    "rollingUpdate": {"maxUnavailable": "25%", "maxSurge": "25%"}
                }
            
            # selector 纠正
            if "selector" in normalized:
                selector = normalized["selector"]
                if not isinstance(selector, dict) or "matchLabels" not in selector:
                    if isinstance(selector, dict):
                        normalized["selector"] = {"matchLabels": selector}
            
            # template 结构与标签对齐
            if "template" in normalized and isinstance(normalized["template"], dict):
                template = normalized["template"]
                if "metadata" not in template:
                    template["metadata"] = {}
                if "spec" not in template:
                    template["spec"] = {}
                if "containers" in template and "containers" not in template["spec"]:
                    template["spec"]["containers"] = template.pop("containers")
                if "selector" in normalized and isinstance(normalized["selector"], dict) and "matchLabels" in normalized["selector"]:
                    template["metadata"]["labels"] = normalized["selector"]["matchLabels"]
            
            # StatefulSet 特有字段
            if kind == "StatefulSet":
                if for_backup:
                    # 移除运行时状态
                    normalized.pop("currentReplicas", None)
                    normalized.pop("readyReplicas", None)
                    normalized.pop("currentRevision", None)
                    normalized.pop("updateRevision", None)

        elif kind == "Job":
            if for_backup:
                # Job 运行时字段
                for f in ["activeDeadlineSeconds", "completions", "parallelism"]:
                    if f in normalized and normalized[f] is None:
                        normalized.pop(f, None)

        elif kind == "CronJob":
            if for_backup:
                # CronJob 运行时字段
                normalized.pop("lastScheduleTime", None)

        elif kind == "Ingress":
            if for_backup:
                # Ingress 运行时字段
                normalized.pop("loadBalancer", None)

        elif kind in ["Role", "ClusterRole"]:
            # RBAC 角色类型
            if "rules" in normalized:
                # 确保 rules 是列表格式
                rules = normalized["rules"]
                if isinstance(rules, list):
                    for rule in rules:
                        if isinstance(rule, dict):
                            # 标准化字段名
                            if "api_groups" in rule:
                                rule["apiGroups"] = rule.pop("api_groups")
                            if "resource_names" in rule:
                                rule["resourceNames"] = rule.pop("resource_names")

        elif kind in ["RoleBinding", "ClusterRoleBinding"]:
            # RBAC 绑定类型
            if "roleRef" in normalized:
                role_ref = normalized["roleRef"]
                if isinstance(role_ref, dict):
                    # 标准化字段名
                    if "api_group" in role_ref:
                        role_ref["apiGroup"] = role_ref.pop("api_group")
            
            if "subjects" in normalized:
                subjects = normalized["subjects"]
                if isinstance(subjects, list):
                    for subject in subjects:
                        if isinstance(subject, dict):
                            # 标准化字段名
                            if "api_group" in subject:
                                subject["apiGroup"] = subject.pop("api_group")
                            # 清理空的apiGroup字段
                            if subject.get("apiGroup") is None or subject.get("apiGroup") == "":
                                subject.pop("apiGroup", None)

        elif kind == "ServiceAccount":
            if for_backup:
                # ServiceAccount 运行时字段
                normalized.pop("secrets", None)  # 自动生成的 secrets

        return normalized

    def _set_api_version_for_kind(self, resource: Dict) -> None:
        kind = resource.get("kind")
        if not kind:
            return
        api = self._api_version_map.get(kind)
        if api:
            resource["apiVersion"] = api
    
    def _create_base_k8s_resource(self, data: Dict, kind: str, from_backup: bool = False) -> Dict:
        """创建基础的 Kubernetes 资源结构
        
        Args:
            data: 原始数据（扁平化或备份格式）
            kind: 资源类型
            from_backup: 是否来自备份数据
        """
        # 处理 metadata
        if from_backup:
            metadata = data.get("metadata", {})
        else:
            # 从扁平化数据构建 metadata
            flat_metadata = data.get("metadata", {})
            metadata = {
                "name": data.get("name") or flat_metadata.get("name", ""),
                "namespace": data.get("namespace") or flat_metadata.get("namespace", ""),
                "labels": data.get("labels") or flat_metadata.get("labels") or {},
                "annotations": data.get("annotations") or flat_metadata.get("annotations") or {}
            }
        
        # 创建基础资源结构
        k8s_resource = {
            "apiVersion": self._api_version_map.get(kind, "v1"),
            "kind": kind,
            "metadata": metadata
        }
        
        return k8s_resource

    def _populate_resource_content(self, k8s_resource: Dict, data: Dict, kind: str, from_backup: bool = False) -> Dict:
        """填充资源的具体内容（spec、data、rules等）
        
        Args:
            k8s_resource: 基础 K8s 资源结构
            data: 原始数据
            kind: 资源类型
            from_backup: 是否来自备份数据
        """
        if kind == "ConfigMap":
            k8s_resource["data"] = data.get("data", {})
            if data.get("binary_data") or data.get("binaryData"):
                k8s_resource["binaryData"] = data.get("binary_data") or data.get("binaryData", {})
                
        elif kind == "Secret":
            # 处理Secret的数据字段
            if from_backup:
                k8s_resource["data"] = data.get("data", {})
            else:
                # 从API响应中获取数据，API返回的是decoded_data
                decoded_data = data.get("decoded_data", {})
                # 将明文数据转换为base64编码（Kubernetes要求）
                import base64
                encoded_data = {}
                for key, value in decoded_data.items():
                    if isinstance(value, str):
                        encoded_data[key] = base64.b64encode(value.encode('utf-8')).decode('utf-8')
                    else:
                        encoded_data[key] = value
                k8s_resource["data"] = encoded_data
            k8s_resource["type"] = data.get("type", "Opaque")
            
        elif kind == "Role":
            rules = data.get("rules", [])
            # 标准化 RBAC 字段名（如果不是来自备份）
            if not from_backup:
                cleaned_rules = []
                for rule in rules:
                    if isinstance(rule, dict):
                        cleaned_rule = {}
                        # 处理必需字段
                        if rule.get("api_groups"):
                            cleaned_rule["apiGroups"] = rule.get("api_groups")
                        elif "api_groups" in rule:
                            cleaned_rule["apiGroups"] = rule.pop("api_groups")
                        
                        if rule.get("resources"):
                            cleaned_rule["resources"] = rule.get("resources")
                        
                        if rule.get("verbs"):
                            cleaned_rule["verbs"] = rule.get("verbs")
                        
                        # 处理可选字段（只有当有值时才添加）
                        if rule.get("resource_names"):
                            cleaned_rule["resourceNames"] = rule.get("resource_names")
                        elif "resource_names" in rule and rule["resource_names"]:
                            cleaned_rule["resourceNames"] = rule.pop("resource_names")
                        
                        if rule.get("non_resource_urls"):
                            cleaned_rule["nonResourceURLs"] = rule.get("non_resource_urls")
                        
                        cleaned_rules.append(cleaned_rule)
                rules = cleaned_rules
            k8s_resource["rules"] = rules
            
        elif kind == "RoleBinding":
            subjects = data.get("subjects", [])
            role_ref = data.get("role_ref") or data.get("roleRef", {})
            
            # 标准化字段名（如果不是来自备份）
            if not from_backup:
                for subject in subjects:
                    if isinstance(subject, dict):
                        if "api_group" in subject:
                            subject["apiGroup"] = subject.pop("api_group")
                
                if isinstance(role_ref, dict):
                    if "api_group" in role_ref:
                        role_ref["apiGroup"] = role_ref.pop("api_group")
            
            k8s_resource["subjects"] = subjects
            k8s_resource["roleRef"] = role_ref
            
        elif kind in ["Deployment", "StatefulSet", "DaemonSet", "Service", "Job", "CronJob", "Ingress", "PersistentVolumeClaim", "ServiceAccount"]:
            # 处理有 spec 字段的资源
            if from_backup:
                spec = data.get("spec", {})
                spec = self._normalize_spec(kind, spec, for_backup=False)
            else:
                # 从扁平化数据构建 spec
                spec = self._build_spec_from_flat_data(data, kind)
            k8s_resource["spec"] = spec
        
        return k8s_resource
    
    def _build_spec_from_flat_data(self, flat_data: Dict, kind: str) -> Dict:
        """从扁平化数据构建 spec 字段"""
        if kind == "Deployment":
            # 从API返回的结构中提取spec数据
            api_spec = flat_data.get("spec", {})
            
            spec = {
                "replicas": api_spec.get("replicas", 1),
                "selector": {
                    "matchLabels": api_spec.get("selector", {})
                },
                "template": {
                    "metadata": api_spec.get("template", {}).get("metadata", {"labels": api_spec.get("selector", {})}),
                    "spec": {
                        "containers": self._convert_containers(api_spec.get("template", {}).get("spec", {}).get("containers", [])),
                        "volumes": api_spec.get("template", {}).get("spec", {}).get("volumes", [])
                    }
                }
            }
            # 添加策略
            if api_spec.get("strategy"):
                spec["strategy"] = {"type": api_spec.get("strategy")}
            return spec
            
        elif kind == "StatefulSet":
            # 从API返回的结构中提取spec数据
            api_spec = flat_data.get("spec", {})
            
            spec = {
                "replicas": api_spec.get("replicas", 1),
                "selector": {
                    "matchLabels": api_spec.get("selector", {})
                },
                "serviceName": api_spec.get("serviceName", ""),
                "template": {
                    "metadata": api_spec.get("template", {}).get("metadata", {"labels": api_spec.get("selector", {})}),
                    "spec": {
                        "containers": self._convert_containers(api_spec.get("template", {}).get("spec", {}).get("containers", [])),
                        "volumes": api_spec.get("template", {}).get("spec", {}).get("volumes", [])
                    }
                }
            }
            if api_spec.get("volumeClaimTemplates"):
                spec["volumeClaimTemplates"] = self._convert_volume_claim_templates(
                    api_spec.get("volumeClaimTemplates", [])
                )
            return spec
            
        elif kind == "DaemonSet":
            # 从API返回的结构中提取spec数据
            api_spec = flat_data.get("spec", {})
            
            return {
                "selector": {
                    "matchLabels": api_spec.get("selector", {})
                },
                "template": {
                    "metadata": api_spec.get("template", {}).get("metadata", {"labels": api_spec.get("selector", {})}),
                    "spec": {
                        "containers": self._convert_containers(api_spec.get("template", {}).get("spec", {}).get("containers", [])),
                        "volumes": api_spec.get("template", {}).get("spec", {}).get("volumes", [])
                    }
                }
            }

        elif kind == "Service":
            # 从API返回的结构中提取spec数据
            api_spec = flat_data.get("spec", {})
            
            spec = {
                "type": api_spec.get("type", "ClusterIP"),
                "ports": api_spec.get("ports", []),
                "selector": api_spec.get("selector", {})
            }
            if api_spec.get("cluster_ip") or api_spec.get("clusterIP"):
                spec["clusterIP"] = api_spec.get("cluster_ip") or api_spec.get("clusterIP")
            return spec

        elif kind == "Job":
            # 从API返回的结构中提取spec数据
            api_spec = flat_data.get("spec", {})
            
            spec = {
                "template": {
                    "metadata": api_spec.get("template", {}).get("metadata", {}),
                    "spec": {
                        "containers": self._convert_containers(api_spec.get("template", {}).get("spec", {}).get("containers", [])),
                        "restartPolicy": api_spec.get("template", {}).get("spec", {}).get("restartPolicy", api_spec.get("template", {}).get("restart_policy", "Never"))
                    }
                }
            }
            for field in ["completions", "parallelism", "backoffLimit"]:
                if api_spec.get(field):
                    spec[field] = api_spec.get(field)
            return spec
            
        elif kind == "CronJob":
            # 从API返回的结构中提取spec数据
            api_spec = flat_data.get("spec", {})
            
            spec = {
                "schedule": api_spec.get("schedule", ""),
                "jobTemplate": {
                    "spec": {
                        "template": {
                            "metadata": api_spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("metadata", {}),
                            "spec": {
                                "containers": self._convert_containers(api_spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])),
                                "restartPolicy": api_spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec", {}).get("restartPolicy", api_spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("restart_policy", "Never"))
                            }
                        }
                    }
                }
            }
            if api_spec.get("suspend") is not None:
                spec["suspend"] = api_spec.get("suspend")
            return spec
            
        elif kind == "Ingress":
            # 从API返回的结构中提取spec数据
            api_spec = flat_data.get("spec", {})
            
            spec = {}
            if api_spec.get("rules"):
                spec["rules"] = api_spec.get("rules", [])
            if api_spec.get("tls"):
                spec["tls"] = api_spec.get("tls", [])
            if api_spec.get("ingressClassName"):
                spec["ingressClassName"] = api_spec.get("ingressClassName")
            return spec
            
        elif kind == "PersistentVolumeClaim":
            # 从API返回的结构中提取spec数据
            api_spec = flat_data.get("spec", {})
            
            spec = {
                "accessModes": api_spec.get("accessModes", ["ReadWriteOnce"]),
                "resources": api_spec.get("resources", {
                    "requests": {
                        "storage": api_spec.get("resources", {}).get("requests", {}).get("storage", "1Gi")
                    }
                })
            }
            if api_spec.get("storageClassName"):
                spec["storageClassName"] = api_spec.get("storageClassName")
            if api_spec.get("volumeMode"):
                spec["volumeMode"] = api_spec.get("volumeMode")
            return spec

        elif kind == "ServiceAccount":
            # ServiceAccount通常不需要从spec构建，大部分信息在metadata中
            spec = {}
            if flat_data.get("automount_service_account_token") is not None:
                spec["automountServiceAccountToken"] = flat_data.get("automount_service_account_token")
            if flat_data.get("image_pull_secrets"):
                spec["imagePullSecrets"] = [
                    {"name": secret} for secret in flat_data.get("image_pull_secrets", [])
                ]
            return spec
        
        return {}

    def _convert_flat_to_k8s_format(self, flat_data: Dict, kind: str) -> Dict:
        """将 k8s_api_service 返回的扁平化数据转换为标准的 Kubernetes 资源格式"""
        if not flat_data or not kind:
            return {}
        
        # 使用统一的转换系统
        k8s_resource = self._create_base_k8s_resource(flat_data, kind, from_backup=False)
        k8s_resource = self._populate_resource_content(k8s_resource, flat_data, kind, from_backup=False)
        
        return k8s_resource
    
    def _convert_containers(self, containers_data: list) -> list:
        """转换容器数据格式"""
        containers = []
        for c in containers_data:
            container = {
                "name": c.get("name", ""),
                "image": c.get("image", "")
            }
            if c.get("imagePullPolicy"):
                container["imagePullPolicy"] = c.get("imagePullPolicy")
            if c.get("command"):
                container["command"] = c.get("command")
            if c.get("args"):
                container["args"] = c.get("args")
            if c.get("ports"):
                container["ports"] = []
                for port in c.get("ports", []):
                    port_config = {"containerPort": port.get("containerPort", port.get("port", 80))}
                    if port.get("name"):
                        port_config["name"] = port.get("name")
                    if port.get("protocol"):
                        port_config["protocol"] = port.get("protocol")
                    container["ports"].append(port_config)
            if c.get("env"):
                # 清理env中的None值
                env_vars = []
                for env in c.get("env", []):
                    if env.get("name"):
                        env_var = {"name": env.get("name")}
                        if env.get("value") is not None:
                            env_var["value"] = env.get("value")
                        elif env.get("valueFrom"):
                            value_from = env.get("valueFrom")
                            if value_from.get("secretKeyRef"):
                                env_var["valueFrom"] = {"secretKeyRef": value_from.get("secretKeyRef")}
                            elif value_from.get("configMapKeyRef"):
                                env_var["valueFrom"] = {"configMapKeyRef": value_from.get("configMapKeyRef")}
                        # 如果既没有value也没有valueFrom，仍然添加环境变量（可能是占位符）
                        env_vars.append(env_var)
                container["env"] = env_vars
            if c.get("resources"):
                # 清理resources中的None值
                resources = {}
                if c.get("resources", {}).get("requests"):
                    requests = {k: v for k, v in c.get("resources", {}).get("requests", {}).items() if v is not None}
                    if requests:
                        resources["requests"] = requests
                if c.get("resources", {}).get("limits"):
                    limits = {k: v for k, v in c.get("resources", {}).get("limits", {}).items() if v is not None}
                    if limits:
                        resources["limits"] = limits
                if resources:
                    container["resources"] = resources
            if c.get("livenessProbe"):
                probe = c.get("livenessProbe")
                if probe.get("httpGet") or probe.get("initialDelaySeconds") or probe.get("periodSeconds"):
                    liveness_probe = {}
                    if probe.get("httpGet"):
                        liveness_probe["httpGet"] = probe.get("httpGet")
                    if probe.get("initialDelaySeconds"):
                        liveness_probe["initialDelaySeconds"] = probe.get("initialDelaySeconds")
                    if probe.get("periodSeconds"):
                        liveness_probe["periodSeconds"] = probe.get("periodSeconds")
                    if probe.get("successThreshold"):
                        liveness_probe["successThreshold"] = probe.get("successThreshold")
                    if probe.get("failureThreshold"):
                        liveness_probe["failureThreshold"] = probe.get("failureThreshold")
                    container["livenessProbe"] = liveness_probe
            if c.get("readinessProbe"):
                probe = c.get("readinessProbe")
                if probe.get("httpGet") or probe.get("initialDelaySeconds") or probe.get("periodSeconds"):
                    readiness_probe = {}
                    if probe.get("httpGet"):
                        readiness_probe["httpGet"] = probe.get("httpGet")
                    if probe.get("initialDelaySeconds"):
                        readiness_probe["initialDelaySeconds"] = probe.get("initialDelaySeconds")
                    if probe.get("periodSeconds"):
                        readiness_probe["periodSeconds"] = probe.get("periodSeconds")
                    if probe.get("successThreshold"):
                        readiness_probe["successThreshold"] = probe.get("successThreshold")
                    if probe.get("failureThreshold"):
                        readiness_probe["failureThreshold"] = probe.get("failureThreshold")
                    container["readinessProbe"] = readiness_probe
            if c.get("volumeMounts"):
                container["volumeMounts"] = []
                for vm in c.get("volumeMounts", []):
                    volume_mount = {
                        "name": vm.get("name", ""),
                        "mountPath": vm.get("mountPath", "")
                    }
                    if vm.get("readOnly") is not None:
                        volume_mount["readOnly"] = vm.get("readOnly")
                    if vm.get("subPath"):
                        volume_mount["subPath"] = vm.get("subPath")
                    container["volumeMounts"].append(volume_mount)
            containers.append(container)
        return containers
    
    def _convert_volume_claim_templates(self, vct_data: list) -> list:
        """转换卷声明模板数据格式"""
        templates = []
        for vct in vct_data:
            template = {
                "metadata": vct.get("metadata", {"name": vct.get("name", "")}),
                "spec": {
                    "accessModes": vct.get("spec", {}).get("accessModes", vct.get("access_modes", ["ReadWriteOnce"])),
                    "resources": vct.get("spec", {}).get("resources", {
                        "requests": {
                            "storage": vct.get("storage", "1Gi")
                        }
                    })
                }
            }
            storage_class = vct.get("spec", {}).get("storageClassName") or vct.get("storage_class")
            if storage_class:
                template["spec"]["storageClassName"] = storage_class
            templates.append(template)
        return templates
    
    async def _backup_resource_type(self, resource_type: str, namespace: str) -> List[Dict]:
        """统一的资源类型备份方法"""
        try:
            # 使用ResourceManager获取配置
            config = self.resource_manager.get_resource_config(resource_type)
            if not config:
                return []
            
            resources = []
            
            # 获取列表和详情操作方法
            list_method = self.resource_manager.get_operation_method(resource_type, "list", namespace)
            get_method = self.resource_manager.get_operation_method(resource_type, "get", namespace)
            
            # 列出资源
            listed = await list_method()
            
            for r in listed:
                resource_name = r.get("name")
                if not resource_name:
                    continue
                
                # 检查跳过条件
                if config.skip_condition and config.skip_condition(resource_name):
                    continue
                
                try:
                    # 获取资源详情
                    resource_data = await get_method(resource_name)
                    if not resource_data or resource_data == {}:
                        continue
                    
                    # 使用转换函数处理资源数据
                    k8s_resource = self._convert_flat_to_k8s_format(resource_data, config.kind)
                    processed_resource = self._sanitize_for_backup(k8s_resource)
                    
                    resources.append(processed_resource)
                    
                except Exception as e:
                    print(f"获取 {config.kind} {resource_name} 失败: {e}")
                    continue
        
        except Exception as e:
            print(f"备份 {resource_type} 失败: {e}")
            return []
        
        return resources
    
    # ==================== 批量操作相关方法 ====================
    
    def _get_resource_operation(self, resource_type: str, operation: str, namespace: str = "default"):
        """获取资源操作方法的统一接口"""
        resource_type = resource_type.lower()
        
        # 资源类型规范化映射 - 将简写转换为标准名称
        resource_type_normalization = {
            "hpa": "horizontalpodautoscalers",
            "pvc": "persistentvolumeclaims",
            "pv": "persistentvolumes",
            "sc": "storageclasses",
            "sa": "serviceaccounts",
            "cm": "configmaps",
            "svc": "services",
            "deploy": "deployments",
            "sts": "statefulsets",
            "ds": "daemonsets",
            "rs": "replicasets",
            "rc": "replicationcontrollers",
            "ep": "endpoints",
            "ev": "events",
            "ns": "namespaces",
            "no": "nodes",
            "po": "pods",
            # 单数形式也映射到复数形式
            "deployment": "deployments",
            "statefulset": "statefulsets",
            "daemonset": "daemonsets",
            "service": "services",
            "configmap": "configmaps",
            "secret": "secrets",
            "job": "jobs",
            "cronjob": "cronjobs",
            "ingress": "ingresses",
            "storageclass": "storageclasses",
            "persistentvolume": "persistentvolumes",
            "persistentvolumeclaim": "persistentvolumeclaims",
            "role": "roles",
            "clusterrole": "clusterroles",
            "rolebinding": "rolebindings",
            "clusterrolebinding": "clusterrolebindings",
            "serviceaccount": "serviceaccounts",
            "namespace": "namespaces",
            "pod": "pods",
            "node": "nodes",
            "horizontalpodautoscaler": "horizontalpodautoscalers",
            "networkpolicy": "networkpolicies",
            "resourcequota": "resourcequotas"
        }
        
        # 规范化资源类型
        resource_type = resource_type_normalization.get(resource_type, resource_type)
        
        # 列表操作映射
        list_operations = {
            "deployments": lambda: self.k8s_service.list_deployments(namespace=namespace),
            "statefulsets": lambda: self.k8s_service.list_statefulsets(namespace=namespace),
            "daemonsets": lambda: self.k8s_service.list_daemonsets(namespace=namespace),
            "services": lambda: self.k8s_service.list_services(namespace=namespace),
            "configmaps": lambda: self.k8s_service.list_configmaps(namespace=namespace),
            "secrets": lambda: self.k8s_service.list_secrets(namespace=namespace),
            "jobs": lambda: self.k8s_service.list_jobs(namespace=namespace),
            "cronjobs": lambda: self.k8s_service.list_cronjobs(namespace=namespace),
            "ingresses": lambda: self.k8s_service.list_ingresses(namespace=namespace),
            "storageclasses": lambda: self.k8s_service.list_storageclasses(),
            "persistentvolumes": lambda: self.k8s_service.list_persistentvolumes(),
            "persistentvolumeclaims": lambda: self.k8s_service.list_persistentvolumeclaims(namespace=namespace),
            "roles": lambda: self.k8s_service.list_roles(namespace=namespace),
            "clusterroles": lambda: self.k8s_service.list_cluster_roles(),
            "rolebindings": lambda: self.k8s_service.list_role_bindings(namespace=namespace),
            "clusterrolebindings": lambda: self.k8s_service.list_cluster_role_bindings(),
            "serviceaccounts": lambda: self.k8s_service.list_serviceaccounts(namespace=namespace),
            "namespaces": lambda: self.k8s_service.list_namespaces(),
            "pods": lambda: self.k8s_service.list_pods(namespace=namespace),
            "nodes": lambda: self.k8s_service.list_nodes(),
            "horizontalpodautoscalers": lambda: self.k8s_service.list_hpas(namespace=namespace),
            "networkpolicies": lambda: self.k8s_service.list_network_policies(namespace=namespace),
            "resourcequotas": lambda: self.k8s_service.list_resource_quotas(namespace=namespace),
        }
        
        # 创建操作映射
        create_operations = {
            "deployments": lambda resource: self.k8s_service.create_deployment(resource=resource, namespace=namespace),
            "statefulsets": lambda resource: self.k8s_service.create_statefulset(resource=resource, namespace=namespace),
            "daemonsets": lambda resource: self.k8s_service.create_daemonset(resource=resource, namespace=namespace),
            "services": lambda resource: self.k8s_service.create_service(resource=resource, namespace=namespace),
            "configmaps": lambda resource: self.k8s_service.create_configmap(resource=resource, namespace=namespace),
            "secrets": lambda resource: self.k8s_service.create_secret(resource=resource, namespace=namespace),
            "jobs": lambda resource: self.k8s_service.create_job(resource=resource, namespace=namespace),
            "cronjobs": lambda resource: self.k8s_service.create_cronjob(resource=resource, namespace=namespace),
            "ingresses": lambda resource: self.k8s_service.create_ingress(resource=resource, namespace=namespace),
            "storageclasses": lambda resource: self.k8s_service.create_storageclass(resource=resource),
            "persistentvolumes": lambda resource: self.k8s_service.create_persistentvolume(resource=resource),
            "persistentvolumeclaims": lambda resource: self.k8s_service.create_persistentvolumeclaim(resource=resource, namespace=namespace),
            "roles": lambda resource: self.k8s_service.create_role(resource=resource, namespace=namespace),
            "clusterroles": lambda resource: self.k8s_service.create_cluster_role(resource=resource),
            "rolebindings": lambda resource: self.k8s_service.create_role_binding(resource=resource, namespace=namespace),
            "clusterrolebindings": lambda resource: self.k8s_service.create_cluster_role_binding(resource=resource),
            "serviceaccounts": lambda resource: self.k8s_service.create_serviceaccount(resource=resource, namespace=namespace),
            "namespaces": lambda resource: self.k8s_service.create_namespace(resource=resource),
            "horizontalpodautoscalers": lambda resource: self.k8s_service.create_hpa(resource=resource, namespace=namespace),
            "networkpolicies": lambda resource: self.k8s_service.create_network_policy(resource=resource, namespace=namespace),
            "resourcequotas": lambda resource: self.k8s_service.create_resource_quota(resource=resource, namespace=namespace),
        }
        
        # 更新操作映射
        update_operations = {
            "deployments": lambda name, resource: self.k8s_service.update_deployment(name=name, namespace=namespace, resource=resource),
            "statefulsets": lambda name, resource: self.k8s_service.update_statefulset(name=name, namespace=namespace, resource=resource),
            "daemonsets": lambda name, resource: self.k8s_service.update_daemonset(name=name, namespace=namespace, resource=resource),
            "services": lambda name, resource: self.k8s_service.update_service(name=name, namespace=namespace, resource=resource),
            "configmaps": lambda name, resource: self.k8s_service.update_configmap(name=name, namespace=namespace, resource=resource),
            "secrets": lambda name, resource: self.k8s_service.update_secret(name=name, namespace=namespace, resource=resource),
            "jobs": lambda name, resource: self.k8s_service.update_job(name=name, namespace=namespace, resource=resource),
            "cronjobs": lambda name, resource: self.k8s_service.update_cronjob(name=name, namespace=namespace, resource=resource),
            "ingresses": lambda name, resource: self.k8s_service.update_ingress(name=name, namespace=namespace, resource=resource),
            "storageclasses": lambda name, resource: self.k8s_service.update_storageclass(name=name, resource=resource),
            "persistentvolumes": lambda name, resource: self.k8s_service.update_persistentvolume(name=name, resource=resource),
            "persistentvolumeclaims": lambda name, resource: self.k8s_service.update_persistentvolumeclaim(name=name, namespace=namespace, resource=resource),
            "roles": lambda name, resource: self.k8s_service.update_role(name=name, namespace=namespace, resource=resource),
            "clusterroles": lambda name, resource: self.k8s_service.update_cluster_role(name=name, resource=resource),
            "rolebindings": lambda name, resource: self.k8s_service.update_role_binding(name=name, namespace=namespace, resource=resource),
            "clusterrolebindings": lambda name, resource: self.k8s_service.update_cluster_role_binding(name=name, resource=resource),
            "serviceaccounts": lambda name, resource: self.k8s_service.update_serviceaccount(name=name, namespace=namespace, resource=resource),
            "namespaces": lambda name, resource: self.k8s_service.update_namespace(name=name, resource=resource),
            "horizontalpodautoscalers": lambda name, resource: self.k8s_service.update_hpa(name=name, namespace=namespace, resource=resource),
            "networkpolicies": lambda name, resource: self.k8s_service.update_network_policy(name=name, namespace=namespace, resource=resource),
            "resourcequotas": lambda name, resource: self.k8s_service.update_resource_quota(name=name, namespace=namespace, resource=resource),
        }
        
        # 获取单个资源操作映射
        get_operations = {
            "deployments": lambda name: self.k8s_service.get_deployment(name=name, namespace=namespace),
            "statefulsets": lambda name: self.k8s_service.get_statefulset(name=name, namespace=namespace),
            "daemonsets": lambda name: self.k8s_service.get_daemonset(name=name, namespace=namespace),
            "services": lambda name: self.k8s_service.get_service(name=name, namespace=namespace),
            "configmaps": lambda name: self.k8s_service.get_configmap(name=name, namespace=namespace),
            "secrets": lambda name: self.k8s_service.get_secret(name=name, namespace=namespace),
            "jobs": lambda name: self.k8s_service.get_job(name=name, namespace=namespace),
            "cronjobs": lambda name: self.k8s_service.get_cronjob(name=name, namespace=namespace),
            "ingresses": lambda name: self.k8s_service.get_ingress(name=name, namespace=namespace),
            "storageclasses": lambda name: self.k8s_service.get_storageclass(name=name),
            "persistentvolumes": lambda name: self.k8s_service.get_persistentvolume(name=name),
            "persistentvolumeclaims": lambda name: self.k8s_service.get_persistentvolumeclaim(name=name, namespace=namespace),
            "roles": lambda name: self.k8s_service.get_role(name=name, namespace=namespace),
            "clusterroles": lambda name: self.k8s_service.get_cluster_role(name=name),
            "rolebindings": lambda name: self.k8s_service.get_role_binding(name=name, namespace=namespace),
            "clusterrolebindings": lambda name: self.k8s_service.get_cluster_role_binding(name=name),
            "serviceaccounts": lambda name: self.k8s_service.get_serviceaccount(name=name, namespace=namespace),
            "namespaces": lambda name: self.k8s_service.get_namespace(name=name),
            "pods": lambda name: self.k8s_service.get_pod(name=name, namespace=namespace),
            "nodes": lambda name: self.k8s_service.get_node(name=name),
            "horizontalpodautoscalers": lambda name: self.k8s_service.get_hpa(name=name, namespace=namespace),
            "networkpolicies": lambda name: self.k8s_service.get_network_policy(name=name, namespace=namespace),
            "resourcequotas": lambda name: self.k8s_service.get_resource_quota(name=name, namespace=namespace),
        }

        # 删除操作映射（带grace_period_seconds支持）
        delete_operations = {
            "deployments": lambda name, grace: self.k8s_service.delete_deployment(name=name, namespace=namespace, grace_period_seconds=grace),
            "statefulsets": lambda name, grace: self.k8s_service.delete_statefulset(name=name, namespace=namespace, grace_period_seconds=grace),
            "daemonsets": lambda name, grace: self.k8s_service.delete_daemonset(name=name, namespace=namespace),
            "services": lambda name, grace: self.k8s_service.delete_service(name=name, namespace=namespace),
            "configmaps": lambda name, grace: self.k8s_service.delete_configmap(name=name, namespace=namespace),
            "secrets": lambda name, grace: self.k8s_service.delete_secret(name=name, namespace=namespace),
            "jobs": lambda name, grace: self.k8s_service.delete_job(name=name, namespace=namespace),
            "cronjobs": lambda name, grace: self.k8s_service.delete_cronjob(name=name, namespace=namespace),
            "ingresses": lambda name, grace: self.k8s_service.delete_ingress(name=name, namespace=namespace),
            "storageclasses": lambda name, grace: self.k8s_service.delete_storageclass(name=name),
            "persistentvolumes": lambda name, grace: self.k8s_service.delete_persistentvolume(name=name),
            "persistentvolumeclaims": lambda name, grace: self.k8s_service.delete_persistentvolumeclaim(name=name, namespace=namespace),
            "roles": lambda name, grace: self.k8s_service.delete_role(name=name, namespace=namespace),
            "clusterroles": lambda name, grace: self.k8s_service.delete_cluster_role(name=name),
            "rolebindings": lambda name, grace: self.k8s_service.delete_role_binding(name=name, namespace=namespace),
            "clusterrolebindings": lambda name, grace: self.k8s_service.delete_cluster_role_binding(name=name),
            "serviceaccounts": lambda name, grace: self.k8s_service.delete_serviceaccount(name=name, namespace=namespace, grace_period_seconds=grace),
            "namespaces": lambda name, grace: self.k8s_service.delete_namespace(name=name),
            "pods": lambda name, grace: self.k8s_service.delete_pod(name=name, namespace=namespace, grace_period_seconds=grace),
            "horizontalpodautoscalers": lambda name, grace: self.k8s_service.delete_hpa(name=name, namespace=namespace),
            "networkpolicies": lambda name, grace: self.k8s_service.delete_network_policy(name=name, namespace=namespace),
            "resourcequotas": lambda name, grace: self.k8s_service.delete_resource_quota(name=name, namespace=namespace),
        }
        
        operations_map = {
            "list": list_operations,
            "get": get_operations,
            "create": create_operations,
            "update": update_operations,
            "delete": delete_operations
        }
        
        if operation not in operations_map:
            raise ValueError(f"不支持的操作类型: {operation}")
        
        if resource_type not in operations_map[operation]:
            raise ValueError(f"资源类型 {resource_type} 不支持 {operation} 操作")
        
        return operations_map[operation][resource_type]

    def _resolve_to_api_version_kind(self, resource_type: str) -> tuple:
        """将 resource_type 解析为 (api_version, kind)，用于动态 API"""
        rt = resource_type.lower().strip()
        kind = self._resource_type_to_kind.get(rt)
        if kind:
            api_version = self._api_version_map.get(kind, "v1")
            return (api_version, kind)
        # 从集群发现中查找（支持 CRD 等任意资源）
        for r in self._dynamic_service.list_available_resources():
            if r["name"].lower() == rt or r["kind"].lower() == rt:
                return (r["group_version"], r["kind"])
        raise ValueError(f"无法解析资源类型: {resource_type}，请使用 batch_list_resources(resource_types='all') 查看可用资源")

    def list_available_api_resources(self) -> List[Dict[str, Any]]:
        """列出集群中所有可发现的 API 资源"""
        return self._dynamic_service.list_available_resources()

    async def batch_list_resources(self, resource_types: List[str], namespace: str = "default") -> Dict:
        """批量查看资源"""
        # 特殊值：列出集群中所有可用的 API 资源类型
        if len(resource_types) == 1 and resource_types[0].lower() in ("all", "__all__", "__discover__"):
            try:
                resources = self.list_available_api_resources()
                return {
                    "success": [{"resource_type": "__discover__", "available_resources": resources, "count": len(resources)}],
                    "failed": [],
                    "total": 1
                }
            except Exception as e:
                return {"success": [], "failed": [{"resource_type": "__discover__", "error": str(e)}], "total": 1}

        results = {"success": [], "failed": [], "total": len(resource_types)}
        
        for resource_type in resource_types:
            try:
                resource_type = resource_type.lower()
                try:
                    operation_func = self._get_resource_operation(resource_type, "list", namespace)
                    result = await operation_func()
                except ValueError:
                    # 不在预定义映射中，尝试动态 API
                    api_version, kind = self._resolve_to_api_version_kind(resource_type)
                    result = self._dynamic_service.list_resources(api_version, kind, namespace)
                
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

    async def batch_describe_resources(self, resource_specs: List[Dict], namespace: str = "default") -> Dict:
        """批量获取资源详细信息"""
        results = {"success": [], "failed": [], "total": len(resource_specs)}
        
        for spec in resource_specs:
            try:
                kind = spec["kind"]
                name = spec["name"]
                api_version = spec.get("apiVersion") or self._api_version_map.get(kind, "v1")
                
                try:
                    resource_type = self._kind_to_resource_type(kind)
                    operation_func = self._get_resource_operation(resource_type, "get", namespace)
                    result = await operation_func(name)
                except ValueError:
                    result = self._dynamic_service.get_resource(api_version, kind, name, namespace)
                
                results["success"].append({
                    "kind": kind,
                    "name": name,
                    "namespace": namespace,
                    "details": result
                })
                
            except Exception as e:
                results["failed"].append({
                    "kind": spec.get("kind", "Unknown"),
                    "name": spec.get("name", "Unknown"),
                    "error": str(e)
                })
        
        return results
    
    def _kind_to_resource_type(self, kind: str) -> str:
        """将 Kind 转换为资源类型"""
        kind_mapping = {
            "Pod": "pods",
            "Deployment": "deployments", 
            "StatefulSet": "statefulsets",
            "DaemonSet": "daemonsets",
            "Service": "services",
            "ConfigMap": "configmaps",
            "Secret": "secrets",
            "Job": "jobs",
            "CronJob": "cronjobs",
            "Ingress": "ingresses",
            "PersistentVolumeClaim": "persistentvolumeclaims",
            "ServiceAccount": "serviceaccounts",
            "Role": "roles",
            "RoleBinding": "rolebindings",
            "Node": "nodes",
            "Namespace": "namespaces",
            "HorizontalPodAutoscaler": "horizontalpodautoscalers",
            "HPA": "horizontalpodautoscalers",  # 简写也映射到标准名称
            "NetworkPolicy": "networkpolicies",
            "ResourceQuota": "resourcequotas"
        }
        
        resource_type = kind_mapping.get(kind)
        if not resource_type:
            raise ValueError(f"不支持的资源类型: {kind}")
        
        return resource_type

    # 注意：通用批量操作方法已删除，现在使用专门的批量方法

    async def batch_create_resources(self, resources: List[Dict], namespace: str = "default") -> Dict:
        """批量创建k8s资源 - 自动集成验证和预览功能"""
        print(f"\n🚀 开始批量创建 {len(resources)} 个资源...")
        
        results = {"success": [], "failed": [], "total": len(resources)}
        
        for resource in resources:
            resource_type = resource.get("kind", "").lower()
            resource_name = resource.get("metadata", {}).get("name", "unknown")
                
            try:
                try:
                    operation_func = self._get_resource_operation(resource_type, "create", namespace)
                    result = await operation_func(resource)
                except ValueError:
                    # 不在预定义映射中，使用动态 API
                    result = self._dynamic_service.create_resource(resource, namespace)
                results["success"].append({
                    "name": resource_name,
                    "kind": resource_type,
                    "result": result
                })
            except Exception as e:
                results["failed"].append({
                    "name": resource_name,
                    "kind": resource_type,
                    "error": str(e)
                })
        
        print(f"✅ 批量创建完成: {len(results['success'])} 成功, {len(results['failed'])} 失败\n")
        return results
    
    async def batch_update_resources(self, resources: List[Dict], namespace: str = "default") -> Dict:
        """批量更新资源 - 自动集成验证和预览功能"""
        print(f"\n🔄 开始批量更新 {len(resources)} 个资源...")
        
        results = {"success": [], "failed": [], "total": len(resources)}
        
        for resource in resources:
            resource_type = resource.get("kind", "").lower()
            resource_name = resource.get("metadata", {}).get("name", "unknown")
                
            try:
                try:
                    operation_func = self._get_resource_operation(resource_type, "update", namespace)
                    result = await operation_func(resource_name, resource)
                except ValueError:
                    result = self._dynamic_service.update_resource(resource, namespace)
                results["success"].append({
                    "name": resource_name,
                    "kind": resource_type,
                    "result": result
                })
            except Exception as e:
                results["failed"].append({
                    "name": resource_name,
                    "kind": resource_type,
                    "error": str(e)
                })
        
        print(f"✅ 批量更新完成: {len(results['success'])} 成功, {len(results['failed'])} 失败\n")
        return results
    
    async def batch_rollout_resources(self, operations: List[Dict], namespace: str = "default") -> Dict:
        """批量发布操作：status 查看状态、undo 回滚、pause 暂停、resume 恢复"""
        results = {"success": [], "failed": [], "total": len(operations)}
        supported_kinds = ["deployment", "statefulset", "daemonset"]
        for op in operations:
            kind = (op.get("kind") or "").lower()
            name = op.get("name", "")
            action = (op.get("action") or "status").lower()
            ns = op.get("namespace") or namespace
            try:
                if kind not in supported_kinds:
                    raise ValueError(f"不支持的资源类型: {kind}")
                if not name:
                    raise ValueError("必须指定 name")
                if action == "status":
                    result = await self.k8s_service.rollout_status(kind, name, ns)
                elif action == "undo":
                    result = await self.k8s_service.rollout_undo(kind, name, ns, op.get("revision"))
                elif action == "pause":
                    result = await self.k8s_service.rollout_pause(kind, name, ns)
                elif action == "resume":
                    result = await self.k8s_service.rollout_resume(kind, name, ns)
                else:
                    raise ValueError(f"不支持的操作: {action}，支持 status/undo/pause/resume")
                results["success"].append({"kind": kind, "name": name, "action": action, "result": result})
            except Exception as e:
                results["failed"].append({"kind": kind, "name": name, "action": action, "error": str(e)})
        return results

    async def batch_top_resources(self, resource_types: List[str], namespace: str = "default") -> Dict:
        """批量获取 Node/Pod 的 CPU、内存使用（依赖 metrics-server）"""
        results = {"nodes": [], "pods": [], "error": None}
        try:
            if "nodes" in resource_types or "node" in resource_types:
                results["nodes"] = await self.k8s_service.get_node_metrics()
            if "pods" in resource_types or "pod" in resource_types:
                results["pods"] = await self.k8s_service.get_pod_metrics(namespace)
        except Exception as e:
            results["error"] = str(e)
        return results
    
    async def batch_delete_resources(self, resources: List[Dict], namespace: str = "default", 
                                   grace_period_seconds: Optional[int] = None) -> Dict:
        """批量删除资源 - 自动集成验证和预览功能"""
        print(f"\n🗑️  开始批量删除 {len(resources)} 个资源...")
        
        results = {"success": [], "failed": [], "total": len(resources)}
        
        for resource in resources:
            resource_type = resource.get("kind", "").lower()
            resource_name = resource.get("metadata", {}).get("name", "unknown")
                
            try:
                try:
                    operation_func = self._get_resource_operation(resource_type, "delete", namespace)
                    result = await operation_func(resource_name, grace_period_seconds)
                except ValueError:
                    kind = resource.get("kind", "Unknown")
                    api_version = resource.get("apiVersion") or self._api_version_map.get(kind, "v1")
                    result = self._dynamic_service.delete_resource(
                        api_version, kind, resource_name, namespace, grace_period_seconds
                    )
                results["success"].append({
                    "name": resource_name,
                    "kind": resource_type,
                    "result": result
                })
            except Exception as e:
                results["failed"].append({
                    "name": resource_name,
                    "kind": resource_type,
                    "error": str(e)
                })
        
        print(f"✅ 批量删除完成: {len(results['success'])} 成功, {len(results['failed'])} 失败\n")
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
    
    async def backup_namespace(self, namespace: str, cluster_name: str = None, include_secrets: bool = True) -> str:
        """备份整个命名空间的资源"""
        if not cluster_name:
            # 获取当前集群名称
            cluster_info = await self.k8s_service.get_cluster_info()
            cluster_name = cluster_info.get("cluster_name", "default")
        
        backup_data = {
            "metadata": {
                "cluster_name": cluster_name,
                "namespace": namespace,
                "version": "v1"
            },
            "namespace": None,  # 将在后面设置
            "resources": {}
        }
        
        # 备份namespace本身
        try:
            namespaces = await self.k8s_service.list_namespaces()
            namespace_obj = None
            for ns in namespaces:
                if ns.get("name") == namespace:
                    namespace_obj = ns
                    break
            
            if namespace_obj:
                # 构建完整的namespace资源定义
                namespace_resource = {
                    "apiVersion": "v1",
                    "kind": "Namespace",
                    "metadata": {
                        "name": namespace_obj.get("name"),
                        "labels": namespace_obj.get("labels", {}),
                        "annotations": namespace_obj.get("annotations", {})
                    }
                }
                backup_data["namespace"] = self._sanitize_for_backup(namespace_resource)
            else:
                print(f"警告: 无法找到命名空间 {namespace}")
        except Exception as e:
            print(f"备份命名空间 {namespace} 失败: {e}")
        
        # 备份命名空间级资源（排除 Pods/ClusterRole/ClusterRoleBinding/StorageClass/PV 等）
        resource_types = [
            "deployments", "statefulsets", "daemonsets",
            "services", "configmaps", "jobs", "cronjobs", "ingresses", 
            "persistentvolumeclaims", "serviceaccounts", "roles", "rolebindings"
        ]
        if include_secrets:
            resource_types.append("secrets")

        # 使用统一的备份方法处理所有资源类型
        for resource_type in resource_types:
            try:
                resources = await self._backup_resource_type(resource_type, namespace)
                backup_data["resources"][resource_type] = resources
            except Exception as e:
                print(f"备份 {resource_type} 失败: {e}")
                backup_data["resources"][resource_type] = {"error": str(e)}

        # 保存备份文件（YAML）
        backup_path = self._get_backup_path(cluster_name, namespace)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_path, f"namespace_backup_{timestamp}.yaml")

        # 自定义YAML Dumper，处理多行字符串和禁用别名
        class CustomYamlDumper(yaml.SafeDumper):
            def ignore_aliases(self, data):
                return True
            
            def represent_str(self, data):
                # 如果字符串包含换行符，使用literal style (|)
                if '\n' in data:
                    return self.represent_scalar('tag:yaml.org,2002:str', data, style='|')
                return self.represent_scalar('tag:yaml.org,2002:str', data)
        
        # 注册字符串表示方法
        CustomYamlDumper.add_representer(str, CustomYamlDumper.represent_str)

        with open(backup_file, 'w', encoding='utf-8') as f:
            yaml.dump(backup_data, f, sort_keys=False, allow_unicode=True, Dumper=CustomYamlDumper, default_flow_style=False)

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
            elif resource_type == "statefulset":
                resource_data = await self.k8s_service.get_statefulset(resource_name, namespace)
            elif resource_type == "daemonset":
                resource_data = await self.k8s_service.get_daemonset(resource_name, namespace)
            elif resource_type == "service":
                resource_data = await self.k8s_service.get_service(resource_name, namespace)
            elif resource_type == "configmap":
                resource_data = await self.k8s_service.get_configmap(resource_name, namespace)
            elif resource_type == "secret":
                resource_data = await self.k8s_service.get_secret(resource_name, namespace)
            elif resource_type == "job":
                resource_data = await self.k8s_service.get_job(resource_name, namespace)
            elif resource_type == "cronjob":
                resource_data = await self.k8s_service.get_cronjob(resource_name, namespace)
            elif resource_type == "ingress":
                resource_data = await self.k8s_service.get_ingress(resource_name, namespace)
            elif resource_type == "persistentvolumeclaim":
                resource_data = await self.k8s_service.get_persistentvolumeclaim(resource_name, namespace)
            elif resource_type == "serviceaccount":
                resource_data = await self.k8s_service.get_serviceaccount(resource_name, namespace)
            elif resource_type == "role":
                resource_data = await self.k8s_service.get_role(resource_name, namespace)
            elif resource_type == "rolebinding":
                resource_data = await self.k8s_service.get_role_binding(resource_name, namespace)
            else:
                raise ValueError(f"不支持的资源类型: {resource_type}")
            
            backup_data = {
                "metadata": {
                    "cluster_name": cluster_name,
                    "namespace": namespace,
                    "resource_type": resource_type,
                    "resource_name": resource_name,
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
            backup_data = yaml.safe_load(f)
        
        metadata = backup_data["metadata"]
        original_namespace = metadata["namespace"]
        original_cluster = metadata["cluster_name"]
        
        # 不允许恢复到不同的命名空间，必须恢复到原命名空间
        if target_namespace and target_namespace != original_namespace:
            raise ValueError(f"不允许恢复到不同的命名空间。原命名空间: {original_namespace}, 目标命名空间: {target_namespace}")
        
        target_namespace = original_namespace  # 强制使用原命名空间
        target_cluster = target_cluster or original_cluster
        
        results = {"success": [], "failed": [], "total": 0}
        
        # 恢复namespace本身（如果备份中包含）
        if "namespace" in backup_data:
            try:
                namespace_resource = backup_data["namespace"]
                await self.k8s_service.create_namespace(resource=namespace_resource)
                results["success"].append(f"namespace/{original_namespace}")
                results["total"] += 1
                print(f"成功恢复命名空间: {original_namespace}")
            except Exception as e:
                # 命名空间可能已存在，这是正常的
                if "already exists" in str(e).lower() or "conflict" in str(e).lower():
                    print(f"命名空间 {original_namespace} 已存在，跳过创建")
                else:
                    results["failed"].append({
                        "resource": f"namespace/{original_namespace}",
                        "error": str(e)
                    })
                    print(f"恢复命名空间失败: {e}")
        else:
            # 如果备份中没有namespace定义，尝试创建（向后兼容）
            try:
                await self.k8s_service.create_namespace(name=target_namespace)
            except Exception:
                # 命名空间已存在则忽略
                pass
        
        # 如果是命名空间备份
        if "resources" in backup_data:
            for resource_type, resources in backup_data["resources"].items():
                if isinstance(resources, dict) and "error" in resources:
                    results["failed"].append({
                        "resource_type": resource_type,
                        "error": resources["error"]
                    })
                    continue
                
                # 过滤掉无效的资源
                valid_resources = []
                for resource in resources:
                    if not resource or resource == {}:
                        continue
                    # 跳过系统自动创建的资源
                    resource_name = resource.get("metadata", {}).get("name", "")
                    if not resource_name or resource_name in ["kube-root-ca.crt"] or resource_name.startswith("default-token-"):
                        continue
                    valid_resources.append(resource)
                
                for resource in valid_resources:
                    try:
                        # 确保命名空间正确（应该已经是原命名空间）
                        if "metadata" in resource:
                            # 验证命名空间是否匹配，不允许修改
                            current_ns = resource["metadata"].get("namespace")
                            if current_ns and current_ns != target_namespace:
                                print(f"警告: 资源 {resource.get('metadata', {}).get('name')} 的命名空间 {current_ns} 与目标命名空间 {target_namespace} 不匹配")
                            resource["metadata"]["namespace"] = target_namespace
                        
                        # 根据资源类型调用相应的创建方法，使用完整资源定义
                        if resource_type == "deployments":
                            await self.k8s_service.create_deployment(resource=self._convert_to_k8s_resource(resource, "Deployment"), namespace=target_namespace)
                        elif resource_type == "statefulsets":
                            await self.k8s_service.create_statefulset(resource=self._convert_to_k8s_resource(resource, "StatefulSet"), namespace=target_namespace)
                        elif resource_type == "daemonsets":
                            await self.k8s_service.create_daemonset(resource=self._convert_to_k8s_resource(resource, "DaemonSet"), namespace=target_namespace)
                        elif resource_type == "services":
                            await self.k8s_service.create_service(resource=self._convert_to_k8s_resource(resource, "Service"), namespace=target_namespace)
                        elif resource_type == "configmaps":
                            await self.k8s_service.create_configmap(resource=self._convert_to_k8s_resource(resource, "ConfigMap"), namespace=target_namespace)
                        elif resource_type == "secrets":
                            await self.k8s_service.create_secret(resource=self._convert_to_k8s_resource(resource, "Secret"), namespace=target_namespace)
                        elif resource_type == "jobs":
                            await self.k8s_service.create_job(resource=self._convert_to_k8s_resource(resource, "Job"), namespace=target_namespace)
                        elif resource_type == "cronjobs":
                            await self.k8s_service.create_cronjob(resource=self._convert_to_k8s_resource(resource, "CronJob"), namespace=target_namespace)
                        elif resource_type == "ingresses":
                            await self.k8s_service.create_ingress(resource=self._convert_to_k8s_resource(resource, "Ingress"), namespace=target_namespace)
                        elif resource_type == "persistentvolumeclaims":
                            await self.k8s_service.create_persistentvolumeclaim(resource=self._convert_to_k8s_resource(resource, "PersistentVolumeClaim"), namespace=target_namespace)    
                        elif resource_type == "serviceaccounts":
                            await self.k8s_service.create_serviceaccount(resource=self._convert_to_k8s_resource(resource, "ServiceAccount"), namespace=target_namespace)
                        elif resource_type == "roles":
                            await self.k8s_service.create_role(resource=self._convert_to_k8s_resource(resource, "Role"), namespace=target_namespace)
                        elif resource_type == "rolebindings":
                            await self.k8s_service.create_role_binding(resource=self._convert_to_k8s_resource(resource, "RoleBinding"), namespace=target_namespace)
                        
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
                
                # 根据资源类型调用相应的创建方法，使用完整资源定义
                if resource_type == "deployment":
                    await self.k8s_service.create_deployment(resource=self._convert_to_k8s_resource(resource, "Deployment"), namespace=target_namespace)
                elif resource_type == "statefulset":
                    await self.k8s_service.create_statefulset(resource=self._convert_to_k8s_resource(resource, "StatefulSet"), namespace=target_namespace)
                elif resource_type == "daemonset":
                    await self.k8s_service.create_daemonset(resource=self._convert_to_k8s_resource(resource, "DaemonSet"), namespace=target_namespace)
                elif resource_type == "service":
                    await self.k8s_service.create_service(resource=self._convert_to_k8s_resource(resource, "Service"), namespace=target_namespace)
                elif resource_type == "configmap":
                    await self.k8s_service.create_configmap(resource=self._convert_to_k8s_resource(resource, "ConfigMap"), namespace=target_namespace)
                elif resource_type == "secret":
                    await self.k8s_service.create_secret(resource=self._convert_to_k8s_resource(resource, "Secret"), namespace=target_namespace)
                elif resource_type == "job":
                    await self.k8s_service.create_job(resource=self._convert_to_k8s_resource(resource, "Job"), namespace=target_namespace)
                elif resource_type == "cronjob":
                    await self.k8s_service.create_cronjob(resource=self._convert_to_k8s_resource(resource, "CronJob"), namespace=target_namespace)
                elif resource_type == "ingress":
                    await self.k8s_service.create_ingress(resource=self._convert_to_k8s_resource(resource, "Ingress"), namespace=target_namespace)
                elif resource_type == "persistentvolumeclaim":
                    await self.k8s_service.create_persistentvolumeclaim(resource=self._convert_to_k8s_resource(resource, "PersistentVolumeClaim"), namespace=target_namespace)
                elif resource_type == "serviceaccount":
                    await self.k8s_service.create_serviceaccount(resource=self._convert_to_k8s_resource(resource, "ServiceAccount"), namespace=target_namespace)
                elif resource_type == "role":
                    await self.k8s_service.create_role(resource=self._convert_to_k8s_resource(resource, "Role"), namespace=target_namespace)
                elif resource_type == "rolebinding":
                    await self.k8s_service.create_role_binding(resource=self._convert_to_k8s_resource(resource, "RoleBinding"), namespace=target_namespace)
                
                results["success"].append(f"{resource_type}/{resource['metadata']['name']}")
                results["total"] += 1
                
            except Exception as e:
                results["failed"].append({
                    "resource": f"{resource_type}/{resource.get('metadata', {}).get('name', 'unknown')}",
                    "error": str(e)
                })
        
        return results
    
    def _convert_to_k8s_resource(self, resource_data: Dict, kind: str) -> Dict:
        """将备份的资源数据转换为标准的 Kubernetes 资源定义"""
        # 使用统一的转换系统
        k8s_resource = self._create_base_k8s_resource(resource_data, kind, from_backup=True)
        k8s_resource = self._populate_resource_content(k8s_resource, resource_data, kind, from_backup=True)

        # 清理不需要的字段
        if "metadata" in k8s_resource:
            metadata = k8s_resource["metadata"]
            # 移除 Kubernetes 自动生成的字段
            for field in ["uid", "resourceVersion", "generation", "creationTimestamp", "created", "managedFields"]:
                metadata.pop(field, None)
        
        return k8s_resource
    
    def _sanitize_for_backup(self, resource_obj: Dict) -> Dict:
        """按照 K8s YAML 标准严格过滤字段，仅保留声明式配置"""
        if not isinstance(resource_obj, dict):
            return resource_obj
        
        resource = json.loads(json.dumps(resource_obj))  # 深拷贝
        
        # 1. 顶级字段白名单：仅保留声明式配置相关字段
        allowed_top_fields = {"apiVersion", "kind", "metadata", "spec", "data", "binaryData", "type", "rules", "roleRef", "subjects"}
        keys_to_remove = [k for k in list(resource.keys()) if k not in allowed_top_fields]
        for k in keys_to_remove:
            resource.pop(k, None)
        
        # 2. metadata 字段白名单：仅保留用户定义的元数据
        metadata = resource.get("metadata", {})
        if metadata:
            allowed_meta_fields = {"name", "namespace", "labels", "annotations"}
            meta_keys_to_remove = [k for k in list(metadata.keys()) if k not in allowed_meta_fields]
            for k in meta_keys_to_remove:
                metadata.pop(k, None)
            resource["metadata"] = metadata
        
        # 3. 移除所有 status 相关字段（运行时状态）
        resource.pop("status", None)
        
        # 清理volumes中的自定义type字段
        if resource.get("spec", {}).get("template", {}).get("spec", {}).get("volumes"):
            volumes = resource["spec"]["template"]["spec"]["volumes"]
            for volume in volumes:
                volume.pop("type", None)
        
        # 清理Job和CronJob的template metadata中的运行时字段
        if resource.get("kind") in ["Job", "CronJob"]:
            template_metadata = None
            if resource.get("kind") == "Job":
                template_metadata = resource.get("spec", {}).get("template", {}).get("metadata", {})
            elif resource.get("kind") == "CronJob":
                template_metadata = resource.get("spec", {}).get("jobTemplate", {}).get("spec", {}).get("template", {}).get("metadata", {})
            
            if template_metadata:
                # 移除运行时生成的标签
                runtime_labels = [
                    "batch.kubernetes.io/controller-uid",
                    "batch.kubernetes.io/job-name", 
                    "controller-uid",
                    "job-name"
                ]
                for label in runtime_labels:
                    template_metadata.get("labels", {}).pop(label, None)
        
        # 4. 如果是 spec，进行统一规范化
        spec = resource.get("spec")
        if spec is not None and isinstance(spec, dict):
            resource["spec"] = self._normalize_spec(resource.get("kind"), spec, for_backup=True)
            # 如果spec为空，移除它（特别是ServiceAccount）
            if not resource["spec"]:
                resource.pop("spec", None)
        
        # 5. 确保必要字段存在且不为空
        if not resource.get("metadata"):
            print(f"警告: 资源缺少 metadata: {resource}")
        
        # 检查需要 spec 字段的资源类型
        spec_required_kinds = ["Deployment", "StatefulSet", "DaemonSet", "Service", "Job", "CronJob", "Ingress", "PersistentVolumeClaim"]
        if resource.get("kind") in spec_required_kinds and not resource.get("spec"):
            print(f"警告: {resource.get('kind')} 缺少 spec: {resource}")
        
        # 检查 RBAC 资源的特殊字段
        if resource.get("kind") == "Role" and not resource.get("rules"):
            print(f"警告: Role 缺少 rules: {resource}")
        if resource.get("kind") == "RoleBinding" and (not resource.get("subjects") or not resource.get("roleRef")):
            print(f"警告: RoleBinding 缺少 subjects 或 roleRef: {resource}")
        
        return resource
    
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
                if file.endswith('.json') or file.endswith('.yaml'):
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
                        "timestamp": file.split('_')[-1].replace('.json', '').replace('.yaml', '') if '_' in file else "unknown"
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
    
    def _get_role_template_rules(self, role_type: str) -> List[Dict]:
        """获取角色模板的规则定义"""
        templates = {
            "developer": [
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
            ],
            "admin": [
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
            ],
            "operator": [
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
            ],
            "readonly": [
                {
                    "api_groups": [""],
                    "resources": ["pods", "services", "configmaps", "persistentvolumeclaims", "events"],
                    "verbs": ["get", "list", "watch"]
                },
                {
                    "api_groups": ["apps"],
                    "resources": ["deployments", "statefulsets", "daemonsets", "replicasets"],
                    "verbs": ["get", "list", "watch"]
                },
                {
                    "api_groups": ["networking.k8s.io"],
                    "resources": ["ingresses", "networkpolicies"],
                    "verbs": ["get", "list", "watch"]
                },
                {
                    "api_groups": ["batch"],
                    "resources": ["jobs", "cronjobs"],
                    "verbs": ["get", "list", "watch"]
                }
            ],
            "deployer": [
                {
                    "api_groups": [""],
                    "resources": ["pods", "services", "configmaps", "secrets", "persistentvolumeclaims"],
                    "verbs": ["get", "list", "watch", "create", "update", "patch", "delete"]
                },
                {
                    "api_groups": ["apps"],
                    "resources": ["deployments", "statefulsets", "daemonsets"],
                    "verbs": ["get", "list", "watch", "create", "update", "patch", "delete"]
                },
                {
                    "api_groups": ["networking.k8s.io"],
                    "resources": ["ingresses"],
                    "verbs": ["get", "list", "watch", "create", "update", "patch", "delete"]
                },
                {
                    "api_groups": ["batch"],
                    "resources": ["jobs", "cronjobs"],
                    "verbs": ["get", "list", "watch", "create", "update", "patch", "delete"]
                },
                {
                    "api_groups": [""],
                    "resources": ["events"],
                    "verbs": ["get", "list", "watch"]
                }
            ],
            "monitor": [
                {
                    "api_groups": [""],
                    "resources": ["*"],
                    "verbs": ["get", "list", "watch"]
                },
                {
                    "api_groups": ["apps"],
                    "resources": ["*"],
                    "verbs": ["get", "list", "watch"]
                },
                {
                    "api_groups": ["networking.k8s.io"],
                    "resources": ["*"],
                    "verbs": ["get", "list", "watch"]
                },
                {
                    "api_groups": ["batch"],
                    "resources": ["*"],
                    "verbs": ["get", "list", "watch"]
                },
                {
                    "api_groups": ["metrics.k8s.io"],
                    "resources": ["*"],
                    "verbs": ["get", "list"]
                }
            ],
            "debug": [
                {
                    "api_groups": [""],
                    "resources": ["pods"],
                    "verbs": ["get", "list", "watch"]
                },
                {
                    "api_groups": [""],
                    "resources": ["pods/log"],
                    "verbs": ["get", "list"]
                },
                {
                    "api_groups": [""],
                    "resources": ["pods/exec"],
                    "verbs": ["create"]
                },
                {
                    "api_groups": [""],
                    "resources": ["pods/portforward"],
                    "verbs": ["create"]
                },
                {
                    "api_groups": [""],
                    "resources": ["events"],
                    "verbs": ["get", "list", "watch"]
                }
            ]
        }
        
        return templates.get(role_type, [])
    
    async def create_role_template(self, role_type: str, namespace: str, role_name: str = None) -> Dict:
        """创建角色模板
        
        Args:
            role_type: 角色类型 (developer/admin/operator/readonly/deployer/monitor/debug)
            namespace: 命名空间
            role_name: 角色名称，默认使用role_type
        """
        if not role_name:
            role_name = role_type
        
        rules = self._get_role_template_rules(role_type)
        if not rules:
            return {"success": False, "error": f"不支持的角色类型: {role_type}"}
        
        try:
            # 先检查角色是否已存在
            try:
                existing_role = await self.k8s_service.get_role(role_name, namespace)
                if existing_role:
                    return {
                        "success": False,
                        "error": f"角色 '{role_name}' 在命名空间 '{namespace}' 中已存在",
                        "suggestion": f"请使用不同的角色名称或删除现有角色后重试"
                    }
            except Exception:
                # 角色不存在，可以创建
                pass
            
            return await self.k8s_service.create_role(role_name, namespace, rules)
            
        except Exception as e:
            error_msg = str(e)
            if "already exists" in error_msg or "AlreadyExists" in error_msg:
                return {
                    "success": False,
                    "error": f"角色 '{role_name}' 在命名空间 '{namespace}' 中已存在",
                    "suggestion": f"请使用不同的角色名称或删除现有角色后重试"
                }
            else:
                return {"success": False, "error": str(e)}


    def _analyze_role_permissions(self, rules: List[Dict]) -> Dict:
        """分析角色权限特征
        
        Returns:
            Dict containing permission analysis including:
            - is_admin: 是否为管理员权限
            - is_readonly: 是否为只读权限
            - permission_level: 权限级别 (admin/write/read)
        """
        if not rules:
            return {"is_admin": False, "is_readonly": False, "permission_level": "none"}
        
        has_wildcard_resources = False
        has_wildcard_verbs = False
        has_write_verbs = False
        has_rbac_permissions = False
        
        write_verbs = {"create", "update", "patch", "delete", "deletecollection"}
        readonly_verbs = {"get", "list", "watch"}
        
        for rule in rules:
            resources = rule.get("resources", [])
            verbs = set(rule.get("verbs", []))
            api_groups = rule.get("api_groups", rule.get("apiGroups", []))
            
            # 检查通配符
            if "*" in resources:
                has_wildcard_resources = True
            if "*" in verbs:
                has_wildcard_verbs = True
            
            # 检查写权限
            if verbs & write_verbs or "*" in verbs:
                has_write_verbs = True
            
            # 检查RBAC权限
            if "rbac.authorization.k8s.io" in api_groups and (verbs & write_verbs or "*" in verbs):
                has_rbac_permissions = True
        
        # 判断权限级别
        is_admin = (has_wildcard_resources and has_wildcard_verbs) or has_rbac_permissions
        is_readonly = not has_write_verbs and not has_wildcard_verbs
        
        if is_admin:
            permission_level = "admin"
        elif has_write_verbs:
            permission_level = "write"
        elif is_readonly:
            permission_level = "read"
        else:
            permission_level = "none"
        
        return {
            "is_admin": is_admin,
            "is_readonly": is_readonly,
            "permission_level": permission_level,
            "has_wildcard_resources": has_wildcard_resources,
            "has_wildcard_verbs": has_wildcard_verbs,
            "has_write_verbs": has_write_verbs,
            "has_rbac_permissions": has_rbac_permissions
        }


    async def analyze_serviceaccount_permissions(self, service_account_name: str, namespace: str) -> Dict:
        """分析ServiceAccount的权限"""
        try:
            permissions = {"roles": [], "cluster_roles": []}
            
            # 查找ServiceAccount的RoleBinding
            role_bindings = await self.k8s_service.list_role_bindings(namespace)
            for rb in role_bindings:
                if rb.get("subjects"):
                    for subject in rb["subjects"]:
                        if (subject.get("kind") == "ServiceAccount" and 
                            subject.get("name") == service_account_name and
                            subject.get("namespace", namespace) == namespace):
                            role_ref = rb.get("role_ref", {})
                            permissions["roles"].append({
                                "binding_name": rb["name"],
                                "role_name": role_ref.get("name"),
                                "role_kind": role_ref.get("kind"),
                                "namespace": namespace
                            })
            
            # 查找ServiceAccount的ClusterRoleBinding
            cluster_role_bindings = await self.k8s_service.list_cluster_role_bindings()
            for crb in cluster_role_bindings:
                if crb.get("subjects"):
                    for subject in crb["subjects"]:
                        if (subject.get("kind") == "ServiceAccount" and 
                            subject.get("name") == service_account_name and
                            subject.get("namespace", namespace) == namespace):
                            role_ref = crb.get("role_ref", {})
                            permissions["cluster_roles"].append({
                                "binding_name": crb["name"],
                                "role_name": role_ref.get("name"),
                                "role_kind": role_ref.get("kind")
                            })
            
            # 获取具体权限详情
            for role_info in permissions["roles"]:
                try:
                    if role_info["role_kind"] == "Role":
                        role_detail = await self.k8s_service.get_role(
                            role_info["role_name"], role_info["namespace"]
                        )
                        role_info["rules"] = role_detail.get("rules", [])
                    elif role_info["role_kind"] == "ClusterRole":
                        role_detail = await self.k8s_service.get_cluster_role(role_info["role_name"])
                        role_info["rules"] = role_detail.get("rules", [])
                except:
                    role_info["rules"] = []
            
            for role_info in permissions["cluster_roles"]:
                try:
                    role_detail = await self.k8s_service.get_cluster_role(role_info["role_name"])
                    role_info["rules"] = role_detail.get("rules", [])
                except:
                    role_info["rules"] = []
            
            return {
                "service_account": service_account_name,
                "namespace": namespace,
                "permissions": permissions,
                "summary": {
                    "total_roles": len(permissions["roles"]),
                    "total_cluster_roles": len(permissions["cluster_roles"])
                }
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    async def check_serviceaccount_permission_conflicts(self, namespace: str) -> Dict:
        """检查命名空间中ServiceAccount的权限冲突"""
        try:
            conflicts = []
            
            # 获取所有RoleBinding
            role_bindings = await self.k8s_service.list_role_bindings(namespace)
            
            # 按ServiceAccount分组检查权限
            sa_permissions = {}
            for rb in role_bindings:
                if rb.get("subjects"):
                    for subject in rb["subjects"]:
                        if subject.get("kind") == "ServiceAccount":
                            sa_name = subject.get("name")
                            sa_namespace = subject.get("namespace", namespace)
                            sa_key = f"{sa_namespace}/{sa_name}"
                            
                            if sa_key not in sa_permissions:
                                sa_permissions[sa_key] = []
                            
                            role_ref = rb.get("role_ref", {})
                            sa_permissions[sa_key].append({
                                "binding": rb["name"],
                                "role_name": role_ref.get("name"),
                                "role_kind": role_ref.get("kind")
                            })
            
            # 检查每个ServiceAccount的权限冲突
            for sa_key, permissions in sa_permissions.items():
                if len(permissions) > 1:
                    # 检查重复的角色绑定
                    role_names = [p["role_name"] for p in permissions]
                    duplicates = set([x for x in role_names if role_names.count(x) > 1])
                    if duplicates:
                        conflicts.append({
                            "type": "duplicate_bindings",
                            "service_account": sa_key,
                            "message": f"ServiceAccount {sa_key} 被重复绑定到角色: {', '.join(duplicates)}",
                            "permissions": permissions
                        })
                    
                    # 基于实际权限规则检查冲突
                    try:
                        role_analyses = []
                        for perm in permissions:
                            role_name = perm["role_name"]
                            role_kind = perm["role_kind"]
                            
                            try:
                                if role_kind == "Role":
                                    role_detail = await self.k8s_service.get_role(role_name, namespace)
                                elif role_kind == "ClusterRole":
                                    role_detail = await self.k8s_service.get_cluster_role(role_name)
                                else:
                                    continue
                                    
                                rules = role_detail.get("rules", [])
                                analysis = self._analyze_role_permissions(rules)
                                analysis["role_name"] = role_name
                                analysis["role_kind"] = role_kind
                                role_analyses.append(analysis)
                            except:
                                continue
                        
                        # 检查是否同时拥有管理员权限和只读权限
                        admin_roles = [ra for ra in role_analyses if ra["is_admin"]]
                        readonly_roles = [ra for ra in role_analyses if ra["is_readonly"]]
                        
                        if admin_roles and readonly_roles:
                            admin_role_names = [ra["role_name"] for ra in admin_roles]
                            readonly_role_names = [ra["role_name"] for ra in readonly_roles]
                            conflicts.append({
                                "type": "redundant_permissions",
                                "service_account": sa_key,
                                "message": f"ServiceAccount {sa_key} 同时拥有管理员权限({', '.join(admin_role_names)})和只读权限({', '.join(readonly_role_names)})，只读权限是冗余的",
                                "permissions": permissions,
                                "admin_roles": admin_role_names,
                                "readonly_roles": readonly_role_names
                            })
                        
                        # 检查是否有多个管理员角色（可能是冗余的）
                        if len(admin_roles) > 1:
                            admin_role_names = [ra["role_name"] for ra in admin_roles]
                            conflicts.append({
                                "type": "excessive_admin_permissions",
                                "service_account": sa_key,
                                "message": f"ServiceAccount {sa_key} 拥有多个管理员权限角色({', '.join(admin_role_names)})，可能存在冗余",
                                "permissions": permissions,
                                "admin_roles": admin_role_names
                            })
                            
                    except Exception as e:
                        # 如果权限分析失败，记录但不中断整个检查过程
                        pass
            
            return {
                "namespace": namespace,
                "conflicts": conflicts,
                "summary": {
                    "total_conflicts": len(conflicts),
                    "service_accounts_checked": len(sa_permissions)
                }
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    async def list_role_serviceaccounts(self, role_name: str, namespace: str, role_type: str = "Role") -> Dict:
        """列出绑定到指定角色的所有ServiceAccount"""
        try:
            service_accounts = []
            
            if role_type == "Role":
                # 查找RoleBinding
                role_bindings = await self.k8s_service.list_role_bindings(namespace)
                for rb in role_bindings:
                    role_ref = rb.get("role_ref", {})
                    if (role_ref.get("kind") == role_type and 
                        role_ref.get("name") == role_name):
                        
                        if rb.get("subjects"):
                            for subject in rb["subjects"]:
                                if subject.get("kind") == "ServiceAccount":
                                    subject_info = {
                                        "name": subject.get("name"),
                                        "namespace": subject.get("namespace", namespace),
                                        "binding": rb["name"]
                                    }
                                    service_accounts.append(subject_info)
            
            elif role_type == "ClusterRole":
                # 查找ClusterRoleBinding
                cluster_role_bindings = await self.k8s_service.list_cluster_role_bindings()
                for crb in cluster_role_bindings:
                    role_ref = crb.get("role_ref", {})
                    if (role_ref.get("kind") == role_type and 
                        role_ref.get("name") == role_name):
                        
                        if crb.get("subjects"):
                            for subject in crb["subjects"]:
                                if subject.get("kind") == "ServiceAccount":
                                    subject_info = {
                                        "name": subject.get("name"),
                                        "namespace": subject.get("namespace", ""),
                                        "binding": crb["name"]
                                    }
                                    service_accounts.append(subject_info)
            
            return {
                "role_name": role_name,
                "role_type": role_type,
                "namespace": namespace,
                "service_accounts": service_accounts,
                "summary": {
                    "total_service_accounts": len(service_accounts)
                }
            }
            
        except Exception as e:
            return {"error": str(e)}


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
            elif resource_type == "pod":
                return await self.k8s_service.get_pod(resource_name, namespace)
            elif resource_type == "node":
                return await self.k8s_service.get_node(resource_name)
            elif resource_type == "horizontalpodautoscaler":
                return await self.k8s_service.get_hpa(resource_name, namespace)
            elif resource_type == "networkpolicy":
                return await self.k8s_service.get_network_policy(resource_name, namespace)
            elif resource_type == "resourcequota":
                return await self.k8s_service.get_resource_quota(resource_name, namespace)
            else:
                raise ValueError(f"不支持的资源类型: {resource_type}")
        except Exception as e:
            return {"error": str(e)}

    async def get_resource_after_operation(self, resource_type: str, resource_name: str, 
                                          namespace: str = "default") -> Dict:
        """获取操作后的资源状态"""
        return await self.get_resource_before_operation(resource_type, resource_name, namespace)
    
    # ==================== 通用资源比较方法 ====================
    
    def _compare_resource_fields(self, before: Dict, after: Dict, field_configs: Dict) -> Dict:
        """通用的资源字段比较方法
        
        Args:
            before: 操作前的资源状态
            after: 操作后的资源状态
            field_configs: 字段配置，格式为 {field_name: field_path_or_function}
        """
        changes = {}
        
        if before.get("error") or after.get("error"):
            return {"error": "无法获取资源状态"}
        
        for field_name, config in field_configs.items():
            if callable(config):
                # 如果是函数，调用函数获取值
                before_value = config(before)
                after_value = config(after)
            elif isinstance(config, str):
                # 如果是字符串路径，按路径获取值
                before_value = self._get_nested_value(before, config)
                after_value = self._get_nested_value(after, config)
            else:
                # 如果是元组，第一个元素是before路径，第二个是after路径
                before_path, after_path = config
                before_value = self._get_nested_value(before, before_path)
                after_value = self._get_nested_value(after, after_path)
            
            if before_value != after_value:
                changes[field_name] = {
                    "before": before_value,
                    "after": after_value
                }
                # 如果值是简单类型，添加change描述
                if isinstance(before_value, (str, int, bool)) and isinstance(after_value, (str, int, bool)):
                    changes[field_name]["change"] = f"{before_value} -> {after_value}"
        
        return changes
    
    def _get_nested_value(self, data: Dict, path: str, default=None):
        """从嵌套字典中获取值"""
        keys = path.split(".")
        current = data
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        
        return current

    # ==================== 统一的资源比较和验证系统 ====================
    
    def _get_resource_field_configs(self, resource_type: str) -> Dict:
        """获取资源类型的字段配置"""
        configs = {
            "deployment": {
                "replicas": "spec.replicas",
                "labels": "metadata.labels",
                "annotations": "metadata.annotations",
                "image": lambda r: self._get_first_container_field(r, "image"),
                "resources": lambda r: self._get_first_container_field(r, "resources"),
                "env_vars": lambda r: self._get_first_container_field(r, "env")
            },
            "statefulset": {
                "replicas": "spec.replicas",
                "labels": "metadata.labels",
                "annotations": "metadata.annotations",
                "image": lambda r: self._get_first_container_field(r, "image"),
                "resources": lambda r: self._get_first_container_field(r, "resources"),
                "env_vars": lambda r: self._get_first_container_field(r, "env"),
                "volume_claims": "spec.volumeClaimTemplates"
            },
            "daemonset": {
                "labels": "metadata.labels",
                "annotations": "metadata.annotations",
                "image": lambda r: self._get_first_container_field(r, "image"),
                "resources": lambda r: self._get_first_container_field(r, "resources"),
                "env_vars": lambda r: self._get_first_container_field(r, "env")
            },
            "service": {
                "service_type": "spec.type",
                "ports": "spec.ports",
                "selector": "spec.selector",
                "labels": "metadata.labels",
                "annotations": "metadata.annotations"
            },
            "configmap": {
                "data": "data",
                "binary_data": "binaryData",
                "labels": "metadata.labels",
                "annotations": "metadata.annotations"
            },
            "secret": {
                "data": lambda r: list(r.get("data", {}).keys()),  # 只比较键名，不比较值
                "type": "type",
                "labels": "metadata.labels",
                "annotations": "metadata.annotations"
            },
            "job": {
                "parallelism": "spec.parallelism",
                "completions": "spec.completions",
                "active_deadline_seconds": "spec.activeDeadlineSeconds",
                "backoff_limit": "spec.backoffLimit",
                "labels": "metadata.labels",
                "annotations": "metadata.annotations"
            },
            "cronjob": {
                "schedule": "spec.schedule",
                "suspend": "spec.suspend",
                "labels": "metadata.labels",
                "annotations": "metadata.annotations"
            },
            "ingress": {
                "rules": "spec.rules",
                "tls": "spec.tls",
                "ingress_class": "spec.ingressClassName",
                "labels": "metadata.labels",
                "annotations": "metadata.annotations"
            },
            "persistentvolumeclaim": {
                "size": "spec.resources.requests.storage",
                "access_modes": "spec.accessModes",
                "storage_class": "spec.storageClassName",
                "labels": "metadata.labels",
                "annotations": "metadata.annotations"
            },
            "persistentvolume": {
                "capacity": "capacity.storage",
                "access_modes": "access_modes",
                "reclaim_policy": "reclaim_policy",
                "storage_class": "storage_class_name",
                "labels": "metadata.labels",
                "annotations": "metadata.annotations"
            },
            "storageclass": {
                "provisioner": "provisioner",
                "parameters": "parameters",
                "allow_volume_expansion": "allow_volume_expansion",
                "labels": "metadata.labels",
                "annotations": "metadata.annotations"
            },
            "serviceaccount": {
                "labels": "labels",
                "annotations": "annotations",
                "secrets": "secrets",
                "image_pull_secrets": "image_pull_secrets",
                "automount_service_account_token": "automount_service_account_token"
            },
            "role": {
                "rules": "rules",
                "labels": "metadata.labels",
                "annotations": "metadata.annotations"
            },
            "clusterrole": {
                "rules": "rules",
                "labels": "metadata.labels",
                "annotations": "metadata.annotations"
            },
            "rolebinding": {
                "role_ref": "role_ref",
                "subjects": "subjects",
                "labels": "metadata.labels",
                "annotations": "metadata.annotations"
            },
            "clusterrolebinding": {
                "role_ref": "role_ref",
                "subjects": "subjects",
                "labels": "metadata.labels",
                "annotations": "metadata.annotations"
            },
            "namespace": {
                "status": "status.phase",
                "labels": "metadata.labels",
                "annotations": "metadata.annotations"
            },
            "pod": {
                "phase": "phase",
                "ready": "ready",
                "restart_count": "restart_count",
                "node_name": "node_name",
                "labels": "labels",
                "annotations": "annotations",
                "containers": lambda r: [c.get("name") for c in r.get("containers", [])]
            },
            "node": {
                "status": "status",
                "roles": "roles",
                "version": "version",
                "os_image": "os_image",
                "labels": "labels",
                "annotations": "annotations"
            }
        }
        return configs.get(resource_type, {})
    
    def _get_first_container_field(self, resource: Dict, field: str):
        """获取第一个容器的字段值"""
        containers = resource.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        return containers[0].get(field) if containers else None
    
    def compare_resource_changes(self, resource_type: str, before: Dict, after: Dict) -> Dict:
        """统一的资源变化比较方法"""
        field_configs = self._get_resource_field_configs(resource_type)
        if not field_configs:
            return {"error": f"不支持的资源类型: {resource_type}"}
        
        return self._compare_resource_fields(before, after, field_configs)
    
    # ==================== 统一的验证和预览方法 ====================
    
    def _is_cluster_resource(self, resource_type: str) -> bool:
        """判断是否为集群级别资源"""
        return resource_type.lower() in ["persistentvolume", "storageclass", "clusterrole", "clusterrolebinding", "namespace", "node"]
    
    def _validate_operation_support(self, resource_type: str, operation: str) -> tuple[bool, str]:
        """验证操作是否支持"""
        unsupported_operations = {
            "persistentvolume": ["update"],  # PV通常不支持更新
            "storageclass": ["update"],      # SC的核心字段不可变
            "namespace": ["update"]          # NS只支持标签和注解更新
        }
        
        if resource_type in unsupported_operations and operation in unsupported_operations[resource_type]:
            return False, f"{resource_type} 不支持 {operation} 操作"
        
        return True, ""
    
    def _format_change_output(self, field: str, before_value, after_value) -> list:
        """格式化变化输出 - 返回详细的变化列表"""
        if before_value == after_value:
            return []
        
        changes = []
        
        # 处理简单值类型
        if isinstance(before_value, (str, int, float, bool)) and isinstance(after_value, (str, int, float, bool)):
            changes.append(f"   • {field}: {before_value} → {after_value}")
        
        # 处理列表类型 - 特别处理复杂对象列表
        elif isinstance(before_value, list) and isinstance(after_value, list):
            # 对于复杂对象列表（如RBAC rules, ports等），进行深度比较
            if before_value and isinstance(before_value[0], dict):
                changes.extend(self._format_complex_list_changes(field, before_value, after_value))
            else:
                # 简单列表处理
                before_set = set(str(item) for item in before_value) if before_value else set()
                after_set = set(str(item) for item in after_value) if after_value else set()
                
                added_items = after_set - before_set
                removed_items = before_set - after_set
                
                if added_items:
                    for item in sorted(added_items):
                        changes.append(f"   • {field}: 新增 {item}")
                if removed_items:
                    for item in sorted(removed_items):
                        changes.append(f"   • {field}: 删除 {item}")
                if not added_items and not removed_items and before_value != after_value:
                    changes.append(f"   • {field}: 顺序或内容已更新")
        
        # 处理字典类型
        elif isinstance(before_value, dict) and isinstance(after_value, dict):
            before_dict = before_value if before_value else {}
            after_dict = after_value if after_value else {}
            
            # 找出新增、删除和修改的键
            before_keys = set(before_dict.keys())
            after_keys = set(after_dict.keys())
            
            added_keys = after_keys - before_keys
            removed_keys = before_keys - after_keys
            common_keys = before_keys & after_keys
            
            # 新增的键
            for key in sorted(added_keys):
                changes.append(f"   • {field}.{key}: 新增 = {after_dict[key]}")
            
            # 删除的键
            for key in sorted(removed_keys):
                changes.append(f"   • {field}.{key}: 删除 = {before_dict[key]}")
            
            # 修改的键
            for key in sorted(common_keys):
                if before_dict[key] != after_dict[key]:
                    changes.append(f"   • {field}.{key}: {before_dict[key]} → {after_dict[key]}")
        
        # 处理 None 值
        elif before_value is None and after_value is not None:
            if isinstance(after_value, (dict, list)):
                if isinstance(after_value, list) and after_value:
                    # 显示具体的列表内容
                    if isinstance(after_value[0], dict):
                        changes.append(f"   • {field}: 新增 {len(after_value)} 项配置")
                        for i, item in enumerate(after_value):
                            changes.append(f"     [{i+1}] {self._format_dict_summary(item)}")
                    else:
                        changes.append(f"   • {field}: 新增 {after_value}")
                else:
                    changes.append(f"   • {field}: 从空设置为 {type(after_value).__name__}")
            else:
                changes.append(f"   • {field}: 未设置 → {after_value}")
        elif before_value is not None and after_value is None:
            if isinstance(before_value, (dict, list)):
                changes.append(f"   • {field}: 清空 {type(before_value).__name__}")
            else:
                changes.append(f"   • {field}: {before_value} → 未设置")
        
        # 其他情况
        else:
            changes.append(f"   • {field}: 类型变化 {type(before_value).__name__} → {type(after_value).__name__}")
        
        return changes
    
    def _format_complex_list_changes(self, field: str, before_list: list, after_list: list) -> list:
        """格式化复杂列表（如RBAC rules, ports等）的变化"""
        changes = []
        
        # 为复杂对象生成唯一标识符进行比较
        def get_item_key(item):
            if isinstance(item, dict):
                # 对于RBAC rules，使用resources+verbs作为key
                if 'resources' in item and 'verbs' in item:
                    resources = ','.join(sorted(item.get('resources', [])))
                    verbs = ','.join(sorted(item.get('verbs', [])))
                    api_groups = ','.join(sorted(item.get('apiGroups', item.get('api_groups', []))))
                    return f"{api_groups}:{resources}:{verbs}"
                # 对于ports，使用port+protocol作为key
                elif 'port' in item:
                    return f"{item.get('port')}:{item.get('protocol', 'TCP')}"
                # 对于其他情况，使用所有键值对
                else:
                    return str(sorted(item.items()))
            return str(item)
        
        before_dict = {get_item_key(item): item for item in before_list}
        after_dict = {get_item_key(item): item for item in after_list}
        
        before_keys = set(before_dict.keys())
        after_keys = set(after_dict.keys())
        
        added_keys = after_keys - before_keys
        removed_keys = before_keys - after_keys
        common_keys = before_keys & after_keys
        
        # 新增的项
        for key in added_keys:
            item = after_dict[key]
            changes.append(f"   • {field}: 新增规则 {self._format_dict_summary(item)}")
        
        # 删除的项
        for key in removed_keys:
            item = before_dict[key]
            changes.append(f"   • {field}: 删除规则 {self._format_dict_summary(item)}")
        
        # 修改的项
        for key in common_keys:
            before_item = before_dict[key]
            after_item = after_dict[key]
            if before_item != after_item:
                changes.append(f"   • {field}: 修改规则")
                changes.append(f"     原: {self._format_dict_summary(before_item)}")
                changes.append(f"     新: {self._format_dict_summary(after_item)}")
        
        return changes
    
    def _format_dict_summary(self, item: dict) -> str:
        """格式化字典为简洁的摘要"""
        if not isinstance(item, dict):
            return str(item)
        
        # RBAC规则摘要
        if 'resources' in item and 'verbs' in item:
            api_groups = item.get('apiGroups', item.get('api_groups', ['']))
            resources = item.get('resources', [])
            verbs = item.get('verbs', [])
            api_groups_str = ','.join(api_groups) if api_groups != [''] else 'core'
            return f"[{api_groups_str}] {','.join(resources)} -> {','.join(verbs)}"
        
        # 端口摘要
        elif 'port' in item:
            port = item.get('port')
            target_port = item.get('targetPort', item.get('target_port'))
            protocol = item.get('protocol', 'TCP')
            name = item.get('name', '')
            if target_port and target_port != port:
                return f"{name}:{port}->{target_port}/{protocol}" if name else f"{port}->{target_port}/{protocol}"
            else:
                return f"{name}:{port}/{protocol}" if name else f"{port}/{protocol}"
        
        # 通用摘要
        else:
            key_values = []
            for k, v in item.items():
                if isinstance(v, (list, dict)):
                    key_values.append(f"{k}={type(v).__name__}")
                else:
                    key_values.append(f"{k}={v}")
            return "{" + ", ".join(key_values[:3]) + ("..." if len(key_values) > 3 else "") + "}"
    
    async def validate_and_preview_operation(self, resource_type: str, name: str, 
                                           operation: str, namespace: str = "default", 
                                           new_resource: Dict = None) -> Dict:
        """统一的操作验证和预览方法"""
        result = {
            "valid": False,
            "message": "",
            "changes": [],
            "warnings": []
        }
        
        try:
            # 1. 验证操作支持性
            supported, reason = self._validate_operation_support(resource_type, operation)
            if not supported:
                result["message"] = f"❌ {reason}"
                return result
            
            # 2. 获取当前状态（仅对update/delete操作）
            if operation in ["update", "delete"]:
                if self._is_cluster_resource(resource_type):
                    current_state = await self.get_resource_before_operation(resource_type, name)
                else:
                    current_state = await self.get_resource_before_operation(resource_type, name, namespace)
                
                if current_state.get("error"):
                    result["message"] = f"❌ 资源不存在: {current_state['error']}"
                    return result
            
            # 3. 生成变化预览（仅对update操作）
            if operation == "update" and new_resource:
                changes = self.compare_resource_changes(resource_type, current_state, new_resource)
                
                if changes and not changes.get("error"):
                    change_list = []
                    for field, change in changes.items():
                        if change is not None and not (isinstance(change, dict) and change.get('error')):
                            if isinstance(change, dict) and 'before' in change and 'after' in change:
                                formatted_changes = self._format_change_output(field, change['before'], change['after'])
                                change_list.extend(formatted_changes)
                    
                    result["changes"] = change_list
            
            # 4. 添加操作风险警告
            if operation == "delete":
                result["warnings"] = [f"⚠️  将删除资源 {resource_type}/{name}，此操作不可逆"]
            
            result["valid"] = True
            result["message"] = "✅ 操作内容验证通过"
            
            return result
            
        except Exception as e:
            result["message"] = f"❌ 验证失败: {str(e)}"
            return result
    
    # ==================== 自动验证和预览的写操作方法 ====================
    # 注意：验证功能现在直接集成在 k8s_api_service 的方法中，不再需要这个包装方法

