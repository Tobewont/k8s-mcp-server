"""
管理 API：签发用户 token、撤销 jti、集群导入（需管理员 JWT，由中间件校验）
"""
from __future__ import annotations

import logging
import re

from starlette.requests import Request
from starlette.responses import JSONResponse

from config import MCP_AUTH_ENABLED, MCP_TOKEN_MAX_EXPIRY
from utils.auth_context import current_user_id
from utils.jwt_service import ROLE_ADMIN, ROLE_USER, issue_token
from utils.operations_logger import log_admin_api
from utils.revocation_store import cleanup_expired, list_revoked, revoke_jti, revoke_jtis_bulk
from utils.token_store import (
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
        return JSONResponse(
            {"error": "bad_request", "detail": "缺少 user_id 字符串"},
            status_code=400,
        )
    if not _SAFE_ID_RE.match(user_id):
        return JSONResponse(
            {"error": "bad_request", "detail": "user_id 格式无效（只允许字母、数字、连字符、下划线、点）"},
            status_code=400,
        )
    try:
        expires_in = int(body.get("expires_in_seconds", 86400))
    except (TypeError, ValueError):
        return JSONResponse(
            {"error": "bad_request", "detail": "expires_in_seconds 无效"},
            status_code=400,
        )
    if expires_in < 60:
        return JSONResponse(
            {"error": "bad_request", "detail": "expires_in_seconds 至少 60"},
            status_code=400,
        )
    if expires_in > MCP_TOKEN_MAX_EXPIRY:
        return JSONResponse(
            {"error": "bad_request", "detail": f"expires_in_seconds 不能超过 {MCP_TOKEN_MAX_EXPIRY}（{MCP_TOKEN_MAX_EXPIRY // 86400} 天）"},
            status_code=400,
        )
    role = body.get("role") or ROLE_USER
    if role not in (ROLE_USER, ROLE_ADMIN):
        return JSONResponse(
            {"error": "bad_request", "detail": "role 只能是 user 或 admin"},
            status_code=400,
        )

    token, jti = issue_token(user_id, role, expires_in)
    record_grant(user_id, jti, role, expires_in)
    log_admin_api("issue_token", _caller_id(), {"user_id": user_id, "role": role, "jti": jti}, True)
    return JSONResponse(
        {
            "token": token,
            "jti": jti,
            "user_id": user_id,
            "role": role,
            "expires_in_seconds": expires_in,
        }
    )


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
        return JSONResponse({"ok": True, "jti": jti})

    if user_id and isinstance(user_id, str):
        revoked_jtis = mark_user_all_revoked(user_id)
        revoke_jtis_bulk(revoked_jtis)
        log_admin_api("revoke_user", _caller_id(), {"user_id": user_id, "count": len(revoked_jtis)}, True)
        return JSONResponse({"ok": True, "user_id": user_id, "revoked_count": len(revoked_jtis)})

    return JSONResponse(
        {"error": "bad_request", "detail": "需要 jti 或 user_id"},
        status_code=400,
    )


async def admin_list_revoked(_request: Request) -> JSONResponse:
    if not MCP_AUTH_ENABLED:
        return JSONResponse(
            {"error": "bad_request", "detail": "未启用 MCP_AUTH_ENABLED"},
            status_code=400,
        )
    jtis = list_revoked()
    log_admin_api("list_revoked", _caller_id(), {"count": len(jtis)}, True)
    return JSONResponse({"revoked": jtis, "count": len(jtis)})


async def admin_list_users(_request: Request) -> JSONResponse:
    if not MCP_AUTH_ENABLED:
        return JSONResponse(
            {"error": "bad_request", "detail": "未启用 MCP_AUTH_ENABLED"},
            status_code=400,
        )
    users = list_all_users()
    log_admin_api("list_users", _caller_id(), {"count": len(users)}, True)
    return JSONResponse({"users": users, "count": len(users)})


async def admin_cleanup_revoked(_request: Request) -> JSONResponse:
    """清理撤销列表中已过期的记录"""
    if not MCP_AUTH_ENABLED:
        return JSONResponse(
            {"error": "bad_request", "detail": "未启用 MCP_AUTH_ENABLED"},
            status_code=400,
        )
    removed = cleanup_expired()
    log_admin_api("cleanup_revoked", _caller_id(), {"removed": removed}, True)
    return JSONResponse({"ok": True, "removed": removed})


_MAX_UPLOAD_SIZE = 1 * 1024 * 1024  # 1 MB


async def internal_upload_kubeconfig(request: Request) -> JSONResponse:
    """内部接口：接收 kubeconfig 文件并保存到用户的 kubeconfigs 目录。

    供 AI Agent 在调用 import_cluster MCP tool 前，通过 curl 将本地文件
    传输到服务端。文件内容走 HTTP 二进制传输，不经过 LLM。
    此接口不包含集群导入逻辑，仅负责文件落盘。

    用法: curl -s -F "file=@kubeconfig.yaml" -F "name=my-cluster" <URL>
    """
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        try:
            form = await request.form()
        except Exception:
            return JSONResponse(
                {"error": "bad_request", "detail": "无法解析 multipart 表单"},
                status_code=400,
            )
        upload = form.get("file")
        if upload is None:
            return JSONResponse(
                {"error": "bad_request", "detail": "缺少 file 字段"},
                status_code=400,
            )
        raw = await upload.read()
        name = form.get("name", "")
    else:
        raw = await request.body()
        name = request.query_params.get("name", "")

    if not name:
        return JSONResponse(
            {"error": "bad_request", "detail": "缺少 name 参数"},
            status_code=400,
        )
    if not raw:
        return JSONResponse(
            {"error": "bad_request", "detail": "上传内容为空"},
            status_code=400,
        )
    if len(raw) > _MAX_UPLOAD_SIZE:
        return JSONResponse(
            {"error": "bad_request", "detail": f"文件超过 {_MAX_UPLOAD_SIZE // 1024} KB 限制"},
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
