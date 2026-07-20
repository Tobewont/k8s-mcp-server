"""
JWT jti 延期表（token_extensions.json）。

为什么需要这层：
- JWT 内的 exp 是签名 payload 的一部分，无法在不重新签名（即换 token 字符串）的情况下修改。
- 为了支持"用户 token 字符串不变 + 管理员延长其有效时间"，把"实际生效到期时间"放在服务端：
    effective_exp = max(jwt.exp, extension[jti].extended_until if exists else jwt.exp)
- 这样旧 token 行为不变（max(jwt.exp, jwt.exp) = jwt.exp），延期只是叠加层。

存储路径与 revoked_jtis.json / user_grants.json 同目录（data/auth/），同为本地 JSON + 进程内锁。
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

from config import AUTH_EXTENSIONS_FILE, ensure_dirs

_lock = threading.Lock()


def _load_raw() -> Dict[str, Any]:
    if not os.path.isfile(AUTH_EXTENSIONS_FILE):
        return {"extensions": {}}
    try:
        with open(AUTH_EXTENSIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"extensions": {}}
        if "extensions" not in data or not isinstance(data["extensions"], dict):
            data["extensions"] = {}
        return data
    except (json.JSONDecodeError, OSError):
        return {"extensions": {}}


def _save_raw(data: Dict[str, Any]) -> None:
    ensure_dirs()
    os.makedirs(os.path.dirname(AUTH_EXTENSIONS_FILE), exist_ok=True)
    tmp = AUTH_EXTENSIONS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, AUTH_EXTENSIONS_FILE)


def get_extension(jti: str) -> Optional[Dict[str, Any]]:
    """返回 {extended_until, user_id, role, updated_at} 或 None"""
    with _lock:
        data = _load_raw()
        ext = data.get("extensions", {}).get(jti)
        return dict(ext) if isinstance(ext, dict) else None


def set_extension(jti: str, extended_until: int, user_id: str, role: str) -> Dict[str, Any]:
    """写入/更新一条延期记录。幂等：再次调用覆盖 updated_at 与 extended_until（取较大值）。

    存储层兜底：若 jti 已在撤销表中，拒绝写入。
    """
    from utils.revocation_store import is_revoked
    if is_revoked(jti):
        raise ValueError(f"jti {jti} 已撤销，不能延期")
    now = int(time.time())
    with _lock:
        data = _load_raw()
        store = data.setdefault("extensions", {})
        existing = store.get(jti)
        if isinstance(existing, dict) and isinstance(existing.get("extended_until"), int):
            extended_until = max(existing["extended_until"], extended_until)
        record = {
            "extended_until": int(extended_until),
            "user_id": user_id,
            "role": role,
            "updated_at": now,
        }
        store[jti] = record
        _save_raw(data)
        return record


def set_extensions_bulk(items: List[Dict[str, Any]]) -> int:
    """批量 upsert。items: [{jti, extended_until, user_id, role}, ...]。返回实际写入/更新数量。

    存储层兜底：跳过已撤销的 jti。
    """
    from utils.revocation_store import is_revoked
    if not items:
        return 0
    now = int(time.time())
    count = 0
    with _lock:
        data = _load_raw()
        store = data.setdefault("extensions", {})
        for it in items:
            jti = it.get("jti")
            until = it.get("extended_until")
            if not jti or not isinstance(until, int):
                continue
            if is_revoked(jti):
                continue
            existing = store.get(jti)
            if isinstance(existing, dict) and isinstance(existing.get("extended_until"), int):
                until = max(existing["extended_until"], until)
            store[jti] = {
                "extended_until": until,
                "user_id": str(it.get("user_id", "")),
                "role": str(it.get("role", "")),
                "updated_at": now,
            }
            count += 1
        if count:
            _save_raw(data)
    return count


def remove_extension(jti: str) -> bool:
    with _lock:
        data = _load_raw()
        store = data.get("extensions", {})
        if jti in store:
            del store[jti]
            _save_raw(data)
            return True
        return False


def remove_extensions_bulk(jtis: List[str]) -> int:
    if not jtis:
        return 0
    removed = 0
    with _lock:
        data = _load_raw()
        store = data.get("extensions", {})
        for jti in jtis:
            if jti in store:
                del store[jti]
                removed += 1
        if removed:
            _save_raw(data)
    return removed


def list_extensions() -> Dict[str, Dict[str, Any]]:
    with _lock:
        data = _load_raw()
        out = data.get("extensions", {})
        return dict(out) if isinstance(out, dict) else {}


def cleanup_expired(max_token_lifetime: int = 0) -> int:
    """清理已经过期很久的延期记录。

    判定：extended_until < now - max_token_lifetime
    （此时即使被延期，token 也已经超过最大可能生命周期，可安全删除。）
    """
    if max_token_lifetime <= 0:
        from config import MCP_TOKEN_MAX_EXPIRY
        max_token_lifetime = MCP_TOKEN_MAX_EXPIRY
    cutoff = int(time.time()) - max_token_lifetime
    removed = 0
    with _lock:
        data = _load_raw()
        store = data.get("extensions", {})
        expired_keys = [
            k for k, v in store.items()
            if isinstance(v, dict) and isinstance(v.get("extended_until"), int)
            and v["extended_until"] < cutoff
        ]
        for k in expired_keys:
            del store[k]
            removed += 1
        if removed:
            _save_raw(data)
    return removed


# ---------------- 旧数据迁移 ----------------

def _is_admin_grant(user_id: str, role: str) -> bool:
    """是否为全局唯一的 admin 账户（user_id == 'admin'），该账户不纳入延期管理。"""
    return user_id == "admin"


def purge_admin_extensions() -> int:
    """清理延期表中 user_id == 'admin' 的记录。返回清理的记录数。"""
    removed = 0
    with _lock:
        data = _load_raw()
        store = data.get("extensions", {})
        admin_jtis = [
            jti for jti, rec in store.items()
            if isinstance(rec, dict) and _is_admin_grant(
                str(rec.get("user_id", "")), str(rec.get("role", ""))
            )
        ]
        for jti in admin_jtis:
            del store[jti]
            removed += 1
        if removed:
            _save_raw(data)
    return removed


def migrate_from_grants(*, dry_run: bool = False, overwrite: bool = False) -> Dict[str, Any]:
    """把 user_grants.json 中 active grant 的 expires_at 写入延期表作为初始 extended_until。

    user_id == 'admin' 的 grant 跳过。默认幂等不覆盖已存在的延期记录。

    Returns:
        {"scanned": int, "migrated": int, "skipped_existing": int, "skipped_admin": int, "dry_run": bool}
    """
    from utils.token_store import _load_raw as _load_grants

    grants_data = _load_grants()
    items: List[Dict[str, Any]] = []
    skipped = 0
    skipped_admin = 0

    for uid, udata in grants_data.items():
        if not isinstance(udata, dict):
            continue
        for g in udata.get("grants", []):
            if not isinstance(g, dict):
                continue
            if g.get("status") != "active":
                continue
            jti = g.get("jti")
            expires_at = g.get("expires_at")
            role = str(g.get("role", ""))
            if not jti or not isinstance(expires_at, int):
                continue
            if _is_admin_grant(str(uid), role):
                skipped_admin += 1
                continue
            if not overwrite:
                existing = get_extension(str(jti))
                if existing:
                    skipped += 1
                    continue
            items.append({
                "jti": str(jti),
                "extended_until": int(expires_at),
                "user_id": str(uid),
                "role": role,
            })

    if dry_run:
        return {
            "scanned": sum(
                1 for u in grants_data.values()
                if isinstance(u, dict) for g in u.get("grants", []) if isinstance(g, dict)
            ),
            "migrated": 0,
            "planned": len(items),
            "skipped_existing": skipped,
            "skipped_admin": skipped_admin,
            "dry_run": True,
        }

    migrated = set_extensions_bulk(items)
    return {
        "scanned": sum(
            1 for u in grants_data.values()
            if isinstance(u, dict) for g in u.get("grants", []) if isinstance(g, dict)
        ),
        "migrated": migrated,
        "skipped_existing": skipped,
        "skipped_admin": skipped_admin,
        "dry_run": False,
    }


def migrate_if_needed() -> Dict[str, Any]:
    """启动时维护延期表：清理 admin 延期记录；延期表不存在时从 user_grants.json 迁移 active grant。"""
    purged = purge_admin_extensions()
    if os.path.isfile(AUTH_EXTENSIONS_FILE):
        return {"skipped": True, "reason": "extensions file already exists", "purged_admin": purged}
    result = migrate_from_grants(dry_run=False, overwrite=False)
    result["purged_admin"] = purged
    return result
