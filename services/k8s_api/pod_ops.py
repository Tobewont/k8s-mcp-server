from typing import Dict, List, Any, Optional
from kubernetes import client
from kubernetes.client.exceptions import ApiException
from utils.k8s_helpers import to_local_time_str

class PodOpsMixin:
    """Pod 相关操作"""

    async def list_pods(self, namespace: str = "default", label_selector: Optional[str] = None,
                  field_selector: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出 Pod"""
        try:
            if namespace == "all":
                pods = self.v1_api.list_pod_for_all_namespaces(
                    label_selector=label_selector,
                    field_selector=field_selector
                )
            else:
                pods = self.v1_api.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=label_selector,
                    field_selector=field_selector
                )
        
            pod_list = []
            for pod in pods.items:
                containers_resources = []
                for c in (pod.spec.containers or []):
                    res = c.resources or {}
                    containers_resources.append({
                        "requests": dict(res.requests) if res.requests else {},
                        "limits": dict(res.limits) if res.limits else {}
                    })
                pod_info = {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "status": pod.status.phase,
                    "created": to_local_time_str(pod.metadata.creation_timestamp) if pod.metadata.creation_timestamp else None,
                    "node": pod.spec.node_name,
                    "ready": self._get_pod_ready_status(pod),
                    "restarts": self._get_pod_restart_count(pod),
                    "pod_ip": pod.status.pod_ip,
                    "labels": pod.metadata.labels or {},
                    "containers_resources": containers_resources,
                }
                pod_list.append(pod_info)
        
            return pod_list
        
        except ApiException as e:
            raise Exception(f"获取 Pod 列表失败: {e.reason}")

    async def get_pod(self, name: str, namespace: str = "default") -> Dict[str, Any]:
        """获取单个 Pod 详情"""
        try:
            pod = self.v1_api.read_namespaced_pod(name=name, namespace=namespace)
        
            return {
                "metadata": {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "labels": pod.metadata.labels or {},
                    "annotations": pod.metadata.annotations or {},
                    "created": to_local_time_str(pod.metadata.creation_timestamp) if pod.metadata.creation_timestamp else None,
                    "uid": pod.metadata.uid
                },
                "spec": {
                    "node_name": pod.spec.node_name,
                    "restart_policy": pod.spec.restart_policy,
                    "service_account": pod.spec.service_account,
                    "containers": [
                        {
                            "name": container.name,
                            "image": container.image,
                            "ports": [
                                {"containerPort": port.container_port, "protocol": port.protocol}
                                for port in (container.ports or [])
                            ],
                            "resources": {
                                "requests": container.resources.requests or {} if container.resources else {},
                                "limits": container.resources.limits or {} if container.resources else {}
                            },
                            "env": [
                                {"name": env.name, "value": env.value or ""}
                                for env in (container.env or [])
                            ]
                        }
                        for container in pod.spec.containers
                    ]
                },
                "status": {
                    "phase": pod.status.phase,
                    "pod_ip": pod.status.pod_ip,
                    "start_time": to_local_time_str(pod.status.start_time) if pod.status.start_time else None,
                    "conditions": [
                        {
                            "type": condition.type,
                            "status": condition.status,
                            "reason": condition.reason,
                            "message": condition.message
                        }
                        for condition in (pod.status.conditions or [])
                    ],
                    "container_statuses": [
                        {
                            "name": status.name,
                            "ready": status.ready,
                            "restart_count": status.restart_count,
                            "image": status.image,
                            "state": self._extract_container_state(status.state)
                        }
                        for status in (pod.status.container_statuses or [])
                    ]
                }
            }
        
        except ApiException as e:
            raise Exception(f"获取 Pod 详情失败: {e.reason}")

    async def get_pod_logs(self, name: str, namespace: str = "default",
                     container: Optional[str] = None, lines: int = 100,
                     since_seconds: Optional[int] = None, follow: bool = False,
                     previous: bool = False) -> str:
        """获取 Pod 日志，previous=True 时获取上一实例（崩溃容器）的日志"""
        try:
            logs = self.v1_api.read_namespaced_pod_log(
                name=name,
                namespace=namespace,
                container=container,
                tail_lines=lines,
                since_seconds=since_seconds,
                follow=follow,
                previous=previous
            )
            return logs
        
        except ApiException as e:
            raise Exception(f"获取 Pod 日志失败: {e.reason}")

    async def delete_pod(self, name: str, namespace: str = "default",
                   grace_period_seconds: Optional[int] = None) -> Dict[str, Any]:
        """删除 Pod"""
        try:
            body = client.V1DeleteOptions(grace_period_seconds=grace_period_seconds)
            response = self.v1_api.delete_namespaced_pod(
                name=name,
                namespace=namespace,
                body=body
            )
        
                # 安全地获取uid，避免details属性不存在的问题
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
        
        except ApiException as e:
            raise Exception(f"删除 Pod 失败: {e.reason}")


    def _get_pod_ready_status(self, pod) -> str:
        """获取 Pod 就绪状态"""
        if not pod.status.conditions:
            return "Unknown"
    
        for condition in pod.status.conditions:
            if condition.type == "Ready":
                return "Ready" if condition.status == "True" else "NotReady"
        return "Unknown"

    def _get_pod_restart_count(self, pod) -> int:
        """获取 Pod 重启次数"""
        if not pod.status.container_statuses:
            return 0
    
        return sum(status.restart_count for status in pod.status.container_statuses)

    def _extract_container_state(self, state) -> Dict[str, Any]:
        """提取容器状态"""
        if state.running:
            return {
                "state": "running",
                "started_at": to_local_time_str(state.running.started_at) if state.running.started_at else None
            }
        elif state.waiting:
            return {
                "state": "waiting",
                "reason": state.waiting.reason,
                "message": state.waiting.message
            }
        elif state.terminated:
            return {
                "state": "terminated",
                "reason": state.terminated.reason,
                "message": state.terminated.message,
                "started_at": to_local_time_str(state.terminated.started_at) if state.terminated.started_at else None,
                "finished_at": to_local_time_str(state.terminated.finished_at) if state.terminated.finished_at else None,
                "exit_code": state.terminated.exit_code
            }
        else:
            return {"state": "unknown"}
