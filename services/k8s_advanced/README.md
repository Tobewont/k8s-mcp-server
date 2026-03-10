# k8s_advanced 包

Kubernetes 进阶服务，拆分为多个 Mixin 模块便于维护。

## 模块说明

| 模块 | 职责 |
|------|------|
| `base.py` | ResourceManager、ResourceConfig、BatchOperationResult、API 版本映射常量 |
| `resource_conversion.py` | 规格归一化、扁平数据→K8s 格式转换、容器/卷转换 |
| `batch_ops.py` | 批量 list/create/update/delete/rollout/top 操作 |
| `backup_restore.py` | 命名空间备份、单资源备份、恢复、列出备份 |
| `rbac_advanced.py` | 角色模板、ServiceAccount 权限分析、冲突检查 |
| `validation.py` | 操作前后资源获取、变化比较、验证与预览 |

## 使用方式

通过 `services.k8s_advanced_service.KubernetesAdvancedService` 或 `services.factory.get_k8s_advanced_service()` 获取实例，对外接口保持不变。
