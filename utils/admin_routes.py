"""
管理 API：签发用户 token、撤销 jti、集群导入（需管理员 JWT，由中间件校验）
"""
from __future__ import annotations

import logging
import re
import time

from starlette.requests import Request
from starlette.responses import JSONResponse

from config import MCP_AUTH_ENABLED, MCP_TOKEN_MAX_EXPIRY
from utils.auth_context import current_user_id
from utils.extension_store import (
    cleanup_expired as cleanup_extensions,
    set_extension,
)
from utils.jwt_service import ROLE_ADMIN, ROLE_USER, issue_token
from utils.operations_logger import log_admin_api
from utils.revocation_store import cleanup_expired, list_revoked, revoke_jti, revoke_jtis_bulk
from utils.token_store import (
    get_grant_by_jti,
    get_user_active_jtis,
    get_user_grants,
    list_all_users,
    mark_grant_revoked,
    mark_user_all_revoked,
    record_grant,
)

logger = logging.getLogger(__name__)


_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,252}$")


def _caller_id() -> str:
    return current_user_id.get() or "unknown"


async def admin_issue_token(request: Request) -> JSONResponse:
    if not MCP_AUTH_ENABLED:
        return JSONResponse(
            {"error": "bad_request", "detail": "未启用 MCP_AUTH_ENABLED"},
            status_code=400,
        )
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "bad_request", "detail": "无效 JSON"}, status_code=400)

    user_id = body.get("user_id")
    if not user_id or not isinstance(user_id, str):
        return JSONResponse({"error": "bad_request", "detail": "缺少 user_id"}, status_code=400)
    if not _SAFE_ID_RE.match(user_id):
        return JSONResponse({"error": "bad_request", "detail": "user_id 格式无效"}, status_code=400)
    if user_id == "admin":
        return JSONResponse(
            {"error": "bad_request", "detail": "user_id 'admin' 系统保留，仅由 mcp-admin bootstrap 生成"},
            status_code=400,
        )

    role = body.get("role", "user")
    if role not in ("user", "admin"):
        return JSONResponse(
            {"error": "bad_request", "detail": "role 只能是 user 或 admin"},
            status_code=400,
        )

    try:
        expires_in = int(body.get("expires_in_seconds", 86400))
    except (TypeError, ValueError):
        return JSONResponse({"error": "bad_request", "detail": "expires_in_seconds 无效"}, status_code=400)
    if expires_in < 60:
        return JSONResponse({"error": "bad_request", "detail": "expires_in_seconds 至少 60"}, status_code=400)
    if expires_in > MCP_TOKEN_MAX_EXPIRY:
        return JSONResponse(
            {"error": "bad_request",
             "detail": f"expires_in_seconds 不能超过 {MCP_TOKEN_MAX_EXPIRY}（{MCP_TOKEN_MAX_EXPIRY // 86400} 天）"},
            status_code=400,
        )

    token, jti = issue_token(user_id, role, expires_in)
    record_grant(user_id, jti, role, expires_in)
    log_admin_api("issue_token", _caller_id(), {"user_id": user_id, "role": role, "jti": jti}, True)
    return JSONResponse({
        "ok": True,
        "token": token,
        "jti": jti,
        "user_id": user_id,
        "role": role,
        "expires_in_seconds": expires_in,
    })


async def admin_revoke_token(request: Request) -> JSONResponse:
    if not MCP_AUTH_ENABLED:
        return JSONResponse(
            {"error": "bad_request", "detail": "未启用 MCP_AUTH_ENABLED"},
            status_code=400,
        )
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "bad_request", "detail": "无效 JSON"}, status_code=400)

    jti = body.get("jti")
    user_id = body.get("user_id")

    if jti and isinstance(jti, str):
        revoke_jti(jti)
        mark_grant_revoked(jti)
        log_admin_api("revoke_token", _caller_id(), {"jti": jti}, True)
        return JSONResponse({"ok": True, "jti": jti, "message": "已撤销"})

    if user_id and isinstance(user_id, str):
        revoked_jtis = mark_user_all_revoked(user_id)
        revoke_jtis_bulk(revoked_jtis)
        log_admin_api("revoke_user", _caller_id(), {"user_id": user_id, "count": len(revoked_jtis)}, True)
        return JSONResponse({
            "ok": True, "user_id": user_id,
            "revoked_count": len(revoked_jtis), "revoked_jtis": revoked_jtis,
        })

    return JSONResponse({"error": "bad_request", "detail": "需要 jti 或 user_id"}, status_code=400)


async def admin_list_revoked(_request: Request) -> JSONResponse:
    if not MCP_AUTH_ENABLED:
        return JSONResponse(
            {"error": "bad_request", "detail": "未启用 MCP_AUTH_ENABLED"},
            status_code=400,
        )
    jtis = list_revoked()
    log_admin_api("list_revoked", _caller_id(), {"count": len(jtis)}, True)
    return JSONResponse({"ok": True, "revoked_jtis": jtis, "count": len(jtis)})


async def admin_list_users(_request: Request) -> JSONResponse:
    if not MCP_AUTH_ENABLED:
        return JSONResponse(
            {"error": "bad_request", "detail": "未启用 MCP_AUTH_ENABLED"},
            status_code=400,
        )
    users = list_all_users()
    log_admin_api("list_users", _caller_id(), {"count": len(users)}, True)
    return JSONResponse({"ok": True, "users": users, "count": len(users)})


async def admin_cleanup_revoked(_request: Request) -> JSONResponse:
    """清理撤销列表与延期表中已过期的记录"""
    if not MCP_AUTH_ENABLED:
        return JSONResponse(
            {"error": "bad_request", "detail": "未启用 MCP_AUTH_ENABLED"},
            status_code=400,
        )
    removed_revoked = cleanup_expired()
    removed_ext = cleanup_extensions()
    log_admin_api("cleanup_revoked", _caller_id(),
                  {"removed_revoked": removed_revoked, "removed_extensions": removed_ext}, True)
    return JSONResponse({
        "ok": True,
        "removed_revoked": removed_revoked,
        "removed_extensions": removed_ext,
    })


async def admin_extend_token(request: Request) -> JSONResponse:
    """延长 token 实际生效到期时间（token 字符串不变，仅更新服务端延期表）。

    请求体（二选一）：{"jti": "...", "expires_in_seconds": 7776000} 或
                    {"user_id": "...", "expires_in_seconds": 7776000}

    约束：expires_in_seconds 在 [60, MCP_TOKEN_MAX_EXPIRY]；
    user_id == 'admin' 不纳入延期管理。
    """
    if not MCP_AUTH_ENABLED:
        return JSONResponse(
            {"error": "bad_request", "detail": "未启用 MCP_AUTH_ENABLED"},
            status_code=400,
        )
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "bad_request", "detail": "无效 JSON"}, status_code=400)

    try:
        expires_in = int(body.get("expires_in_seconds", 7776000))
    except (TypeError, ValueError):
        return JSONResponse({"error": "bad_request", "detail": "expires_in_seconds 无效"}, status_code=400)
    if expires_in < 60:
        return JSONResponse({"error": "bad_request", "detail": "expires_in_seconds 至少 60"}, status_code=400)
    if expires_in > MCP_TOKEN_MAX_EXPIRY:
        return JSONResponse(
            {"error": "bad_request",
             "detail": f"expires_in_seconds 不能超过 {MCP_TOKEN_MAX_EXPIRY}（{MCP_TOKEN_MAX_EXPIRY // 86400} 天）"},
            status_code=400,
        )

    jti = body.get("jti")
    user_id = body.get("user_id")
    now = int(time.time())
    new_until = now + expires_in

    if jti and isinstance(jti, str):
        grant = get_grant_by_jti(jti)
        if not grant:
            return JSONResponse({"error": "not_found", "detail": f"未找到 jti={jti} 的签发记录"}, status_code=404)
        if grant.get("status") == "revoked":
            return JSONResponse({"error": "bad_request", "detail": "该 token 已撤销，无法延期"}, status_code=400)
        if str(grant.get("user_id", "")) == "admin":
            return JSONResponse(
                {"error": "bad_request", "detail": "user_id 'admin' 不纳入延期管理"},
                status_code=400,
            )
        rec = set_extension(jti, new_until, str(grant.get("user_id", "")), str(grant.get("role", "")))
        log_admin_api("extend_token", _caller_id(),
                      {"jti": jti, "extended_until": rec["extended_until"]}, True)
        return JSONResponse({
            "ok": True,
            "jti": jti,
            "user_id": rec["user_id"],
            "role": rec["role"],
            "extended_until": rec["extended_until"],
            "expires_in_seconds": expires_in,
        })

    if user_id and isinstance(user_id, str):
        if user_id == "admin":
            return JSONResponse(
                {"error": "bad_request", "detail": "user_id 'admin' 不纳入延期管理"},
                status_code=400,
            )
        active_jtis = get_user_active_jtis(user_id)
        if not active_jtis:
            return JSONResponse(
                {"error": "not_found", "detail": f"用户 {user_id} 没有可续期的 token（全部已撤销）"},
                status_code=404,
            )
        grants = {g["jti"]: g for g in get_user_grants(user_id) if g.get("status") == "active" and "jti" in g}
        # 只续期 expires_at 最大的那一个 token
        latest_jti = max(active_jtis, key=lambda j: grants.get(j, {}).get("expires_at", 0))
        latest_grant = grants.get(latest_jti, {})
        rec = set_extension(latest_jti, new_until, user_id, str(latest_grant.get("role", "")))
        log_admin_api("extend_token", _caller_id(),
                      {"user_id": user_id, "jti": latest_jti, "extended_until": rec["extended_until"]}, True)
        return JSONResponse({
            "ok": True,
            "user_id": user_id,
            "jti": latest_jti,
            "role": rec["role"],
            "extended_until": rec["extended_until"],
            "expires_in_seconds": expires_in,
        })

    return JSONResponse(
        {"error": "bad_request", "detail": "需要 jti 或 user_id"},
        status_code=400,
    )


_MAX_UPLOAD_SIZE = 1 * 1024 * 1024  # 1 MB


async def internal_upload_kubeconfig(request: Request) -> JSONResponse:
    """内部接口：接收 kubeconfig 文件并保存到用户的 kubeconfigs 目录。

    由 AI Agent 在调用 import_cluster MCP tool 前，通过 curl 将本地文件
    传输到服务端。文件内容走 HTTP 二进制传输，不经过 LLM。

    Query params:
        name: 集群名称（必填）

    Headers:
        Content-Type: application/octet-stream（推荐）或 text/yaml
        Authorization: Bearer <admin_jwt>

    Body:
        kubeconfig 文件原始内容
    """
    if not MCP_AUTH_ENABLED:
        return JSONResponse(
            {"error": "bad_request", "detail": "未启用 MCP_AUTH_ENABLED"},
            status_code=400,
        )

    name = request.query_params.get("name")
    if not name or not isinstance(name, str):
        return JSONResponse(
            {"error": "bad_request", "detail": "缺少 query param: name"},
            status_code=400,
        )
    if not _SAFE_ID_RE.match(name):
        return JSONResponse(
            {"error": "bad_request", "detail": f"name 格式无效: {name}"},
            status_code=400,
        )

    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > _MAX_UPLOAD_SIZE:
        return JSONResponse(
            {"error": "bad_request", "detail": f"文件超过 {_MAX_UPLOAD_SIZE} 字节限制"},
            status_code=400,
        )

    raw = await request.body()
    if not raw:
        return JSONResponse(
            {"error": "bad_request", "detail": "请求体为空"},
            status_code=400,
        )
    if len(raw) > _MAX_UPLOAD_SIZE:
        return JSONResponse(
            {"error": "bad_request", "detail": f"文件超过 {_MAX_UPLOAD_SIZE} 字节限制"},
            status_code=400,
        )

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return JSONResponse(
            {"error": "bad_request", "detail": "文件不是有效的 UTF-8 文本"},
            status_code=400,
        )

    from tools.cluster_tools import _validate_cluster_name

    name_err = _validate_cluster_name(name, strict=True)
    if name_err:
        return JSONResponse({"error": "bad_request", "detail": name_err}, status_code=400)

    from utils.cluster_config import get_cluster_config_manager

    try:
        path = get_cluster_config_manager().save_kubeconfig(name, text)
    except Exception as e:
        logger.error("保存 kubeconfig 失败: %s", e)
        return JSONResponse(
            {"error": "server_error", "detail": "保存文件失败"},
            status_code=500,
        )

    log_admin_api("upload_kubeconfig", _caller_id(), {"name": name, "path": path}, True)
    return JSONResponse({"ok": True, "name": name, "path": path})
