"""
按接口返回的资源对象做备份与恢复。
"""
import logging
import os
import tempfile
from datetime import datetime
from typing import Dict, List, Optional

from config import BACKUP_RETENTION_DAYS
from services.k8s_advanced.base import RESOURCE_TYPE_TO_KIND
from services.k8s_constants import API_VERSION_MAP, RESOURCE_TYPE_SINGULAR_TO_KIND
from utils.backup_paths import cleanup_expired_backups, get_backup_path, list_backup_files, resolve_backup_file
from utils.resource_yaml import dumps_manifests, loads_manifests, short_error

logger = logging.getLogger(__name__)

_KIND_TO_PLURAL = {kind: plural for plural, kind in RESOURCE_TYPE_TO_KIND.items()}

_SHORT_ALIASES = {
    "deploy": "deployment",
    "sts": "statefulset",
    "ds": "daemonset",
    "svc": "service",
    "cm": "configmap",
    "sa": "serviceaccount",
    "pvc": "persistentvolumeclaim",
    "pv": "persistentvolume",
    "ns": "namespace",
    "hpa": "horizontalpodautoscaler",
    "np": "networkpolicy",
    "quota": "resourcequota",
}

_NAMESPACE_TYPES = (
    "serviceaccounts",
    "configmaps",
    "secrets",
    "persistentvolumeclaims",
    "roles",
    "rolebindings",
    "services",
    "ingresses",
    "deployments",
    "statefulsets",
    "daemonsets",
    "jobs",
    "cronjobs",
)

# 命名空间备份不扫描这些组，以及以 .k8s.io 结尾的组。
_BUILTIN_API_GROUPS = {
    "",
    "apps",
    "autoscaling",
    "batch",
    "extensions",
    "policy",
}


def _api_group(group_version: str) -> str:
    if "/" not in (group_version or ""):
        return ""
    return group_version.rsplit("/", 1)[0]


def _is_custom_resource(group_version: str) -> bool:
    group = _api_group(group_version)
    if not group or group in _BUILTIN_API_GROUPS or group.endswith(".k8s.io"):
        return False
    return True


def _version_rank(group_version: str):
    version = group_version.rsplit("/", 1)[-1].lower()
    prerelease = 1 if ("alpha" in version or "beta" in version) else 0
    return prerelease, version


def _prefer_resource(candidate: Dict, current: Dict) -> bool:
    """同一 Kind 的多个版本里，优先 preferred，其次稳定版本中较新的一个。"""
    if bool(candidate.get("preferred")) != bool(current.get("preferred")):
        return bool(candidate.get("preferred"))
    candidate_rank = _version_rank(candidate.get("group_version") or "")
    current_rank = _version_rank(current.get("group_version") or "")
    if candidate_rank[0] != current_rank[0]:
        return candidate_rank[0] < current_rank[0]
    return candidate_rank[1] > current_rank[1]


def resolve_resource(resource_type: str, api_version: Optional[str] = None):
    """解析资源类型，返回 (复数类型, Kind, apiVersion)。"""
    raw = (resource_type or "").strip()
    if not raw:
        raise ValueError("资源类型不能为空")
    key = _SHORT_ALIASES.get(raw.lower(), raw.lower())
    kind = RESOURCE_TYPE_SINGULAR_TO_KIND.get(key)
    if kind is None and raw in API_VERSION_MAP:
        kind = raw
    if kind is None:
        kind = RESOURCE_TYPE_TO_KIND.get(key)
    if kind is None:
        if api_version:
            return key, raw, api_version
        raise ValueError(f"不支持的资源类型: {resource_type}")
    version = api_version or API_VERSION_MAP.get(kind)
    if not version:
        raise ValueError(f"不支持的资源类型: {resource_type}")
    plural = _KIND_TO_PLURAL.get(kind, kind.lower())
    return plural, kind, version


def _path_segment(value: str, label: str) -> str:
    if (
        not value
        or value in (".", "..")
        or any(ch in value for ch in ("/", "\\", "\x00"))
    ):
        raise ValueError(f"非法的{label}")
    return value


def _is_generated(kind: str, name: str) -> bool:
    if kind == "ConfigMap" and name == "kube-root-ca.crt":
        return True
    if kind == "ServiceAccount" and name == "default":
        return True
    if kind == "Secret" and name.startswith("default-token-"):
        return True
    return False


def _atomic_write(path: str, text: str) -> None:
    directory = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".yaml", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _allocate_path(directory: str, filename: str) -> str:
    path = os.path.join(directory, filename)
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(filename)
    for index in range(1, 1000):
        candidate = os.path.join(directory, f"{stem}_{index}{ext}")
        if not os.path.exists(candidate):
            return candidate
    raise RuntimeError("无法分配备份文件名")


class BackupRestoreMixin:
    """备份与恢复。"""

    async def _resolve_backup_target(self, resource_type: str, api_version: Optional[str] = None):
        """返回 (复数名, Kind, apiVersion)。未登记的类型按集群 API 发现结果匹配。"""
        fallback = None
        try:
            plural, kind, version = resolve_resource(resource_type, api_version)
        except ValueError:
            plural = kind = version = None
        else:
            if kind in API_VERSION_MAP or kind in _KIND_TO_PLURAL:
                return plural, kind, version
            fallback = (plural, kind, version)

        aliased = _SHORT_ALIASES.get((resource_type or "").strip().lower(), (resource_type or "").strip())
        try:
            discovered = await self._dynamic_service.list_available_resources_async()
        except Exception:
            if fallback and fallback[1] != fallback[0]:
                return fallback
            raise
        matches = []
        for item in discovered:
            name = item.get("name") or ""
            if "/" in name:
                continue
            item_kind = item.get("kind") or ""
            if name.lower() == aliased.lower() or item_kind.lower() in {aliased.lower(), (resource_type or "").strip().lower()}:
                matches.append(item)
        if api_version:
            exact = [item for item in matches if (item.get("group_version") or "") == api_version]
            if exact:
                matches = exact
            elif matches:
                raise ValueError(f"资源类型 {resource_type} 在 {api_version} 中不存在")
            elif fallback and fallback[1] != fallback[0]:
                return fallback
            else:
                matches = []
        by_name = [item for item in matches if (item.get("name") or "").lower() == aliased.lower()]
        pool = by_name or matches
        chosen: Dict[tuple, Dict] = {}
        for item in pool:
            key = (_api_group(item.get("group_version") or ""), item.get("kind"))
            current = chosen.get(key)
            if current is None or _prefer_resource(item, current):
                chosen[key] = item
        if len(chosen) == 1:
            item = next(iter(chosen.values()))
            plural_name = item.get("name") or (item.get("kind") or "resource").lower()
            return plural_name, item.get("kind"), item.get("group_version")
        if not chosen:
            if fallback and fallback[1] != fallback[0]:
                return fallback
            raise ValueError(f"不支持的资源类型: {resource_type}")
        versions = ", ".join(
            sorted(f"{item.get('group_version')}/{item.get('kind')}" for item in chosen.values())
        )
        raise ValueError(f"资源类型 {resource_type} 对应多个 API（{versions}），请指定 api_version")

    async def _resolve_cluster_name(self, cluster_name: Optional[str]) -> str:
        if cluster_name:
            return _path_segment(cluster_name, "集群名称")
        info = await self.k8s_service.get_cluster_info()
        resolved = info.get("cluster_name") or "default"
        return _path_segment(resolved, "集群名称")

    def _write_manifests(self, directory: str, filename: str, manifests: List[Dict]) -> str:
        os.makedirs(directory, exist_ok=True)
        text = dumps_manifests(manifests)
        path = _allocate_path(directory, filename)
        _atomic_write(path, text)
        cleanup_expired_backups(self.backup_dir, BACKUP_RETENTION_DAYS)
        return path

    async def save_resource_backup(
        self,
        kind: str,
        name: str,
        namespace: str,
        api_version: Optional[str] = None,
        cluster_name: Optional[str] = None,
        auto: bool = False,
    ) -> str:
        """读取资源原对象并写入备份文件。"""
        plural, resolved_kind, resolved_version = await self._resolve_backup_target(kind, api_version)
        resource_name = _path_segment(name, "资源名称")
        ns = _path_segment(namespace, "命名空间") if namespace else namespace
        cluster = await self._resolve_cluster_name(cluster_name)
        manifest = await self._dynamic_service.get_manifest_async(
            resolved_version, resolved_kind, resource_name, ns
        )
        directory = get_backup_path(
            self.backup_dir,
            cluster,
            namespace=ns,
            resource_type=_path_segment(plural, "资源类型"),
            resource_name=resource_name,
            create_dirs=True,
        )
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        marker = "_auto_" if auto else "_"
        filename = f"{resource_name}{marker}{stamp}.yaml"
        return self._write_manifests(directory, filename, [manifest])

    async def backup_namespace(
        self,
        namespace: str,
        cluster_name: Optional[str] = None,
        include_secrets: bool = True,
    ) -> Dict:
        """备份命名空间中的指定内置资源和自定义资源。已注册类型读取失败时不写文件。"""
        ns = _path_segment(namespace, "命名空间")
        cluster = await self._resolve_cluster_name(cluster_name)
        manifests: List[Dict] = []
        skipped: List[Dict] = []
        errors: List[str] = []

        try:
            namespace_manifest = await self._dynamic_service.get_manifest_async("v1", "Namespace", ns, None)
            manifests.append(namespace_manifest)
        except Exception as exc:
            skipped.append({"resource_type": "namespaces", "reason": short_error(exc)})

        resource_types = [item for item in _NAMESPACE_TYPES if include_secrets or item != "secrets"]
        for resource_type in resource_types:
            try:
                _plural, kind, api_version = resolve_resource(resource_type)
                items = await self._dynamic_service.list_manifests_async(api_version, kind, ns)
            except ValueError as exc:
                skipped.append({"resource_type": resource_type, "reason": short_error(exc)})
                continue
            except Exception as exc:
                errors.append(f"{resource_type}: {short_error(exc)}")
                continue
            for item in items:
                item_name = item.get("metadata", {}).get("name", "")
                if _is_generated(item.get("kind", kind), item_name):
                    continue
                manifests.append(item)

        try:
            discovered = await self._dynamic_service.list_available_resources_async()
        except Exception as exc:
            errors.append(f"customresources: {short_error(exc)}")
            discovered = []
        custom_by_kind: Dict[tuple, Dict] = {}
        for item in discovered:
            name = item.get("name") or ""
            if not item.get("namespaced") or "/" in name or not _is_custom_resource(item.get("group_version") or ""):
                continue
            key = (_api_group(item.get("group_version") or ""), item.get("kind"))
            current = custom_by_kind.get(key)
            if current is None or _prefer_resource(item, current):
                custom_by_kind[key] = item
        for item in custom_by_kind.values():
            resource_type = item.get("name") or item.get("kind")
            try:
                objects = await self._dynamic_service.list_manifests_async(
                    item.get("group_version"), item.get("kind"), ns
                )
            except ValueError as exc:
                skipped.append({"resource_type": resource_type, "reason": short_error(exc)})
                continue
            except Exception as exc:
                errors.append(f"{resource_type}: {short_error(exc)}")
                continue
            manifests.extend(objects)

        if errors:
            raise RuntimeError("备份未完成: " + "; ".join(errors))
        if not manifests:
            raise RuntimeError("没有可备份的资源")

        directory = get_backup_path(self.backup_dir, cluster, namespace=ns, create_dirs=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self._write_manifests(directory, f"namespace_backup_{stamp}.yaml", manifests)
        logger.info("命名空间 %s 备份完成: %s (%d)", ns, backup_file, len(manifests))
        return {
            "backup_file": backup_file,
            "resource_count": len(manifests),
            "skipped": skipped,
        }

    async def backup_specific_resource(
        self,
        resource_type: str,
        resource_name: str,
        namespace: str,
        cluster_name: Optional[str] = None,
        api_version: Optional[str] = None,
    ) -> str:
        """备份指定资源的原对象。resource_type 可以是类型名、Kind 或复数名。"""
        try:
            return await self.save_resource_backup(
                kind=resource_type,
                name=resource_name,
                namespace=namespace,
                api_version=api_version,
                cluster_name=cluster_name,
                auto=False,
            )
        except Exception as exc:
            raise RuntimeError(f"备份资源失败: {short_error(exc)}") from None

    def _backup_file_in_dir(self, backup_file: str) -> str:
        return resolve_backup_file(self.backup_dir, backup_file)

    async def restore_from_backup(self, backup_file: str, target_namespace: Optional[str] = None) -> Dict:
        """按备份写回资源。不存在则创建，已存在则替换。"""
        path = self._backup_file_in_dir(backup_file)
        with open(path, "r", encoding="utf-8") as handle:
            manifests = loads_manifests(handle.read())

        if target_namespace:
            for manifest in manifests:
                namespace = (manifest.get("metadata") or {}).get("namespace")
                if namespace and namespace != target_namespace:
                    raise ValueError(
                        f"不允许恢复到不同的命名空间。原命名空间: {namespace}, 目标命名空间: {target_namespace}"
                    )

        results = {"restored": [], "failed": [], "total": 0}
        for manifest in manifests:
            kind = manifest.get("kind", "")
            name = (manifest.get("metadata") or {}).get("name", "")
            results["total"] += 1
            try:
                action = await self._dynamic_service.apply_manifest_async(manifest)
                results["restored"].append(f"{action} {kind}/{name}")
            except Exception as exc:
                message = short_error(exc)
                logger.warning("恢复 %s/%s 失败: %s", kind, name, message)
                results["failed"].append({"resource": f"{kind}/{name}", "error": message})
        return results

    def list_backups(self, cluster_name: Optional[str] = None, namespace: Optional[str] = None) -> List[Dict]:
        """列出备份文件。"""
        return list_backup_files(self.backup_dir, cluster_name, namespace)
