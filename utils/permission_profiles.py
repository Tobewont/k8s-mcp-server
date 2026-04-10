"""
权限 Profile 管理：内置 + 自定义 profile 的 CRUD，
以及 grant_access / revoke_access 的 K8s RBAC 联动逻辑。
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Dict, List, Optional

from config import DATA_DIR, ensure_dirs

logger = logging.getLogger(__name__)

_PROFILES_DIR = os.path.join(DATA_DIR, "auth", "profiles")
_CUSTOM_PROFILES_FILE = os.path.join(_PROFILES_DIR, "custom_profiles.json")
_ACCESS_GRANTS_FILE = os.path.join(DATA_DIR, "auth", "access_grants.json")
_lock = threading.Lock()

# MCP tool 全量列表（Phase 3 过滤用；这里定义分类，profile 中引用分类名）
# 分类设计原则：每个分类的工具都应能被引用它的 profile 实际执行（K8s RBAC 匹配）
TOOL_CATEGORIES = {
    # --- 命名空间级只读（readonly 模板即可执行；get_cluster_info / get_cluster_events
    #     含集群级 API，对低权限用户优雅降级；test_cluster_connection 使用 VersionApi，无需特殊权限） ---
    "read_basic": [
        "whoami", "list_clusters",
        "list_kubeconfigs", "get_kubeconfig_info",
        "batch_list_resources", "batch_describe_resources",
        "get_cluster_info", "get_pod_logs",
        "check_pod_health", "get_cluster_events",
        "list_backups", "test_cluster_connection",
        "set_default_cluster",
    ],
    # --- 命名空间级写操作（deployer 模板即可执行） ---
    "write_workload": [
        "batch_create_resources", "batch_update_resources",
        "batch_delete_resources", "batch_restart_resources",
        "batch_rollout_resources",
    ],
    # --- Pod 交互操作（需 pods/exec、pods/portforward 子资源权限） ---
    "pod_exec": [
        "exec_pod_command", "copy_pod_files", "port_forward",
    ],
    "cluster_manage": [
        "import_cluster", "delete_cluster",
        "load_kubeconfig", "delete_kubeconfig",
    ],
    # --- 命名空间级运维（备份/恢复，需 get + create 权限） ---
    "ops": [
        "backup_namespace", "backup_resource", "restore_from_backup",
    ],
    # --- 集群级操作（需 ClusterRole 级别权限：nodes/namespaces/events/metrics，operator/admin 可用） ---
    "cluster_ops": [
        "check_cluster_health", "check_node_health",
        "get_cluster_resource_usage", "batch_top_resources",
        "manage_node",
    ],
    # --- 用户/Profile 管理 ---
    "user_manage": [
        "admin_manage_users",
    ],
    "profile_manage": [
        "admin_manage_profiles",
    ],
}

# operator 可分配的 profile 白名单
OPERATOR_GRANTABLE_PROFILES = {"viewer", "developer"}

# 自定义 profile 不允许使用的保留分类（防止通过自定义 profile 提权）
# cluster_ops 需要 ClusterRole 级别权限，Namespace Role 无法授权
RESERVED_CATEGORIES = {"user_manage", "profile_manage", "cluster_ops"}

# ========================== 内置 Profile 定义 ==========================

BUILTIN_PROFILES: Dict[str, Dict[str, Any]] = {
    "viewer": {
        "name": "viewer",
        "description": "命名空间只读：查看资源、日志、事件",
        "builtin": True,
        "mcp_tools": {
            "include_categories": ["read_basic"],
        },
        "k8s_rbac": {
            "role_template": "readonly",
            "description": "get/list/watch 常用资源 + pods/log",
        },
    },
    "developer": {
        "name": "developer",
        "description": "开发者：读写工作负载、exec/port-forward Pod、切换/测试集群",
        "builtin": True,
        "mcp_tools": {
            "include_categories": ["read_basic", "write_workload", "pod_exec"],
        },
        "k8s_rbac": {
            "role_template": "deployer",
            "description": "CRUD 工作负载和服务 + pods/log、exec、portforward",
        },
    },
    "operator": {
        "name": "operator",
        "description": "运维：开发者权限 + 备份恢复、集群诊断、节点排水 + 管理 viewer/developer 用户",
        "builtin": True,
        "mcp_tools": {
            "include_categories": ["read_basic", "write_workload", "pod_exec", "ops", "cluster_ops", "user_manage"],
        },
        "k8s_rbac": {
            "role_template": "operator",
            "description": "命名空间全操作 + rbac 只读 + ClusterRole（nodes、namespaces、events、metrics、drain）",
        },
    },
    "admin": {
        "name": "admin",
        "description": "管理员：全部 MCP 工具 + K8s 集群管理员（使用 admin kubeconfig，天然集群全权限）",
        "builtin": True,
        "mcp_tools": {
            "include_categories": list(TOOL_CATEGORIES.keys()),
        },
        "k8s_rbac": {
            "role_template": "admin",
            "description": "namespace 内全资源全操作（admin 用户使用 K8s admin kubeconfig，无需额外 ClusterRole）",
        },
    },
}


def _ensure_profiles_dir() -> None:
    os.makedirs(_PROFILES_DIR, exist_ok=True)


# ========================== Profile CRUD ==========================

def _load_custom_profiles() -> Dict[str, Any]:
    if not os.path.isfile(_CUSTOM_PROFILES_FILE):
        return {}
    try:
        with open(_CUSTOM_PROFILES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_custom_profiles(data: Dict[str, Any]) -> None:
    _ensure_profiles_dir()
    tmp = _CUSTOM_PROFILES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _CUSTOM_PROFILES_FILE)


def list_profiles() -> List[Dict[str, Any]]:
    result = []
    for p in BUILTIN_PROFILES.values():
        result.append(dict(p))
    with _lock:
        custom = _load_custom_profiles()
    for name, p in custom.items():
        entry = dict(p)
        entry["builtin"] = False
        entry.setdefault("name", name)
        result.append(entry)
    return result


def get_profile(name: str) -> Optional[Dict[str, Any]]:
    if name in BUILTIN_PROFILES:
        return dict(BUILTIN_PROFILES[name])
    with _lock:
        custom = _load_custom_profiles()
    p = custom.get(name)
    if p:
        entry = dict(p)
        entry["builtin"] = False
        entry.setdefault("name", name)
        return entry
    return None


def create_profile(name: str, definition: Dict[str, Any]) -> Dict[str, Any]:
    if name in BUILTIN_PROFILES:
        return {"success": False, "error": f"'{name}' 与内置 profile 同名，不允许"}
    with _lock:
        custom = _load_custom_profiles()
        if name in custom:
            return {"success": False, "error": f"profile '{name}' 已存在"}
        definition["name"] = name
        definition["builtin"] = False
        custom[name] = definition
        _save_custom_profiles(custom)
    return {"success": True, "message": f"profile '{name}' 创建成功"}


def update_profile(name: str, definition: Dict[str, Any]) -> Dict[str, Any]:
    if name in BUILTIN_PROFILES:
        return {"success": False, "error": f"内置 profile '{name}' 不可修改"}
    with _lock:
        custom = _load_custom_profiles()
        if name not in custom:
            return {"success": False, "error": f"profile '{name}' 不存在"}
        definition["name"] = name
        definition["builtin"] = False
        custom[name] = definition
        _save_custom_profiles(custom)
    return {"success": True, "message": f"profile '{name}' 更新成功"}


def delete_profile(name: str) -> Dict[str, Any]:
    if name in BUILTIN_PROFILES:
        return {"success": False, "error": f"内置 profile '{name}' 不可删除"}
    with _lock:
        custom = _load_custom_profiles()
        if name not in custom:
            return {"success": False, "error": f"profile '{name}' 不存在"}
        del custom[name]
        _save_custom_profiles(custom)
    return {"success": True, "message": f"profile '{name}' 已删除"}


def get_profile_allowed_tools(profile_name: str) -> Optional[List[str]]:
    """根据 profile 返回允许的 tool name 列表（Phase 3 可见性过滤使用）"""
    p = get_profile(profile_name)
    if not p:
        return None
    mcp_cfg = p.get("mcp_tools", {})
    cats = mcp_cfg.get("include_categories", [])
    tools: List[str] = []
    for cat in cats:
        tools.extend(TOOL_CATEGORIES.get(cat, []))
    extra = mcp_cfg.get("extra_tools", [])
    tools.extend(extra)
    return list(dict.fromkeys(tools))


# ========================== Access Grant 记录 ==========================

def _load_access_grants() -> Dict[str, Any]:
    if not os.path.isfile(_ACCESS_GRANTS_FILE):
        return {}
    try:
        with open(_ACCESS_GRANTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_access_grants(data: Dict[str, Any]) -> None:
    _ensure_profiles_dir()
    os.makedirs(os.path.dirname(_ACCESS_GRANTS_FILE), exist_ok=True)
    tmp = _ACCESS_GRANTS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _ACCESS_GRANTS_FILE)


def record_access_grant(
    user_id: str,
    cluster: str,
    namespace: str,
    profile: str,
) -> Dict[str, Any]:
    """记录一条用户权限授权，同一 cluster+namespace 只保留最新 active 记录"""
    import time
    grant = {
        "cluster": cluster,
        "namespace": namespace,
        "profile": profile,
        "granted_at": int(time.time()),
        "status": "active",
    }
    with _lock:
        data = _load_access_grants()
        user_grants = data.setdefault(user_id, [])
        data[user_id] = [
            g for g in user_grants
            if not (g.get("cluster") == cluster and g.get("namespace") == namespace)
        ]
        data[user_id].append(grant)
        if not data[user_id]:
            data.pop(user_id, None)
        _save_access_grants(data)
    return grant


def revoke_access_grant(
    user_id: str,
    cluster: str,
    namespace: str,
) -> bool:
    """撤销用户在某集群/namespace 的权限授权，直接移除记录"""
    with _lock:
        data = _load_access_grants()
        user_grants = data.get(user_id, [])
        new_grants = [
            g for g in user_grants
            if not (g.get("cluster") == cluster and g.get("namespace") == namespace)
        ]
        if len(new_grants) == len(user_grants):
            return False
        if new_grants:
            data[user_id] = new_grants
        else:
            data.pop(user_id, None)
        _save_access_grants(data)
    return True


def get_user_access_grants(user_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
    """获取用户的权限授权列表"""
    with _lock:
        data = _load_access_grants()
    grants = data.get(user_id, [])
    if active_only:
        return [g for g in grants if g.get("status") == "active"]
    return list(grants)


def get_k8s_rbac_template_rules(profile_name: str) -> Optional[List[Dict]]:
    """获取 profile 对应的 K8s RBAC 规则（来自 rbac_advanced_mixin 的模板定义）"""
    p = get_profile(profile_name)
    if not p:
        return None
    k8s_cfg = p.get("k8s_rbac", {})
    template_name = k8s_cfg.get("role_template")
    if not template_name:
        return None
    from services.k8s_advanced.rbac_advanced import RbacAdvancedMixin
    mixin = RbacAdvancedMixin()
    rules = mixin._get_role_template_rules(template_name)
    return rules if rules else None


def get_k8s_cluster_rbac_template_rules(profile_name: str) -> Optional[List[Dict]]:
    """获取 profile 对应的 ClusterRole 规则（集群级资源，如 nodes、metrics）。
    返回 None 或空列表表示该 profile 不需要 ClusterRole。
    """
    p = get_profile(profile_name)
    if not p:
        return None
    k8s_cfg = p.get("k8s_rbac", {})
    template_name = k8s_cfg.get("role_template")
    if not template_name:
        return None
    from services.k8s_advanced.rbac_advanced import RbacAdvancedMixin
    mixin = RbacAdvancedMixin()
    rules = mixin._get_cluster_role_template_rules(template_name)
    return rules if rules else None
