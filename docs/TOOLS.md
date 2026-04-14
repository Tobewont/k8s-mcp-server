# k8s-mcp-server 工具清单（35 个）

> **认证模式说明**：`MCP_AUTH_ENABLED=false`（默认）时可见 32 个工具（隐藏 3 个 auth 工具）；
> `MCP_AUTH_ENABLED=true` 时根据用户 Profile 过滤可见工具：viewer 13 个、developer 21 个、operator 30 个、admin 35 个。

---

## Service 层与动态资源支持

批量操作工具（batch_list/create/update/delete/describe）采用**双层服务**：

- **k8s_api_service**：强类型 API，处理内置资源（Deployment、Service、ConfigMap 等）
- **dynamic_resource_service**：DynamicClient，处理任意资源（含 CRD，如 CephFilesystem、KafkaTopic）

未在预定义映射中的资源类型会自动 fallback 到 `dynamic_resource_service`，无需为每个 CRD 单独实现。使用 `batch_list_resources(resource_types="all")` 可列出集群所有可发现的 API 资源类型。

---

## 一、认证与用户管理 (auth_tools.py) — 3 个

> 仅在 `MCP_AUTH_ENABLED=true` 时可见。

| 工具名 | 作用 | 所需角色 |
|--------|------|----------|
| `whoami` | 查看当前用户身份（ID、角色、Token 剩余有效期、已授权的集群与权限） | 任意已认证用户 |
| `admin_manage_users` | 用户与 Token 管理：签发/撤销 Token、授权/撤销集群权限、检查用户实际 K8s 权限 | admin / operator |
| `admin_manage_profiles` | 权限 Profile 模板管理：查看/创建/更新/删除自定义 profile | admin |

### admin_manage_users 支持的 action

| action | 说明 | 必需参数 | operator 限制 |
|--------|------|----------|--------------|
| `issue_token` | 为用户签发 JWT | user_id, [role, expires_in_seconds] | 只能签发 role=user；不能自我签发；不能为高权限用户签发 |
| `revoke_token` | 按 jti 撤销单个 Token | jti | 不能撤销 admin 角色 token；不能撤销高权限用户的 token |
| `revoke_user` | 撤销某用户全部 Token | user_id | 不能操作拥有 admin/operator 权限的用户 |
| `list_users` | 列出所有已签发用户及状态摘要 | — | 自动过滤 admin/operator 级别用户 |
| `get_user` | 查看某用户的签发记录与权限授权 | user_id | 不能查看 admin/operator 级别用户 |
| `grant_access` | 为用户分配集群/命名空间权限（自动创建 K8s Role+RoleBinding+SA） | user_id, cluster_name, namespace, profile | 只能分配 viewer/developer；不能自我授权；使用 admin kubeconfig 创建 K8s RBAC |
| `revoke_access` | 撤销用户的集群/命名空间权限（自动清理 K8s 资源） | user_id, cluster_name, namespace | 只能撤销 viewer/developer |
| `inspect` | 查看用户在 K8s 中的实际 ServiceAccount 权限 | user_id, cluster_name, namespace | 无限制 |

> **输入校验**：`user_id`、`cluster_name`、`namespace`、`profile` 均需满足格式要求（字母数字开头，只允许字母、数字、连字符、下划线、点，长度 1-253），防止路径穿越攻击。
>
> **审计日志**：`issue_token`、`revoke_token`、`revoke_user`、`grant_access`、`revoke_access` 操作均记录到调用者的 `operations.log`。

### admin_manage_profiles 支持的 action

| action | 说明 | 必需参数 |
|--------|------|----------|
| `list` | 列出所有 profile（内置 + 自定义） | — |
| `get` | 查看某个 profile 详情 | name |
| `create` | 创建自定义 profile（不可包含 user_manage/profile_manage/cluster_ops 保留分类） | name, description, k8s_role_template, [mcp_tool_categories, extra_tools] |
| `update` | 更新自定义 profile（内置不可改，不可添加保留分类） | name, [description, k8s_role_template, ...] |
| `delete` | 删除自定义 profile（内置不可删） | name |

---

## 二、核心工具 (k8s_tools.py) — 5 个

| 工具名 | 作用 |
|--------|------|
| `get_cluster_info` | 获取 Kubernetes 集群信息（API 版本、服务器地址等） |
| `get_pod_logs` | 获取 Pod 日志，支持指定行数、容器、previous 上一实例 |
| `exec_pod_command` | 在 Pod 内执行命令（如 `["ls", "-la"]`） |
| `copy_pod_files` | Pod 文件读写：from_pod 读取文件内容返回客户端（支持 `local_path` 直接保存到本地目录，二进制自动解码），to_pod 将客户端内容或本地文件写入 Pod（需 Pod 内有 tar） |
| `port_forward` | Pod 端口转发管理：`action=start` 启动、`action=stop` 停止指定会话、`action=list` 列出活跃会话（认证模式下按用户隔离） |

---

## 三、集群与配置管理 (cluster_tools.py) — 9 个

**说明**：`list_clusters` 列出已导入的集群注册信息（clusters.json），指定 `name` 时返回单个集群详情；`list_kubeconfigs` 列出 `data/kubeconfigs/` 目录下保存的 kubeconfig 文件。

| 工具名 | 作用 |
|--------|------|
| `import_cluster` | 导入集群配置（`kubeconfig` 参数传入**服务端文件路径**或内容）。导入时自动校验客户端证书与私钥是否匹配 |
| `list_clusters` | 查看集群配置：省略 `name` 列出全部，指定 `name` 返回该集群详情 |
| `delete_cluster` | 删除集群配置 |
| `set_default_cluster` | 设置默认集群 |
| `test_cluster_connection` | 测试集群连接（自动刷新该集群的服务缓存，从磁盘重新加载 kubeconfig，确保使用最新凭据） |
| `load_kubeconfig` | 加载已保存的 kubeconfig 内容，支持 `mask_sensitive=True` 脱敏 |
| `list_kubeconfigs` | 列出所有已保存的 kubeconfig 文件 |
| `delete_kubeconfig` | 删除已保存的 kubeconfig 文件 |
| `get_kubeconfig_info` | 获取 kubeconfig 详细信息，或传 content 参数验证格式 |

---

## 四、诊断工具 (diagnostic_tools.py) — 6 个

| 工具名 | 作用 |
|--------|------|
| `check_cluster_health` | 检查集群健康（API、节点、系统 Pod），可选 `include_rbac_check` 附带 RBAC 权限冲突检测 |
| `check_node_health` | 检查节点健康（单节点或全部） |
| `check_pod_health` | 检查 Pod 健康，支持 `only_failed` 筛选异常 Pod |
| `get_cluster_resource_usage` | 获取集群资源使用（CPU/内存、节点利用率等） |
| `get_cluster_events` | 获取集群事件，支持按类型过滤和数量限制 |
| `manage_node` | 节点运维管理：`action=drain` 排水（cordon + 驱逐 Pod）、`action=cordon` 标记不可调度、`action=uncordon` 恢复调度 |

> 注：`get_cluster_info` 归属 k8s_tools.py（核心工具），与 `check_cluster_health` 的区别——前者返回集群元信息，后者做健康检查。

---

## 五、批量操作 (batch_tools.py) — 8 个

**支持集群中所有可发现的 API 资源**（含 CRD）。`resource_types="all"` 可列出集群所有可用资源类型。

| 工具名 | 作用 |
|--------|------|
| `batch_list_resources` | 批量列出资源（如 `["pods","nodes","namespaces"]`） |
| `batch_create_resources` | 批量创建资源，支持失败回滚 |
| `batch_update_resources` | 批量更新资源（含扩缩容、标签等） |
| `batch_delete_resources` | 批量删除资源，支持 `grace_period_seconds` |
| `batch_describe_resources` | 批量获取资源详情 |
| `batch_restart_resources` | 批量重启 Deployment/StatefulSet/DaemonSet |
| `batch_rollout_resources` | 批量发布操作：status/undo/pause/resume |
| `batch_top_resources` | 查看 Node/Pod 的 CPU、内存使用（类似 kubectl top） |

---

## 六、备份恢复 (backup_tools.py) — 4 个

| 工具名 | 作用 |
|--------|------|
| `backup_namespace` | 备份整个命名空间（可选是否包含 Secret） |
| `backup_resource` | 备份指定资源 |
| `restore_from_backup` | 从备份文件恢复资源 |
| `list_backups` | 列出备份文件（可按集群/命名空间过滤），仅读本地目录 |

---

## 权限 Profile × 工具分类矩阵

每个 Profile 包含若干工具分类，决定用户可见的工具范围。**分类设计原则：每个分类内的工具都能被引用它的 Profile 实际执行（K8s RBAC 权限匹配）。**

| 分类 | 包含工具数 | K8s 权限要求 | viewer | developer | operator | admin |
|------|-----------|-------------|--------|-----------|----------|-------|
| `read_basic` | 13 | 命名空间 get/list/watch + pods/log（`get_cluster_info` / `get_cluster_events` 按权限优雅降级；`test_cluster_connection` / `set_default_cluster` 为本地操作或 VersionApi，无需集群级权限） | ✅ | ✅ | ✅ | ✅ |
| `write_workload` | 5 | 命名空间 CRUD 工作负载 | ❌ | ✅ | ✅ | ✅ |
| `pod_exec` | 3 | pods/exec + pods/portforward 子资源 | ❌ | ✅ | ✅ | ✅ |
| `cluster_manage` | 4 | 无（本地操作） | ❌ | ❌ | ❌ | ✅ |
| `ops` | 3 | 命名空间 get + create（备份恢复）+ ClusterRole namespaces（operator） | ❌ | ❌ | ✅ | ✅ |
| `cluster_ops` | 5 | ClusterRole 级别（nodes、namespaces、events、metrics） | ❌ | ❌ | ✅ | ✅ |
| `user_manage` | 1 | 无（MCP 管理操作） | ❌ | ❌ | ✅ | ✅ |
| `profile_manage` | 1 | 无（MCP 管理操作） | ❌ | ❌ | ❌ | ✅ |
| **可见工具总数** | | | **13** | **21** | **30** | **35** |

### 分类详情

- **read_basic** (13)：whoami, list_clusters, list_kubeconfigs, get_kubeconfig_info, batch_list_resources, batch_describe_resources, get_cluster_info, get_pod_logs, check_pod_health, get_cluster_events, list_backups, test_cluster_connection, set_default_cluster
- **write_workload** (5)：batch_create_resources, batch_update_resources, batch_delete_resources, batch_restart_resources, batch_rollout_resources
- **pod_exec** (3)：exec_pod_command, copy_pod_files, port_forward
- **cluster_manage** (4)：import_cluster, delete_cluster, load_kubeconfig, delete_kubeconfig
- **ops** (3)：backup_namespace, backup_resource, restore_from_backup
- **cluster_ops** (5)：check_cluster_health, check_node_health, get_cluster_resource_usage, batch_top_resources, manage_node
- **user_manage** (1)：admin_manage_users（operator 受限：仅 viewer/developer 权限和 user 角色 token；operator 的 grant_access 可跨命名空间，属于 MCP 平台级委派，底层使用 admin kubeconfig）
- **profile_manage** (1)：admin_manage_profiles

> **自定义 Profile 保留分类**：`user_manage`、`profile_manage`、`cluster_ops` 不允许在自定义 profile 中使用（前两者防止提权，cluster_ops 需 ClusterRole 级别权限，命名空间 Role 无法授权）。

### 内置 Profile 与 K8s RBAC 映射

| Profile | 说明 | K8s 角色模板 | 模板包含的 Pod 子资源 |
|---------|------|-------------|---------------------|
| `viewer` | 命名空间只读 | readonly（get/list/watch + pods/log） | pods/log |
| `developer` | 读写工作负载 + exec/port-forward + 切换集群 | deployer（CRUD + pods/log、exec、portforward） | pods/log, pods/exec, pods/portforward |
| `operator` | 开发者 + 备份恢复、集群诊断、节点排水 + 管理 viewer/developer 用户 | operator（命名空间全操作 + rbac 只读 + ClusterRole: nodes/namespaces/events/metrics/drain） | pods/log, pods/exec, pods/portforward |
| `admin` | 全部工具 + 集群级操作（节点、指标） | admin（namespace 全资源；使用 K8s admin kubeconfig） | 全部（`resources: *`） |

> **注意**：readonly/deployer 模板创建的是 Namespace Role，无法访问集群级资源。`get_cluster_info` 和 `get_cluster_events` 对低权限用户优雅降级（返回部分结果或提示指定命名空间），`test_cluster_connection` 使用 VersionApi 无需集群级权限。operator 模板额外创建 ClusterRole + ClusterRoleBinding，授予 nodes（get/list/watch/patch）、namespaces（get/list/create）、events（get/list）、pods/eviction（create）、metrics.k8s.io（get/list）权限，命名空间内还有 rbac roles/rolebindings 的 get/list（用于备份）。admin 用户使用 K8s 管理员 kubeconfig，天然具有集群全权限。

---

## 操作日志（log_operation）

仅**写操作**记录到 `data/users/<user_id>/operations.log`（每用户独立），读操作不记录。

| 记录 | 不记录 |
|------|--------|
| import_cluster, delete_cluster, set_default_cluster | list_clusters |
| delete_kubeconfig | load_kubeconfig, list_kubeconfigs, get_kubeconfig_info |
| copy_pod_files, backup_*, restore_from_backup | list_backups |
| batch_create/update/delete/restart_resources | batch_list, batch_describe, batch_top |
| batch_rollout（仅 undo/pause/resume） | batch_rollout（action=status） |
| manage_node（drain/cordon/uncordon） | check_*, get_cluster_events, get_cluster_resource_usage |
| admin_manage_users: issue_token, revoke_token, revoke_user, grant_access, revoke_access | admin_manage_users: list_users, get_user, inspect |
| REST API: issue_token, revoke_token/user, list_users, list_revoked, cleanup_revoked | — |

## 响应格式与约定

### 批量操作部分成功

`batch_create_resources`、`batch_update_resources`、`batch_delete_resources` 在**部分成功**时返回 `json_partial_success`，包含 `partial: true`、`success_count`、`failed_count`、成功项与失败项列表。

### 回归测试与备份隔离

回归测试中 `backup_namespace` 与 `backup_resource` 的测试会备份到临时目录，测试结束后自动删除，不影响正式备份目录 `data/backup/`。

---

## 安全机制

### 路径安全

- **kubeconfig_path 白名单**：`resolve_kubeconfig_path` 仅允许访问当前用户自己的数据目录（`data/users/<user_id>/`），使用 `os.path.realpath` 解析后检查，防止符号链接和 `..` 穿越
- **标识符格式校验**：`user_id`、`cluster_name`、`namespace`、`profile` 在进入 `admin_manage_users` 前强制校验，只允许 `[a-zA-Z0-9][a-zA-Z0-9._-]{0,252}` 格式

### 权限隔离

- **operator 自我操作禁止**：operator 不能给自己签发 token 或分配集群权限
- **operator 越级操作禁止**：operator 不能签发 admin token、不能为拥有 operator/admin 权限的用户签发 token、不能撤销高权限用户的 token
- **operator RBAC 代理**：operator 调用 `grant_access`/`revoke_access` 时忽略 `kubeconfig_path` 参数，自动使用 admin 的高权限 kubeconfig，因为 operator 自身的 K8s 权限通常不含 RBAC 资源创建能力
- **ClusterRole 联动**：当 profile 模板定义了集群级规则（如 operator 的 nodes/metrics），`grant_access` 自动创建 ClusterRole + ClusterRoleBinding；`revoke_access` 通过 `managed-by=k8s-mcp-server` 标签匹配并清理
- **K8s 客户端缓存失效**：`grant_access`/`revoke_access` 执行后自动失效目标用户的 K8s 服务缓存，避免旧 token 被后续请求复用导致 401；`import_cluster`/`delete_cluster` 操作后同样失效当前用户缓存；`test_cluster_connection` 测试前自动失效该集群的服务缓存并从磁盘重新加载 kubeconfig，确保外部更新（如 `kubectl cp` 替换文件）立即生效
- **import_cluster 证书校验**：导入时自动校验 `client-certificate-data` 与 `client-key-data` 是否匹配（通过 `ssl.SSLContext.load_cert_chain`），不匹配立即拒绝
- **RBAC 模板即时同步**：`grant_access` 使用 `rbac_v1_api.create/replace_namespaced_role` 直接操作 K8s API（绕过带验证层的高级方法），确保 RBAC 模板变更立即生效
- **端口转发线程隔离**：`port_forward` 使用独立的 `ApiClient` 实例处理 WebSocket 连接，避免 `portforward()` 的 monkey-patch 污染共享 API 客户端导致并发请求失败
- **Tar slip 防护**：`copy_from_pod` 在解压前校验 tar 成员路径，拒绝包含 `../` 等路径穿越的恶意 tar 内容
- **自定义 Profile 保护**：自定义 profile 不允许包含 `user_manage`/`profile_manage`/`cluster_ops` 保留分类，也不允许通过 `extra_tools` 添加 `admin_manage_users`/`admin_manage_profiles`

### Token 管理

- **有效期上限**：默认最大 90 天（环境变量 `MCP_TOKEN_MAX_EXPIRY` 可调），MCP Tool 和 REST API 均强制检查
- **撤销列表清理**：`cleanup_expired()` 清理已超过最大 token 生命周期的撤销记录；`revoke_jti` 每 100 次写入自动触发惰性清理；也可通过 `POST /admin/tokens/cleanup` 手动触发
- **过期 token 正确处理**：`_user_has_admin_tokens` 同时检查 token 状态、过期时间和撤销表，确保过期/撤销的 admin token 不会错误地阻止 operator 操作

### 审计

- 所有管理操作（`issue_token`、`revoke_token`、`revoke_user`、`grant_access`、`revoke_access`）记录到调用者的 `data/users/<user_id>/operations.log`
- REST API 端点（`issue_token`、`revoke_token/user`、`list_users`、`list_revoked`、`cleanup_revoked`）均记录审计日志
