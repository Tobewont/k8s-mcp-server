"""
资源规格构建器 - 为验证/预览构建 K8s 资源数据
"""
from typing import Dict, Any, Callable, Optional

KIND_MAPPING = {
    "horizontalpodautoscaler": "HorizontalPodAutoscaler",
    "networkpolicy": "NetworkPolicy",
    "resourcequota": "ResourceQuota",
}


def _workload_template(name: str, params: Dict) -> Dict:
    """工作负载通用模板（Deployment/StatefulSet/DaemonSet）"""
    labels = params.get("labels", {"app": name})
    return {
        "selector": {"matchLabels": labels},
        "template": {
            "metadata": {"labels": labels},
            "spec": {
                "containers": [{
                    "name": name,
                    "image": params.get("image", ""),
                    "ports": params.get("ports", []),
                    "env": [
                        {"name": k, "value": str(v)}
                        for k, v in (params.get("env_vars", {})).items()
                    ],
                    "resources": params.get("resources", {}),
                }]
            },
        },
    }


def _build_deployment(name: str, namespace: str, params: Dict) -> Dict:
    spec = _workload_template(name, params)
    spec["replicas"] = params.get("replicas", 1)
    return {"spec": spec}


def _build_statefulset(name: str, namespace: str, params: Dict) -> Dict:
    spec = _workload_template(name, params)
    spec["replicas"] = params.get("replicas", 1)
    spec["serviceName"] = params.get("service_name", name)
    spec["volumeClaimTemplates"] = params.get("volume_claims", [])
    return {"spec": spec}


def _build_daemonset(name: str, namespace: str, params: Dict) -> Dict:
    return {"spec": _workload_template(name, params)}


def _build_service(name: str, namespace: str, params: Dict) -> Dict:
    return {
        "spec": {
            "type": params.get("service_type", "ClusterIP"),
            "ports": params.get("ports", []),
            "selector": params.get("selector", {}),
        }
    }


def _build_configmap(name: str, namespace: str, params: Dict) -> Dict:
    return {"data": params.get("data", {})}


def _build_secret(name: str, namespace: str, params: Dict) -> Dict:
    return {
        "type": params.get("secret_type", "Opaque"),
        "data": params.get("data", {}),
    }


def _build_job(name: str, namespace: str, params: Dict) -> Dict:
    return {
        "spec": {
            "template": {
                "spec": {
                    "containers": [{
                        "name": name,
                        "image": params.get("image", ""),
                        "command": params.get("command", []),
                        "args": params.get("args", []),
                    }],
                    "restartPolicy": params.get("restart_policy", "Never"),
                }
            },
            "backoffLimit": params.get("backoff_limit", 6),
        }
    }


def _build_cronjob(name: str, namespace: str, params: Dict) -> Dict:
    return {
        "spec": {
            "schedule": params.get("schedule", ""),
            "jobTemplate": {
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [{
                                "name": name,
                                "image": params.get("image", ""),
                                "command": params.get("command", []),
                                "args": params.get("args", []),
                            }],
                            "restartPolicy": params.get("restart_policy", "Never"),
                        }
                    }
                }
            },
            "suspend": params.get("suspend", False),
        }
    }


def _build_ingress(name: str, namespace: str, params: Dict) -> Dict:
    return {
        "spec": {
            "rules": params.get("rules", []),
            "tls": params.get("tls", []),
            "ingressClassName": params.get("ingress_class_name"),
        }
    }


def _build_persistentvolumeclaim(name: str, namespace: str, params: Dict) -> Dict:
    return {
        "spec": {
            "accessModes": params.get("access_modes", ["ReadWriteOnce"]),
            "resources": {"requests": {"storage": params.get("size", "1Gi")}},
            "storageClassName": params.get("storage_class_name"),
        }
    }


def _build_serviceaccount(name: str, namespace: str, params: Dict) -> Dict:
    result = {}
    if params.get("automount_service_account_token") is not None:
        result["automountServiceAccountToken"] = params["automount_service_account_token"]
    return result


def _build_role(name: str, namespace: str, params: Dict) -> Dict:
    return {"rules": params.get("rules", [])}


def _build_rolebinding(name: str, namespace: str, params: Dict) -> Dict:
    return {
        "subjects": params.get("subjects", []),
        "roleRef": params.get("role_ref", {}),
    }


def _build_horizontalpodautoscaler(name: str, namespace: str, params: Dict) -> Dict:
    return {
        "spec": {
            "scaleTargetRef": params.get("target_ref", {}),
            "minReplicas": params.get("min_replicas", 1),
            "maxReplicas": params.get("max_replicas", 10),
            "metrics": params.get("metrics", []),
        }
    }


def _build_networkpolicy(name: str, namespace: str, params: Dict) -> Dict:
    return {
        "spec": {
            "podSelector": params.get("pod_selector", {}),
            "policyTypes": params.get("policy_types", ["Ingress"]),
            "ingress": params.get("ingress", []),
            "egress": params.get("egress", []),
        }
    }


def _build_resourcequota(name: str, namespace: str, params: Dict) -> Dict:
    return {
        "spec": {
            "hard": params.get("hard", {}),
            "scopes": params.get("scopes", []),
        }
    }


_RESOURCE_BUILDERS: Dict[str, Callable[[str, str, Dict], Dict]] = {
    "deployment": _build_deployment,
    "statefulset": _build_statefulset,
    "daemonset": _build_daemonset,
    "service": _build_service,
    "configmap": _build_configmap,
    "secret": _build_secret,
    "job": _build_job,
    "cronjob": _build_cronjob,
    "ingress": _build_ingress,
    "persistentvolumeclaim": _build_persistentvolumeclaim,
    "serviceaccount": _build_serviceaccount,
    "role": _build_role,
    "rolebinding": _build_rolebinding,
    "horizontalpodautoscaler": _build_horizontalpodautoscaler,
    "networkpolicy": _build_networkpolicy,
    "resourcequota": _build_resourcequota,
}


def build_resource_data(
    resource_type: str,
    name: str,
    namespace: str,
    api_version: str,
    params: Optional[Dict] = None,
) -> Dict:
    """
    为验证构建资源数据
    """
    params = params or {}
    kind = KIND_MAPPING.get(resource_type.lower(), resource_type.capitalize())
    base_resource = {
        "apiVersion": api_version,
        "kind": kind,
        "metadata": {"name": name, "namespace": namespace},
    }
    builder = _RESOURCE_BUILDERS.get(resource_type.lower())
    if builder:
        spec_part = builder(name, namespace, params)
        base_resource.update(spec_part)
    return base_resource
