"""
JWT jti 撤销列表（持久化 JSON，进程内与 CLI/管理 API 共用）
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict

from config import AUTH_REVOCATION_FILE, ensure_dirs

_lock = threading.Lock()


def _load_raw() -> Dict[str, Any]:
    if not os.path.isfile(AUTH_REVOCATION_FILE):
        return {"jtis": {}}
    try:
        with open(AUTH_REVOCATION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"jtis": {}}
        if "jtis" not in data or not isinstance(data["jtis"], dict):
            data["jtis"] = {}
        return data
    except (json.JSONDecodeError, OSError):
        return {"jtis": {}}


def _save_raw(data: Dict[str, Any]) -> None:
    ensure_dirs()
    os.makedirs(os.path.dirname(AUTH_REVOCATION_FILE), exist_ok=True)
    tmp = AUTH_REVOCATION_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, AUTH_REVOCATION_FILE)


def is_revoked(jti: str) -> bool:
    with _lock:
        data = _load_raw()
        return jti in data.get("jtis", {})


_cleanup_counter = 0


def revoke_jti(jti: str) -> None:
    """将 jti 加入撤销集合（幂等），每 100 次写入自动触发一次过期清理"""
    global _cleanup_counter
    with _lock:
        data = _load_raw()
        jtis = data.setdefault("jtis", {})
        jtis[jti] = int(time.time())
        _cleanup_counter += 1
        if _cleanup_counter >= 100:
            _cleanup_counter = 0
            _auto_cleanup(data)
        _save_raw(data)


def _auto_cleanup(data: Dict[str, Any]) -> None:
    """在持有锁的情况下，就地清理过期的撤销记录"""
    from config import MCP_TOKEN_MAX_EXPIRY
    cutoff = int(time.time()) - MCP_TOKEN_MAX_EXPIRY
    jtis = data.get("jtis", {})
    expired_keys = [k for k, ts in jtis.items() if isinstance(ts, (int, float)) and ts < cutoff]
    for k in expired_keys:
        del jtis[k]


def revoke_jtis_bulk(jtis: list) -> int:
    """批量撤销多个 jti，返回实际新增数量"""
    if not jtis:
        return 0
    now = int(time.time())
    count = 0
    with _lock:
        data = _load_raw()
        store = data.setdefault("jtis", {})
        for jti in jtis:
            if jti not in store:
                store[jti] = now
                count += 1
        if count:
            _save_raw(data)
    return count


def list_revoked() -> Dict[str, int]:
    """返回 jti -> 撤销时间戳，供调试或管理"""
    with _lock:
        data = _load_raw()
        out = data.get("jtis", {})
        return dict(out) if isinstance(out, dict) else {}


def cleanup_expired(max_token_lifetime: int = 0) -> int:
    """清理已过期的撤销记录。

    一个 jti 被撤销后，如果距撤销时间已超过 max_token_lifetime，
    说明对应 JWT 无论如何都已过期（即使未被撤销也不会通过校验），
    可以安全从撤销列表中移除。

    Args:
        max_token_lifetime: 最大 token 生命周期（秒）。
            为 0 时从 config.MCP_TOKEN_MAX_EXPIRY 读取。

    Returns:
        清理的记录数量
    """
    if max_token_lifetime <= 0:
        from config import MCP_TOKEN_MAX_EXPIRY
        max_token_lifetime = MCP_TOKEN_MAX_EXPIRY
    cutoff = int(time.time()) - max_token_lifetime
    removed = 0
    with _lock:
        data = _load_raw()
        jtis = data.get("jtis", {})
        expired_keys = [k for k, ts in jtis.items() if isinstance(ts, (int, float)) and ts < cutoff]
        for k in expired_keys:
            del jtis[k]
            removed += 1
        if removed:
            _save_raw(data)
    return removed
