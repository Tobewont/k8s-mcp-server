"""
动态资源服务
使用 Kubernetes DynamicClient 发现和操作集群中所有可用的 API 资源
支持 CRD、内置资源及未来新增资源
"""
import asyncio
from typing import Dict, List, Any, Optional
from kubernetes.dynamic.resource import Resource


def _resource_to_dict(obj) -> Dict:
    """将 Kubernetes 对象转为字典"""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        d = obj.to_dict()
        return d if isinstance(d, dict) else {"raw": str(obj)}
    return {"raw": str(obj)}


class DynamicResourceService:
    """基于 DynamicClient 的动态资源操作"""

    def __init__(self, k8s_service):
        self.k8s_service = k8s_service
        self._dyn_client = None

    def _get_client(self):
        if self._dyn_client is None:
            self._dyn_client = self.k8s_service.get_dynamic_client()
        return self._dyn_client

    def list_available_resources(self) -> List[Dict[str, Any]]:
        """
        列出集群中所有可发现的 API 资源
        Returns: [{"group_version": "v1", "kind": "Pod", "namespaced": True, "name": "pods"}, ...]
        """
        client = self._get_client()
        result = []
        seen = set()
        for resource in client.resources.search():
            # 排除 List 类型，只保留资源本身
            if resource.kind.endswith("List"):
                continue
            key = (resource.group_version, resource.kind)
            if key in seen:
                continue
            seen.add(key)
            result.append({
                "group_version": resource.group_version,
                "kind": resource.kind,
                "namespaced": resource.namespaced,
                "name": resource.name,  # 复数形式，如 pods, deployments
            })
        return sorted(result, key=lambda x: (x["group_version"], x["kind"]))

    def _get_resource(self, api_version: str, kind: str) -> Optional[Resource]:
        """根据 apiVersion 和 kind 获取 Resource 对象"""
        client = self._get_client()
        try:
            return client.resources.get(api_version=api_version, kind=kind)
        except Exception:
            return None

    def list_resources(self, api_version: str, kind: str, namespace: str = "default") -> List[Dict]:
        """列出指定类型的资源"""
        resource = self._get_resource(api_version, kind)
        if not resource:
            raise ValueError(f"未找到资源: {api_version}/{kind}")
        try:
            if resource.namespaced:
                resp = resource.get(namespace=namespace)
            else:
                resp = resource.get()
            if isinstance(resp, dict):
                items = resp.get("items", [])
            else:
                items = getattr(resp, "items", []) or []
            return [_resource_to_dict(item) for item in items]
        except Exception as e:
            raise RuntimeError(f"列出 {kind} 失败: {e}") from e

    def get_resource(self, api_version: str, kind: str, name: str, namespace: str = "default") -> Dict:
        """获取单个资源"""
        resource = self._get_resource(api_version, kind)
        if not resource:
            raise ValueError(f"未找到资源: {api_version}/{kind}")
        try:
            if resource.namespaced:
                obj = resource.get(name=name, namespace=namespace)
            else:
                obj = resource.get(name=name)
            return _resource_to_dict(obj)
        except Exception as e:
            raise RuntimeError(f"获取 {kind}/{name} 失败: {e}") from e

    def create_resource(self, body: Dict, namespace: str = "default") -> Dict:
        """创建资源，body 需包含 apiVersion、kind、metadata、spec 等"""
        api_version = body.get("apiVersion", "v1")
        kind = body.get("kind", "")
        if not kind:
            raise ValueError("资源 body 必须包含 kind 字段")
        resource = self._get_resource(api_version, kind)
        if not resource:
            raise ValueError(f"未找到资源: {api_version}/{kind}")
        try:
            if resource.namespaced:
                obj = resource.create(body=body, namespace=namespace)
            else:
                obj = resource.create(body=body)
            return _resource_to_dict(obj)
        except Exception as e:
            raise RuntimeError(f"创建 {kind} 失败: {e}") from e

    def update_resource(self, body: Dict, namespace: str = "default") -> Dict:
        """更新资源（replace），body 需为完整资源定义。若缺少 resourceVersion 则先 get 再合并"""
        api_version = body.get("apiVersion", "v1")
        kind = body.get("kind", "")
        name = body.get("metadata", {}).get("name", "")
        if not kind or not name:
            raise ValueError("资源 body 必须包含 kind 和 metadata.name")
        resource = self._get_resource(api_version, kind)
        if not resource:
            raise ValueError(f"未找到资源: {api_version}/{kind}")
        try:
            # 若缺少 resourceVersion，先获取当前资源并合并
            if not body.get("metadata", {}).get("resourceVersion"):
                existing = self.get_resource(api_version, kind, name, namespace)
                if existing and existing.get("metadata", {}).get("resourceVersion"):
                    body = dict(body)
                    if "metadata" not in body:
                        body["metadata"] = {}
                    body["metadata"]["resourceVersion"] = existing["metadata"]["resourceVersion"]
            if resource.namespaced:
                obj = resource.replace(body=body, namespace=namespace)
            else:
                obj = resource.replace(body=body)
            return _resource_to_dict(obj)
        except Exception as e:
            raise RuntimeError(f"更新 {kind}/{name} 失败: {e}") from e

    def delete_resource(self, api_version: str, kind: str, name: str,
                        namespace: str = "default", grace_period_seconds: int = None) -> Dict:
        """删除资源"""
        resource = self._get_resource(api_version, kind)
        if not resource:
            raise ValueError(f"未找到资源: {api_version}/{kind}")
        try:
            kwargs = {}
            if grace_period_seconds is not None:
                kwargs["body"] = {"gracePeriodSeconds": grace_period_seconds}
            if resource.namespaced:
                resource.delete(name=name, namespace=namespace, **kwargs)
            else:
                resource.delete(name=name, **kwargs)
            return {"status": "deleted", "name": name}
        except Exception as e:
            raise RuntimeError(f"删除 {kind}/{name} 失败: {e}") from e

    # 异步包装，避免阻塞事件循环
    async def list_available_resources_async(self) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self.list_available_resources)

    async def list_resources_async(self, api_version: str, kind: str, namespace: str = "default") -> List[Dict]:
        return await asyncio.to_thread(self.list_resources, api_version, kind, namespace)

    async def get_resource_async(self, api_version: str, kind: str, name: str, namespace: str = "default") -> Dict:
        return await asyncio.to_thread(self.get_resource, api_version, kind, name, namespace)

    async def create_resource_async(self, body: Dict, namespace: str = "default") -> Dict:
        return await asyncio.to_thread(self.create_resource, body, namespace)

    async def update_resource_async(self, body: Dict, namespace: str = "default") -> Dict:
        return await asyncio.to_thread(self.update_resource, body, namespace)

    async def delete_resource_async(self, api_version: str, kind: str, name: str, namespace: str = "default", grace_period_seconds: int = None) -> Dict:
        return await asyncio.to_thread(self.delete_resource, api_version, kind, name, namespace, grace_period_seconds)
