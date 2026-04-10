"""
Token 签发记录持久化（user_id → grants 列表）。
支持按 user_id 查询、按 jti 查询、批量撤销。
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

from config import AUTH_GRANTS_FILE, ensure_dirs

_lock = threading.Lock()


def _load_raw() -> Dict[str, Any]:
    if not os.path.isfile(AUTH_GRANTS_FILE):
        return {}
    try:
        with open(AUTH_GRANTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_raw(data: Dict[str, Any]) -> None:
    ensure_dirs()
    os.makedirs(os.path.dirname(AUTH_GRANTS_FILE), exist_ok=True)
    tmp = AUTH_GRANTS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, AUTH_GRANTS_FILE)


def record_grant(
    user_id: str,
    jti: str,
    role: str,
    expires_in_seconds: int,
) -> Dict[str, Any]:
    """记录一次签发，返回 grant 记录"""
    now = int(time.time())
    grant: Dict[str, Any] = {
        "jti": jti,
        "role": role,
        "issued_at": now,
        "expires_at": now + expires_in_seconds,
        "status": "active",
    }
    with _lock:
        data = _load_raw()
        user_grants = data.setdefault(user_id, {"grants": []})
        if not isinstance(user_grants.get("grants"), list):
            user_grants["grants"] = []
        user_grants["grants"].append(grant)
        _save_raw(data)
    return grant


def get_user_grants(user_id: str) -> List[Dict[str, Any]]:
    """获取某用户的全部签发记录"""
    with _lock:
        data = _load_raw()
    user_data = data.get(user_id, {})
    grants = user_data.get("grants", [])
    return list(grants) if isinstance(grants, list) else []


def get_user_active_jtis(user_id: str) -> List[str]:
    """获取某用户所有 status=active 的 jti"""
    grants = get_user_grants(user_id)
    return [g["jti"] for g in grants if g.get("status") == "active" and "jti" in g]


def mark_grant_revoked(jti: str) -> Optional[str]:
    """标记某个 jti 的 grant 为 revoked，返回其 user_id（找不到返回 None）"""
    with _lock:
        data = _load_raw()
        for uid, udata in data.items():
            for g in udata.get("grants", []):
                if g.get("jti") == jti:
                    g["status"] = "revoked"
                    g["revoked_at"] = int(time.time())
                    _save_raw(data)
                    return uid
    return None


def mark_user_all_revoked(user_id: str) -> List[str]:
    """将某用户所有 active grant 标记为 revoked，返回被撤销的 jti 列表"""
    revoked_jtis: List[str] = []
    now = int(time.time())
    with _lock:
        data = _load_raw()
        udata = data.get(user_id, {})
        for g in udata.get("grants", []):
            if g.get("status") == "active":
                g["status"] = "revoked"
                g["revoked_at"] = now
                if "jti" in g:
                    revoked_jtis.append(g["jti"])
        if revoked_jtis:
            _save_raw(data)
    return revoked_jtis


def get_grant_by_jti(jti: str) -> Optional[Dict[str, Any]]:
    """根据 jti 查找签发记录，返回 {user_id, role, status, ...}，找不到返回 None"""
    with _lock:
        data = _load_raw()
    for uid, udata in data.items():
        for g in udata.get("grants", []):
            if g.get("jti") == jti:
                return {"user_id": uid, **g}
    return None


def list_all_users() -> List[Dict[str, Any]]:
    """列出所有有签发记录的用户摘要"""
    with _lock:
        data = _load_raw()
    now = int(time.time())
    result = []
    for uid, udata in data.items():
        grants = udata.get("grants", [])
        active = [g for g in grants if g.get("status") == "active" and g.get("expires_at", 0) > now]
        expired = [g for g in grants if g.get("status") == "active" and g.get("expires_at", 0) <= now]
        revoked = [g for g in grants if g.get("status") == "revoked"]
        result.append({
            "user_id": uid,
            "total_grants": len(grants),
            "active": len(active),
            "expired": len(expired),
            "revoked": len(revoked),
        })
    return result
