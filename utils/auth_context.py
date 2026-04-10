"""
请求级用户上下文（JWT 解析后写入，供集群配置与工具使用）
"""
from __future__ import annotations

import contextvars
from typing import Optional

current_user_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_user_id", default=None
)
current_role: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_role", default=None
)
current_jti: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_jti", default=None
)


def reset_auth_context() -> None:
    """清除当前上下文（测试或中间件结束时使用）"""
    current_user_id.set(None)
    current_role.set(None)
    current_jti.set(None)


def set_auth_context(user_id: str, role: str, jti: str) -> None:
    current_user_id.set(user_id)
    current_role.set(role)
    current_jti.set(jti)


def get_effective_user_id() -> Optional[str]:
    """
    多租户数据目录使用的用户标识。
    未启用认证时返回 None，表示使用全局 DATA_DIR（兼容旧行为）。
    启用认证时必须有中间件写入的上下文，否则抛出 RuntimeError。
    """
    from config import MCP_AUTH_ENABLED

    if not MCP_AUTH_ENABLED:
        return None
    uid = current_user_id.get()
    if uid is None:
        raise RuntimeError("已启用 MCP 认证但当前请求缺少用户上下文（JWT）")
    return uid
