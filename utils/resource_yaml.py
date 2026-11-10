"""
资源 YAML 的读写。

字符串按原值保存，避免 YAML 1.1 把 yes、0123、时间戳等读成其他类型。
"""
import copy
from typing import Any, Dict, List, Mapping, Optional, Sequence

import yaml
from yaml.resolver import Resolver


_SERVER_METADATA = (
    "uid",
    "resourceVersion",
    "generation",
    "creationTimestamp",
    "managedFields",
    "selfLink",
    "deletionTimestamp",
    "deletionGracePeriodSeconds",
)

_PLAIN_INDICATORS = set("-?:,[]{}#&*!|>'\"%@`")


class ManifestNotFound(Exception):
    """集群中不存在该资源。"""

    def __init__(self, kind: str, name: str):
        super().__init__(f"资源不存在: {kind}/{name}")
        self.kind = kind
        self.name = name


class ApplyNotFound(Exception):
    """读取或替换时资源不存在。"""


class ApplyConflict(Exception):
    """创建或替换时发生版本冲突。"""


class _ManifestDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def _matches_non_string(value: str) -> bool:
    resolvers = list(Resolver.yaml_implicit_resolvers.get(value[0], ()))
    resolvers.extend(Resolver.yaml_implicit_resolvers.get("", ()))
    for tag, regexp in resolvers:
        if tag == "tag:yaml.org,2002:str":
            continue
        if regexp.match(value):
            return True
    return False


def _is_plain_safe(value: str) -> bool:
    if not value or value != value.strip():
        return False
    if any(ch in value for ch in ("\n", "\r", "\t")):
        return False
    if value[0] in _PLAIN_INDICATORS or value.endswith(":"):
        return False
    if ": " in value or " #" in value:
        return False
    return not _matches_non_string(value)


def _represent_str(dumper: yaml.SafeDumper, data: str):
    if _is_plain_safe(data):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')


_ManifestDumper.add_representer(str, _represent_str)


def short_error(exc: BaseException, limit: int = 300) -> str:
    """截断异常说明，不展开响应体。"""
    text = ""
    summary = getattr(exc, "summary", None)
    if callable(summary):
        try:
            text = str(summary())
        except Exception:
            text = ""
    if not text:
        text = str(exc)
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[:limit] + "..."
    return text or exc.__class__.__name__


def _require_manifest(manifest: Mapping[str, Any]) -> None:
    if not isinstance(manifest, Mapping):
        raise ValueError("备份文件不是 Kubernetes 资源 YAML")
    if not isinstance(manifest.get("apiVersion"), str) or not isinstance(manifest.get("kind"), str):
        raise ValueError("备份文件不是 Kubernetes 资源 YAML")
    if str(manifest.get("kind", "")).endswith("List"):
        raise ValueError("备份文件不是 Kubernetes 资源 YAML")
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict) or not metadata.get("name"):
        raise ValueError("备份文件中的资源缺少 metadata.name")


def _assert_plain(value: Any) -> None:
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise RuntimeError("资源包含无法原样保存的数值")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RuntimeError("资源包含无法原样保存的字段")
            _assert_plain(item)
        return
    if isinstance(value, list):
        for item in value:
            _assert_plain(item)
        return
    raise RuntimeError("资源包含无法原样保存的字段")


def _expand_document(document: Mapping[str, Any]) -> List[Dict[str, Any]]:
    kind = document.get("kind")
    if isinstance(kind, str) and kind.endswith("List") and "items" in document:
        items = document.get("items") or []
        if not isinstance(items, list):
            raise ValueError("备份文件不是 Kubernetes 资源 YAML")
        manifests = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("备份文件不是 Kubernetes 资源 YAML")
            _require_manifest(item)
            manifests.append(item)
        return manifests
    _require_manifest(document)
    return [dict(document)]


def dumps_manifests(manifests: Sequence[Mapping[str, Any]]) -> str:
    """把资源对象序列化为 YAML，并校验读回结果与原对象一致。"""
    if not manifests:
        raise ValueError("没有可备份的资源")
    docs = [copy.deepcopy(dict(item)) for item in manifests]
    for doc in docs:
        _require_manifest(doc)
        _assert_plain(doc)
    text = yaml.dump_all(
        docs,
        Dumper=_ManifestDumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=10**6,
    )
    if not text.endswith("\n"):
        text += "\n"
    loaded = loads_manifests(text)
    if loaded != docs:
        raise RuntimeError("备份内容与资源对象不一致，已中止")
    return text


def loads_manifests(text: str) -> List[Dict[str, Any]]:
    """从 YAML 读出资源对象。每个文档需要 apiVersion、kind 和 metadata.name。"""
    if not text or not str(text).strip():
        raise ValueError("备份文件为空")
    try:
        documents = list(yaml.safe_load_all(text))
    except yaml.YAMLError:
        raise ValueError("备份文件不是合法 YAML") from None
    manifests: List[Dict[str, Any]] = []
    for document in documents:
        if document is None:
            continue
        if not isinstance(document, dict):
            raise ValueError("备份文件不是 Kubernetes 资源 YAML")
        manifests.extend(_expand_document(document))
    if not manifests:
        raise ValueError("备份文件不包含资源")
    return manifests


def prepare_for_write(manifest: Mapping[str, Any], resource_version: Optional[str] = None) -> Dict[str, Any]:
    """去掉服务端维护字段，生成可创建或替换的对象。不修改入参。"""
    if not isinstance(manifest, Mapping):
        raise ValueError("资源格式不正确")
    body = copy.deepcopy(dict(manifest))
    body.pop("status", None)
    metadata = body.get("metadata")
    if not isinstance(metadata, dict) or not metadata.get("name"):
        raise ValueError("资源缺少 metadata.name")
    for key in _SERVER_METADATA:
        metadata.pop(key, None)
    if resource_version:
        metadata["resourceVersion"] = resource_version
    return body


def apply_manifest_ops(manifest: Mapping[str, Any], get_live, create, replace) -> str:
    """资源不存在则创建，已存在则用当前 resourceVersion 替换。冲突时重试一次。"""
    source = copy.deepcopy(dict(manifest))
    _require_manifest(source)
    last_error: Optional[BaseException] = None
    for _ in range(2):
        try:
            live = get_live()
        except ApplyNotFound:
            live = None
        try:
            if live is None:
                create(prepare_for_write(source))
                return "created"
            metadata = live.get("metadata") if isinstance(live, dict) else None
            resource_version = metadata.get("resourceVersion") if isinstance(metadata, dict) else None
            if not resource_version:
                kind = source.get("kind")
                name = source.get("metadata", {}).get("name")
                raise RuntimeError(f"无法取得 {kind}/{name} 的 resourceVersion")
            replace(prepare_for_write(source, resource_version))
            return "replaced"
        except (ApplyConflict, ApplyNotFound) as exc:
            last_error = exc
            continue
    raise RuntimeError("资源写入冲突，恢复未完成") from last_error
