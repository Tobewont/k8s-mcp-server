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
            "rolebindings": ResourceConfig("RoleBinding", "list_role_bindings", "get_role_binding")
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
        self.backup_dir = os.path.join(DATA_DIR, BACKUP_DIR_NAME)
        os.makedirs(self.backup_dir, exist_ok=True)
        self.operation_history = []
        
        # 初始化资源管理器
        self.resource_manager = ResourceManager(self.k8s_service)

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

    async def _batch_operation_generic(self, items: List, operation_type: str, namespace: str = "default", **kwargs) -> Dict:
        """通用的批量操作方法"""
        result = BatchOperationResult()
        
        for item in items:
            try:
                if operation_type in ["create", "update", "delete"]:
                    # 资源操作
                    resource_type = item.get("kind", "").lower()
                    resource_name = item.get("metadata", {}).get("name", "unknown")
                    
                    operation_func = self._get_resource_operation(resource_type, operation_type, namespace)
                    
                    if operation_type == "create":
                        op_result = await operation_func(item)
                    elif operation_type == "update":
                        op_result = await operation_func(resource_name, item)
                    elif operation_type == "delete":
                        grace_period = kwargs.get("grace_period_seconds")
                        op_result = await operation_func(resource_name, grace_period)
                    
                    result.add_success({
                        "name": resource_name,
                        "kind": resource_type,
                        "result": op_result
                    })
                    
                elif operation_type == "list":
                    # 列表操作
                    resource_type = item.lower()
                    operation_func = self._get_resource_operation(resource_type, "list", namespace)
                    op_result = await operation_func()
                    
                    result.add_success({
                        "resource_type": resource_type,
                        "count": len(op_result) if isinstance(op_result, list) else 0,
                        "items": op_result
                    })
                
            except Exception as e:
                if operation_type == "list":
                    result.add_failure({"resource_type": item}, e)
                else:
                    result.add_failure({
                        "name": item.get("metadata", {}).get("name", "unknown"),
                        "kind": item.get("kind", "unknown")
                    }, e)
        
        return result.to_dict()

    async def batch_create_resources(self, resources: List[Dict], namespace: str = "default") -> Dict:
        """批量创建k8s资源"""
        return await self._batch_operation_generic(resources, "create", namespace)
    
    async def batch_update_resources(self, resources: List[Dict], namespace: str = "default") -> Dict:
        """批量更新资源"""
        return await self._batch_operation_generic(resources, "update", namespace)
    
    async def batch_delete_resources(self, resources: List[Dict], namespace: str = "default", 
                                   grace_period_seconds: Optional[int] = None) -> Dict:
        """批量删除资源"""
        return await self._batch_operation_generic(resources, "delete", namespace, grace_period_seconds=grace_period_seconds)

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

    # ==================== Deployment 比较和验证方法 ====================
    
    def compare_deployment_changes(self, before: Dict, after: Dict) -> Dict:
        """比较Deployment的变化"""
        def get_first_container_field(resource, field):
            containers = resource.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
            return containers[0].get(field) if containers else None
        
        field_configs = {
            "replicas": "spec.replicas",
            "labels": "metadata.labels",
            "annotations": "metadata.annotations",
            "image": lambda r: get_first_container_field(r, "image"),
            "resources": lambda r: get_first_container_field(r, "resources"),
            "env_vars": lambda r: get_first_container_field(r, "env")
        }
        
        return self._compare_resource_fields(before, after, field_configs)

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

