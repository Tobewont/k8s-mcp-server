#!/usr/bin/env python3
"""
mcp-admin：本地管理 CLI（JWT 签发/撤销、权限 Profile、集群权限分配）。
需与服务器相同的 MCP_JWT_SECRET 与 DATA_DIR。

用法示例：
  MCP_JWT_SECRET=xxx mcp-admin bootstrap
  MCP_JWT_SECRET=xxx mcp-admin issue --user alice --expires 604800
  MCP_JWT_SECRET=xxx mcp-admin revoke --jti <uuid>
  MCP_JWT_SECRET=xxx mcp-admin revoke-user --user alice
  MCP_JWT_SECRET=xxx mcp-admin list-users
  MCP_JWT_SECRET=xxx mcp-admin get-user --user alice
  MCP_JWT_SECRET=xxx mcp-admin grant --user alice --cluster prod --namespace default --profile developer
  MCP_JWT_SECRET=xxx mcp-admin revoke-access --user alice --cluster prod --namespace default
  MCP_JWT_SECRET=xxx mcp-admin list-profiles
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="mcp-admin", description="K8s MCP 管理 CLI（JWT + 权限 Profile）")
    sub = parser.add_subparsers(dest="cmd")

    # --- Token 管理 ---
    sub.add_parser("bootstrap", help="生成长期管理员 JWT，供 MCP_BOOTSTRAP_ADMIN_JWT 预置")

    p_issue = sub.add_parser("issue", help="签发 JWT")
    p_issue.add_argument("--user", required=True, help="sub / 用户标识，对应 data/users/<user>/")
    p_issue.add_argument("--role", default="user", choices=["user", "admin"], help="默认 user")
    p_issue.add_argument("--expires", type=int, default=86400, metavar="SEC", help="有效期（秒），默认 86400")

    p_revoke = sub.add_parser("revoke", help="按 jti 撤销")
    p_revoke.add_argument("--jti", required=True)

    p_revoke_user = sub.add_parser("revoke-user", help="撤销某用户全部 token")
    p_revoke_user.add_argument("--user", required=True)

    sub.add_parser("list-users", help="列出所有已签发用户及 token 状态摘要")

    p_get_user = sub.add_parser("get-user", help="查看某用户的全部签发记录与权限授权")
    p_get_user.add_argument("--user", required=True)

    # --- 权限 Profile ---
    sub.add_parser("list-profiles", help="列出所有权限 Profile（内置 + 自定义）")

    # --- 集群权限分配 ---
    p_grant = sub.add_parser("grant", help="为用户分配集群/命名空间权限（记录到 access_grants.json）")
    p_grant.add_argument("--user", required=True, help="用户标识")
    p_grant.add_argument("--cluster", required=True, help="集群名称")
    p_grant.add_argument("--namespace", required=True, help="命名空间")
    p_grant.add_argument("--profile", required=True, help="权限 Profile 名称（如 viewer/developer/operator/admin）")

    p_revoke_access = sub.add_parser("revoke-access", help="撤销用户的集群/命名空间权限")
    p_revoke_access.add_argument("--user", required=True, help="用户标识")
    p_revoke_access.add_argument("--cluster", required=True, help="集群名称")
    p_revoke_access.add_argument("--namespace", required=True, help="命名空间")

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        return 1

    _root = os.path.dirname(os.path.abspath(__file__))
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from config import MCP_JWT_SECRET
    from utils.jwt_service import ROLE_ADMIN, ROLE_USER, issue_token
    from utils.revocation_store import revoke_jti, revoke_jtis_bulk
    from utils.token_store import (
        get_user_grants,
        list_all_users,
        mark_grant_revoked,
        mark_user_all_revoked,
        record_grant,
    )

    if not MCP_JWT_SECRET:
        print("错误: 请设置环境变量 MCP_JWT_SECRET（与服务器一致）", file=sys.stderr)
        return 1

    if args.cmd == "bootstrap":
        token, jti = issue_token("admin", ROLE_ADMIN, 365 * 86400 * 100)
        record_grant("admin", jti, ROLE_ADMIN, 365 * 86400 * 100)
        print("# 将下行加入 Secret/环境变量作为启动前管理员 token")
        print(f"MCP_BOOTSTRAP_ADMIN_JWT={token}")
        print(f"# jti={jti}", file=sys.stderr)
        return 0

    if args.cmd == "issue":
        role = ROLE_ADMIN if args.role == "admin" else ROLE_USER
        if args.expires < 60:
            print("错误: --expires 至少 60 秒", file=sys.stderr)
            return 1
        token, jti = issue_token(args.user, role, args.expires)
        record_grant(args.user, jti, role, args.expires)
        print(token)
        print(f"jti={jti}", file=sys.stderr)
        return 0

    if args.cmd == "revoke":
        revoke_jti(args.jti)
        mark_grant_revoked(args.jti)
        print("ok")
        return 0

    if args.cmd == "revoke-user":
        revoked = mark_user_all_revoked(args.user)
        revoke_jtis_bulk(revoked)
        print(f"已撤销 {len(revoked)} 个 token")
        for j in revoked:
            print(f"  jti={j}")
        return 0

    if args.cmd == "list-users":
        users = list_all_users()
        if not users:
            print("（无签发记录）")
        else:
            print(json.dumps(users, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "get-user":
        from utils.permission_profiles import get_user_access_grants
        grants = get_user_grants(args.user)
        access = get_user_access_grants(args.user, active_only=False)
        if not grants and not access:
            print(f"用户 {args.user} 无签发记录和权限授权")
        else:
            result = {"token_grants": grants, "access_grants": access}
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "list-profiles":
        from utils.permission_profiles import list_profiles
        profiles = list_profiles()
        print(json.dumps(profiles, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "grant":
        from utils.permission_profiles import get_profile, record_access_grant
        p = get_profile(args.profile)
        if not p:
            print(f"错误: profile '{args.profile}' 不存在", file=sys.stderr)
            return 1
        grant = record_access_grant(args.user, args.cluster, args.namespace, args.profile)
        print(f"已为 {args.user} 在 {args.cluster}/{args.namespace} 分配 {args.profile} 权限")
        print(json.dumps(grant, ensure_ascii=False, indent=2))
        print("提示: K8s RBAC 资源（Role/RoleBinding/SA）需通过 MCP Tool admin_manage_users(action='grant_access') 自动创建", file=sys.stderr)
        return 0

    if args.cmd == "revoke-access":
        from utils.permission_profiles import revoke_access_grant
        result = revoke_access_grant(args.user, args.cluster, args.namespace)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
