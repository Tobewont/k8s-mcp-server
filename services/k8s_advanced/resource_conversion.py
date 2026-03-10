"""
Kubernetes 进阶服务 - 资源转换与规格归一化
"""
import json
from typing import List, Dict


class ResourceConversionMixin:
    """资源转换与规格归一化 Mixin"""

    # ==================== 规格归一化（备份/恢复通用） ====================
    def _normalize_service_ports(self, ports: List[Dict], *, for_backup: bool) -> List[Dict]:
        normalized_ports: List[Dict] = []
        for port in ports or []:
            if not isinstance(port, dict):
                continue
            port = dict(port)
            if "target_port" in port:
                port["targetPort"] = port.pop("target_port")
            if "node_port" in port:
                port["nodePort"] = port.pop("node_port")

            if "targetPort" in port and isinstance(port["targetPort"], str):
                try:
                    port["targetPort"] = int(port["targetPort"])
                except ValueError:
                    pass

            for k in ["nodePort"]:
                port.pop(k, None)

            for k in [key for key, val in list(port.items()) if val is None]:
                port.pop(k, None)

            normalized_ports.append(port)
        return normalized_ports

    def _normalize_spec(self, kind: str, spec: Dict, *, for_backup: bool) -> Dict:
        if not isinstance(spec, dict):
            return spec

        normalized = json.loads(json.dumps(spec))

        runtime_fields_common = ["finalizers"] if for_backup else []
        for f in runtime_fields_common:
            normalized.pop(f, None)

        if kind == "Service":
            runtime_fields_service = ["clusterIP", "clusterIPs", "cluster_ip", "external_ips", "load_balancer_ip", "session_affinity"]
            for f in runtime_fields_service:
                normalized.pop(f, None)
            if "ports" in normalized:
                normalized["ports"] = self._normalize_service_ports(normalized.get("ports", []), for_backup=for_backup)

        elif kind == "PersistentVolumeClaim":
            normalized.pop("volumeName", None)
            if for_backup:
                normalized.pop("phase", None)

        elif kind in ["Deployment", "StatefulSet", "DaemonSet"]:
            if "strategy" in normalized and isinstance(normalized["strategy"], str):
                strategy_type = normalized["strategy"]
                normalized["strategy"] = {
                    "type": strategy_type,
                    "rollingUpdate": {"maxUnavailable": "25%", "maxSurge": "25%"}
                }

            if "selector" in normalized:
                selector = normalized["selector"]
                if not isinstance(selector, dict) or "matchLabels" not in selector:
                    if isinstance(selector, dict):
                        normalized["selector"] = {"matchLabels": selector}

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

            if kind == "StatefulSet":
                if for_backup:
                    normalized.pop("currentReplicas", None)
                    normalized.pop("readyReplicas", None)
                    normalized.pop("currentRevision", None)
                    normalized.pop("updateRevision", None)

        elif kind == "Job":
            if for_backup:
                for f in ["activeDeadlineSeconds", "completions", "parallelism"]:
                    if f in normalized and normalized[f] is None:
                        normalized.pop(f, None)

        elif kind == "CronJob":
            if for_backup:
                normalized.pop("lastScheduleTime", None)

        elif kind == "Ingress":
            if for_backup:
                normalized.pop("loadBalancer", None)

        elif kind in ["Role", "ClusterRole"]:
            if "rules" in normalized:
                rules = normalized["rules"]
                if isinstance(rules, list):
                    for rule in rules:
                        if isinstance(rule, dict):
                            if "api_groups" in rule:
                                rule["apiGroups"] = rule.pop("api_groups")
                            if "resource_names" in rule:
                                rule["resourceNames"] = rule.pop("resource_names")

        elif kind in ["RoleBinding", "ClusterRoleBinding"]:
            if "roleRef" in normalized:
                role_ref = normalized["roleRef"]
                if isinstance(role_ref, dict):
                    if "api_group" in role_ref:
                        role_ref["apiGroup"] = role_ref.pop("api_group")

            if "subjects" in normalized:
                subjects = normalized["subjects"]
                if isinstance(subjects, list):
                    for subject in subjects:
                        if isinstance(subject, dict):
                            if "api_group" in subject:
                                subject["apiGroup"] = subject.pop("api_group")
                            if subject.get("apiGroup") is None or subject.get("apiGroup") == "":
                                subject.pop("apiGroup", None)

        elif kind == "ServiceAccount":
            if for_backup:
                normalized.pop("secrets", None)

        return normalized

    def _set_api_version_for_kind(self, resource: Dict) -> None:
        kind = resource.get("kind")
        if not kind:
            return
        api = self._api_version_map.get(kind)
        if api:
            resource["apiVersion"] = api

    def _create_base_k8s_resource(self, data: Dict, kind: str, from_backup: bool = False) -> Dict:
        if from_backup:
            metadata = data.get("metadata", {})
        else:
            flat_metadata = data.get("metadata", {})
            metadata = {
                "name": data.get("name") or flat_metadata.get("name", ""),
                "namespace": data.get("namespace") or flat_metadata.get("namespace", ""),
                "labels": data.get("labels") or flat_metadata.get("labels") or {},
                "annotations": data.get("annotations") or flat_metadata.get("annotations") or {}
            }

        k8s_resource = {
            "apiVersion": self._api_version_map.get(kind, "v1"),
            "kind": kind,
            "metadata": metadata
        }
        return k8s_resource

    def _populate_resource_content(self, k8s_resource: Dict, data: Dict, kind: str, from_backup: bool = False) -> Dict:
        if kind == "ConfigMap":
            k8s_resource["data"] = data.get("data", {})
            if data.get("binary_data") or data.get("binaryData"):
                k8s_resource["binaryData"] = data.get("binary_data") or data.get("binaryData", {})

        elif kind == "Secret":
            if from_backup:
                k8s_resource["data"] = data.get("data", {})
            else:
                import base64
                decoded_data = data.get("decoded_data", {})
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
            if not from_backup:
                cleaned_rules = []
                for rule in rules:
                    if isinstance(rule, dict):
                        cleaned_rule = {}
                        if rule.get("api_groups"):
                            cleaned_rule["apiGroups"] = rule.get("api_groups")
                        elif "api_groups" in rule:
                            cleaned_rule["apiGroups"] = rule.pop("api_groups")
                        if rule.get("resources"):
                            cleaned_rule["resources"] = rule.get("resources")
                        if rule.get("verbs"):
                            cleaned_rule["verbs"] = rule.get("verbs")
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
            if not from_backup:
                for subject in subjects:
                    if isinstance(subject, dict) and "api_group" in subject:
                        subject["apiGroup"] = subject.pop("api_group")
                if isinstance(role_ref, dict) and "api_group" in role_ref:
                    role_ref["apiGroup"] = role_ref.pop("api_group")
            k8s_resource["subjects"] = subjects
            k8s_resource["roleRef"] = role_ref

        elif kind in ["Deployment", "StatefulSet", "DaemonSet", "Service", "Job", "CronJob", "Ingress", "PersistentVolumeClaim", "ServiceAccount"]:
            if from_backup:
                spec = data.get("spec", {})
                spec = self._normalize_spec(kind, spec, for_backup=False)
            else:
                spec = self._build_spec_from_flat_data(data, kind)
            k8s_resource["spec"] = spec

        return k8s_resource

    def _build_spec_from_flat_data(self, flat_data: Dict, kind: str) -> Dict:
        if kind == "Deployment":
            api_spec = flat_data.get("spec", {})
            spec = {
                "replicas": api_spec.get("replicas", 1),
                "selector": {"matchLabels": api_spec.get("selector", {})},
                "template": {
                    "metadata": api_spec.get("template", {}).get("metadata", {"labels": api_spec.get("selector", {})}),
                    "spec": {
                        "containers": self._convert_containers(api_spec.get("template", {}).get("spec", {}).get("containers", [])),
                        "volumes": api_spec.get("template", {}).get("spec", {}).get("volumes", [])
                    }
                }
            }
            if api_spec.get("strategy"):
                spec["strategy"] = {"type": api_spec.get("strategy")}
            return spec

        elif kind == "StatefulSet":
            api_spec = flat_data.get("spec", {})
            spec = {
                "replicas": api_spec.get("replicas", 1),
                "selector": {"matchLabels": api_spec.get("selector", {})},
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
                spec["volumeClaimTemplates"] = self._convert_volume_claim_templates(api_spec.get("volumeClaimTemplates", []))
            return spec

        elif kind == "DaemonSet":
            api_spec = flat_data.get("spec", {})
            return {
                "selector": {"matchLabels": api_spec.get("selector", {})},
                "template": {
                    "metadata": api_spec.get("template", {}).get("metadata", {"labels": api_spec.get("selector", {})}),
                    "spec": {
                        "containers": self._convert_containers(api_spec.get("template", {}).get("spec", {}).get("containers", [])),
                        "volumes": api_spec.get("template", {}).get("spec", {}).get("volumes", [])
                    }
                }
            }

        elif kind == "Service":
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
            api_spec = flat_data.get("spec", {})
            spec = {
                "template": {
                    "metadata": api_spec.get("template", {}).get("metadata", {}),
                    "spec": {
                        "containers": self._convert_containers(api_spec.get("template", {}).get("spec", {}).get("containers", [])),
                        "restartPolicy": api_spec.get("template", {}).get("spec", {}).get("restartPolicy", api_spec.get("template", {}).get("spec", {}).get("restart_policy", "Never"))
                    }
                }
            }
            for field in ["completions", "parallelism", "backoffLimit"]:
                if api_spec.get(field):
                    spec[field] = api_spec.get(field)
            return spec

        elif kind == "CronJob":
            api_spec = flat_data.get("spec", {})
            spec = {
                "schedule": api_spec.get("schedule", ""),
                "jobTemplate": {
                    "spec": {
                        "template": {
                            "metadata": api_spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("metadata", {}),
                            "spec": {
                                "containers": self._convert_containers(api_spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])),
                                "restartPolicy": api_spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec", {}).get("restartPolicy", api_spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec", {}).get("restart_policy", "Never"))
                            }
                        }
                    }
                }
            }
            if api_spec.get("suspend") is not None:
                spec["suspend"] = api_spec.get("suspend")
            return spec

        elif kind == "Ingress":
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
            api_spec = flat_data.get("spec", {})
            spec = {
                "accessModes": api_spec.get("accessModes", ["ReadWriteOnce"]),
                "resources": api_spec.get("resources", {
                    "requests": {"storage": api_spec.get("resources", {}).get("requests", {}).get("storage", "1Gi")}
                })
            }
            if api_spec.get("storageClassName"):
                spec["storageClassName"] = api_spec.get("storageClassName")
            if api_spec.get("volumeMode"):
                spec["volumeMode"] = api_spec.get("volumeMode")
            return spec

        elif kind == "ServiceAccount":
            spec = {}
            if flat_data.get("automount_service_account_token") is not None:
                spec["automountServiceAccountToken"] = flat_data.get("automount_service_account_token")
            if flat_data.get("image_pull_secrets"):
                spec["imagePullSecrets"] = [{"name": secret} for secret in flat_data.get("image_pull_secrets", [])]
            return spec

        return {}

    def _convert_flat_to_k8s_format(self, flat_data: Dict, kind: str) -> Dict:
        if not flat_data or not kind:
            return {}
        k8s_resource = self._create_base_k8s_resource(flat_data, kind, from_backup=False)
        k8s_resource = self._populate_resource_content(k8s_resource, flat_data, kind, from_backup=False)
        return k8s_resource

    def _convert_containers(self, containers_data: List[Dict]) -> List[Dict]:
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
                        env_vars.append(env_var)
                container["env"] = env_vars
            if c.get("resources"):
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
                    volume_mount = {"name": vm.get("name", ""), "mountPath": vm.get("mountPath", "")}
                    if vm.get("readOnly") is not None:
                        volume_mount["readOnly"] = vm.get("readOnly")
                    if vm.get("subPath"):
                        volume_mount["subPath"] = vm.get("subPath")
                    container["volumeMounts"].append(volume_mount)
            containers.append(container)
        return containers

    def _convert_volume_claim_templates(self, vct_data: List[Dict]) -> List[Dict]:
        templates = []
        for vct in vct_data:
            template = {
                "metadata": vct.get("metadata", {"name": vct.get("name", "")}),
                "spec": {
                    "accessModes": vct.get("spec", {}).get("accessModes", vct.get("access_modes", ["ReadWriteOnce"])),
                    "resources": vct.get("spec", {}).get("resources", {
                        "requests": {"storage": vct.get("storage", "1Gi")}
                    })
                }
            }
            storage_class = vct.get("spec", {}).get("storageClassName") or vct.get("storage_class")
            if storage_class:
                template["spec"]["storageClassName"] = storage_class
            templates.append(template)
        return templates
