"""
Kubernetes MCP Server 配置文件
"""
import os
from typing import Optional

# 数据目录：优先 MCP_DATA_DIR，其次 DATA_DIR，否则包内 data/
_ROOT = os.path.dirname(os.path.abspath(__file__))
_env_data = os.getenv("MCP_DATA_DIR") or os.getenv("DATA_DIR")
DATA_DIR = os.path.abspath(_env_data) if _env_data else os.path.join(_ROOT, "data")
LOGS_DIR = os.path.join(_ROOT, "logs")

# 备份目录
BACKUP_DIR = os.path.join(DATA_DIR, "backup")

# Pod 文件读取单文件上限；内容经 MCP 响应 → LLM 上下文 → 客户端，受内存和上下文窗口限制，不适合大文件
MAX_POD_FILE_SIZE = int(os.getenv("MAX_POD_FILE_SIZE", str(10 * 1024 * 1024)))  # 默认 10MB


# ---------- JWT / 多租户 ----------
MCP_AUTH_ENABLED = os.getenv("MCP_AUTH_ENABLED", "false").lower() == "true"
MCP_JWT_SECRET = os.getenv("MCP_JWT_SECRET", "") or os.getenv("JWT_SECRET", "")
MCP_JWT_ALGORITHM = os.getenv("MCP_JWT_ALGORITHM", "HS256")
MCP_JWT_AUDIENCE = os.getenv("MCP_JWT_AUDIENCE", "k8s-mcp-server")

# Token 有效期上限（秒），默认 90 天，可通过环境变量调整
MCP_TOKEN_MAX_EXPIRY = int(os.getenv("MCP_TOKEN_MAX_EXPIRY", str(90 * 24 * 3600)))

# 管理 API 前缀（需 Bearer 管理员 JWT）
MCP_ADMIN_API_PREFIX = os.getenv("MCP_ADMIN_API_PREFIX", "/admin").rstrip("/") or "/admin"

# 启动前预置的管理员 JWT（仅用于文档/运维说明，服务端校验与普通 JWT 相同）
MCP_BOOTSTRAP_ADMIN_JWT = os.getenv("MCP_BOOTSTRAP_ADMIN_JWT", "")

# 撤销列表文件
AUTH_REVOCATION_FILE = os.path.join(DATA_DIR, "auth", "revoked_jtis.json")

# 签发记录文件（user_id → [grants]）
AUTH_GRANTS_FILE = os.path.join(DATA_DIR, "auth", "user_grants.json")

# 健康检查路径（无需鉴权）
MCP_HEALTH_PATH = os.getenv("MCP_HEALTH_PATH", "/health")


_DEFAULT_USER = "default"


def get_user_data_root(user_id: Optional[str]) -> str:
    """
    返回用户数据根目录，统一使用 data/users/<id>/ 结构。
    未启用认证或 user_id 为空时使用 data/users/default/。
    """
    uid = user_id if (MCP_AUTH_ENABLED and user_id) else _DEFAULT_USER
    return os.path.join(DATA_DIR, "users", uid)


def ensure_dirs() -> None:
    """确保数据目录存在，在工具模块加载时调用"""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    if MCP_AUTH_ENABLED:
        os.makedirs(os.path.join(DATA_DIR, "auth"), exist_ok=True)
    default_root = get_user_data_root(None)
    os.makedirs(os.path.join(default_root, "kubeconfigs"), exist_ok=True)

# 日志配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")
LOG_FILE = os.path.join(LOGS_DIR, "k8s-mcp-server.log")

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

# 时区配置（小时偏移，默认东八区）
TIMEZONE_OFFSET_HOURS = int(os.getenv("TIMEZONE_OFFSET_HOURS", "8"))

# 环境配置文件
ENV_FILE = ".env"
ENV_FILE_ENCODING = "utf-8"
