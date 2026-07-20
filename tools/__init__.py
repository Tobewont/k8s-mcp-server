"""
Kubernetes MCP Server 工具模块

提供 Kubernetes 集群管理相关的各种工具
"""

import sys

# 使用自定义的 FastMCP 类
from utils.fastmcp_custom import FastMCP
from config import MCP_SERVER_CONFIG, ensure_dirs

# 懒创建：在工具模块加载时确保数据目录存在
ensure_dirs()

# 首次启动时把已有 active grant 的 expires_at 迁移到 token 延期表，
# 保证存量用户在延期管理范围内。延期表是叠加层，迁移失败不阻塞启动。
try:
    from utils.extension_store import migrate_if_needed
    _migration_result = migrate_if_needed()
    if isinstance(_migration_result, dict) and not _migration_result.get("skipped"):
        if _migration_result.get("migrated", 0) > 0:
            print(
                f"[info] token extensions migrated: {_migration_result}",
                file=sys.stderr,
            )
except Exception as _e:
    print(f"[warn] token extensions migration skipped: {_e}", file=sys.stderr)

# 创建统一的MCP实例，所有工具模块共享
# 使用配置文件中的统一配置
mcp = FastMCP("k8s-mcp-server", **MCP_SERVER_CONFIG)

# 创建可导入的app对象
app = mcp.create_app()

# 在创建mcp实例后导入所有工具模块
from . import k8s_tools          # 核心工具（健康检查、查询、快捷操作）
from . import batch_tools        # 批量资源管理（核心）
from . import cluster_tools      # 集群和配置管理
from . import diagnostic_tools   # 诊断工具
from . import backup_tools       # 备份工具
from . import auth_tools         # 认证与用户管理（whoami / admin_manage_users / admin_manage_profiles）

__all__ = [
    'k8s_tools',
    'batch_tools',
    'cluster_tools', 
    'diagnostic_tools',
    'backup_tools',
    'auth_tools',
    'mcp',
    'app'
]