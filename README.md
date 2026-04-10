# Kubernetes MCP Server

![python](https://img.shields.io/badge/python-3.11%2B-blue) ![k8s-version](https://img.shields.io/badge/k8s-v1.25%2B-orange) ![license](https://img.shields.io/badge/license-MIT-green)

**[English](README_EN.md)** | 中文

基于 FastMCP 框架的 Kubernetes MCP Server，提供完整的 Kubernetes API 操作功能。

## 🔥 主要特性

- **纯 API 实现**：完全通过 Kubernetes Python Client 实现，无需依赖 kubectl 命令行工具
- **标准 MCP 协议**：基于 FastMCP 框架，遵循 MCP (Model Context Protocol) 标准
- **智能集群管理**：支持多集群配置管理，自动加载默认集群配置
- **全面的 K8s 操作**：支持 35 个工具函数，覆盖所有主要 Kubernetes 资源的完整 CRUD 操作
- **多租户认证**：可选 JWT 认证，支持多用户数据隔离、权限 Profile 分级、Tool 可见性过滤
- **集群诊断**：提供集群健康检查、资源使用分析等诊断功能
- **配置管理**：支持 kubeconfig 文件的保存、切换和管理
- **双重传输协议**：同时支持 SSE 和 Stdio 两种传输方式
- **容器化部署**：支持 Docker 和 Kubernetes 部署，包含完整的 k8s 清单文件
- **资源备份恢复**：支持命名空间和单个资源的备份恢复，按集群/命名空间/资源类型层级存储
- **变更验证预览**：自动验证资源操作并显示具体的变更内容，提供操作前的详细预览

## ⚡ 快速开始

### 环境要求

- Python 3.11+
- 无需安装 kubectl（完全通过 Python API 实现）

### 安装依赖

```bash
# 使用uv
uv pip install -e .
```

### 启动服务

```bash
# 默认 stdio 模式启动（推荐用于MCP客户端）
python main.py

# 或明确指定 stdio 模式
python main.py --transport stdio

# SSE 模式启动（支持HTTP接口）
python main.py --transport sse --host 0.0.0.0 --port 8000

# 或使用 uvicorn 直接启动SSE服务
uvicorn tools:app --host 0.0.0.0 --port 8000
```

**Stdio 模式**：通过标准输入输出与 MCP 客户端通信（默认）

**SSE 模式**：通过 Server-Sent Events 接口（`http://localhost:8000/mcp/k8s-server/sse`）提供 HTTP 服务

**Streamable HTTP 模式**：单一端点同时支持 GET(SSE) 和 POST，推荐 Cursor 等客户端使用（`http://localhost:8000/mcp/k8s-server/streamable`）

#### Cursor MCP 配置

在 Cursor 全局 MCP 配置（如 `~/.cursor/mcp.json` 或项目 `.cursor/mcp.json`）中添加：

```json
{
  "mcpServers": {
    "k8s-mcp-server": {
      "url": "http://localhost:8000/mcp/k8s-server/streamable"
    }
  }
}
```

**启动服务**：`python main.py --transport sse --port 8000`

备选 Stdio 模式（无需先启动 HTTP 服务）：

```json
{
  "mcpServers": {
    "k8s-mcp-server": {
      "command": "python",
      "args": ["main.py", "--transport", "stdio"],
      "cwd": "项目路径"
    }
  }
}
```

配置后重启 Cursor 或执行 **Developer: Reload Window**，即可在 MCP 工具列表中看到工具。

> 未启用认证时可见 32 个工具；启用认证后 admin 角色可见全部 35 个，viewer 13 个、developer 21 个、operator 30 个。

### 容器化部署

```bash
# 构建 Docker 镜像
docker build -t k8s-mcp-server:latest .

# 运行容器
docker run -d --name k8s-mcp-server \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  k8s-mcp-server:latest

# 在 Kubernetes 中部署
kubectl apply -f k8s/
```

## 🏗️ 架构设计

### 核心组件

```
k8s-mcp-server/
├── services/
│   ├── __init__.py
│   ├── factory.py               # 服务实例工厂（按 kubeconfig_path 缓存）
│   ├── k8s_advanced_service.py  # Kubernetes 进阶服务（批量操作、备份恢复、RBAC、验证）
│   ├── dynamic_resource_service.py  # 动态资源服务（DynamicClient，支持 CRD 及任意 API 资源）
│   ├── k8s_api/                 # Kubernetes API 服务层（模块化）
│   │   ├── base.py, cluster_ops.py, pod_ops.py, workload_ops.py
│   │   ├── jobcronjob_ops.py, networking_storage_ops.py, service_config_ops.py
│   │   ├── autoscaling_policy_ops.py, rbac_ops.py, interactive_ops.py
│   │   └── resource_builders.py
│   └── k8s_advanced/            # 进阶服务逻辑（批量、备份、验证、RBAC）
│       ├── batch_ops.py, backup_restore.py, validation.py
│       ├── resource_conversion.py, rbac_advanced.py
│       └── base.py
├── tools/
│   ├── __init__.py              # FastMCP 实例和工具模块导入
│   ├── k8s_tools.py             # 核心 K8s 资源管理工具 (5个)
│   ├── cluster_tools.py         # 多集群配置管理 (9个)
│   ├── diagnostic_tools.py      # 集群诊断工具 (6个)
│   ├── batch_tools.py           # 批量操作工具 (8个)
│   ├── backup_tools.py          # 备份恢复工具 (4个)
│   └── auth_tools.py            # 认证与用户管理 (3个，仅认证模式可见)
├── utils/
│   ├── __init__.py
│   ├── cluster_config.py        # 集群配置管理类（支持多租户隔离）
│   ├── context.py               # 上下文管理
│   ├── fastmcp_custom.py        # 自定义 FastMCP（含 Tool 可见性过滤）
│   ├── auth_context.py          # 请求级用户上下文（contextvars）
│   ├── jwt_service.py           # JWT 签发/验证
│   ├── jwt_middleware.py        # ASGI JWT 认证中间件
│   ├── permission_profiles.py   # 权限 Profile 管理（内置 + 自定义）
│   ├── token_store.py           # JWT 签发记录持久化
│   ├── revocation_store.py      # JWT 撤销列表
│   ├── admin_routes.py          # 管理 API 路由
│   ├── k8s_helpers.py           # K8s 辅助函数
│   ├── k8s_parsers.py          # 参数解析
│   ├── param_parsers.py        # 参数解析
│   ├── operations_logger.py    # 操作日志
│   ├── backup_paths.py         # 备份路径
│   └── decorators.py, response.py, mcp_server.py
├── k8s/                         # Kubernetes 部署文件
│   ├── deployment.yaml          # 主要部署配置
│   ├── service.yaml             # 服务暴露配置
│   ├── configmap.yaml           # 配置管理
│   ├── pvc.yaml                 # 数据持久化
│   └── README.md                # 部署指南
├── data/
│   ├── clusters.json            # 集群配置存储
│   ├── kubeconfigs/             # kubeconfig 文件存储目录
│   ├── backup/                  # 备份存储（按集群/命名空间/资源类型层级）
│   └── copyfiles/               # Pod 文件拷贝本地保存目录
├── tests/                       # 回归测试
│   └── regression_test.py       # 同步/异步 37 个用例
├── docs/
│   └── TOOLS.md                 # 工具清单文档
├── Dockerfile                   # 容器镜像构建文件
├── .dockerignore                # Docker 构建排除文件
├── config.py                    # 服务配置
├── main.py                      # 服务启动入口
└── pyproject.toml               # 依赖列表
```

### Service 层架构

服务层采用三层设计，职责分离、便于扩展：

| 服务 | 位置 | 角色 | 实现方式 | 覆盖范围 |
|------|------|------|----------|----------|
| **KubernetesAPIService** | services/k8s_api/ | 底层 API 封装 | 强类型 API（V1Api、AppsV1Api 等），多 Mixin 模块化 | 内置资源（Pod、Deployment、Service 等） |
| **DynamicResourceService** | dynamic_resource_service.py | 动态资源操作 | DynamicClient，运行时发现 API | 任意资源（内置 + CRD + 未来新增） |
| **KubernetesAdvancedService** | k8s_advanced_service.py + k8s_advanced/ | 编排与业务层 | 组合上述两者及 BatchOps、BackupRestore、Validation 等 Mixin | 批量操作、备份恢复、验证等 |

**调用策略**：批量操作时优先使用预定义方法，若资源类型未命中则 fallback 到 `DynamicResourceService`，从而支持 CephFilesystem、KafkaTopic 等 CRD 及集群中所有可发现的 API 资源。服务实例通过 `services.factory.get_k8s_api_service()` / `get_k8s_advanced_service()` 获取，按 `kubeconfig_path` 缓存。

### 架构特点

1. **Service 层**：三层架构（API 层 + 动态层 + 编排层），内置资源与 CRD 统一入口
2. **Tool 层**：使用 `@mcp.tool` 装饰器定义 MCP 工具函数
3. **统一 MCP 实例**：所有工具共享同一个 FastMCP 实例
4. **双重传输**：同时支持 SSE 和 stdio 两种传输方式
5. **智能配置**：自动加载默认集群配置，无需每次指定 kubeconfig
6. **集群管理**：内置完整的多集群配置管理系统
7. **容器化支持**：提供 Docker 和 Kubernetes 部署支持

## 🛠️ 主要功能

### 工具分类总览

| 分类 | 模块 | 工具数 | 说明 |
|------|------|--------|------|
| 认证管理 | auth_tools | 3 | whoami、用户/Token 管理、权限 Profile 管理（仅认证模式可见） |
| 核心工具 | k8s_tools | 5 | 集群信息、Pod 日志（含 previous）、执行命令、Pod 文件拷贝、端口转发（含启停管理） |
| 集群管理 | cluster_tools | 9 | 集群导入/切换、kubeconfig 管理 |
| 诊断工具 | diagnostic_tools | 6 | 集群/节点/Pod 健康、资源使用、事件、节点管理（drain/cordon/uncordon） |
| 批量操作 | batch_tools | 8 | 批量增删改查、重启、发布操作、top 资源；支持集群所有 API 资源（含 CRD） |
| 备份恢复 | backup_tools | 4 | 命名空间/资源备份与恢复 |

**说明**：`list_clusters` 查看已导入的集群注册信息（省略 `name` 列出全部，指定 `name` 返回单个集群详情）；`list_kubeconfigs` 列出 `data/kubeconfigs/` 目录下保存的 kubeconfig 文件。

### 认证与用户管理 (auth_tools.py)

> 仅在 `MCP_AUTH_ENABLED=true` 时可见。

- `whoami()` - 查看当前用户身份、角色、Token 有效期、已授权的集群与权限
- `admin_manage_users(action, ...)` - 用户与 Token 管理（admin 全功能；operator 限 viewer/developer 权限和 user 角色 token）
- `admin_manage_profiles(action, ...)` - 权限 Profile 模板管理（查看/创建/更新/删除自定义 profile，仅 admin）

### K8s 资源管理 (batch_tools.py)

#### 批量操作工具
- `batch_list_resources()` - 批量查询资源；`resource_types="all"` 可列出集群所有可用 API 资源类型
- `batch_create_resources()` - 批量创建资源（支持事务回滚）
- `batch_update_resources()` - 批量更新资源
- `batch_delete_resources()` - 批量删除资源
- `batch_describe_resources()` - 批量获取资源详细信息
- `batch_restart_resources()` - 批量重启资源（Deployment、StatefulSet、DaemonSet）
- `batch_rollout_resources()` - 批量发布操作：status 查看状态、undo 回滚（支持指定 revision）、pause 暂停、resume 恢复
- `batch_top_resources()` - 批量查看 Node/Pod 的 CPU、内存使用（类似 kubectl top，依赖 metrics-server）

### 核心工具 (k8s_tools.py)

- `get_cluster_info()` - 获取集群信息（API 版本、服务器地址等）
- `get_pod_logs()` - 获取 Pod 日志（支持 `previous` 获取上一实例日志）
- `exec_pod_command()` - 在 Pod 中执行命令
- `copy_pod_files()` - Pod 文件读写：from_pod 将文件内容返回给客户端（支持 `local_path` 直接保存到本地，二进制文件自动解码），to_pod 将客户端内容或本地文件写入 Pod
- `port_forward()` - Pod 端口转发管理：`action="start"` 启动转发、`action="stop"` 停止指定转发、`action="list"` 列出活跃会话；认证模式下按用户隔离

### 集群管理工具 (cluster_tools.py)

- `import_cluster()` - 导入集群配置（含 kubeconfig 保存）
- `list_clusters(name?)` - 查看集群配置（省略 name 列出全部，指定 name 返回详情）
- `delete_cluster()` - 删除集群配置
- `set_default_cluster()` - 设置默认集群
- `test_cluster_connection()` - 测试集群连接
- `load_kubeconfig()` - 加载 kubeconfig 文件（支持脱敏）
- `list_kubeconfigs()` - 列出所有保存的 kubeconfig 文件
- `delete_kubeconfig()` - 删除 kubeconfig 文件
- `get_kubeconfig_info()` - 获取 kubeconfig 详情或验证格式

### 诊断工具 (diagnostic_tools.py)

- `check_cluster_health()` - 检查集群健康状态，可选 `include_rbac_check` 附带 RBAC 权限冲突检测
- `check_node_health()` - 检查节点健康状态
- `check_pod_health()` - 检查 Pod 健康状态（支持筛选失败 Pod）
- `get_cluster_resource_usage()` - 获取集群资源使用情况（支持指定命名空间）
- `get_cluster_events()` - 获取集群事件
- `manage_node()` - 节点运维管理：`action="drain"` 排水（cordon + 驱逐 Pod）、`action="cordon"` 标记不可调度、`action="uncordon"` 恢复调度

#### 支持的批量操作资源类型

**支持集群中所有可发现的 API 资源**（含 CRD）。以下为内置优化类型，其他类型通过 DynamicClient 自动发现并操作。

**工作负载资源**：
- Deployment - 部署管理
- StatefulSet - 有状态应用
- DaemonSet - 守护进程集
- Job - 批处理任务（支持labels和annotations更新）
- CronJob - 定时任务

**网络与服务**：
- Service - 服务暴露
- Ingress - 入口控制器
- NetworkPolicy - 网络策略

**配置与存储**：
- ConfigMap - 配置管理
- Secret - 敏感信息管理
- StorageClass - 存储类
- PersistentVolume - 持久化卷
- PersistentVolumeClaim - 持久化卷声明
- ResourceQuota - 资源配额

**权限与身份管理**：
- Namespace - 命名空间
- ServiceAccount - 服务账户
- Role - 角色（命名空间级别）
- ClusterRole - 集群角色
- RoleBinding - 角色绑定（命名空间级别）
- ClusterRoleBinding - 集群角色绑定

**自动扩缩容**：
- HorizontalPodAutoscaler (HPA) - 水平Pod自动扩缩容

#### 批量操作特性

- **原子性操作**：支持事务性批量操作，失败时自动回滚
- **统一接口**：所有资源类型使用相同的批量操作接口
- **灵活参数**：支持完整资源定义和简化参数两种方式
- **错误处理**：详细的错误信息和成功/失败统计
- **向后兼容**：不影响现有的单资源操作功能

### 备份和恢复工具 (backup_tools.py)

- `backup_namespace()` - 备份整个命名空间
- `backup_resource()` - 备份特定资源
- `restore_from_backup()` - 从备份恢复资源
- `list_backups()` - 列出备份文件

### 变更验证预览系统

系统内置了自动的资源操作验证和预览功能，自动集成到所有写操作中：

#### 核心特性
- **自动验证**：所有创建、更新、删除操作自动执行验证检查
- **具体预览**：显示详细的变更内容，而非模糊的数量描述
- **操作支持性检查**：验证特定资源类型是否支持指定操作
- **风险提示**：删除操作显示不可逆风险警告

#### 预览输出示例
- **具体变更**：`labels.version: 1.0 → 2.0`
- **新增内容**：`data.redis.conf: 新增 = host: redis\nport: 6379`
- **RBAC规则**：`rules: 新增规则 [batch] jobs -> get,list,create`
- **删除提醒**：`⚠️ 将删除资源 configmap/test，此操作不可逆`

#### 支持的资源类型
涵盖所有主要 Kubernetes 资源的验证和预览：
- **工作负载**：Deployment, StatefulSet, DaemonSet, Job, CronJob
- **网络服务**：Service, Ingress, NetworkPolicy
- **配置存储**：ConfigMap, Secret, PVC, PV, StorageClass, ResourceQuota
- **权限管理**：ServiceAccount, Role, ClusterRole, RoleBinding, ClusterRoleBinding
- **集群资源**：Namespace, Node
- **自动扩缩容**：HorizontalPodAutoscaler (HPA)

### 🔥 特殊功能

- **优雅删除**：部分删除函数支持 `grace_period_seconds` 参数，实现优雅或强制删除
- **批量操作**：所有列表函数支持 `label_selector` 参数进行筛选
- **数据持久化**：支持配置和数据的持久化存储
- **健康检查**：提供容器健康检查端点
- **批量资源操作**：支持批量创建、更新、删除多个资源，支持事务回滚
- **发布管理**：支持 Deployment/StatefulSet/DaemonSet 的 status、undo（含指定 revision）、pause、resume
- **资源监控**：`batch_top_resources` 查看 Node/Pod 的 CPU、内存使用（依赖 metrics-server）
- **Pod 文件读写**：`copy_pod_files` 支持 Pod 文件双向传输，内容直接通过响应/参数传递，不依赖服务端磁盘
- **备份恢复**：支持命名空间和单个资源的备份恢复，按集群/命名空间/资源类型层级存储
- **权限 Profile**：内置 viewer/developer/operator/admin 四级权限模板，工具可见性与 K8s RBAC 严格匹配；低权限用户调用集群级工具时优雅降级（返回部分结果或友好提示）；支持自定义 Profile、自动创建 K8s RBAC 资源；operator 可委托管理 viewer/developer 用户
- **变更验证预览**：自动验证所有写操作并显示具体变更内容，提供详细的操作预览

## 📝 使用示例

### 通过 MCP 客户端调用

所有功能都可以通过 MCP 客户端调用。系统支持自动加载默认集群配置：

```json
// 批量列出资源（使用默认集群配置）
{
  "method": "tools/call",
  "params": {
    "name": "batch_list_resources",
    "arguments": {
      "resource_types": "pods,nodes,namespaces",
      "namespace": "default"
    }
  }
}

// 批量删除资源（支持 grace_period_seconds）
{
  "method": "tools/call",
  "params": {
    "name": "batch_delete_resources",
    "arguments": {
      "resources": "[{\"kind\":\"Pod\",\"name\":\"my-pod\"}]",
      "namespace": "default",
      "grace_period_seconds": 30
    }
  }
}

// 批量创建资源
{
  "method": "tools/call",
  "params": {
    "name": "batch_create_resources",
    "arguments": {
      "resources": "[{\"kind\": \"Deployment\", \"metadata\": {\"name\": \"app1\"}, \"spec\": {\"name\": \"app1\", \"image\": \"nginx:latest\", \"replicas\": 3}}, {\"kind\": \"Service\", \"metadata\": {\"name\": \"app1-svc\"}, \"spec\": {\"name\": \"app1-svc\", \"selector\": {\"app\": \"app1\"}, \"ports\": [{\"port\": 80}]}}]",
      "namespace": "default"
    }
  }
}

// 备份命名空间
{
  "method": "tools/call",
  "params": {
    "name": "backup_namespace",
    "arguments": {
      "namespace": "my-app",
      "include_secrets": true
    }
  }
}

// 批量操作会自动显示验证和预览信息
// 更新操作会显示具体的变更内容，如：
// "📋 预览变化:"
// "   • replicas: 3 → 5"
// "   • labels.version: 1.0 → 2.0"

// 批量创建资源
{
  "method": "tools/call",
  "params": {
    "name": "batch_create_resources",
    "arguments": {
      "resources": [
        {
          "apiVersion": "apps/v1",
          "kind": "Deployment",
          "metadata": {"name": "app1", "namespace": "default"},
          "spec": {"replicas": 2, "selector": {"matchLabels": {"app": "app1"}}, "template": {"metadata": {"labels": {"app": "app1"}}, "spec": {"containers": [{"name": "app1", "image": "nginx:1.20"}]}}}
        },
        {
          "apiVersion": "v1",
          "kind": "Service",
          "metadata": {"name": "app1-svc", "namespace": "default"},
          "spec": {"selector": {"app": "app1"}, "ports": [{"port": 80, "targetPort": 80}]}
        }
      ],
      "namespace": "default"
    }
  }
}

// 批量更新Job的labels和annotations
{
  "method": "tools/call",
  "params": {
    "name": "batch_update_resources",
    "arguments": {
      "resources": [
        {
          "apiVersion": "batch/v1",
          "kind": "Job",
          "metadata": {
            "name": "job1",
            "namespace": "default",
            "labels": {"app": "batch-job", "version": "v2", "updated": "true"},
            "annotations": {"description": "Updated batch job", "last-modified": "2025-01-08"}
          }
        }
      ],
      "namespace": "default"
    }
  }
}

// 完全使用默认配置（集群和命名空间）
{
  "method": "tools/call",
  "params": {
    "name": "batch_list_resources",
    "arguments": {
      "resource_types": "pods",
      "namespace": "default"
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

## 🐳 Docker 部署

### 构建镜像

```bash
# 构建镜像
docker build -t k8s-mcp-server:latest .

# 运行容器
docker run -d --name k8s-mcp-server \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  k8s-mcp-server:latest
```

### 环境变量

```bash
docker run -d \
  -e SSE_HOST=0.0.0.0 \
  -e SSE_PORT=8000 \
  -e LOG_LEVEL=INFO \
  -e DATA_DIR=/app/data \
  -e LOGS_DIR=/app/logs \
  k8s-mcp-server:latest
```

## ☸️ Kubernetes 部署

### 快速部署

```bash
# 部署所有资源
kubectl apply -f k8s/

# 查看部署状态
kubectl get pods -l app=k8s-mcp-server
kubectl get svc k8s-mcp-server
```

### 部署组件

- **Deployment**: 主要应用部署，支持数据持久化
- **Service**: 服务暴露，支持 ClusterIP、NodePort、Ingress 方式
- **ConfigMap**: 环境变量和配置管理
- **PersistentVolumeClaim**: 数据和日志持久化
- **RBAC**: 完整的权限配置

### 数据持久化

```yaml
# 数据存储卷
- name: data-volume
  persistentVolumeClaim:
    claimName: k8s-mcp-server-data

# 日志存储卷
- name: logs-volume
  persistentVolumeClaim:
    claimName: k8s-mcp-server-logs
```

### 健康检查

```yaml
livenessProbe:
  tcpSocket:
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  tcpSocket:
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
```

## 🔧 配置

### 环境变量

```bash
# SSE 服务配置
SSE_HOST=0.0.0.0
SSE_PORT=8000

# 数据存储目录（自动创建）
DATA_DIR=./data                 # 集群配置、kubeconfig、备份等数据根目录
LOGS_DIR=./logs

# MCP 路径配置
MCP_MESSAGE_PATH=/mcp/k8s-server/message/
MCP_SSE_PATH=/mcp/k8s-server/sse
MCP_STREAMABLE_PATH=/mcp/k8s-server/streamable  # Streamable HTTP 端点

# 日志级别
LOG_LEVEL=info

# 认证配置（可选，默认不启用）
MCP_AUTH_ENABLED=false          # 设为 true 启用 JWT 认证和多租户隔离
MCP_JWT_SECRET=                 # JWT 签名密钥（启用认证时必填）
MCP_JWT_ALGORITHM=HS256         # JWT 算法
MCP_TOKEN_MAX_EXPIRY=7776000    # Token 最大有效期（秒），默认 90 天
MCP_ADMIN_API_PREFIX=/admin     # 管理 API 路由前缀
```

### kubeconfig 管理

系统会将 kubeconfig 文件保存在 `data/kubeconfigs/` 目录下，支持：

- 多集群配置管理
- 配置文件的增删改查
- 集群间快速切换
- 自动加载默认集群配置

### 自动加载功能

系统提供智能的配置自动加载机制：

1. **默认集群**：设置一个集群为默认集群后，所有工具都会自动使用该集群的配置
2. **默认命名空间**：每个集群可以设置默认的命名空间
3. **参数优先级**：明确指定的参数 > 默认集群配置 > 系统默认值

这意味着您可以：
- 导入集群配置一次，后续无需每次指定 kubeconfig
- 大部分操作无需指定任何参数，直接使用默认配置

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
- 默认集群自动加载
- 集群连接测试和验证

### 智能配置系统

提供完整的配置管理体系：

- **自动发现**：自动加载默认集群和命名空间配置
- **参数简化**：大部分操作无需指定冗余参数
- **配置验证**：完整的 kubeconfig 格式验证
- **错误处理**：友好的错误提示和自动回退机制

### 优雅删除机制

支持 Kubernetes 标准的优雅删除：

- **grace_period_seconds**: 设置优雅关闭等待时间
- **立即删除**: 设置为 0 实现强制删除
- **默认行为**: 使用 Kubernetes 默认的优雅删除策略

## 📚 开发指南

### 添加新工具

1. 在对应的工具模块中添加函数
2. 使用 `@mcp.tool` 装饰器
3. 通过 `KubernetesAPIService` 进行 API 调用

示例：

```python
@mcp.tool()
async def my_new_tool(kubeconfig_path: str = None, namespace: str = "default") -> str:
    """新工具描述"""
    try:
        from services.factory import get_k8s_api_service
        from utils.response import json_success, json_error
        k8s_service = get_k8s_api_service(kubeconfig_path)  # 按 kubeconfig_path 缓存
        result = await k8s_service.some_api_call(namespace=namespace)
        return json_success({"data": result})
    except Exception as e:
        return json_error(str(e))
```

### 扩展 API 服务

在 `services/k8s_api/` 的相应 Mixin 模块（如 `pod_ops.py`、`workload_ops.py`）中添加新的 API 方法：

```python
async def new_api_method(self, param1: str, grace_period_seconds: int = None) -> Dict[str, Any]:
    """新的 API 方法"""
    try:
        # 支持优雅删除
        body = client.V1DeleteOptions(grace_period_seconds=grace_period_seconds) if grace_period_seconds is not None else None
        
        # 使用 self.v1_api, self.apps_v1_api 等进行 API 调用
        result = self.v1_api.some_kubernetes_api(body=body)
        return self._format_result(result)
    except ApiException as e:
        raise Exception(f"API 调用失败: {e.reason}")
```

## 🚀 快速入门指南

### 1. 导入集群配置

```bash
# 启动服务
python main.py

# 在 MCP 客户端中导入集群
import_cluster(
    name="生产环境",
    kubeconfig="/path/to/kubeconfig",
    namespace="default",
    is_default=True
)
```

### 2. 使用自动加载功能

一旦设置了默认集群，所有操作都可以简化：

```bash
# 批量列出 Pod（自动使用默认集群和命名空间）
batch_list_resources(resource_types="pods", namespace="default")

# 查看集群信息
get_cluster_info()

# 检查集群健康状态
check_cluster_health()

# 批量创建资源（含 Deployment）
batch_create_resources(resources="[{...}]", namespace="default")
```

### 3. 管理多集群

```bash
# 查看所有集群
list_clusters()

# 切换默认集群
set_default_cluster(name="测试环境")

# 测试集群连接
test_cluster_connection(name="生产环境")
```

### 4. 多租户认证（可选）

适用于团队/线上多人使用场景。

```bash
# 1. 启动服务（启用认证）
MCP_AUTH_ENABLED=true MCP_JWT_SECRET=your-secret-key \
  python main.py --transport sse --host 0.0.0.0 --port 8000

# 2. 生成管理员 Token
MCP_JWT_SECRET=your-secret-key mcp-admin bootstrap
# 输出：MCP_BOOTSTRAP_ADMIN_JWT=eyJhbGci...

# 3. 为用户签发 Token
MCP_JWT_SECRET=your-secret-key mcp-admin issue --user alice --expires 604800

# 4. 通过 MCP Tool 为用户分配集群权限（管理员在 MCP 对话中执行）
# admin_manage_users(action="grant_access", user_id="alice",
#   cluster_name="prod", namespace="default", profile="developer")
```

用户在 MCP 客户端配置 Token（以 Cursor 为例）：

```json
{
  "mcpServers": {
    "k8s-mcp-server": {
      "url": "http://your-server:8000/mcp/k8s-server/streamable",
      "headers": {
        "Authorization": "Bearer eyJhbGci..."
      }
    }
  }
}
```

#### 权限 Profile

| Profile | 可见工具 | K8s 权限 | 管理能力 |
|---------|---------|---------|---------|
| `viewer` | 13 个（只读 + 日志 + 连接测试 + 切换集群） | get/list/watch + pods/log | — |
| `developer` | 21 个（读写 + exec） | CRUD 工作负载 + pods/log、exec、portforward | — |
| `operator` | 30 个（+ 备份恢复、集群诊断、节点排水、用户管理） | 命名空间全操作 + rbac 只读 + ClusterRole（nodes/namespaces/events/metrics/drain） | 可管理 viewer/developer 用户 |
| `admin` | 35 个（全部，含集群级操作） | 使用 K8s admin kubeconfig，天然集群全权限 | 全部 |

#### 安全机制

- **路径注入防护**：`kubeconfig_path` 仅允许指向当前用户自己的数据目录，阻止跨用户读取
- **输入校验**：`user_id`、`cluster_name`、`namespace` 等标识符强制格式校验（字母数字、连字符、下划线、点），防止路径穿越
- **operator 权限隔离**：operator 不能自我授权、不能操作高权限用户、不能签发 admin token。operator 自身的 K8s 操作权限限定在被授权的命名空间内，但其用户管理能力（`grant_access`）属于 MCP 平台级委派，可跨命名空间为用户分配 viewer/developer 权限（底层使用 admin kubeconfig 创建 RBAC），适合作为平台维护人员统一管理多团队接入
- **自定义 Profile 限制**：自定义 profile 不允许包含 `user_manage`/`profile_manage`/`cluster_ops` 保留分类或管理工具
- **Token 有效期上限**：默认最大 90 天（可通过 `MCP_TOKEN_MAX_EXPIRY` 调整）
- **撤销列表自动清理**：过期的 jti 会自动从撤销表中移除，防止无限增长
- **审计日志**：所有管理操作（签发/撤销 Token、授权/撤销集群权限）均记录到 `operations.log`
- **Operator RBAC 代理**：operator 调用 `grant_access` 时自动使用 admin 的高权限 kubeconfig 创建 K8s RBAC 资源
- **ClusterRole 联动**：operator profile 的 `grant_access` 额外创建 ClusterRole + ClusterRoleBinding（nodes、namespaces、events、metrics、pods/eviction），`revoke_access` 同步清理
- **集群级工具优雅降级**：`get_cluster_info` 对无集群级权限的用户返回部分结果（跳过 nodes/namespaces）；`get_cluster_events` 在 ns=all 失败时提示指定命名空间；`test_cluster_connection` 使用 VersionApi 无需集群级权限
- **K8s 服务缓存失效**：`grant_access`/`revoke_access` 执行后自动失效目标用户的 K8s 客户端缓存，避免旧 token 被后续请求复用
- **RBAC 模板即时同步**：`grant_access` 使用 K8s API 直接创建/替换 Role，确保模板变更立即生效，无需手动删除旧 Role
- **端口转发线程隔离**：port_forward 使用独立的 ApiClient 实例，避免 monkey-patch 污染共享 API 客户端
- **Tar slip 防护**：从 Pod 拷贝文件时校验 tar 成员路径，防止路径穿越写入目标目录之外

#### 管理 REST API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/admin/tokens/issue` | POST | 签发 Token |
| `/admin/tokens/revoke` | POST | 撤销 Token |
| `/admin/tokens/revoked` | GET | 查看撤销列表 |
| `/admin/tokens/cleanup` | POST | 清理过期撤销记录 |
| `/admin/users` | GET | 列出所有用户 |

#### CLI 管理工具

```bash
mcp-admin bootstrap          # 生成管理员 Token
mcp-admin issue --user bob   # 签发用户 Token
mcp-admin revoke --jti xxx   # 撤销单个 Token
mcp-admin revoke-user --user bob  # 撤销用户全部 Token
mcp-admin list-users         # 列出所有用户
mcp-admin grant --user bob --cluster prod --namespace default --profile developer  # 分配权限
mcp-admin revoke-access --user bob --cluster prod --namespace default  # 撤销权限
mcp-admin list-profiles      # 列出所有 Profile
```

### 5. 容器化部署

```bash
# 构建并部署到 Kubernetes
docker build -t k8s-mcp-server:latest .
kubectl apply -f k8s/

# 查看部署状态
kubectl get pods -l app=k8s-mcp-server
kubectl logs -f deployment/k8s-mcp-server
```

## 🔄 更新说明

### 最新版本特性

- ✅ **35 个工具函数**：涵盖所有主要 Kubernetes 资源（含 CRD 动态发现）
- ✅ **优雅删除支持**：部分删除函数支持 `grace_period_seconds` 参数
- ✅ **容器化支持**：提供 Docker 和 Kubernetes 部署
- ✅ **数据持久化**：支持配置、日志及 Pod 拷贝文件（data/copyfiles）的持久化存储
- ✅ **健康检查**：提供完整的健康检查机制
- ✅ **多集群管理**：支持多集群配置和快速切换
- ✅ **批量操作**：支持集群所有可发现 API 资源的批量操作，包含事务回滚
- ✅ **发布管理**：支持 Deployment/StatefulSet/DaemonSet 的 status、undo（含指定 revision）、pause、resume
- ✅ **资源监控**：batch_top_resources 查看 Node/Pod CPU、内存使用（依赖 metrics-server）
- ✅ **Pod 文件读写**：copy_pod_files 支持 Pod 文件双向传输，支持 `local_path` 直接落盘（二进制自动解码，无中间 base64 文件）
- ✅ **多租户认证**：JWT 认证、权限 Profile 分级、Tool 可见性过滤、K8s RBAC 自动联动、输入校验与审计日志
- ✅ **备份恢复**：支持命名空间和资源级别的备份恢复
- ✅ **变更验证预览**：自动验证所有写操作，显示具体变更内容和操作风险
- ✅ **交互式操作**：支持 Pod 命令执行、端口转发（含启停管理）、日志（含 previous 上一实例）
- ✅ **多集群 kubeconfig**：batch、backup、rbac 等工具均支持 `kubeconfig_path` 参数指定目标集群


## ⚠️ 注意事项

### CronJob 兼容性说明

- ❌ 本项目（k8s-mcp-server）**不支持 batch/v1beta1 CronJob API**。
- ✅ 仅适用于 Kubernetes v1.25 及以上版本（即只支持 batch/v1 版本的 CronJob 资源）。
- ⏫ 如果你的集群版本低于 v1.25，或仍在使用 batch/v1beta1，请升级集群或手动迁移 CronJob 资源。


## 🧪 回归测试

```bash
# 运行全部回归测试（需可用的 K8s 集群）
python -m tests.regression_test

# 仅运行同步测试（无需集群）
REGRESSION_SKIP_ASYNC=1 python -m tests.regression_test
```

- **同步测试**（7 个）：导入、资源构建器、参数解析、kubeconfig 验证、tools 导出等
- **异步测试**（30 个）：覆盖 MCP 工具的实际调用，需集群连接
- **备份测试隔离**：`backup_namespace`、`backup_resource` 的回归测试使用临时目录，测试后自动删除，不影响正式备份数据

## 🤝 贡献

欢迎贡献代码！请确保：

1. 遵循现有的代码风格
2. 添加适当的错误处理
3. 更新相关文档
4. 添加测试用例
5. 支持优雅删除机制（如适用）

## 📄 许可证

MIT License - 详见 [LICENSE](./LICENSE) 文件