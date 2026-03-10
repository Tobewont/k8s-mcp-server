"""
Kubernetes 进阶服务 - RBAC 高级功能
"""
from typing import List, Dict, Optional


class RbacAdvancedMixin:
    """RBAC 高级功能 Mixin"""

    def _get_role_template_rules(self, role_type: str) -> List[Dict]:
        """获取角色模板的规则定义"""
        templates = {
            "developer": [
                {"api_groups": [""], "resources": ["pods", "services", "configmaps", "persistentvolumeclaims"], "verbs": ["get", "list", "watch"]},
                {"api_groups": ["apps"], "resources": ["deployments", "statefulsets", "daemonsets"], "verbs": ["get", "list", "watch"]},
                {"api_groups": ["networking.k8s.io"], "resources": ["ingresses"], "verbs": ["get", "list", "watch"]},
                {"api_groups": ["batch"], "resources": ["jobs", "cronjobs"], "verbs": ["get", "list", "watch"]}
            ],
            "admin": [
                {"api_groups": [""], "resources": ["*"], "verbs": ["*"]},
                {"api_groups": ["apps"], "resources": ["*"], "verbs": ["*"]},
                {"api_groups": ["networking.k8s.io"], "resources": ["*"], "verbs": ["*"]},
                {"api_groups": ["batch"], "resources": ["*"], "verbs": ["*"]},
                {"api_groups": ["rbac.authorization.k8s.io"], "resources": ["*"], "verbs": ["*"]}
            ],
            "operator": [
                {"api_groups": [""], "resources": ["pods", "services", "configmaps", "secrets", "persistentvolumeclaims"], "verbs": ["*"]},
                {"api_groups": ["apps"], "resources": ["deployments", "statefulsets", "daemonsets"], "verbs": ["*"]},
                {"api_groups": ["networking.k8s.io"], "resources": ["ingresses"], "verbs": ["*"]},
                {"api_groups": ["batch"], "resources": ["jobs", "cronjobs"], "verbs": ["*"]}
            ],
            "readonly": [
                {"api_groups": [""], "resources": ["pods", "services", "configmaps", "persistentvolumeclaims", "events"], "verbs": ["get", "list", "watch"]},
                {"api_groups": ["apps"], "resources": ["deployments", "statefulsets", "daemonsets", "replicasets"], "verbs": ["get", "list", "watch"]},
                {"api_groups": ["networking.k8s.io"], "resources": ["ingresses", "networkpolicies"], "verbs": ["get", "list", "watch"]},
                {"api_groups": ["batch"], "resources": ["jobs", "cronjobs"], "verbs": ["get", "list", "watch"]}
            ],
            "deployer": [
                {"api_groups": [""], "resources": ["pods", "services", "configmaps", "secrets", "persistentvolumeclaims"], "verbs": ["get", "list", "watch", "create", "update", "patch", "delete"]},
                {"api_groups": ["apps"], "resources": ["deployments", "statefulsets", "daemonsets"], "verbs": ["get", "list", "watch", "create", "update", "patch", "delete"]},
                {"api_groups": ["networking.k8s.io"], "resources": ["ingresses"], "verbs": ["get", "list", "watch", "create", "update", "patch", "delete"]},
                {"api_groups": ["batch"], "resources": ["jobs", "cronjobs"], "verbs": ["get", "list", "watch", "create", "update", "patch", "delete"]},
                {"api_groups": [""], "resources": ["events"], "verbs": ["get", "list", "watch"]}
            ],
            "monitor": [
                {"api_groups": [""], "resources": ["*"], "verbs": ["get", "list", "watch"]},
                {"api_groups": ["apps"], "resources": ["*"], "verbs": ["get", "list", "watch"]},
                {"api_groups": ["networking.k8s.io"], "resources": ["*"], "verbs": ["get", "list", "watch"]},
                {"api_groups": ["batch"], "resources": ["*"], "verbs": ["get", "list", "watch"]},
                {"api_groups": ["metrics.k8s.io"], "resources": ["*"], "verbs": ["get", "list"]}
            ],
            "debug": [
                {"api_groups": [""], "resources": ["pods"], "verbs": ["get", "list", "watch"]},
                {"api_groups": [""], "resources": ["pods/log"], "verbs": ["get", "list"]},
                {"api_groups": [""], "resources": ["pods/exec"], "verbs": ["create"]},
                {"api_groups": [""], "resources": ["pods/portforward"], "verbs": ["create"]},
                {"api_groups": [""], "resources": ["events"], "verbs": ["get", "list", "watch"]}
            ]
        }
        return templates.get(role_type, [])

    async def create_role_template(self, role_type: str, namespace: str, role_name: Optional[str] = None) -> Dict:
        """创建角色模板"""
        if not role_name:
            role_name = role_type

        rules = self._get_role_template_rules(role_type)
        if not rules:
            return {"success": False, "error": f"不支持的角色类型: {role_type}"}

        try:
            try:
                existing_role = await self.k8s_service.get_role(role_name, namespace)
                if existing_role:
                    return {
                        "success": False,
                        "error": f"角色 '{role_name}' 在命名空间 '{namespace}' 中已存在",
                        "suggestion": "请使用不同的角色名称或删除现有角色后重试"
                    }
            except Exception:
                pass
            return await self.k8s_service.create_role(role_name, namespace, rules)
        except Exception as e:
            error_msg = str(e)
            if "already exists" in error_msg or "AlreadyExists" in error_msg:
                return {
                    "success": False,
                    "error": f"角色 '{role_name}' 在命名空间 '{namespace}' 中已存在",
                    "suggestion": "请使用不同的角色名称或删除现有角色后重试"
                }
            return {"success": False, "error": str(e)}

    def _analyze_role_permissions(self, rules: List[Dict]) -> Dict:
        """分析角色权限特征"""
        if not rules:
            return {"is_admin": False, "is_readonly": False, "permission_level": "none"}

        has_wildcard_resources = False
        has_wildcard_verbs = False
        has_write_verbs = False
        has_rbac_permissions = False
        write_verbs = {"create", "update", "patch", "delete", "deletecollection"}

        for rule in rules:
            resources = rule.get("resources", [])
            verbs = set(rule.get("verbs", []))
            api_groups = rule.get("api_groups", rule.get("apiGroups", []))
            if "*" in resources:
                has_wildcard_resources = True
            if "*" in verbs:
                has_wildcard_verbs = True
            if verbs & write_verbs or "*" in verbs:
                has_write_verbs = True
            if "rbac.authorization.k8s.io" in api_groups and (verbs & write_verbs or "*" in verbs):
                has_rbac_permissions = True

        is_admin = (has_wildcard_resources and has_wildcard_verbs) or has_rbac_permissions
        is_readonly = not has_write_verbs and not has_wildcard_verbs
        if is_admin:
            permission_level = "admin"
        elif has_write_verbs:
            permission_level = "write"
        elif is_readonly:
            permission_level = "read"
        else:
            permission_level = "none"

        return {
            "is_admin": is_admin,
            "is_readonly": is_readonly,
            "permission_level": permission_level,
            "has_wildcard_resources": has_wildcard_resources,
            "has_wildcard_verbs": has_wildcard_verbs,
            "has_write_verbs": has_write_verbs,
            "has_rbac_permissions": has_rbac_permissions
        }

    async def analyze_serviceaccount_permissions(self, service_account_name: str, namespace: str) -> Dict:
        """分析ServiceAccount的权限"""
        try:
            permissions = {"roles": [], "cluster_roles": []}
            role_bindings = await self.k8s_service.list_role_bindings(namespace)
            for rb in role_bindings:
                if rb.get("subjects"):
                    for subject in rb["subjects"]:
                        if (subject.get("kind") == "ServiceAccount" and
                                subject.get("name") == service_account_name and
                                subject.get("namespace", namespace) == namespace):
                            role_ref = rb.get("role_ref", {})
                            permissions["roles"].append({
                                "binding_name": rb["name"],
                                "role_name": role_ref.get("name"),
                                "role_kind": role_ref.get("kind"),
                                "namespace": namespace
                            })

            cluster_role_bindings = await self.k8s_service.list_cluster_role_bindings()
            for crb in cluster_role_bindings:
                if crb.get("subjects"):
                    for subject in crb["subjects"]:
                        if (subject.get("kind") == "ServiceAccount" and
                                subject.get("name") == service_account_name and
                                subject.get("namespace", namespace) == namespace):
                            role_ref = crb.get("role_ref", {})
                            permissions["cluster_roles"].append({
                                "binding_name": crb["name"],
                                "role_name": role_ref.get("name"),
                                "role_kind": role_ref.get("kind")
                            })

            for role_info in permissions["roles"]:
                try:
                    if role_info["role_kind"] == "Role":
                        role_detail = await self.k8s_service.get_role(role_info["role_name"], role_info["namespace"])
                        role_info["rules"] = role_detail.get("rules", [])
                    elif role_info["role_kind"] == "ClusterRole":
                        role_detail = await self.k8s_service.get_cluster_role(role_info["role_name"])
                        role_info["rules"] = role_detail.get("rules", [])
                except Exception:
                    role_info["rules"] = []

            for role_info in permissions["cluster_roles"]:
                try:
                    role_detail = await self.k8s_service.get_cluster_role(role_info["role_name"])
                    role_info["rules"] = role_detail.get("rules", [])
                except Exception:
                    role_info["rules"] = []

            return {
                "service_account": service_account_name,
                "namespace": namespace,
                "permissions": permissions,
                "summary": {
                    "total_roles": len(permissions["roles"]),
                    "total_cluster_roles": len(permissions["cluster_roles"])
                }
            }
        except Exception as e:
            return {"error": str(e)}

    async def check_serviceaccount_permission_conflicts(self, namespace: str) -> Dict:
        """检查命名空间中ServiceAccount的权限冲突"""
        try:
            conflicts = []
            role_bindings = await self.k8s_service.list_role_bindings(namespace)
            sa_permissions = {}
            for rb in role_bindings:
                if rb.get("subjects"):
                    for subject in rb["subjects"]:
                        if subject.get("kind") == "ServiceAccount":
                            sa_name = subject.get("name")
                            sa_namespace = subject.get("namespace", namespace)
                            sa_key = f"{sa_namespace}/{sa_name}"
                            if sa_key not in sa_permissions:
                                sa_permissions[sa_key] = []
                            role_ref = rb.get("role_ref", {})
                            sa_permissions[sa_key].append({
                                "binding": rb["name"],
                                "role_name": role_ref.get("name"),
                                "role_kind": role_ref.get("kind")
                            })

            for sa_key, permissions in sa_permissions.items():
                if len(permissions) > 1:
                    role_names = [p["role_name"] for p in permissions]
                    duplicates = set([x for x in role_names if role_names.count(x) > 1])
                    if duplicates:
                        conflicts.append({
                            "type": "duplicate_bindings",
                            "service_account": sa_key,
                            "message": f"ServiceAccount {sa_key} 被重复绑定到角色: {', '.join(duplicates)}",
                            "permissions": permissions
                        })
                    try:
                        role_analyses = []
                        for perm in permissions:
                            role_name = perm["role_name"]
                            role_kind = perm["role_kind"]
                            try:
                                if role_kind == "Role":
                                    role_detail = await self.k8s_service.get_role(role_name, namespace)
                                elif role_kind == "ClusterRole":
                                    role_detail = await self.k8s_service.get_cluster_role(role_name)
                                else:
                                    continue
                                rules = role_detail.get("rules", [])
                                analysis = self._analyze_role_permissions(rules)
                                analysis["role_name"] = role_name
                                analysis["role_kind"] = role_kind
                                role_analyses.append(analysis)
                            except Exception:
                                continue

                        admin_roles = [ra for ra in role_analyses if ra["is_admin"]]
                        readonly_roles = [ra for ra in role_analyses if ra["is_readonly"]]
                        if admin_roles and readonly_roles:
                            admin_role_names = [ra["role_name"] for ra in admin_roles]
                            readonly_role_names = [ra["role_name"] for ra in readonly_roles]
                            conflicts.append({
                                "type": "redundant_permissions",
                                "service_account": sa_key,
                                "message": f"ServiceAccount {sa_key} 同时拥有管理员权限({', '.join(admin_role_names)})和只读权限({', '.join(readonly_role_names)})，只读权限是冗余的",
                                "permissions": permissions,
                                "admin_roles": admin_role_names,
                                "readonly_roles": readonly_role_names
                            })
                        if len(admin_roles) > 1:
                            admin_role_names = [ra["role_name"] for ra in admin_roles]
                            conflicts.append({
                                "type": "excessive_admin_permissions",
                                "service_account": sa_key,
                                "message": f"ServiceAccount {sa_key} 拥有多个管理员权限角色({', '.join(admin_role_names)})，可能存在冗余",
                                "permissions": permissions,
                                "admin_roles": admin_role_names
                            })
                    except Exception:
                        pass

            return {
                "namespace": namespace,
                "conflicts": conflicts,
                "summary": {
                    "total_conflicts": len(conflicts),
                    "service_accounts_checked": len(sa_permissions)
                }
            }
        except Exception as e:
            return {"error": str(e)}

    async def list_role_serviceaccounts(self, role_name: str, namespace: str, role_type: str = "Role") -> Dict:
        """列出绑定到指定角色的所有ServiceAccount"""
        try:
            service_accounts = []
            if role_type == "Role":
                role_bindings = await self.k8s_service.list_role_bindings(namespace)
                for rb in role_bindings:
                    role_ref = rb.get("role_ref", {})
                    if role_ref.get("kind") == role_type and role_ref.get("name") == role_name:
                        if rb.get("subjects"):
                            for subject in rb["subjects"]:
                                if subject.get("kind") == "ServiceAccount":
                                    service_accounts.append({
                                        "name": subject.get("name"),
                                        "namespace": subject.get("namespace", namespace),
                                        "binding": rb["name"]
                                    })
            elif role_type == "ClusterRole":
                cluster_role_bindings = await self.k8s_service.list_cluster_role_bindings()
                for crb in cluster_role_bindings:
                    role_ref = crb.get("role_ref", {})
                    if role_ref.get("kind") == role_type and role_ref.get("name") == role_name:
                        if crb.get("subjects"):
                            for subject in crb["subjects"]:
                                if subject.get("kind") == "ServiceAccount":
                                    service_accounts.append({
                                        "name": subject.get("name"),
                                        "namespace": subject.get("namespace", ""),
                                        "binding": crb["name"]
                                    })
            return {
                "role_name": role_name,
                "role_type": role_type,
                "namespace": namespace,
                "service_accounts": service_accounts,
                "summary": {"total_service_accounts": len(service_accounts)}
            }
        except Exception as e:
            return {"error": str(e)}
