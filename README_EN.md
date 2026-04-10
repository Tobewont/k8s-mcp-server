# Kubernetes MCP Server

![python](https://img.shields.io/badge/python-3.11%2B-blue) ![k8s-version](https://img.shields.io/badge/k8s-v1.25%2B-orange) ![license](https://img.shields.io/badge/license-MIT-green)

[中文](README.md) | **English**

A Kubernetes MCP Server built on the FastMCP framework, providing comprehensive Kubernetes API operations through the MCP (Model Context Protocol) standard.

## Key Features

- **Pure API Implementation** — Entirely based on the Kubernetes Python Client; no kubectl required
- **Standard MCP Protocol** — Built on FastMCP, fully compliant with the MCP specification
- **Multi-Cluster Management** — Import, switch, and test multiple cluster configurations with auto-loading defaults
- **35 Tool Functions** — Full CRUD coverage for all major Kubernetes resources, including CRDs via dynamic discovery
- **Multi-Tenant Auth** — Optional JWT authentication with per-user data isolation, permission profiles, and tool visibility filtering
- **Cluster Diagnostics** — Health checks, resource usage analysis, event collection, and node management (drain/cordon/uncordon)
- **Backup & Restore** — Namespace-level and resource-level backup/restore, organized by cluster/namespace/resource type
- **Change Validation & Preview** — Automatic validation for all write operations with detailed diff preview
- **Dual Transport** — Supports both SSE (HTTP) and Stdio transport modes
- **Containerized Deployment** — Docker and Kubernetes manifests included

## Quick Start

### Requirements

- Python 3.11+
- No kubectl needed

### Install

```bash
uv pip install -e .
```

### Start the Server

```bash
# Stdio mode (default, recommended for MCP clients)
python main.py

# SSE mode (HTTP interface)
python main.py --transport sse --host 0.0.0.0 --port 8000

# Or via uvicorn directly
uvicorn tools:app --host 0.0.0.0 --port 8000
```

### Cursor MCP Configuration

Add to your Cursor MCP config (`~/.cursor/mcp.json` or project `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "k8s-mcp-server": {
      "url": "http://localhost:8000/mcp/k8s-server/streamable"
    }
  }
}
```

Then start the server: `python main.py --transport sse --port 8000`

Alternative Stdio mode (no HTTP server needed):

```json
{
  "mcpServers": {
    "k8s-mcp-server": {
      "command": "python",
      "args": ["main.py", "--transport", "stdio"],
      "cwd": "/path/to/project"
    }
  }
}
```

> Without auth: 32 tools visible. With auth enabled: admin sees all 35, viewer 13, developer 21, operator 30.

## Tool Overview

| Category | Module | Count | Description |
|----------|--------|-------|-------------|
| Auth | auth_tools | 3 | whoami, user/token management, permission profile management (auth mode only) |
| Core | k8s_tools | 5 | Cluster info, pod logs (incl. previous), exec, file copy, port forward |
| Cluster | cluster_tools | 9 | Cluster import/switch, kubeconfig management |
| Diagnostics | diagnostic_tools | 6 | Cluster/node/pod health, resource usage, events, node management |
| Batch | batch_tools | 8 | Batch CRUD, restart, rollout, top resources; supports all API resources incl. CRDs |
| Backup | backup_tools | 4 | Namespace/resource backup and restore |

### Core Tools (k8s_tools.py)

- `get_cluster_info()` — Cluster metadata (API version, server address, etc.)
- `get_pod_logs()` — Pod logs with `previous` support for crashed containers
- `exec_pod_command()` — Execute commands inside a pod
- `copy_pod_files()` — Bidirectional file transfer between pod and client
- `port_forward()` — Port forward management: start/stop/list sessions (user-isolated in auth mode)

### Cluster Management (cluster_tools.py)

- `import_cluster()` — Import cluster config (with kubeconfig persistence)
- `list_clusters(name?)` — List all clusters or get a specific cluster's details
- `delete_cluster()` — Remove a cluster config
- `set_default_cluster()` — Set the default cluster
- `test_cluster_connection()` — Test cluster connectivity
- `load_kubeconfig()` — Load kubeconfig content (supports sensitive data masking)
- `list_kubeconfigs()` — List saved kubeconfig files
- `delete_kubeconfig()` — Delete a kubeconfig file
- `get_kubeconfig_info()` — Get kubeconfig details or validate content

### Batch Operations (batch_tools.py)

- `batch_list_resources()` — List resources; `resource_types="all"` discovers all API resource types
- `batch_create_resources()` — Batch create with transaction rollback
- `batch_update_resources()` — Batch update (scaling, labels, etc.)
- `batch_delete_resources()` — Batch delete with `grace_period_seconds`
- `batch_describe_resources()` — Batch describe resources
- `batch_restart_resources()` — Batch restart Deployment/StatefulSet/DaemonSet
- `batch_rollout_resources()` — Rollout operations: status/undo/pause/resume
- `batch_top_resources()` — Node/Pod CPU & memory usage (requires metrics-server)

### Diagnostics (diagnostic_tools.py)

- `check_cluster_health()` — Cluster health with optional RBAC conflict detection
- `check_node_health()` — Node health status
- `check_pod_health()` — Pod health with `only_failed` filter
- `get_cluster_resource_usage()` — Cluster resource utilization
- `get_cluster_events()` — Cluster events with type/count filtering
- `manage_node()` — Node operations: drain, cordon, uncordon

### Backup & Restore (backup_tools.py)

- `backup_namespace()` — Back up an entire namespace (optional secrets)
- `backup_resource()` — Back up a specific resource
- `restore_from_backup()` — Restore from backup file
- `list_backups()` — List backup files (filterable by cluster/namespace)

## Multi-Tenant Authentication

Enable JWT-based multi-tenant mode for team environments:

```bash
# Start with auth
MCP_AUTH_ENABLED=true MCP_JWT_SECRET=your-secret-key \
  python main.py --transport sse --host 0.0.0.0 --port 8000

# Bootstrap admin token
MCP_JWT_SECRET=your-secret-key mcp-admin bootstrap

# Issue user tokens
MCP_JWT_SECRET=your-secret-key mcp-admin issue --user alice --expires 604800

# Grant cluster access (via MCP tool as admin)
# admin_manage_users(action="grant_access", user_id="alice",
#   cluster_name="prod", namespace="default", profile="developer")
```

Client configuration with token (Cursor example):

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

### Permission Profiles

| Profile | Visible Tools | K8s Permissions | Management |
|---------|--------------|-----------------|------------|
| `viewer` | 13 (read-only + logs + connection test + switch cluster) | get/list/watch + pods/log | — |
| `developer` | 21 (read-write + exec) | CRUD workloads + pods/log, exec, portforward | — |
| `operator` | 30 (+ backup/restore, diagnostics, node drain, user management) | Namespace full ops + rbac read + ClusterRole (nodes/namespaces/events/metrics/drain) | Manage viewer/developer users |
| `admin` | 35 (all tools) | Uses K8s admin kubeconfig with full cluster privileges | Full management |

### Security

- **Path injection protection** — kubeconfig_path restricted to user's own data directory
- **Input validation** — Strict format checks on user_id, cluster_name, namespace, etc.
- **Operator isolation** — Cannot self-grant, cannot manage privileged users, cannot issue admin tokens. Operator's K8s operations are namespace-scoped, but `grant_access` is an MCP platform-level delegation (cross-namespace, using admin kubeconfig) for managing viewer/developer onboarding
- **Custom profile protection** — Reserved categories (`user_manage`, `profile_manage`, `cluster_ops`) blocked from custom profiles
- **Token expiry cap** — Default max 90 days (configurable via `MCP_TOKEN_MAX_EXPIRY`)
- **Audit logging** — All management operations recorded to per-user `operations.log`
- **Graceful degradation** — Cluster-level tools return partial results for users without cluster-wide permissions
- **Tar slip protection** — Pod file copy validates tar member paths to prevent directory traversal

### Admin REST API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/tokens/issue` | POST | Issue token |
| `/admin/tokens/revoke` | POST | Revoke token |
| `/admin/tokens/revoked` | GET | List revoked tokens |
| `/admin/tokens/cleanup` | POST | Clean up expired revocations |
| `/admin/users` | GET | List all users |

### CLI Tool

```bash
mcp-admin bootstrap                    # Generate admin token
mcp-admin issue --user bob             # Issue user token
mcp-admin revoke --jti xxx             # Revoke a token
mcp-admin revoke-user --user bob       # Revoke all user tokens
mcp-admin list-users                   # List all users
mcp-admin grant --user bob --cluster prod --namespace default --profile developer
mcp-admin revoke-access --user bob --cluster prod --namespace default
mcp-admin list-profiles                # List all profiles
```

## Deployment

### Docker

```bash
docker build -t k8s-mcp-server:latest .

docker run -d --name k8s-mcp-server \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  k8s-mcp-server:latest
```

### Kubernetes

```bash
kubectl apply -f k8s/
kubectl get pods -l app=k8s-mcp-server
```

See [k8s/README.md](k8s/README.md) for detailed deployment guide including PVC, ConfigMap, auth secrets, and Ingress configuration.

## Configuration

### Environment Variables

```bash
SSE_HOST=0.0.0.0                # Server listen address
SSE_PORT=8000                   # Server port
DATA_DIR=./data                 # Data root (cluster configs, kubeconfigs, backups, user ops logs)
LOG_LEVEL=info                  # Log level

# MCP paths
MCP_MESSAGE_PATH=/mcp/k8s-server/message/
MCP_SSE_PATH=/mcp/k8s-server/sse
MCP_STREAMABLE_PATH=/mcp/k8s-server/streamable

# Auth (optional)
MCP_AUTH_ENABLED=false          # Set true to enable JWT auth
MCP_JWT_SECRET=                 # JWT signing secret (required when auth enabled)
MCP_JWT_ALGORITHM=HS256         # JWT algorithm
MCP_TOKEN_MAX_EXPIRY=7776000    # Max token lifetime in seconds (default 90 days)
MCP_ADMIN_API_PREFIX=/admin     # Admin API route prefix
```

## Architecture

Three-layer service design:

| Service | Location | Role | Coverage |
|---------|----------|------|----------|
| **KubernetesAPIService** | services/k8s_api/ | Typed API wrapper | Built-in resources (Pod, Deployment, Service, etc.) |
| **DynamicResourceService** | dynamic_resource_service.py | Dynamic resource ops | Any resource (built-in + CRD) |
| **KubernetesAdvancedService** | k8s_advanced_service.py | Orchestration layer | Batch ops, backup/restore, validation |

Batch operations prefer pre-defined methods and fallback to DynamicClient for unknown resource types, supporting CRDs like CephFilesystem, KafkaTopic, etc.

## Regression Tests

```bash
# Full suite (requires K8s cluster)
python -m tests.regression_test

# Sync tests only (no cluster needed)
REGRESSION_SKIP_ASYNC=1 python -m tests.regression_test
```

- **Sync tests** (7): Imports, resource builders, parsers, kubeconfig validation, tool exports
- **Async tests** (30): Full MCP tool invocation coverage, requires cluster connectivity
- **Backup isolation**: Backup tests use temp directories, auto-cleaned after run

## Notes

- Requires Kubernetes v1.25+ (only `batch/v1` CronJob API supported, not `batch/v1beta1`)
- No kubectl dependency — purely Python API based
- Only a valid kubeconfig is needed to connect and manage clusters

## Contributing

Contributions welcome! Please:

1. Follow existing code style
2. Add proper error handling
3. Update documentation
4. Add test cases

## License

MIT License — see [LICENSE](./LICENSE)
