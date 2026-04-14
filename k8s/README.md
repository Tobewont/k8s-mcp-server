# K8s-MCP-Server Kubernetes 部署指南

本指南详细说明如何将 k8s-mcp-server 部署到 Kubernetes 集群中，包括数据持久化配置和权限设置。

## 📋 先决条件

- Kubernetes 集群 (版本 1.18+)
- kubectl 命令行工具
- Docker 镜像仓库访问权限
- 集群管理员权限（用于创建 ClusterRole）

## 🚀 快速部署

### 1. 构建Docker镜像

```bash
# 在项目根目录下构建镜像
docker build -t k8s-mcp-server:latest .

# 如果使用私有仓库，推送镜像
docker tag k8s-mcp-server:latest your-registry/k8s-mcp-server:latest
docker push your-registry/k8s-mcp-server:latest
```

### 2. 更新镜像地址

编辑 `k8s/deployment.yaml` 文件，更新镜像地址：

```yaml
containers:
- name: k8s-mcp-server
  image: your-registry/k8s-mcp-server:latest  # 替换为实际的镜像地址
```

### 3. 部署资源

按照以下顺序部署 Kubernetes 资源：

```bash
# 1. 创建 PersistentVolumeClaim（数据持久化）
kubectl apply -f k8s/pvc.yaml

# 2. 创建 ConfigMap（配置管理）
kubectl apply -f k8s/configmap.yaml

# 3. 如需启用认证，先编辑 secret.yaml 填入 JWT 密钥，然后：
# kubectl apply -f k8s/secret.yaml

# 4. 创建 Deployment
kubectl apply -f k8s/deployment.yaml

# 5. 创建 Service（服务暴露）
kubectl apply -f k8s/service.yaml
```

### 4. 验证部署

```bash
# 检查 Pod 状态
kubectl get pods -l app=k8s-mcp-server

# 检查 Service 状态
kubectl get svc k8s-mcp-server

# 查看 Pod 日志
kubectl logs -l app=k8s-mcp-server -f

# 检查持久化卷状态
kubectl get pvc
```

## 🔧 配置说明

### 数据持久化

项目使用 PersistentVolumeClaim 来实现数据持久化：

- **k8s-mcp-server-data** (5Gi): 存储集群配置、kubeconfig 文件、备份数据、用户操作日志等

### 权限配置

k8s-mcp-server 需要以下权限：

- **Core API**: pods, services, nodes, namespaces, configmaps, secrets, events
- **Apps API**: deployments, statefulsets, daemonsets
- **Batch API**: jobs, cronjobs
- **Networking API**: ingresses
- **Storage API**: storageclasses, persistentvolumes, persistentvolumeclaims

### 环境变量

通过 ConfigMap 管理的环境变量：

```yaml
SSE_HOST: "0.0.0.0"          # 服务监听地址
SSE_PORT: "8000"             # 服务端口
LOG_LEVEL: "INFO"            # 日志级别
DATA_DIR: "/app/data"        # 数据目录
```

### 认证配置（可选）

启用 JWT 多租户认证时，需要三步操作：

#### 步骤 1：准备 Secret

编辑 `k8s/secret.yaml`，将 `MCP_JWT_SECRET` 替换为高强度随机字符串：

```bash
# 生成随机密钥
openssl rand -base64 32
```

如需预置管理员 Token，先在本地生成后填入：

```bash
MCP_JWT_SECRET=your-strong-secret-key mcp-admin bootstrap
# 将输出的 Token 填入 secret.yaml 的 MCP_BOOTSTRAP_ADMIN_JWT 字段
```

然后创建 Secret：

```bash
kubectl apply -f k8s/secret.yaml
```

> 也可以不使用 `secret.yaml`，通过命令行创建：
> ```bash
> kubectl create secret generic k8s-mcp-server-auth \
>   --from-literal=MCP_JWT_SECRET='your-strong-secret-key'
> ```

#### 步骤 2：取消 ConfigMap 中的认证配置注释

编辑 `k8s/configmap.yaml`，取消认证相关行的注释（`MCP_AUTH_ENABLED`、`MCP_JWT_ALGORITHM` 等）。

#### 步骤 3：取消 Deployment 中的 env 注释

编辑 `k8s/deployment.yaml`，取消 `env` 段的注释，使 Pod 能从 Secret 中读取 `MCP_JWT_SECRET`。

#### 应用变更

```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml
# Pod 会自动滚动更新
```

启用认证后：
- 所有 MCP 连接需携带 `Authorization: Bearer <jwt>` 请求头
- 每个用户的数据隔离到 `data/users/<user_id>/` 子目录
- 管理 API（`/admin/tokens/*`、`/admin/users`、`/admin/kubeconfigs/upload`）需管理员 JWT
- 管理员可通过 MCP Tool 或 CLI 签发/撤销用户 Token 和集群权限

## 🌐 服务访问

### 内部访问

```bash
# 集群内部访问
kubectl port-forward svc/k8s-mcp-server 8000:8000

# 访问 SSE 端点
curl http://localhost:8000/mcp/k8s-server/sse
```

### 外部访问

#### 方法1：NodePort 服务

```bash
# 获取节点端口
kubectl get svc k8s-mcp-server-external

# 访问服务（假设节点IP为 192.168.1.100）
curl http://192.168.1.100:30800/mcp/k8s-server/sse
```

#### 方法2：Ingress（推荐）

```bash
# 确保 Ingress Controller 已安装
kubectl apply -f k8s/service.yaml

# 配置 DNS 或 hosts 文件
echo "192.168.1.100 k8s-mcp-server.local" >> /etc/hosts

# 访问服务
curl http://k8s-mcp-server.local/mcp/k8s-server/sse
```

## 🔐 安全配置

### 管理外部集群

如果需要管理外部 Kubernetes 集群，可以通过 Secret 提供 kubeconfig：

```bash
# 创建 kubeconfig Secret
kubectl create secret generic k8s-mcp-server-kubeconfig \
  --from-file=config=/path/to/external-kubeconfig

# 或者使用 base64 编码
kubectl patch secret k8s-mcp-server-kubeconfig \
  -p='{"data":{"config":"'$(base64 -w 0 < /path/to/external-kubeconfig)'"}}'
```

### 网络策略

可以创建 NetworkPolicy 来限制 Pod 的网络访问：

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: k8s-mcp-server-policy
  namespace: default
spec:
  podSelector:
    matchLabels:
      app: k8s-mcp-server
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector: {}
    ports:
    - protocol: TCP
      port: 8000
  egress:
  - to: []
    ports:
    - protocol: TCP
      port: 443  # Kubernetes API
```

## 📊 监控和日志

### 日志收集

```bash
# 查看实时日志
kubectl logs -l app=k8s-mcp-server -f

# 查看用户操作日志
kubectl exec -it $(kubectl get pods -l app=k8s-mcp-server -o jsonpath='{.items[0].metadata.name}') -- ls -la /app/data/users/
```

### 健康检查

应用提供端口健康检查：

- **Liveness Probe**: `8000` - 存活检查
- **Readiness Probe**: `8000` - 就绪检查

### 资源监控

```bash
# 查看资源使用情况
kubectl top pods -l app=k8s-mcp-server

# 查看 PVC 使用情况
kubectl get pvc
```

## 🛠️ 故障排除

### 常见问题

1. **Pod 无法启动**
  ```bash
   kubectl describe pod -l app=k8s-mcp-server
  ```
2. **存储问题**
  ```bash
   kubectl get pvc
   kubectl describe pvc k8s-mcp-server-data
  ```
3. **镜像拉取失败**
  ```bash
   kubectl describe pod -l app=k8s-mcp-server | grep -A 10 "Events:"
  ```

### 调试命令

```bash
# 进入 Pod 进行调试
kubectl exec -it $(kubectl get pods -l app=k8s-mcp-server -o jsonpath='{.items[0].metadata.name}') -- /bin/bash

# 查看配置
kubectl get configmap k8s-mcp-server-config -o yaml

# 查看 Secret
kubectl get secret k8s-mcp-server-kubeconfig -o yaml
```

## 🔄 升级部署

### 滚动更新

```bash
# 更新镜像
kubectl set image deployment/k8s-mcp-server k8s-mcp-server=your-registry/k8s-mcp-server:v2.0.0

# 查看更新状态
kubectl rollout status deployment/k8s-mcp-server

# 回滚部署
kubectl rollout undo deployment/k8s-mcp-server
```

### 配置更新

```bash
# 更新 ConfigMap
kubectl apply -f k8s/configmap.yaml

# 重启 Pod 以应用新配置
kubectl rollout restart deployment/k8s-mcp-server
```

## 📝 清理资源

```bash
# 删除所有资源
kubectl delete -f k8s/

# 或者逐个删除
kubectl delete deployment k8s-mcp-server
kubectl delete service k8s-mcp-server k8s-mcp-server-external
kubectl delete ingress k8s-mcp-server-ingress
kubectl delete configmap k8s-mcp-server-config
kubectl delete pvc k8s-mcp-server-data

# 如果启用了认证，一并清理 Secret
# kubectl delete secret k8s-mcp-server-auth
```

## 🎯 最佳实践

1. **资源限制**: 根据实际需求调整 CPU 和内存限制
2. **存储大小**: 根据预期的数据量调整 PVC 大小
3. **副本数量**: 生产环境建议设置多个副本
4. **镜像标签**: 使用具体的版本标签而不是 `latest`
5. **监控告警**: 配置适当的监控和告警机制
6. **备份策略**: 定期备份持久化数据

## 📚 参考资料

- [Kubernetes 官方文档](https://kubernetes.io/docs/)
- [FastMCP 框架文档](https://github.com/fastmcp/fastmcp)
- [Kubernetes Python Client](https://github.com/kubernetes-client/python)
