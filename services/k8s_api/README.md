# k8s_api 包结构

Kubernetes API 服务拆分为多个模块，便于维护。

## 模块说明

| 模块 | 职责 |
|------|------|
| `base.py` | 初始化、load_config、验证框架、_extract_volume_info、_extract_container_info、get_dynamic_client |
| `pod_ops.py` | Pod：list/get/logs/delete、_get_pod_ready_status、_extract_container_state |
| `workload_ops.py` | Deployment、StatefulSet、DaemonSet、rollout |
| `service_config_ops.py` | Service、ConfigMap、Secret |
| `batch_ops.py` | Job、CronJob |
| `networking_storage_ops.py` | Ingress、StorageClass、PV、PVC |
| `rbac_ops.py` | ServiceAccount、Role、ClusterRole、RoleBinding、ClusterRoleBinding |
| `autoscaling_policy_ops.py` | HPA、NetworkPolicy、ResourceQuota |
| `interactive_ops.py` | exec_pod_command、copy_from_pod、copy_to_pod、port_forward |
| `cluster_ops.py` | Node、Namespace、Event、check_api_health、get_cluster_info、metrics、drain_node、cordon_node、uncordon_node |

## 使用

```python
from services.k8s_api import KubernetesAPIService
# 或
from services.k8s_api import KubernetesAPIService
```
