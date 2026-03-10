# k8s-mcp-server 工具清单（40 个）

## 回归测试与备份隔离

回归测试（`python -m tests.regression_test`）中，`backup_namespace` 与 `backup_resource` 的测试会备份到临时目录，测试结束后自动删除，**不影响正式备份目录** `data/backup/`。

---

## Service 层与动态资源支持

批量操作工具（batch_list/create/update/delete/describe）采用**双层服务**：

- **k8s_api_service**：强类型 API，处理内置资源（Deployment、Service、ConfigMap 等）
- **dynamic_resource_service**：DynamicClient，处理任意资源（含 CRD，如 CephFilesystem、KafkaTopic）

未在预定义映射中的资源类型会自动 fallback 到 `dynamic_resource_service`，无需为每个 CRD 单独实现。使用 `batch_list_resources(resource_types="all")` 可列出集群所有可发现的 API 资源类型。

---

## 一、核心工具 (k8s_tools.py) - 5 个


| 工具名                | 作用                                |
| ------------------ | --------------------------------- |
| `get_cluster_info` | 获取 Kubernetes 集群信息（API 版本、服务器地址等） |
| `get_pod_logs`     | 获取 Pod 日志，支持指定行数、容器、previous 上一实例 |
| `exec_pod_command` | 在 Pod 内执行命令（如 `["ls", "-la"]`）    |
| `copy_pod_file`    | Pod 与本地双向拷贝文件/目录，本地默认保存到 data/copyfiles（需 Pod 内有 tar） |
| `port_forward`     | 将本地端口转发到 Pod 端口                   |


---

## 二、集群与配置管理 (cluster_tools.py) - 13 个

**说明**：`list_clusters` 列出已导入的集群注册信息（clusters.json）；`list_kubeconfigs` 列出 `data/kubeconfigs/` 目录下保存的 kubeconfig 文件。

| 工具名                       | 作用                              |
| ------------------------- | ------------------------------- |
| `import_cluster`          | 导入集群配置（kubeconfig 内容或路径），可设为默认  |
| `list_clusters`           | 列出所有已导入的集群                      |
| `get_cluster`             | 获取指定集群的配置信息                     |
| `delete_cluster`          | 删除集群配置                          |
| `set_default_cluster`     | 设置默认集群                          |
| `test_cluster_connection` | 测试集群连接是否正常                      |
| `get_default_cluster`     | 获取当前默认集群                        |
| `save_kubeconfig`         | 保存 kubeconfig 文件到本地             |
| `load_kubeconfig`         | 加载已保存的 kubeconfig 内容，支持 `mask_sensitive=True` 脱敏 token/证书 |
| `list_kubeconfigs`        | 列出所有已保存的 kubeconfig 文件          |
| `delete_kubeconfig`       | 删除已保存的 kubeconfig 文件            |
| `validate_kubeconfig`     | 验证 kubeconfig 格式是否有效（参数 content：kubeconfig 文件内容） |
| `get_kubeconfig_info`     | 获取 kubeconfig 的详细信息（集群、上下文、用户等） |


---

## 三、诊断工具 (diagnostic_tools.py) - 6 个


| 工具名                          | 作用                                  |
| ---------------------------- | ----------------------------------- |
| `check_cluster_health`       | 检查集群健康（API、节点、系统 Pod）并给出建议          |
| `check_node_health`          | 检查节点健康（单节点或全部）                      |
| `check_pod_health`           | 检查 Pod 健康，支持 `only_failed` 筛选异常 Pod |
| `get_cluster_resource_usage` | 获取集群资源使用（CPU/内存、节点利用率等）             |
| `get_cluster_events`         | 获取集群事件，支持按类型过滤和数量限制                 |
| `drain_node`                 | 节点排水（cordon + 驱逐 Pod，跳过 DaemonSet/mirror pod） |


---

## 四、批量操作 (batch_tools.py) - 8 个

**支持集群中所有可发现的 API 资源**（含 CRD）。`resource_types="all"` 可列出集群所有可用资源类型。所有工具均支持 `kubeconfig_path` 指定集群。

内置支持：deployments, statefulsets, daemonsets, services, configmaps, secrets, jobs, cronjobs, ingresses, persistentvolumeclaims, serviceaccounts, roles, rolebindings, horizontalpodautoscalers, networkpolicies, resourcequotas, namespaces, pods, nodes, storageclasses, clusterroles, clusterrolebindings 等；未知类型通过 DynamicClient 自动发现并操作。


| 工具名                        | 作用                                          |
| -------------------------- | ------------------------------------------- |
| `batch_list_resources`     | 批量列出资源（如 `["pods","nodes","namespaces"]`）   |
| `batch_create_resources`   | 批量创建资源，支持失败回滚                               |
| `batch_update_resources`   | 批量更新资源（含扩缩容、重启等）                            |
| `batch_delete_resources`   | 批量删除资源，支持 `grace_period_seconds`            |
| `batch_describe_resources` | 批量获取资源详情（如 `[{"kind":"Pod","name":"xxx"}]`） |
| `batch_restart_resources`  | 批量重启 Deployment/StatefulSet/DaemonSet       |
| `batch_rollout_resources`  | 批量发布操作：status 查看状态、undo 回滚（可指定 revision）、pause 暂停、resume 恢复 |
| `batch_top_resources`      | 批量查看 Node/Pod 的 CPU、内存使用（类似 kubectl top，依赖 metrics-server） |


---

## 五、备份恢复 (backup_tools.py) - 4 个

所有工具均支持 `kubeconfig_path` 指定集群。


| 工具名                   | 作用                      |
| --------------------- | ----------------------- |
| `backup_namespace`    | 备份整个命名空间（可选是否包含 Secret） |
| `backup_resource`     | 备份指定资源                  |
| `restore_from_backup` | 从备份文件恢复资源               |
| `list_backups`        | 列出备份文件（可按集群/命名空间过滤），仅读本地目录，无需 K8s 连接 |


---

## 六、RBAC 管理 (rbac_tools.py) - 4 个

所有工具均支持 `kubeconfig_path` 指定集群。


| 工具名                                         | 作用                                                               |
| ------------------------------------------- | ---------------------------------------------------------------- |
| `create_role_template`                      | 创建角色模板（developer/admin/operator/readonly/deployer/monitor/debug） |
| `analyze_serviceaccount_permissions`        | 分析 ServiceAccount 的权限                                            |
| `check_serviceaccount_permission_conflicts` | 检查命名空间内 SA 权限冲突                                                  |
| `list_role_serviceaccounts`                 | 列出绑定到某角色的所有 ServiceAccount                                       |


---

## 工具能力说明

- **get_cluster_info**：获取集群元信息（API 版本、服务器地址、集群名称等），与 `batch_list_resources` 不同。
- **batch_list_resources**：列出各类资源的实例（如 Pod、Node、Deployment 等），`resource_types="all"` 可发现集群所有可用 API 资源类型。

## 已覆盖的常见能力（通过 batch 工具）

- **list_namespaces / list_nodes / list_pods** → `batch_list_resources` 传入 `["namespaces"]` / `["nodes"]` / `["pods"]`
- **kubectl top nodes / kubectl top pods** → `batch_top_resources` 传入 `["nodes"]` / `["pods"]`
- **kubectl rollout undo/status/pause/resume** → `batch_rollout_resources` 传入 operations 数组，每项含 kind、name、action（status/undo/pause/resume），undo 可带 `revision` 指定回滚版本
- **kubectl cp** → `copy_pod_file` 指定 direction 为 from_pod 或 to_pod
- **create_namespace** → `batch_create_resources` 传入 Namespace 资源
- **scale_deployment** → `batch_update_resources` 传入修改了 `spec.replicas` 的 Deployment
- **get_pod_describe** → `batch_describe_resources` 传入 `[{"kind":"Pod","name":"xxx"}]`
- **apply_yaml** → `batch_create_resources` / `batch_update_resources` 传入解析后的资源对象
- **bind_user_to_role** → `batch_create_resources` 传入 RoleBinding 资源

## 响应格式与约定

### 批量操作部分成功

`batch_create_resources`、`batch_update_resources`、`batch_delete_resources` 在**部分成功**（既有成功又有失败）时返回 `json_partial_success`，响应包含：

- `success`: true
- `partial`: true
- `success_count`: 成功数量
- `failed_count`: 失败数量
- `success`: 成功项列表
- `failed`: 失败项列表

全成功或全失败时仍使用标准 `json_success` 格式。

### 操作日志（log_operation）

仅**写操作**记录到 `logs/operations.log`，读操作不记录。

| 记录 | 不记录 |
|------|--------|
| import_cluster, delete_cluster, set_default_cluster | list_clusters, get_cluster, get_default_cluster |
| save_kubeconfig, delete_kubeconfig | load_kubeconfig, list_kubeconfigs, validate_kubeconfig |
| copy_pod_file, backup_*, restore_from_backup | list_backups |
| batch_create/update/delete/restart_resources | batch_list, batch_describe, batch_top |
| batch_rollout（仅 undo/pause/resume） | batch_rollout（action=status） |
| drain_node, create_role_template | analyze_*, check_*, list_role_serviceaccounts |

