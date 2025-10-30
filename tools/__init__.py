"""
Kubernetes MCP Server 工具模块

提供 Kubernetes 集群管理相关的各种工具
"""

# 使用自定义的 FastMCP 类
from utils.fastmcp_custom import FastMCP
from config import MCP_SERVER_CONFIG

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
from . import rbac_tools         # RBAC 工具

__all__ = [
    'k8s_tools',
    'batch_tools',
    'cluster_tools', 
    'diagnostic_tools',
    'backup_tools',
    'rbac_tools',
    'mcp',
    'app'
]