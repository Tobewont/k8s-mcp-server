"""
Kubernetes MCP Server 工具模块

提供 Kubernetes 集群管理相关的各种工具
"""

# 使用自定义的 FastMCP 类
from utils.fastmcp_custom import FastMCP
from config import MCP_MESSAGE_PATH, MCP_SSE_PATH

# 创建统一的MCP实例，所有工具模块共享
mcp = FastMCP("k8s-mcp-server", message_path=MCP_MESSAGE_PATH, sse_path=MCP_SSE_PATH)

# 创建可导入的app对象
app = mcp.create_app()

# 在创建mcp实例后导入所有工具模块
from . import k8s_tools
from . import cluster_tools
from . import config_tools
from . import diagnostic_tools

__all__ = [
    'k8s_tools',
    'cluster_tools', 
    'config_tools',
    'diagnostic_tools',
    'mcp',
    'app'
]