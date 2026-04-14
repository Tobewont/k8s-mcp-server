# Kubernetes Cluster Management

通过 K8s MCP Server 管理 Kubernetes 集群。支持多种 MCP 连接方式（mcporter、Cursor 内置 MCP、SSE / Streamable HTTP），覆盖集群信息查询、工作负载 CRUD、诊断、备份恢复、节点运维等 35 个工具。

---

## 环境变量

使用本 Skill 前，用户需要提供以下信息（按连接方式选填）：

| 变量 | 说明 | 示例 |
|------|------|------|
| `K8S_MCP_URL` | MCP Server 的 SSE / Streamable HTTP 地址 | `http://localhost:8000/mcp/k8s-server/streamable` |
| `K8S_MCP_TOKEN` | JWT 认证 Token（MCP Server 启用认证时必填） | `eyJhbGciOi...` |
| `K8S_MCP_SERVER` | mcporter 中注册的 MCP Server 名称 | `k8s-mcp-server` |

---

## MCP 连接方式

本 Skill 支持三种方式调用 K8s MCP Server，按优先级自动选择：

### 方式一：Cursor 内置 MCP（推荐）

如果 K8s MCP Server 已在 Cursor 的 MCP 配置中注册（`~/.cursor/mcp.json` 或项目 `.cursor/mcp.json`），直接使用 `CallMcpTool` 调用：

```json
{
  "mcpServers": {
    "k8s-mcp-server": {
      "url": "http://localhost:8000/mcp/k8s-server/streamable"
    }
  }
}
```

调用方式：

```
CallMcpTool(server="k8s-mcp-server", toolName="<工具名>", arguments={...})
```

带认证时，需要在 MCP 配置的 `headers` 中加上 Token：

```json
{
  "mcpServers": {
    "k8s-mcp-server": {
      "url": "http://localhost:8000/mcp/k8s-server/streamable",
      "headers": {
        "Authorization": "Bearer <K8S_MCP_TOKEN>"
      }
    }
  }
}
```

### 方式二：mcporter 命令行

mcporter 配置（`~/.mcporter/config.json` 或项目下 `.mcporter.json`）：

```json
{
  "mcpServers": {
    "k8s-mcp-server": {
      "url": "http://localhost:8000/mcp/k8s-server/streamable",
      "transport": "http",
      "headers": {
        "Authorization": "Bearer <K8S_MCP_TOKEN>"
      }
    }
  }
}
```

调用格式：

```bash
mcporter call k8s-mcp-server.<工具名> --args '<JSON参数>'
```

无认证时省略 `headers`。查看可用工具列表：

```bash
mcporter tools k8s-mcp-server
```

### 方式三：stdio 模式（本地直连）

无需 HTTP 服务，直接通过 stdio 启动 MCP Server：

Cursor MCP 配置：

```json
{
  "mcpServers": {
    "k8s-mcp-server": {
      "command": "python",
      "args": ["main.py", "--transport", "stdio"],
      "cwd": "<k8s-mcp-server项目路径>"
    }
  }
}
```

mcporter 配置：

```json
{
  "mcpServers": {
    "k8s-mcp-server": {
      "command": "python",
      "args": ["main.py", "--transport", "stdio"],
      "cwd": "<k8s-mcp-server项目路径>",
      "transport": "stdio"
    }
  }
}
```

---

## 连接方式选择规则

1. 如果当前 Cursor 环境已配置 `k8s-mcp-server` 的 MCP Server（可通过 `CallMcpTool` 直接调用），**优先使用方式一**。
2. 如果用户提供了 `K8S_MCP_SERVER` 环境变量且 `mcporter` 命令可用，**使用方式二**。
3. 如果以上都不可用，提示用户按上述任一方式配置后重试。
4. 需要 Token 认证时，任何方式都需要用户提供 `K8S_MCP_TOKEN`。

---

## 工具清单（35 个）

### 核心工具（k8s_tools）— 5 个

| 工具名 | 用途 | 关键参数 |
|--------|------|----------|
| `get_cluster_info` | 获取集群信息（API版本、地址等） | `cluster_name` |
| `get_pod_logs` | 获取 Pod 日志 | `name`, `namespace`, `lines`, `container`, `previous` |
| `exec_pod_command` | 在 Pod 内执行命令 | `pod_name`, `command`(数组), `namespace`, `container` |
| `copy_pod_files` | Pod 文件读写 | `pod_name`, `namespace`, `direction`(from_pod/to_pod), `remote_path` |
| `port_forward` | Pod 端口转发 | `action`(start/stop/list), `pod_name`, `namespace`, `pod_port`, `local_port` |

### 集群配置管理（cluster_tools）— 9 个

| 工具名 | 用途 | 关键参数 |
|--------|------|----------|
| `import_cluster` | 导入集群（kubeconfig） | `name`, `kubeconfig`, `is_default` |
| `list_clusters` | 查看集群列表或单个详情 | `name`(可选) |
| `delete_cluster` | 删除集群配置 | `name` |
| `set_default_cluster` | 设置默认集群 | `name` |
| `test_cluster_connection` | 测试连接 | `cluster_name` |
| `load_kubeconfig` | 加载 kubeconfig 内容 | `name`, `mask_sensitive` |
| `list_kubeconfigs` | 列出已保存的 kubeconfig | — |
| `delete_kubeconfig` | 删除 kubeconfig | `name` |
| `get_kubeconfig_info` | kubeconfig 详情或校验 | `name`或`content` |

### 诊断工具（diagnostic_tools）— 6 个

| 工具名 | 用途 | 关键参数 |
|--------|------|----------|
| `check_cluster_health` | 集群健康检查 | `cluster_name`, `include_rbac_check` |
| `check_node_health` | 节点健康检查 | `node_name`(可选), `cluster_name` |
| `check_pod_health` | Pod 健康检查 | `namespace`, `only_failed`, `cluster_name` |
| `get_cluster_resource_usage` | 集群资源使用 | `cluster_name` |
| `get_cluster_events` | 集群事件 | `namespace`, `event_type`, `limit`, `cluster_name` |
| `manage_node` | 节点运维（drain/cordon/uncordon） | `node_name`, `action`, `cluster_name` |

### 批量操作（batch_tools）— 8 个

| 工具名 | 用途 | 关键参数 |
|--------|------|----------|
| `batch_list_resources` | 批量列出资源 | `resource_types`(JSON数组或"all"), `namespace`, `cluster_name` |
| `batch_create_resources` | 批量创建资源 | `resources`(JSON), `namespace`, `rollback_on_failure` |
| `batch_update_resources` | 批量更新资源 | `resources`(JSON), `namespace`, `cluster_name` |
| `batch_delete_resources` | 批量删除资源 | `resources`(JSON), `namespace`, `grace_period_seconds` |
| `batch_describe_resources` | 批量获取资源详情 | `resource_specs`(JSON), `namespace`, `cluster_name` |
| `batch_restart_resources` | 批量重启 Deployment/StatefulSet/DaemonSet | `resources`(JSON), `namespace`, `cluster_name` |
| `batch_rollout_resources` | 发布操作（status/undo/pause/resume） | `operations`(JSON), `namespace`, `cluster_name` |
| `batch_top_resources` | Node/Pod CPU/内存使用 | `resource_types`(JSON), `namespace`, `cluster_name` |

### 备份恢复（backup_tools）— 4 个

| 工具名 | 用途 | 关键参数 |
|--------|------|----------|
| `backup_namespace` | 备份整个命名空间 | `namespace`, `include_secrets`, `cluster_name` |
| `backup_resource` | 备份指定资源 | `kind`, `name`, `namespace`, `cluster_name` |
| `restore_from_backup` | 从备份恢复 | `backup_path`, `namespace`, `cluster_name` |
| `list_backups` | 列出备份文件 | `cluster_name`, `namespace` |

### 认证管理（auth_tools，需启用认证）— 3 个

| 工具名 | 用途 |
|--------|------|
| `whoami` | 查看当前用户身份与权限 |
| `admin_manage_users` | 用户/Token管理（issue_token, revoke_token, grant_access 等） |
| `admin_manage_profiles` | 权限 Profile 模板管理 |

---

## 常用操作示例

以下示例使用 Cursor MCP（`CallMcpTool`）方式。mcporter 方式将 `CallMcpTool(...)` 替换为 `mcporter call k8s-mcp-server.<工具名> --args '<JSON>'` 即可。

### 查看集群列表

```
CallMcpTool(server="k8s-mcp-server", toolName="list_clusters", arguments={})
```

### 列出某命名空间下的 Deployment 和 Pod

```
CallMcpTool(server="k8s-mcp-server", toolName="batch_list_resources", arguments={
  "resource_types": "[\"deployments\",\"pods\"]",
  "namespace": "production"
})
```

### 更新 Deployment 镜像

```
CallMcpTool(server="k8s-mcp-server", toolName="batch_update_resources", arguments={
  "resources": "[{\"kind\":\"Deployment\",\"apiVersion\":\"apps/v1\",\"metadata\":{\"name\":\"my-app\"},\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"my-app\",\"image\":\"my-registry/my-app:v2.0\"}]}}}}]",
  "namespace": "production",
  "cluster_name": "my-cluster"
})
```

### 检查发布状态

```
CallMcpTool(server="k8s-mcp-server", toolName="batch_rollout_resources", arguments={
  "operations": "[{\"kind\":\"Deployment\",\"name\":\"my-app\",\"action\":\"status\"}]",
  "namespace": "production"
})
```

### 回滚 Deployment

```
CallMcpTool(server="k8s-mcp-server", toolName="batch_rollout_resources", arguments={
  "operations": "[{\"kind\":\"Deployment\",\"name\":\"my-app\",\"action\":\"undo\"}]",
  "namespace": "production"
})
```

### 扩缩容

```
CallMcpTool(server="k8s-mcp-server", toolName="batch_update_resources", arguments={
  "resources": "[{\"kind\":\"Deployment\",\"apiVersion\":\"apps/v1\",\"metadata\":{\"name\":\"my-app\"},\"spec\":{\"replicas\":5}}]",
  "namespace": "production"
})
```

### 查看 Pod 日志

```
CallMcpTool(server="k8s-mcp-server", toolName="get_pod_logs", arguments={
  "name": "my-app-pod-xyz",
  "namespace": "production",
  "lines": 200
})
```

### 在 Pod 中执行命令

```
CallMcpTool(server="k8s-mcp-server", toolName="exec_pod_command", arguments={
  "pod_name": "my-app-pod-xyz",
  "command": ["df", "-h"],
  "namespace": "production"
})
```

### 集群健康检查

```
CallMcpTool(server="k8s-mcp-server", toolName="check_cluster_health", arguments={
  "cluster_name": "my-cluster"
})
```

### 查看节点资源使用

```
CallMcpTool(server="k8s-mcp-server", toolName="batch_top_resources", arguments={
  "resource_types": "[\"nodes\",\"pods\"]",
  "namespace": "production"
})
```

### 备份命名空间

```
CallMcpTool(server="k8s-mcp-server", toolName="backup_namespace", arguments={
  "namespace": "production",
  "include_secrets": false,
  "cluster_name": "my-cluster"
})
```

### 节点排水（维护前）

```
CallMcpTool(server="k8s-mcp-server", toolName="manage_node", arguments={
  "node_name": "worker-node-3",
  "action": "drain",
  "cluster_name": "my-cluster"
})
```

---

## 参数约定

### cluster_name 与 kubeconfig_path

所有工具都支持可选的 `cluster_name` 或 `kubeconfig_path` 来指定目标集群：

- **省略两者**：使用 MCP Server 上配置的默认集群
- **指定 `cluster_name`**：使用 MCP Server 已导入的指定集群（通过 `list_clusters` 查看）
- **指定 `kubeconfig_path`**：直接使用服务端本地 kubeconfig 文件

### 批量操作的 JSON 参数

`batch_*` 系列工具的 `resources`、`resource_types`、`operations`、`resource_specs` 参数均为 **JSON 字符串**（不是原生对象），例如：

- `resource_types`: `"[\"pods\",\"deployments\"]"` 或 `"pods"`（单个类型） 或 `"all"`
- `resources`: `"[{\"kind\":\"Deployment\",...}]"`
- `operations`: `"[{\"kind\":\"Deployment\",\"name\":\"xxx\",\"action\":\"status\"}]"`

### 命名空间

- 大多数工具默认 `namespace="default"`，操作前需确认实际命名空间
- 列出所有命名空间：`batch_list_resources(resource_types="[\"namespaces\"]")`

---

## 操作流程建议

### 镜像更新发布

1. `list_clusters` — 确认目标集群
2. `batch_list_resources` — 定位目标 namespace 下的 Deployment
3. `batch_describe_resources` — 查看当前镜像版本
4. `batch_update_resources` — 更新镜像
5. `batch_rollout_resources`（action=status）— 等待发布完成，确认所有副本就绪

### 故障排查

1. `check_cluster_health` — 整体健康概览
2. `check_pod_health`（only_failed=true）— 找到异常 Pod
3. `get_pod_logs` — 查看日志
4. `batch_describe_resources` — 查看 Pod/Deployment 详情和事件
5. `exec_pod_command` — 进入容器排查

### 节点运维

1. `check_node_health` — 确认节点状态
2. `batch_top_resources`（resource_types=nodes）— 查看资源使用
3. `manage_node`（action=cordon）— 标记不可调度
4. `manage_node`（action=drain）— 排水驱逐 Pod
5. 运维完毕后：`manage_node`（action=uncordon）— 恢复调度

---

## 注意事项

1. **写操作谨慎**：`batch_update_resources`、`batch_delete_resources`、`manage_node(drain)` 等会直接修改集群状态，操作前应先用 `batch_describe_resources` 确认目标正确。
2. **CRD 支持**：批量操作（batch_list/create/update/delete/describe）支持集群内任意已注册的 API 资源（含 CRD），未在预定义映射中的资源类型会自动通过 DynamicClient 处理。
3. **认证模式**：MCP Server 启用认证（`MCP_AUTH_ENABLED=true`）时，不同角色（viewer/developer/operator/admin）可见的工具数量不同。未认证时可见 32 个工具。
4. **多集群**：MCP Server 支持管理多个集群，通过 `import_cluster` 导入、`set_default_cluster` 切换默认集群、或在每次调用时指定 `cluster_name`。
