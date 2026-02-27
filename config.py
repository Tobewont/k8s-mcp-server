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
MCP_MESSAGE_PATH = os.getenv("MCP_MESSAGE_PATH", "/mcp/k8s-server/message/")
MCP_SSE_PATH = os.getenv("MCP_SSE_PATH", "/mcp/k8s-server/sse")
MCP_STREAMABLE_PATH = os.getenv("MCP_STREAMABLE_PATH", "/mcp/k8s-server/streamable")

# MCP FastMCP 服务器配置
MCP_SERVER_CONFIG = {
    # 基础配置
    "debug": os.getenv("MCP_DEBUG", "false").lower() == "true",
    "log_level": os.getenv("MCP_LOG_LEVEL", "INFO").upper(),
    "host": os.getenv("MCP_HOST", SSE_HOST),
    "port": int(os.getenv("MCP_PORT", SSE_PORT)),
    
    # 路径配置
    "mount_path": os.getenv("MCP_MOUNT_PATH", "/"),
    "sse_path": MCP_SSE_PATH,
    "message_path": MCP_MESSAGE_PATH,
    "streamable_http_path": MCP_STREAMABLE_PATH,
    
    # 行为配置
    "json_response": os.getenv("MCP_JSON_RESPONSE", "false").lower() == "true",
    "stateless_http": os.getenv("MCP_STATELESS_HTTP", "false").lower() == "true",
    
    # 警告配置
    "warn_on_duplicate_resources": os.getenv("MCP_WARN_DUPLICATE_RESOURCES", "true").lower() == "true",
    "warn_on_duplicate_tools": os.getenv("MCP_WARN_DUPLICATE_TOOLS", "true").lower() == "true",
    "warn_on_duplicate_prompts": os.getenv("MCP_WARN_DUPLICATE_PROMPTS", "true").lower() == "true",
    
    # 高级配置
    "dependencies": [],  # 可以通过环境变量 MCP_DEPENDENCIES 以逗号分隔的形式提供
    "lifespan": None,
    "auth": None,
    "transport_security": None,
}

# 处理依赖列表（如果通过环境变量提供）
_dependencies_env = os.getenv("MCP_DEPENDENCIES", "")
if _dependencies_env.strip():
    MCP_SERVER_CONFIG["dependencies"] = [dep.strip() for dep in _dependencies_env.split(",")]

# 环境配置文件
ENV_FILE = ".env"
ENV_FILE_ENCODING = "utf-8" 