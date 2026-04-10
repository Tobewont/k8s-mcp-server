"""
JWT 签发与校验（HS256），与撤销表联动
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional, Tuple

import jwt
from jwt.exceptions import InvalidTokenError

from config import MCP_JWT_ALGORITHM, MCP_JWT_AUDIENCE, MCP_JWT_SECRET
from utils.revocation_store import is_revoked

ROLE_ADMIN = "admin"
ROLE_USER = "user"


def _require_secret() -> str:
    if not MCP_JWT_SECRET:
        raise ValueError("未设置 MCP_JWT_SECRET，无法签发或校验 JWT")
    return MCP_JWT_SECRET


def issue_token(
    user_id: str,
    role: str,
    expires_in_seconds: int,
    *,
    secret: Optional[str] = None,
) -> Tuple[str, str]:
    """
    签发 JWT，返回 (token_string, jti)
    """
    sec = secret or _require_secret()
    jti = str(uuid.uuid4())
    now = int(time.time())
    payload: Dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "jti": jti,
        "iat": now,
        "exp": now + int(expires_in_seconds),
        "aud": MCP_JWT_AUDIENCE,
    }
    token = jwt.encode(payload, sec, algorithm=MCP_JWT_ALGORITHM)
    if isinstance(token, bytes):
        token = token.decode("ascii")
    return token, jti


def decode_and_verify(
    token: str, *, secret: Optional[str] = None, verify_exp: bool = True
) -> Dict[str, Any]:
    """
    解码并校验签名与 exp；检查撤销表。
    """
    sec = secret or _require_secret()
    options = {"verify_exp": verify_exp}
    payload = jwt.decode(
        token,
        sec,
        algorithms=[MCP_JWT_ALGORITHM],
        audience=MCP_JWT_AUDIENCE,
        options=options,
    )
    jti = payload.get("jti")
    if not jti:
        raise InvalidTokenError("缺少 jti")
    if is_revoked(str(jti)):
        raise InvalidTokenError("token 已撤销")
    return payload


def decode_payload_unsafe(token: str) -> Dict[str, Any]:
    """不校验签名，仅用于 CLI 展示 jti（需本地可信环境）"""
    return jwt.decode(
        token,
        algorithms=[MCP_JWT_ALGORITHM],
        options={"verify_signature": False, "verify_exp": False},
    )
