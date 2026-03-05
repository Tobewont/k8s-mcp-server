# Kubernetes MCP Server

![python](https://img.shields.io/badge/python-3.11%2B-blue) ![k8s-version](https://img.shields.io/badge/k8s-v1.25%2B-orange) ![license](https://img.shields.io/badge/license-MIT-green)

基于 FastMCP 框架的 Kubernetes MCP Server，提供完整的 Kubernetes API 操作功能。

## 🔥 主要特性

- **纯 API 实现**：完全通过 Kubernetes Python Client 实现，无需依赖 kubectl 命令行工具
- **标准 MCP 协议**：基于 FastMCP 框架，遵循 MCP (Model Context Protocol) 标准
- **智能集群管理**：支持多集群配置管理，自动加载默认集群配置
- **全面的 K8s 操作**：支持 40 个工具函数，覆盖所有主要 Kubernetes 资源的完整 CRUD 操作
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

配置后重启 Cursor 或执行 **Developer: Reload Window**，即可在 MCP 工具列表中看到 40 个工具。

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
│   ├── k8s_api_service.py       # Kubernetes API 服务层
│   ├── k8s_advanced_service.py  # Kubernetes 进阶服务层（批量操作、备份恢复、RBAC、验证）
│   └── dynamic_resource_service.py  # 动态资源服务（DynamicClient，支持集群所有 API 资源及 CRD）
├── tools/
│   ├── __init__.py              # FastMCP 实例和工具模块导入
│   ├── k8s_tools.py             # 核心 K8s 资源管理工具 (5个工具)
│   ├── cluster_tools.py         # 多集群配置管理 (13个工具)
│   ├── diagnostic_tools.py      # 集群诊断工具 (6个工具)
│   ├── batch_tools.py           # 批量操作工具 (8个工具)
│   ├── backup_tools.py          # 备份恢复工具 (4个工具)
│   └── rbac_tools.py            # RBAC管理工具 (4个工具)
├── utils/
│   ├── __init__.py
│   ├── cluster_config.py        # 集群配置管理类
│   ├── context.py               # 上下文管理
│   ├── fastmcp_custom.py        # 自定义FastMCP类
│   └── lowlevel.py              # 底层工具函数
├── k8s/                         # Kubernetes 部署文件
│   ├── deployment.yaml          # 主要部署配置
│   ├── service.yaml             # 服务暴露配置
│   ├── configmap.yaml           # 配置管理
│   ├── pvc.yaml                 # 数据持久化
│   └── README.md                # 部署指南
├── data/
│   ├── clusters.json            # 集群配置存储
│   ├── kubeconfigs/             # kubeconfig 文件存储目录
│   └── copyfiles/               # Pod 文件拷贝本地保存目录
├── Dockerfile                   # 容器镜像构建文件
├── .dockerignore                # Docker 构建排除文件
├── config.py                    # 服务配置
├── main.py                      # 服务启动入口
└── pyproject.toml               # 依赖列表
```

### Service 层架构

服务层采用三层设计，职责分离、便于扩展：

| 服务 | 文件 | 角色 | 实现方式 | 覆盖范围 |
|------|------|------|----------|----------|
| **KubernetesAPIService** | k8s_api_service.py | 底层 API 封装 | 强类型 API（V1Api、AppsV1Api 等） | 内置资源（Pod、Deployment、Service 等） |
| **DynamicResourceService** | dynamic_resource_service.py | 动态资源操作 | DynamicClient，运行时发现 API | 任意资源（内置 + CRD + 未来新增） |
| **KubernetesAdvancedService** | k8s_advanced_service.py | 编排与业务层 | 组合上述两者 | 批量操作、备份恢复、验证等 |

**调用策略**：批量操作时优先使用预定义方法，若资源类型未命中则 fallback 到 `DynamicResourceService`，从而支持 CephFilesystem、KafkaTopic 等 CRD 及集群中所有可发现的 API 资源。

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
| 核心工具 | k8s_tools | 5 | 集群信息、Pod 日志（含 previous）、执行命令、Pod 文件拷贝、端口转发 |
| 集群管理 | cluster_tools | 13 | 集群导入/切换、kubeconfig 管理 |
| 诊断工具 | diagnostic_tools | 6 | 集群/节点/Pod 健康、资源使用、事件、节点排水 |
| 批量操作 | batch_tools | 8 | 批量增删改查、重启、发布操作、top 资源；支持集群所有 API 资源（含 CRD），`resource_types="all"` 可发现可用资源 |
| 备份恢复 | backup_tools | 4 | 命名空间/资源备份与恢复 |
| RBAC 管理 | rbac_tools | 4 | 角色模板、权限分析、冲突检查 |

**说明**：`list_clusters` 列出已导入的集群注册信息；`list_kubeconfigs` 列出 `data/kubeconfigs/` 目录下保存的 kubeconfig 文件。

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

#### 集群信息
- `get_cluster_info()` - 获取集群信息

#### Pod 操作工具
- `get_pod_logs()` - 获取 Pod 日志（支持 `previous` 获取上一实例日志）
- `copy_pod_file()` - Pod 与本地双向拷贝文件/目录，本地默认保存到 `data/copyfiles`
- `exec_pod_command()` - 在 Pod 中执行命令
- `port_forward()` - 配置端口转发到 Pod

### 集群管理工具 (cluster_tools.py)

- `import_cluster()` - 导入集群配置
- `list_clusters()` - 列出所有集群配置
- `get_cluster()` - 获取指定集群配置
- `delete_cluster()` - 删除集群配置
- `set_default_cluster()` - 设置默认集群
- `test_cluster_connection()` - 测试集群连接
- `get_default_cluster()` - 获取默认集群
- `save_kubeconfig()` - 保存 kubeconfig 文件
- `load_kubeconfig()` - 加载 kubeconfig 文件
- `list_kubeconfigs()` - 列出所有保存的 kubeconfig 文件
- `delete_kubeconfig()` - 删除 kubeconfig 文件
- `validate_kubeconfig()` - 验证 kubeconfig 文件
- `get_kubeconfig_info()` - 获取 kubeconfig 信息

### 诊断工具 (diagnostic_tools.py)

- `check_cluster_health()` - 检查集群健康状态
- `check_node_health()` - 检查节点健康状态
- `check_pod_health()` - 检查Pod健康状态（支持筛选失败Pod）
- `get_cluster_resource_usage()` - 获取集群资源使用情况（支持指定命名空间）
- `get_cluster_events()` - 获取集群事件
- `drain_node()` - 节点排水（cordon + 驱逐 Pod，跳过 DaemonSet/mirror pod）

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

### RBAC管理工具 (rbac_tools.py)

- `create_role_template(template_type, namespace, role_name)` - 创建角色模板（developer/admin/operator/readonly/deployer/monitor/debug）
- `analyze_serviceaccount_permissions()` - 分析 ServiceAccount 的权限
- `check_serviceaccount_permission_conflicts()` - 检查命名空间内 SA 权限冲突
- `list_role_serviceaccounts()` - 列出绑定到某角色的所有 ServiceAccount

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
- **Pod 文件拷贝**：`copy_pod_file` 支持 Pod 与本地双向拷贝，本地保存至 `data/copyfiles`
- **备份恢复**：支持命名空间和单个资源的备份恢复，按集群/命名空间/资源类型层级存储
- **RBAC管理**：完整的角色和权限管理，支持角色模板和用户绑定
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

// 创建角色模板（template_type: developer/admin/operator/readonly/deployer/monitor/debug）
{
  "method": "tools/call",
  "params": {
    "name": "create_role_template",
    "arguments": {
      "template_type": "developer",
      "namespace": "my-app",
      "role_name": "developer"
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
DATA_DIR=./data
KUBECONFIGS_DIR=./data/kubeconfigs
LOGS_DIR=./logs

# MCP配置
MCP_MESSAGE_PATH=/mcp/k8s-server/message/
MCP_SSE_PATH=/mcp/k8s-server/sse
MCP_STREAMABLE_PATH=/mcp/k8s-server/streamable  # Streamable HTTP 端点

# 日志配置
LOG_LEVEL=info
LOG_FILE=./logs/k8s-mcp-server.log
OPERATIONS_LOG_FILE=./logs/operations.log  # 写操作日志（create/update/delete/backup/restore 等）
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
async def my_new_tool(kubeconfig_path: str = None, namespace: str = None) -> str:
    """新工具描述"""
    try:
        k8s_service = KubernetesAPIService()
        # 自动加载配置：如果没有指定 kubeconfig_path，会自动使用默认集群
        k8s_service.load_config(kubeconfig_path=kubeconfig_path)
        
        # 解析命名空间：如果没有指定，会使用默认集群的命名空间
        namespace = _resolve_namespace(namespace)
        
        # 使用 k8s_service 进行 API 调用
        result = await k8s_service.some_api_call(namespace=namespace)
        
        return json.dumps({
            "success": True, 
            "data": result
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)
```

### 扩展 API 服务

在 `services/k8s_api_service.py` 中添加新的 API 方法：

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

### 4. 容器化部署

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

- ✅ **36 个工具函数**：涵盖所有主要 Kubernetes 资源
- ✅ **优雅删除支持**：部分删除函数支持 `grace_period_seconds` 参数
- ✅ **容器化支持**：提供 Docker 和 Kubernetes 部署
- ✅ **数据持久化**：支持配置和日志的持久化存储
- ✅ **健康检查**：提供完整的健康检查机制
- ✅ **多集群管理**：支持多集群配置和快速切换
- ✅ **批量操作**：支持21种资源类型的批量操作，包含事务回滚
- ✅ **RBAC管理**：完整的角色和权限管理系统
- ✅ **备份恢复**：支持命名空间和资源级别的备份恢复
- ✅ **变更验证预览**：自动验证所有写操作，显示具体变更内容和操作风险
- ✅ **交互式操作**：支持 Pod 命令执行和端口转发
- ✅ **扩展资源支持**：新增 HPA、NetworkPolicy、ResourceQuota 支持


## ⚠️ 注意事项

### CronJob 兼容性说明

- ❌ 本项目（k8s-mcp-server）**不支持 batch/v1beta1 CronJob API**。
- ✅ 仅适用于 Kubernetes v1.25 及以上版本（即只支持 batch/v1 版本的 CronJob 资源）。
- ⏫ 如果你的集群版本低于 v1.25，或仍在使用 batch/v1beta1，请升级集群或手动迁移 CronJob 资源。


## 🤝 贡献

欢迎贡献代码！请确保：

1. 遵循现有的代码风格
2. 添加适当的错误处理
3. 更新相关文档
4. 添加测试用例
5. 支持优雅删除机制（如适用）

## 📄 许可证

MIT License - 详见 [LICENSE](./LICENSE) 文件