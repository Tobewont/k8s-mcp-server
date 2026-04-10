"""
认证与用户管理工具
- whoami: 所有已认证用户可用
- admin_manage_users: admin 全功能；operator 限 viewer/developer 权限和 user 角色 token
- admin_manage_profiles: 仅 admin 可用
"""
from __future__ import annotations

import os
import re
import time
import yaml
from typing import Optional

from config import MCP_AUTH_ENABLED, MCP_TOKEN_MAX_EXPIRY, get_user_data_root
from utils.auth_context import current_jti, current_role, current_user_id
from utils.cluster_config import ClusterConfigManager, ClusterInfo, resolve_kubeconfig_path
from utils.decorators import handle_tool_errors
from utils.jwt_service import ROLE_ADMIN, ROLE_USER, issue_token
from utils.permission_profiles import (
    OPERATOR_GRANTABLE_PROFILES,
    RESERVED_CATEGORIES,
    TOOL_CATEGORIES,
    create_profile,
    delete_profile,
    get_k8s_cluster_rbac_template_rules,
    get_k8s_rbac_template_rules,
    get_profile,
    get_profile_allowed_tools,
    get_user_access_grants,
    list_profiles,
    record_access_grant,
    revoke_access_grant,
    update_profile,
)
from utils.operations_logger import log_operation
from utils.response import json_error, json_success
from utils.revocation_store import revoke_jti, revoke_jtis_bulk
from utils.token_store import (
    get_grant_by_jti,
    get_user_grants,
    list_all_users,
    mark_grant_revoked,
    mark_user_all_revoked,
    record_grant,
)

from . import mcp


# ========================== whoami ==========================

@mcp.tool()
@handle_tool_errors
async def whoami() -> str:
    """查看当前用户身份信息（用户 ID、角色、Token 有效期、已授权的集群与权限）

    Returns:
        当前用户身份与授权摘要
    """
    if not MCP_AUTH_ENABLED:
        return json_success({
            "auth_enabled": False,
            "message": "未启用认证，当前为匿名模式",
        })

    uid = current_user_id.get()
    role = current_role.get()
    jti = current_jti.get()

    if not uid:
        return json_error("无法获取用户身份（未携带有效 JWT）")

    now = int(time.time())
    grants = get_user_grants(uid)
    active_grants = [
        g for g in grants
        if g.get("status") == "active" and g.get("expires_at", 0) > now
    ]

    current_grant = None
    for g in grants:
        if g.get("jti") == jti:
            current_grant = g
            break

    remaining = None
    if current_grant and current_grant.get("expires_at"):
        remaining = max(0, current_grant["expires_at"] - now)

    access = get_user_access_grants(uid, active_only=True)
    access_summary = [
        {
            "cluster": a["cluster"],
            "namespace": a["namespace"],
            "profile": a["profile"],
            "user_cluster_name": f"{a['cluster']}-{a['namespace']}",
        }
        for a in access
    ]

    return json_success({
        "user_id": uid,
        "role": role,
        "jti": jti,
        "token_remaining_seconds": remaining,
        "active_token_grants": len(active_grants),
        "access_grants": access_summary,
        "hint": "使用 access_grants 中的 user_cluster_name 作为 cluster_name 参数来操作对应集群" if access_summary else None,
    })


# ========================== helpers ==========================

_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,252}$")
_UNSAFE_CLUSTER_NAME_CHARS = set('/\\:*?"<>|')


def _validate_identifier(value: str, label: str) -> Optional[str]:
    """校验 K8s 标识符（user_id / namespace / profile）格式安全性。
    返回 None 表示合法，否则返回错误描述。
    仅允许 ASCII 字母、数字、连字符、下划线、点（K8s 资源名称要求）。
    """
    if not value or not isinstance(value, str):
        return f"{label} 不能为空"
    if ".." in value or "/" in value or "\\" in value:
        return f"{label} 包含非法字符（不允许 .. / \\）"
    if not _SAFE_ID_RE.match(value):
        return f"{label} 格式无效（只允许字母、数字、连字符、下划线、点，长度 1-253）"
    return None


def _validate_cluster_name(value: str) -> Optional[str]:
    """校验集群名称（宽松模式，支持中文等 Unicode）。
    集群名称由用户在 import_cluster 时自定义，允许 Unicode 字符，
    仅禁止路径分隔符和文件系统特殊字符，防止路径穿越。
    """
    if not value or not isinstance(value, str) or not value.strip():
        return "cluster_name 不能为空"
    if ".." in value:
        return "cluster_name 包含非法字符（不允许 ..）"
    if any(c in value for c in _UNSAFE_CLUSTER_NAME_CHARS):
        return "cluster_name 不能包含路径分隔符或特殊字符（/ \\ : * ? \" < > |）"
    return None


def _require_admin() -> Optional[str]:
    """检查当前用户是否为 admin，不是则返回错误消息"""
    if not MCP_AUTH_ENABLED:
        return "未启用认证（MCP_AUTH_ENABLED=false）"
    if current_role.get() != ROLE_ADMIN:
        return "权限不足：仅管理员可执行此操作"
    return None


def _caller_has_operator_profile() -> bool:
    """当前用户的 profile 是否实际包含 user_manage 工具分类（基于分类而非名字判断）"""
    uid = current_user_id.get()
    if not uid:
        return False
    grants = get_user_access_grants(uid, active_only=True)
    for g in grants:
        pname = g.get("profile", "")
        tools = get_profile_allowed_tools(pname)
        if tools and "admin_manage_users" in tools:
            return True
    return False


def _require_manager() -> Optional[str]:
    """检查当前用户是否为 admin（JWT role）或 operator（profile），不是则返回错误消息"""
    if not MCP_AUTH_ENABLED:
        return "未启用认证（MCP_AUTH_ENABLED=false）"
    if current_role.get() == ROLE_ADMIN:
        return None
    if _caller_has_operator_profile():
        return None
    return "权限不足：需要 admin 或 operator 角色"


def _caller_is_operator() -> bool:
    """当前调用者是 operator（非 admin JWT role）"""
    return current_role.get() != ROLE_ADMIN


def _user_has_elevated_grants(uid: str) -> bool:
    """用户是否拥有 operator/admin 级别的权限授权"""
    grants = get_user_access_grants(uid, active_only=True)
    for g in grants:
        if g.get("profile") not in OPERATOR_GRANTABLE_PROFILES:
            return True
    return False


def _user_has_admin_tokens(uid: str) -> bool:
    """用户是否持有未过期且未撤销的 admin 角色 token（同时检查撤销表）"""
    from utils.revocation_store import is_revoked
    now = int(time.time())
    for g in get_user_grants(uid):
        if (g.get("role") == ROLE_ADMIN
                and g.get("status") == "active"
                and g.get("expires_at", 0) > now
                and not is_revoked(g.get("jti", ""))):
            return True
    return False


def _resolve_management_kubeconfig(
    cluster_name: str,
    kubeconfig_path: Optional[str] = None,
    is_operator: bool = False,
) -> Optional[str]:
    """解析 RBAC 管理操作需要的高权限 kubeconfig。

    admin 调用：正常解析（支持 kubeconfig_path）。
    operator 调用：忽略 kubeconfig_path，总是从 admin 用户的集群配置解析，
    因为 operator 自身的 kubeconfig 通常不具备创建 SA/Role/RoleBinding 的权限。
    admin 需要预先导入目标集群的高权限 kubeconfig，operator 的 grant_access 才能成功。
    """
    import logging
    _logger = logging.getLogger(__name__)

    if not is_operator:
        return resolve_kubeconfig_path(cluster_name, kubeconfig_path)

    if kubeconfig_path:
        _logger.info(
            "operator 调用管理操作，忽略用户指定的 kubeconfig_path=%s，改用 admin 集群配置",
            kubeconfig_path,
        )
    admin_root = get_user_data_root("admin")
    admin_mgr = ClusterConfigManager(base_dir=admin_root)
    try:
        cluster = admin_mgr.get_cluster(cluster_name)
        if cluster:
            _logger.info("operator 管理操作使用 admin kubeconfig: cluster=%s", cluster_name)
            return cluster.kubeconfig_path
        _logger.warning("admin 用户未导入集群 '%s'，operator 管理操作无法执行", cluster_name)
        return None
    except ValueError:
        _logger.warning("admin 用户集群配置中未找到 '%s'", cluster_name)
        return None


# ========================== admin_manage_users ==========================

@mcp.tool()
@handle_tool_errors
async def admin_manage_users(
    action: str,
    user_id: Optional[str] = None,
    role: Optional[str] = None,
    expires_in_seconds: Optional[int] = None,
    jti: Optional[str] = None,
    cluster_name: Optional[str] = None,
    namespace: Optional[str] = None,
    profile: Optional[str] = None,
    kubeconfig_path: Optional[str] = None,
) -> str:
    """用户与 Token 管理（admin 全功能；operator 限 viewer/developer 权限和 user 角色 token）

    Args:
        action: 操作类型，支持：
            - issue_token: 为用户签发 JWT（需 user_id，可选 role/expires_in_seconds）
            - revoke_token: 按 jti 撤销单个 token（需 jti）
            - revoke_user: 撤销某用户全部 token（需 user_id）
            - list_users: 列出所有已签发用户及 token 状态摘要
            - get_user: 查看某用户的全部签发记录与权限授权（需 user_id）
            - grant_access: 为用户分配集群/命名空间权限（需 user_id/cluster_name/namespace/profile，自动在 K8s 创建 Role+RoleBinding+SA）
            - revoke_access: 撤销用户的集群/命名空间权限（需 user_id/cluster_name/namespace，自动清理 K8s 资源）
            - inspect: 查看用户在 K8s 中的实际 ServiceAccount 权限（需 user_id/cluster_name/namespace）
        user_id: 用户标识
        role: 角色 user/admin（仅 issue_token，operator 调用时只能为 user）
        expires_in_seconds: Token 有效期秒数（仅 issue_token，默认 86400，最小 60）
        jti: Token 的 jti（仅 revoke_token）
        cluster_name: 集群名称（grant_access/revoke_access/inspect）
        namespace: 命名空间（grant_access/revoke_access/inspect）
        profile: 权限 Profile 名称（仅 grant_access；operator 调用时只能为 viewer/developer）
        kubeconfig_path: kubeconfig 路径（可选，不指定则使用 cluster_name 对应的配置）

    Returns:
        操作结果
    """
    err = _require_manager()
    if err:
        return json_error(err)

    is_op = _caller_is_operator()

    # ---------- issue_token ----------
    if action == "issue_token":
        id_err = _validate_identifier(user_id or "", "user_id")
        if id_err:
            return json_error(f"issue_token: {id_err}")
        if is_op and user_id == current_user_id.get():
            return json_error("operator 不能为自己签发 token")
        if is_op and (_user_has_admin_tokens(user_id) or _user_has_elevated_grants(user_id)):
            return json_error("operator 不能为拥有 operator/admin 权限的用户签发 token")
        r = role or ROLE_USER
        if r not in (ROLE_USER, ROLE_ADMIN):
            return json_error("role 只能是 user 或 admin")
        if is_op and r != ROLE_USER:
            return json_error("operator 只能签发 role=user 的 token")
        exp = expires_in_seconds if expires_in_seconds is not None else 86400
        if exp < 60:
            return json_error("expires_in_seconds 至少 60")
        if exp > MCP_TOKEN_MAX_EXPIRY:
            return json_error(f"expires_in_seconds 不能超过 {MCP_TOKEN_MAX_EXPIRY}（{MCP_TOKEN_MAX_EXPIRY // 86400} 天）")
        token_str, new_jti = issue_token(user_id, r, exp)
        record_grant(user_id, new_jti, r, exp)
        log_operation("admin_manage_users", "issue_token", {
            "target_user": user_id, "role": r, "jti": new_jti, "expires_in": exp,
        }, True)
        return json_success({
            "action": "issue_token",
            "token": token_str,
            "jti": new_jti,
            "user_id": user_id,
            "role": r,
            "expires_in_seconds": exp,
        })

    # ---------- revoke_token ----------
    if action == "revoke_token":
        if not jti or not isinstance(jti, str):
            return json_error("revoke_token 需要 jti")
        if is_op:
            grant_record = get_grant_by_jti(jti)
            if not grant_record:
                return json_error("operator 只能撤销已知签发记录中的 token")
            if grant_record.get("role") == ROLE_ADMIN:
                return json_error("operator 无权撤销 admin 角色的 token")
            target_uid = grant_record.get("user_id")
            if target_uid and (_user_has_admin_tokens(target_uid) or _user_has_elevated_grants(target_uid)):
                return json_error("operator 无权撤销拥有 operator/admin 权限的用户的 token")
        revoke_jti(jti)
        found_uid = mark_grant_revoked(jti)
        log_operation("admin_manage_users", "revoke_token", {
            "jti": jti, "target_user": found_uid,
        }, True)
        return json_success({
            "action": "revoke_token",
            "jti": jti,
            "user_id": found_uid,
            "message": "已撤销",
        })

    # ---------- revoke_user ----------
    if action == "revoke_user":
        id_err = _validate_identifier(user_id or "", "user_id")
        if id_err:
            return json_error(f"revoke_user: {id_err}")
        if is_op and (_user_has_admin_tokens(user_id) or _user_has_elevated_grants(user_id)):
            return json_error("operator 无权撤销拥有 operator/admin 权限的用户")
        revoked_jtis = mark_user_all_revoked(user_id)
        revoke_jtis_bulk(revoked_jtis)
        log_operation("admin_manage_users", "revoke_user", {
            "target_user": user_id, "revoked_count": len(revoked_jtis),
        }, True)
        return json_success({
            "action": "revoke_user",
            "user_id": user_id,
            "revoked_count": len(revoked_jtis),
            "revoked_jtis": revoked_jtis,
        })

    # ---------- list_users ----------
    if action == "list_users":
        users = list_all_users()
        if is_op:
            users = [u for u in users if not _user_has_admin_tokens(u["user_id"])
                     and not _user_has_elevated_grants(u["user_id"])]
        return json_success({
            "action": "list_users",
            "users": users,
            "count": len(users),
        })

    # ---------- get_user ----------
    if action == "get_user":
        id_err = _validate_identifier(user_id or "", "user_id")
        if id_err:
            return json_error(f"get_user: {id_err}")
        if is_op and (_user_has_admin_tokens(user_id) or _user_has_elevated_grants(user_id)):
            return json_error("operator 无权查看拥有 operator/admin 权限的用户")
        token_grants = get_user_grants(user_id)
        now = int(time.time())
        for g in token_grants:
            exp_at = g.get("expires_at", 0)
            if g.get("status") == "active" and exp_at <= now:
                g["_effective_status"] = "expired"
            else:
                g["_effective_status"] = g.get("status", "unknown")
        access = get_user_access_grants(user_id, active_only=False)
        return json_success({
            "action": "get_user",
            "user_id": user_id,
            "token_grants": token_grants,
            "access_grants": access,
        })

    # ---------- grant_access ----------
    if action == "grant_access":
        for _lbl, _val in [("user_id", user_id), ("namespace", namespace), ("profile", profile)]:
            id_err = _validate_identifier(_val or "", _lbl)
            if id_err:
                return json_error(f"grant_access: {id_err}")
        cn_err = _validate_cluster_name(cluster_name or "")
        if cn_err:
            return json_error(f"grant_access: {cn_err}")
        if is_op and user_id == current_user_id.get():
            return json_error("operator 不能为自己分配权限")
        if is_op and profile not in OPERATOR_GRANTABLE_PROFILES:
            return json_error(
                f"operator 只能分配以下 profile: {', '.join(sorted(OPERATOR_GRANTABLE_PROFILES))}"
            )
        p = get_profile(profile)
        if not p:
            return json_error(f"profile '{profile}' 不存在，请先创建或使用内置 profile")
        rules = get_k8s_rbac_template_rules(profile)
        if not rules:
            return json_error(f"profile '{profile}' 未关联 K8s RBAC 模板规则")

        effective_path = _resolve_management_kubeconfig(cluster_name, kubeconfig_path, is_operator=is_op)
        if not effective_path:
            return json_error(
                f"无法解析集群 '{cluster_name}' 的管理用 kubeconfig，"
                "请确认 admin 用户已导入该集群配置"
            )
        sa_name = f"mcp-{user_id}"
        role_name = f"mcp-{user_id}-{profile}"
        rb_name = f"mcp-{user_id}-{profile}-binding"

        try:
            from kubernetes import client as k8s_client
            from services.factory import get_k8s_api_service
            svc = get_k8s_api_service(effective_path)

            # 1) 创建 ServiceAccount（若不存在）
            try:
                svc.v1_api.read_namespaced_service_account(name=sa_name, namespace=namespace)
            except Exception:
                svc.v1_api.create_namespaced_service_account(
                    namespace=namespace,
                    body=k8s_client.V1ServiceAccount(
                        metadata=k8s_client.V1ObjectMeta(
                            name=sa_name,
                            labels={"managed-by": "k8s-mcp-server", "mcp-user": user_id},
                        )
                    ),
                )

            # 2) 创建或更新 Role
            # 直接使用 K8s API，绕过 _execute_with_validation_and_preview
            # 原因：验证层会在 Role 已存在时静默返回 error dict 而非抛异常，
            # 导致 update_role 永远不会被调用，Role 规则永远不会更新。
            role_rules = [
                k8s_client.V1PolicyRule(
                    api_groups=r.get("api_groups", []),
                    resources=r.get("resources", []),
                    verbs=r.get("verbs", []),
                )
                for r in rules
            ]
            role_body = k8s_client.V1Role(
                metadata=k8s_client.V1ObjectMeta(
                    name=role_name,
                    namespace=namespace,
                    labels={"managed-by": "k8s-mcp-server", "mcp-user": user_id},
                ),
                rules=role_rules,
            )
            try:
                svc.rbac_v1_api.create_namespaced_role(namespace=namespace, body=role_body)
            except Exception as e:
                if "AlreadyExists" in str(e) or "already exists" in str(e):
                    svc.rbac_v1_api.replace_namespaced_role(
                        name=role_name, namespace=namespace, body=role_body
                    )
                else:
                    raise

            # 3) 创建 RoleBinding（若已存在则跳过）
            rb_body = k8s_client.V1RoleBinding(
                metadata=k8s_client.V1ObjectMeta(
                    name=rb_name,
                    namespace=namespace,
                    labels={"managed-by": "k8s-mcp-server", "mcp-user": user_id},
                ),
                role_ref=k8s_client.V1RoleRef(
                    api_group="rbac.authorization.k8s.io",
                    kind="Role",
                    name=role_name,
                ),
                subjects=[k8s_client.RbacV1Subject(
                    kind="ServiceAccount",
                    name=sa_name,
                    api_group="",
                    namespace=namespace,
                )],
            )
            try:
                svc.rbac_v1_api.create_namespaced_role_binding(namespace=namespace, body=rb_body)
            except Exception as e:
                if "AlreadyExists" not in str(e) and "already exists" not in str(e):
                    raise

            # 3.5) 创建 ClusterRole + ClusterRoleBinding（若 profile 需要集群级权限）
            # ClusterRole 按 user+profile 共享；CRB 按 user+profile+namespace 独立
            # 因为 CRB subjects 引用的 SA 是 namespace-scoped 的
            cluster_rules = get_k8s_cluster_rbac_template_rules(profile)
            cr_name = f"mcp-{user_id}-{profile}-cluster"
            crb_name = f"mcp-{user_id}-{profile}-{namespace}-cluster-binding"
            if cluster_rules:
                cr_rules = []
                for rule in cluster_rules:
                    cr_rules.append(k8s_client.V1PolicyRule(
                        api_groups=rule.get("api_groups", []),
                        resources=rule.get("resources", []),
                        verbs=rule.get("verbs", []),
                    ))
                cr_body = k8s_client.V1ClusterRole(
                    metadata=k8s_client.V1ObjectMeta(
                        name=cr_name,
                        labels={"managed-by": "k8s-mcp-server", "mcp-user": user_id},
                    ),
                    rules=cr_rules,
                )
                try:
                    svc.rbac_v1_api.create_cluster_role(body=cr_body)
                except Exception as e:
                    if "AlreadyExists" in str(e) or "already exists" in str(e):
                        svc.rbac_v1_api.replace_cluster_role(name=cr_name, body=cr_body)
                    else:
                        raise
                try:
                    svc.rbac_v1_api.create_cluster_role_binding(
                        body=k8s_client.V1ClusterRoleBinding(
                            metadata=k8s_client.V1ObjectMeta(
                                name=crb_name,
                                labels={
                                    "managed-by": "k8s-mcp-server",
                                    "mcp-user": user_id,
                                    "mcp-namespace": namespace,
                                },
                            ),
                            role_ref=k8s_client.V1RoleRef(
                                api_group="rbac.authorization.k8s.io",
                                kind="ClusterRole",
                                name=cr_name,
                            ),
                            subjects=[k8s_client.RbacV1Subject(
                                kind="ServiceAccount",
                                name=sa_name,
                                api_group="",
                                namespace=namespace,
                            )],
                        )
                    )
                except Exception as e:
                    if "AlreadyExists" not in str(e) and "already exists" not in str(e):
                        raise

            # 4) 获取 SA Token
            # 策略：先删旧 Secret 再创建，确保 token 与当前 SA 匹配
            # （revoke 后 re-grant、或手动删除 SA 再 re-grant 时旧 Secret 的 token 无效）
            sa_token = None
            token_errors = []
            import base64 as _b64
            import asyncio

            secret_name = f"{sa_name}-token"
            # 删除已存在的旧 Secret（如果有），避免读到旧 SA 的无效 token
            try:
                svc.v1_api.delete_namespaced_secret(name=secret_name, namespace=namespace)
            except Exception:
                pass
            # 创建新 Secret，让 K8s token controller 为当前 SA 填充 token
            try:
                svc.v1_api.create_namespaced_secret(
                    namespace=namespace,
                    body=k8s_client.V1Secret(
                        metadata=k8s_client.V1ObjectMeta(
                            name=secret_name,
                            annotations={"kubernetes.io/service-account.name": sa_name},
                        ),
                        type="kubernetes.io/service-account-token",
                    ),
                )
            except Exception:
                pass
            # 等待 token controller 填充 token（带重试）
            for _retry in range(5):
                await asyncio.sleep(1)
                try:
                    sec = svc.v1_api.read_namespaced_secret(name=secret_name, namespace=namespace)
                    if sec.data and sec.data.get("token"):
                        sa_token = _b64.b64decode(sec.data["token"]).decode()
                        break
                except Exception as e:
                    token_errors.append(f"Secret(attempt {_retry + 1}): {e}")

            # Secret 方式失败时，回退到 TokenRequest API
            if not sa_token:
                try:
                    token_req = k8s_client.AuthenticationV1TokenRequest(
                        spec=k8s_client.V1TokenRequestSpec(
                            expiration_seconds=365 * 24 * 3600,
                        )
                    )
                    token_resp = svc.v1_api.create_namespaced_service_account_token(
                        name=sa_name, namespace=namespace, body=token_req
                    )
                    sa_token = token_resp.status.token
                except Exception as e2:
                    token_errors.append(f"TokenRequest: {e2}")

            # 5) 生成用户 kubeconfig 并失效旧的服务缓存
            user_kubeconfig_path = None
            kc_error = None
            if sa_token and effective_path:
                try:
                    with open(effective_path, "r", encoding="utf-8") as f:
                        admin_kc = yaml.safe_load(f)
                    cluster_entry = (admin_kc.get("clusters") or [{}])[0].get("cluster", {})
                    server = cluster_entry.get("server", "")
                    ca_data = cluster_entry.get("certificate-authority-data", "")
                    skip_tls = cluster_entry.get("insecure-skip-tls-verify", False)

                    ctx_name = f"{sa_name}-{namespace}"
                    cluster_def = {"server": server}
                    if ca_data:
                        cluster_def["certificate-authority-data"] = ca_data
                    if skip_tls:
                        cluster_def["insecure-skip-tls-verify"] = True

                    user_kc = {
                        "apiVersion": "v1",
                        "kind": "Config",
                        "clusters": [{"name": ctx_name, "cluster": cluster_def}],
                        "users": [{"name": sa_name, "user": {"token": sa_token}}],
                        "contexts": [{
                            "name": ctx_name,
                            "context": {"cluster": ctx_name, "user": sa_name, "namespace": namespace},
                        }],
                        "current-context": ctx_name,
                    }

                    user_data_root = get_user_data_root(user_id)
                    user_mgr = ClusterConfigManager(base_dir=user_data_root)
                    kc_name = f"{cluster_name}-{namespace}"
                    user_kubeconfig_path = user_mgr.save_kubeconfig(kc_name, yaml.dump(user_kc, allow_unicode=True))

                    ci = ClusterInfo(
                        name=kc_name,
                        kubeconfig_path=user_kubeconfig_path,
                        service_account=sa_name,
                        namespace=namespace,
                        is_default=not user_mgr.list_clusters(),
                    )
                    if not user_mgr.add_cluster(ci):
                        user_mgr.update_cluster(ci)

                    # 失效该用户的 K8s 服务缓存，确保下次请求使用新 token
                    from services.factory import invalidate_user_service_cache
                    invalidate_user_service_cache(user_id)
                except Exception as e:
                    kc_error = str(e)
            elif not sa_token:
                kc_error = f"无法获取 SA Token: {'; '.join(token_errors)}"
            elif not effective_path:
                kc_error = "无法解析管理员 kubeconfig 路径"

            record_access_grant(user_id, cluster_name, namespace, profile)
            log_operation("admin_manage_users", "grant_access", {
                "target_user": user_id, "cluster": cluster_name,
                "namespace": namespace, "profile": profile,
            }, True)

            k8s_res = {
                "service_account": sa_name,
                "role": role_name,
                "role_binding": rb_name,
            }
            if cluster_rules:
                k8s_res["cluster_role"] = cr_name
                k8s_res["cluster_role_binding"] = crb_name
            result_data = {
                "action": "grant_access",
                "user_id": user_id,
                "cluster": cluster_name,
                "namespace": namespace,
                "profile": profile,
                "k8s_resources": k8s_res,
                "message": f"已为 {user_id} 在 {cluster_name}/{namespace} 分配 {profile} 权限",
            }
            if user_kubeconfig_path:
                result_data["user_kubeconfig"] = user_kubeconfig_path
                result_data["user_cluster_name"] = f"{cluster_name}-{namespace}"
            else:
                result_data["warning"] = f"未能自动生成用户 kubeconfig: {kc_error}"

            return json_success(result_data)
        except Exception as e:
            return json_error(f"grant_access 失败: {e}")

    # ---------- revoke_access ----------
    if action == "revoke_access":
        for _lbl, _val in [("user_id", user_id), ("namespace", namespace)]:
            id_err = _validate_identifier(_val or "", _lbl)
            if id_err:
                return json_error(f"revoke_access: {id_err}")
        cn_err = _validate_cluster_name(cluster_name or "")
        if cn_err:
            return json_error(f"revoke_access: {cn_err}")
        if is_op:
            existing = get_user_access_grants(user_id, active_only=True)
            match = [g for g in existing
                     if g.get("cluster") == cluster_name and g.get("namespace") == namespace]
            if match and match[0].get("profile") not in OPERATOR_GRANTABLE_PROFILES:
                return json_error(
                    f"operator 无权撤销 {match[0].get('profile')} 级别的权限，"
                    f"仅可操作: {', '.join(sorted(OPERATOR_GRANTABLE_PROFILES))}"
                )

        effective_path = _resolve_management_kubeconfig(cluster_name, kubeconfig_path, is_operator=is_op)
        if not effective_path:
            return json_error(
                f"无法解析集群 '{cluster_name}' 的管理用 kubeconfig，"
                "请确认 admin 用户已导入该集群配置"
            )
        sa_name = f"mcp-{user_id}"
        cleaned = []
        errors = []

        try:
            from services.factory import get_k8s_api_service
            svc = get_k8s_api_service(effective_path)

            # 查找并删除该用户的 RoleBinding
            try:
                rbs = await svc.list_role_bindings(namespace)
                for rb in rbs:
                    subjects = rb.get("subjects") or []
                    for s in subjects:
                        if s.get("kind") == "ServiceAccount" and s.get("name") == sa_name:
                            try:
                                svc.rbac_v1_api.delete_namespaced_role_binding(
                                    name=rb["name"], namespace=namespace
                                )
                                cleaned.append(f"RoleBinding/{rb['name']}")
                            except Exception as e2:
                                errors.append(f"删除 RoleBinding/{rb['name']} 失败: {e2}")
                            # 同时尝试删除关联的 Role
                            role_ref = rb.get("role_ref", {})
                            if role_ref.get("kind") == "Role" and role_ref.get("name", "").startswith(f"mcp-{user_id}"):
                                try:
                                    svc.rbac_v1_api.delete_namespaced_role(
                                        name=role_ref["name"], namespace=namespace
                                    )
                                    cleaned.append(f"Role/{role_ref['name']}")
                                except Exception:
                                    pass
            except Exception as e:
                errors.append(f"查询 RoleBinding 失败: {e}")

            # 清理该用户在此 namespace 的 ClusterRoleBinding，
            # 仅当用户无其他同类 CRB 时才删除共享的 ClusterRole
            try:
                all_crbs = svc.rbac_v1_api.list_cluster_role_binding(
                    label_selector=f"managed-by=k8s-mcp-server,mcp-user={user_id}"
                )
                deleted_cr_refs = set()
                remaining_cr_refs = set()
                for crb in all_crbs.items:
                    labels = crb.metadata.labels or {}
                    if labels.get("mcp-namespace") == namespace:
                        try:
                            svc.rbac_v1_api.delete_cluster_role_binding(name=crb.metadata.name)
                            cleaned.append(f"ClusterRoleBinding/{crb.metadata.name}")
                            if crb.role_ref:
                                deleted_cr_refs.add(crb.role_ref.name)
                        except Exception as e2:
                            errors.append(f"删除 ClusterRoleBinding/{crb.metadata.name} 失败: {e2}")
                    else:
                        if crb.role_ref:
                            remaining_cr_refs.add(crb.role_ref.name)
                for cr_name_to_delete in deleted_cr_refs - remaining_cr_refs:
                    try:
                        svc.rbac_v1_api.delete_cluster_role(name=cr_name_to_delete)
                        cleaned.append(f"ClusterRole/{cr_name_to_delete}")
                    except Exception:
                        pass
            except Exception as e:
                errors.append(f"查询 ClusterRoleBinding 失败: {e}")

            # 删除 Token Secret（grant_access 创建的）
            try:
                svc.v1_api.delete_namespaced_secret(name=f"{sa_name}-token", namespace=namespace)
                cleaned.append(f"Secret/{sa_name}-token")
            except Exception:
                pass

            # 删除 ServiceAccount
            try:
                svc.v1_api.delete_namespaced_service_account(name=sa_name, namespace=namespace)
                cleaned.append(f"ServiceAccount/{sa_name}")
            except Exception:
                pass

        except Exception as e:
            errors.append(f"连接集群失败: {e}")

        revoke_access_grant(user_id, cluster_name, namespace)
        log_operation("admin_manage_users", "revoke_access", {
            "target_user": user_id, "cluster": cluster_name, "namespace": namespace,
        }, True)

        # 清理用户侧的 kubeconfig、集群配置、服务缓存
        try:
            user_data_root = get_user_data_root(user_id)
            user_mgr = ClusterConfigManager(base_dir=user_data_root)
            kc_name = f"{cluster_name}-{namespace}"
            kc_path = user_mgr.get_kubeconfig_path(kc_name)
            if user_mgr.remove_cluster(kc_name):
                cleaned.append(f"UserClusterConfig/{kc_name}")
            if kc_path and os.path.isfile(kc_path):
                os.remove(kc_path)
                cleaned.append(f"UserKubeconfig/{kc_name}")
        except Exception:
            pass

        # 失效该用户的服务缓存，防止旧 token 被后续请求复用
        try:
            from services.factory import invalidate_user_service_cache
            invalidate_user_service_cache(user_id)
        except Exception:
            pass

        return json_success({
            "action": "revoke_access",
            "user_id": user_id,
            "cluster": cluster_name,
            "namespace": namespace,
            "cleaned_k8s_resources": cleaned,
            "errors": errors if errors else None,
        })

    # ---------- inspect ----------
    if action == "inspect":
        for _lbl, _val in [("user_id", user_id), ("namespace", namespace)]:
            id_err = _validate_identifier(_val or "", _lbl)
            if id_err:
                return json_error(f"inspect: {id_err}")
        cn_err = _validate_cluster_name(cluster_name or "")
        if cn_err:
            return json_error(f"inspect: {cn_err}")

        effective_path = _resolve_management_kubeconfig(cluster_name, kubeconfig_path, is_operator=is_op)
        if not effective_path:
            return json_error(
                f"无法解析集群 '{cluster_name}' 的管理用 kubeconfig，"
                "请确认 admin 用户已导入该集群配置"
            )
        sa_name = f"mcp-{user_id}"

        try:
            from services.factory import get_k8s_advanced_service
            adv_svc = get_k8s_advanced_service(effective_path)
            result = await adv_svc.analyze_serviceaccount_permissions(sa_name, namespace)
            access = get_user_access_grants(user_id, active_only=True)
            cluster_access = [a for a in access if a.get("cluster") == cluster_name and a.get("namespace") == namespace]
            result["mcp_access_grant"] = cluster_access[0] if cluster_access else None
            return json_success({"action": "inspect", "user_id": user_id, **result})
        except Exception as e:
            return json_error(f"inspect 失败: {e}")

    return json_error(
        f"不支持的 action: {action}。"
        "支持: issue_token, revoke_token, revoke_user, list_users, get_user, "
        "grant_access, revoke_access, inspect"
    )


# ========================== admin_manage_profiles ==========================

@mcp.tool()
@handle_tool_errors
async def admin_manage_profiles(
    action: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    k8s_role_template: Optional[str] = None,
    mcp_tool_categories: Optional[str] = None,
    extra_tools: Optional[str] = None,
) -> str:
    """权限 Profile 模板管理（仅管理员可用）

    Args:
        action: 操作类型，支持：
            - list: 列出所有 profile（内置 + 自定义）
            - get: 查看某个 profile 详情（需 name）
            - create: 创建自定义 profile（需 name/description/k8s_role_template，可选 mcp_tool_categories/extra_tools）
            - update: 更新自定义 profile（需 name，其余同 create）
            - delete: 删除自定义 profile（需 name，内置不可删）
        name: Profile 名称
        description: Profile 描述（create/update）
        k8s_role_template: K8s RBAC 角色模板名称，支持 readonly/developer/deployer/operator/admin/monitor/debug（create/update）
        mcp_tool_categories: MCP 工具分类，逗号分隔，支持 read_basic/write_workload/pod_exec/cluster_manage/ops/cluster_ops/user_manage/profile_manage（create/update）
        extra_tools: 额外允许的 MCP 工具名，逗号分隔（create/update）

    Returns:
        操作结果
    """
    err = _require_admin()
    if err:
        return json_error(err)

    if action == "list":
        profiles = list_profiles()
        return json_success({
            "action": "list",
            "profiles": profiles,
            "count": len(profiles),
        })

    if action == "get":
        if not name:
            return json_error("get 需要 name")
        p = get_profile(name)
        if not p:
            return json_error(f"profile '{name}' 不存在")
        return json_success({"action": "get", "profile": p})

    if action == "create":
        if not name:
            return json_error("create 需要 name")
        if not description:
            return json_error("create 需要 description")
        if not k8s_role_template:
            return json_error("create 需要 k8s_role_template")
        cats = [c.strip() for c in (mcp_tool_categories or "read_basic").split(",") if c.strip()]
        invalid_cats = [c for c in cats if c not in TOOL_CATEGORIES]
        if invalid_cats:
            valid = ", ".join(sorted(TOOL_CATEGORIES.keys()))
            return json_error(f"无效的工具分类: {', '.join(invalid_cats)}。可用: {valid}")
        reserved_used = [c for c in cats if c in RESERVED_CATEGORIES]
        if reserved_used:
            return json_error(
                f"自定义 profile 不允许包含保留分类: {', '.join(reserved_used)}。"
                "这些分类仅限内置 profile 使用"
            )
        extras = [t.strip() for t in (extra_tools or "").split(",") if t.strip()]
        reserved_tools = {"admin_manage_users", "admin_manage_profiles"}
        forbidden_extras = [t for t in extras if t in reserved_tools]
        if forbidden_extras:
            return json_error(
                f"自定义 profile 不允许添加管理工具: {', '.join(forbidden_extras)}"
            )
        definition = {
            "description": description,
            "mcp_tools": {
                "include_categories": cats,
                "extra_tools": extras,
            },
            "k8s_rbac": {
                "role_template": k8s_role_template,
                "description": description,
            },
        }
        result = create_profile(name, definition)
        return json_success({"action": "create", **result})

    if action == "update":
        if not name:
            return json_error("update 需要 name")
        existing = get_profile(name)
        if not existing:
            return json_error(f"profile '{name}' 不存在")
        definition = dict(existing)
        if description:
            definition["description"] = description
        if k8s_role_template:
            definition.setdefault("k8s_rbac", {})["role_template"] = k8s_role_template
        if mcp_tool_categories is not None:
            cats = [c.strip() for c in mcp_tool_categories.split(",") if c.strip()]
            invalid_cats = [c for c in cats if c not in TOOL_CATEGORIES]
            if invalid_cats:
                valid = ", ".join(sorted(TOOL_CATEGORIES.keys()))
                return json_error(f"无效的工具分类: {', '.join(invalid_cats)}。可用: {valid}")
            reserved_used = [c for c in cats if c in RESERVED_CATEGORIES]
            if reserved_used:
                return json_error(
                    f"自定义 profile 不允许包含保留分类: {', '.join(reserved_used)}。"
                    "这些分类仅限内置 profile 使用"
                )
            definition.setdefault("mcp_tools", {})["include_categories"] = cats
        if extra_tools is not None:
            extras = [t.strip() for t in extra_tools.split(",") if t.strip()]
            reserved_tools = {"admin_manage_users", "admin_manage_profiles"}
            forbidden_extras = [t for t in extras if t in reserved_tools]
            if forbidden_extras:
                return json_error(
                    f"自定义 profile 不允许添加管理工具: {', '.join(forbidden_extras)}"
                )
            definition.setdefault("mcp_tools", {})["extra_tools"] = extras
        result = update_profile(name, definition)
        return json_success({"action": "update", **result})

    if action == "delete":
        if not name:
            return json_error("delete 需要 name")
        result = delete_profile(name)
        return json_success({"action": "delete", **result})

    return json_error(
        f"不支持的 action: {action}。支持: list, get, create, update, delete"
    )
