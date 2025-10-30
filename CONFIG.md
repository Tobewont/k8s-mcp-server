# 配置说明文档

## 📋 配置架构

现在所有的MCP服务器配置都统一管理在 `config.py` 文件中，通过环境变量支持灵活配置。

## 🔧 配置结构

### 1. **基础配置**
```python
# config.py 中的 MCP_SERVER_CONFIG
{
    "debug": False,           # 调试模式
    "log_level": "INFO",      # 日志级别
    "host": "0.0.0.0",        # 服务器地址
    "port": 8000,             # 服务器端口
}
```

### 2. **路径配置**
```python
{
    "mount_path": "/",                          # 应用挂载路径
    "sse_path": "/mcp/k8s-server/sse",         # SSE端点路径
    "message_path": "/mcp/k8s-server/message/", # 消息端点路径
    "streamable_http_path": "/streamable",      # 流式HTTP路径
}
```

### 3. **行为配置**
```python
{
    "json_response": False,              # JSON响应模式
    "stateless_http": False,             # 无状态HTTP
    "warn_on_duplicate_resources": True, # 重复资源警告
    "warn_on_duplicate_tools": True,     # 重复工具警告
    "warn_on_duplicate_prompts": True,   # 重复提示警告
}
```

## 🌍 环境变量支持

所有配置都支持通过环境变量覆盖：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `MCP_DEBUG` | `false` | 调试模式开关 |
| `MCP_LOG_LEVEL` | `INFO` | 日志级别 |
| `MCP_HOST` | `0.0.0.0` | 服务器地址 |
| `MCP_PORT` | `8000` | 服务器端口 |
| `MCP_MOUNT_PATH` | `/` | 应用挂载路径 |
| `MCP_STREAMABLE_PATH` | `/streamable` | 流式HTTP路径 |
| `MCP_JSON_RESPONSE` | `false` | JSON响应模式 |
| `MCP_STATELESS_HTTP` | `false` | 无状态HTTP |
| `MCP_WARN_DUPLICATE_RESOURCES` | `true` | 重复资源警告 |
| `MCP_WARN_DUPLICATE_TOOLS` | `true` | 重复工具警告 |
| `MCP_WARN_DUPLICATE_PROMPTS` | `true` | 重复提示警告 |
| `MCP_DEPENDENCIES` | `` | 依赖列表（逗号分隔） |

## 📝 使用方式

### 1. **默认配置**
直接启动，使用 `config.py` 中的默认配置：
```bash
python main.py --transport sse --port 8000
```

### 2. **环境变量配置**
通过环境变量覆盖配置：
```bash
# Windows
set MCP_DEBUG=true
set MCP_LOG_LEVEL=DEBUG
python main.py --transport sse --port 8000

# Linux/Mac
export MCP_DEBUG=true
export MCP_LOG_LEVEL=DEBUG
python main.py --transport sse --port 8000
```

### 3. **环境变量文件**
创建 `.env` 文件：
```env
MCP_DEBUG=true
MCP_LOG_LEVEL=DEBUG
MCP_HOST=127.0.0.1
MCP_PORT=8001
```

## ✅ 优势

1. **✅ 统一管理**: 所有配置集中在 `config.py`
2. **✅ 环境变量支持**: 支持生产环境配置覆盖
3. **✅ 类型安全**: 自动类型转换和验证
4. **✅ 默认值**: 提供合理的默认配置
5. **✅ 文档化**: 每个配置项都有清晰的说明
6. **✅ 扩展性**: 易于添加新的配置项

## 🔄 迁移说明

**之前的方式**（硬编码在 `tools/__init__.py`）：
```python
mcp = FastMCP(
    "k8s-mcp-server",
    debug=False,
    log_level="INFO",
    # ... 大量硬编码参数
)
```

**现在的方式**（配置文件管理）：
```python
from config import MCP_SERVER_CONFIG
mcp = FastMCP("k8s-mcp-server", **MCP_SERVER_CONFIG)
```

这样的架构更加清晰、可维护，并且支持生产环境的灵活配置！
