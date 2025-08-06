"""
Kubernetes MCP Server 配置文件
"""
import os

# 数据目录配置
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")

# 确保目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# 集群配置文件路径
CLUSTERS_CONFIG_FILE = os.path.join(DATA_DIR, "clusters.json")
KUBECONFIGS_DIR = os.path.join(DATA_DIR, "kubeconfigs")

# 备份目录名称
BACKUP_DIR_NAME = "backup"
BACKUP_DIR = os.path.join(DATA_DIR, BACKUP_DIR_NAME)

# 确保kubeconfigs目录存在
os.makedirs(KUBECONFIGS_DIR, exist_ok=True)

# 日志配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")
LOG_FILE = os.path.join(LOGS_DIR, "k8s-mcp-server.log")
OPERATIONS_LOG_FILE = os.path.join(LOGS_DIR, "operations.log")

# SSE服务器配置
SSE_HOST = os.getenv("SSE_HOST", "0.0.0.0")
SSE_PORT = int(os.getenv("SSE_PORT", "8000"))

# MCP配置
MCP_MESSAGE_PATH = "/mcp/k8s-server/message/"
MCP_SSE_PATH = "/mcp/k8s-server/sse"

# 环境配置文件
ENV_FILE = ".env"
ENV_FILE_ENCODING = "utf-8" 