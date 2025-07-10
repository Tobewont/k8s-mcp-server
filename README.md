# Kubernetes MCP Server

基于 FastMCP 框架的 Kubernetes 集群管理服务器，提供完整的 Kubernetes API 操作功能。

## 🔥 主要特性

- **纯 API 实现**：完全通过 Kubernetes Python Client 实现，无需依赖 kubectl 命令行工具
- **标准 MCP 协议**：基于 FastMCP 框架，遵循 MCP (Model Context Protocol) 标准
- **多集群支持**：支持管理多个 Kubernetes 集群的配置
- **全面的 K8s 操作**：支持 Pod、Deployment、Service、Node 等资源的完整 CRUD 操作
- **集群诊断**：提供集群健康检查、资源使用分析等诊断功能
- **配置管理**：支持 kubeconfig 文件的保存、切换和管理

## ⚡ 快速开始

### 环境要求

- Python 3.8+
- 无需安装 kubectl（完全通过 Python API 实现）

### 安装依赖

```bash
# 使用pip
pip install -e .

# 或使用uv
uv pip install -e .
```

### 启动服务

```bash
# 开发模式启动
python main.py

# 或使用 uvicorn 直接启动
uvicorn tools:app --host 0.0.0.0 --port 8001
```

服务启动后，MCP 客户端可以通过 SSE 接口（`http://localhost:8001/sse`）连接。

## 🏗️ 架构设计

### 核心组件

```
k8s-mcp-server/
├── services/
│   ├── __init__.py
│   └── k8s_api_service.py       # Kubernetes API 服务层
├── tools/
│   ├── __init__.py              # FastMCP 实例
│   ├── k8s_tools.py             # 核心 K8s 资源管理工具
│   ├── cluster_tools.py         # 多集群配置管理
│   ├── config_tools.py          # kubeconfig 文件管理
│   └── diagnostic_tools.py      # 集群诊断工具
├── config.py                    # 服务配置
├── main.py                      # 服务启动入口
└── pyproject.toml               # 依赖列表
```

### 架构特点

1. **Service 层**：`KubernetesAPIService` 封装所有 Kubernetes API 操作
2. **Tool 层**：使用 `@mcp.tool` 装饰器定义 MCP 工具函数
3. **统一 MCP 实例**：所有工具共享同一个 FastMCP 实例
4. **SSE 通信**：通过 Server-Sent Events 与 MCP 客户端通信

## 🛠️ 主要功能

### K8s 资源管理 (k8s_tools.py)

#### Pod 管理
- `list_pods()` - 列出 Pod
- `describe_pod()` - 获取 Pod 详情
- `get_pod_logs()` - 获取 Pod 日志
- `delete_pod()` - 删除 Pod

#### Deployment 管理
- `list_deployments()` - 列出 Deployment
- `describe_deployment()` - 获取 Deployment 详情
- `scale_deployment()` - 扩缩容 Deployment
- `delete_deployment()` - 删除 Deployment

#### Service 管理
- `list_services()` - 列出 Service
- `describe_service()` - 获取 Service 详情
- `delete_service()` - 删除 Service

#### 节点和集群管理
- `list_nodes()` - 列出节点
- `describe_node()` - 获取节点详情
- `list_namespaces()` - 列出命名空间
- `create_namespace()` - 创建命名空间
- `delete_namespace()` - 删除命名空间
- `get_cluster_info()` - 获取集群信息

### 集群诊断 (diagnostic_tools.py)

- `check_cluster_health()` - 集群整体健康检查
- `check_node_health()` - 节点健康检查
- `check_pod_health()` - Pod 健康检查
- `check_resource_usage()` - 资源使用分析
- `get_cluster_events()` - 获取集群事件

### 配置管理 (config_tools.py & cluster_tools.py)

- `save_kubeconfig()` - 保存 kubeconfig 文件
- `list_kubeconfigs()` - 列出已保存的配置
- `get_kubeconfig_content()` - 获取配置内容
- `delete_kubeconfig()` - 删除配置
- `set_current_cluster()` - 设置当前活跃集群

## 📝 使用示例

### 通过 MCP 客户端调用

所有功能都可以通过 MCP 客户端调用，例如：

```json
{
  "method": "tools/call",
  "params": {
    "name": "list_pods",
    "arguments": {
      "namespace": "default",
      "kubeconfig_path": "/path/to/kubeconfig"
    }
  }
}
```

### 响应格式

所有工具都返回标准化的响应格式：

```json
{
  "success": true,
  "pods": [...],
  "count": 5,
  "namespace": "default"
}
```

## 🔧 配置

### 环境变量

```bash
# SSE 服务配置
SSE_HOST=0.0.0.0
SSE_PORT=8000

# 数据存储目录
DATA_DIR=./data
KUBECONFIG_DIR=./data/kubeconfigs
```

### kubeconfig 管理

系统会将 kubeconfig 文件保存在 `data/kubeconfigs/` 目录下，支持：

- 多集群配置管理
- 配置文件的增删改查
- 集群间快速切换

## 🔍 依赖说明

### 核心依赖

- **fastmcp**: MCP 协议实现框架
- **kubernetes**: Kubernetes Python 客户端库
- **pyyaml**: YAML 配置文件解析
- **pydantic**: 数据验证和序列化
- **uvicorn**: ASGI 服务器

### 特别说明

❌ **不依赖 kubectl**：本项目完全通过 Kubernetes Python Client API 实现，无需安装 kubectl 命令行工具

✅ **仅需 kubeconfig**：只需要有效的 kubeconfig 文件即可连接和管理 Kubernetes 集群

## 🚀 高级功能

### 集群健康监控

系统提供全方位的集群健康检查：

- 节点状态监控
- 系统 Pod 健康检查
- API 服务器连通性检查
- 资源使用率分析
- 事件日志收集

### 资源分析

提供详细的资源使用分析：

- CPU/内存请求和限制统计
- 集群资源利用率计算
- 资源优化建议

### 多集群管理

支持管理多个 Kubernetes 集群：

- 集群配置存储和管理
- 快速切换集群上下文
- 集群列表和状态展示

## 📚 开发指南

### 添加新工具

1. 在对应的工具模块中添加函数
2. 使用 `@mcp.tool` 装饰器
3. 通过 `KubernetesAPIService` 进行 API 调用

示例：

```python
@mcp.tool
def my_new_tool(kubeconfig_path: str = None) -> Dict[str, Any]:
    """新工具描述"""
    try:
        k8s_service = KubernetesAPIService()
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        # 使用 k8s_service 进行 API 调用
        result = k8s_service.some_api_call()
        
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### 扩展 API 服务

在 `services/k8s_api_service.py` 中添加新的 API 方法：

```python
def new_api_method(self, param1: str) -> Dict[str, Any]:
    """新的 API 方法"""
    try:
        # 使用 self.v1_api, self.apps_v1_api 等进行 API 调用
        result = self.v1_api.some_kubernetes_api()
        return self._format_result(result)
    except ApiException as e:
        raise Exception(f"API 调用失败: {e.reason}")
```

## 🤝 贡献

欢迎贡献代码！请确保：

1. 遵循现有的代码风格
2. 添加适当的错误处理
3. 更新相关文档
4. 添加测试用例

## 📄 许可证

MIT License - 详见 LICENSE 文件 