"""
Bearer JWT 校验中间件（SSE / Streamable / 管理 API）
"""
from __future__ import annotations

from typing import Callable

from jwt.exceptions import PyJWTError
from starlette.requests import Request
from starlette.responses import JSONResponse

from config import MCP_ADMIN_API_PREFIX, MCP_AUTH_ENABLED, MCP_HEALTH_PATH, MCP_JWT_SECRET
from utils.auth_context import reset_auth_context, set_auth_context
from utils.jwt_service import decode_and_verify


def _json_401(detail: str) -> JSONResponse:
    return JSONResponse(
        {"error": "unauthorized", "detail": detail},
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _needs_auth(path: str) -> bool:
    if path == MCP_HEALTH_PATH or path.rstrip("/") == "/healthz":
        return False
    return True


class JWTAuthMiddleware:
    """未启用 MCP_AUTH_ENABLED 时透传；启用时除健康检查外要求 Authorization: Bearer <jwt>"""

    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET")

        if not MCP_AUTH_ENABLED:
            await self.app(scope, receive, send)
            return

        if not MCP_JWT_SECRET:
            resp = JSONResponse(
                {
                    "error": "misconfigured",
                    "detail": "已启用 MCP_AUTH_ENABLED 但未设置 MCP_JWT_SECRET",
                },
                status_code=503,
            )
            await resp(scope, receive, send)
            return

        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        if not _needs_auth(path):
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        auth = request.headers.get("authorization") or ""
        if not auth.lower().startswith("bearer "):
            await _json_401("缺少 Bearer token")(scope, receive, send)
            return
        raw = auth[7:].strip()
        if not raw:
            await _json_401("空的 Bearer token")(scope, receive, send)
            return

        try:
            payload = decode_and_verify(raw)
        except (PyJWTError, ValueError) as e:
            await _json_401(f"token 无效: {e}")(scope, receive, send)
            return

        sub = payload.get("sub")
        role = payload.get("role") or "user"
        jti = payload.get("jti")
        if not sub or not jti:
            await _json_401("token 缺少 sub 或 jti")(scope, receive, send)
            return

        prefix = MCP_ADMIN_API_PREFIX
        if path == prefix or path.startswith(prefix + "/"):
            if role != "admin":
                await JSONResponse(
                    {"error": "forbidden", "detail": "需要管理员 token"},
                    status_code=403,
                )(scope, receive, send)
                return

        set_auth_context(str(sub), str(role), str(jti))
        try:
            await self.app(scope, receive, send)
        finally:
            reset_auth_context()
