"""
功能回归测试 - 验证优化后功能完好
运行: python -m tests.regression_test

回归测试使用临时目录，不污染实际备份、操作日志、copyfiles，测试结束后自动清理。

环境变量：
  REGRESSION_SKIP_ASYNC=1  - 跳过异步测试（集群不可用时快速跑完）
  REGRESSION_ASYNC_TIMEOUT - 异步单测超时秒数，默认 60

若异步测试卡住：运行 python -m tests.check_cluster_reachability 诊断集群可达性。
"""
import atexit
import asyncio
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 使用临时目录，不污染实际备份、日志、copyfiles
_REGRESSION_TMP = tempfile.mkdtemp(prefix="regression_test_")
os.makedirs(os.path.join(_REGRESSION_TMP, "backup"), exist_ok=True)
os.makedirs(os.path.join(_REGRESSION_TMP, "logs"), exist_ok=True)
os.makedirs(os.path.join(_REGRESSION_TMP, "copyfiles"), exist_ok=True)


def _cleanup_regression_tmp():
    shutil.rmtree(_REGRESSION_TMP, ignore_errors=True)


atexit.register(_cleanup_regression_tmp)

# 必须在任何使用 config 的模块导入前 patch
import config
config.BACKUP_DIR = os.path.join(_REGRESSION_TMP, "backup")
config.LOGS_DIR = os.path.join(_REGRESSION_TMP, "logs")



# 异步单测超时（秒），集群不可达时避免无限挂起
ASYNC_TEST_TIMEOUT = int(os.getenv("REGRESSION_ASYNC_TIMEOUT", "60"))
# 设为 1 时跳过异步测试（集群不可用时快速跑完同步测试）
SKIP_ASYNC = os.getenv("REGRESSION_SKIP_ASYNC", "0") == "1"


def _print_cluster_hint():
    """超时时打印集群诊断提示"""
    try:
        from utils.cluster_config import get_cluster_config_manager
        default = get_cluster_config_manager().get_default_cluster()
        if default:
            print(f"  [诊断] 默认集群: {default.name}, kubeconfig: {default.kubeconfig_path}", flush=True)
            print("  [诊断] 运行 python -m tests.check_cluster_reachability 查看详情", flush=True)
    except Exception:
        pass


# ==================== 同步测试 ====================

def test_imports_and_factory():
    """导入与工厂（不创建服务，避免 load_kube_config 在 exec 认证等场景下阻塞）"""
    from services.factory import get_k8s_api_service, get_k8s_advanced_service, clear_service_cache
    from utils.param_parsers import parse_json_or_single
    from utils.cluster_config import get_cluster_config_manager
    # 仅验证导入与单例，不调用 get_k8s_api_service() 以免 load_kube_config 阻塞（exec 认证等）
    mgr = get_cluster_config_manager()
    assert mgr is get_cluster_config_manager()  # 单例
    lst, err = parse_json_or_single('["pods"]')
    assert lst == ["pods"] and err is None
    clear_service_cache()
    return "OK"


def test_resource_builders():
    """资源构建器"""
    from services.k8s_api.resource_builders import build_resource_data
    r = build_resource_data("deployment", "test", "default", "apps/v1", {"replicas": 2})
    assert r["kind"] == "Deployment"
    assert r["spec"]["replicas"] == 2
    return "OK"


def test_k8s_helpers_direct():
    """k8s_helpers 直接导入（lowlevel 已移除）"""
    from utils.k8s_helpers import parse_secret_data, to_local_time_str
    assert callable(parse_secret_data) and callable(to_local_time_str)
    return "OK"


def test_param_parsers():
    """param_parsers 解析"""
    from utils.param_parsers import parse_json_or_single, parse_json_array, parse_and_validate_resource_specs
    lst, err = parse_json_or_single("pods")
    assert lst == ["pods"] and err is None
    lst2, err2 = parse_json_array('[{"kind":"Pod","name":"x"}]')
    assert lst2 and len(lst2) == 1 and err2 is None
    specs, err3 = parse_and_validate_resource_specs('[{"kind":"Pod","name":"x"}]')
    assert specs and err3 is None
    return "OK"


def test_validate_kubeconfig_tool():
    """cluster_tools.get_kubeconfig_info(content=...)（无需集群）"""
    from tools.cluster_tools import get_kubeconfig_info
    result = asyncio.run(get_kubeconfig_info(content='{"apiVersion":"v1","kind":"Config","clusters":[]}'))
    data = json.loads(result)
    assert "success" in data or "valid" in data
    return "OK"


# ==================== 异步测试（需集群） ====================

async def test_factory_cache():
    """工厂缓存（首次创建服务，验证缓存生效）"""
    from services.factory import get_k8s_api_service, get_k8s_advanced_service
    api = get_k8s_api_service()
    adv = get_k8s_advanced_service()
    assert api is not None and adv is not None
    assert api is get_k8s_api_service()
    assert adv is get_k8s_advanced_service()
    return "OK"


async def test_get_cluster_info():
    """k8s_tools.get_cluster_info"""
    from tools.k8s_tools import get_cluster_info
    result = await get_cluster_info()
    data = json.loads(result)
    assert data.get("success") is True and "cluster_info" in data
    return "OK"


async def test_get_pod_logs():
    """k8s_tools.get_pod_logs"""
    from tools.k8s_tools import get_pod_logs
    from services.factory import get_k8s_api_service
    pods = await get_k8s_api_service().list_pods(namespace="default")
    if not pods:
        return "SKIP (no pods)"
    result = await get_pod_logs(name=pods[0]["name"], namespace="default", lines=5)
    data = json.loads(result)
    assert data.get("success") is True
    return "OK"


async def test_exec_pod_command():
    """k8s_tools.exec_pod_command"""
    from tools.k8s_tools import exec_pod_command
    from services.factory import get_k8s_api_service
    pods = await get_k8s_api_service().list_pods(namespace="default")
    if not pods:
        return "SKIP (no pods)"
    result = await exec_pod_command(pod_name=pods[0]["name"], command=["echo", "ok"], namespace="default")
    data = json.loads(result)
    assert data.get("success") is True and ("ok" in data.get("output", "") or data.get("output", "").strip() == "ok")
    return "OK"


async def test_batch_list_resources():
    """batch_tools.batch_list_resources"""
    from tools.batch_tools import batch_list_resources
    result = await batch_list_resources(resource_types='["pods","deployments"]', namespace="default")
    data = json.loads(result)
    assert "success" in data
    return "OK"


async def test_batch_describe_resources():
    """batch_tools.batch_describe_resources"""
    from tools.batch_tools import batch_describe_resources
    from services.factory import get_k8s_api_service
    pods = await get_k8s_api_service().list_pods(namespace="default")
    if not pods:
        return "SKIP (no pods)"
    spec = json.dumps([{"kind": "Pod", "name": pods[0]["name"]}])
    result = await batch_describe_resources(resource_specs=spec, namespace="default")
    data = json.loads(result)
    assert "success" in data
    return "OK"


async def test_batch_top_resources():
    """batch_tools.batch_top_resources"""
    from tools.batch_tools import batch_top_resources
    result = await batch_top_resources(resource_types='["nodes"]', namespace="default")
    data = json.loads(result)
    assert "success" in data or "nodes" in data
    return "OK"


async def test_batch_rollout_status():
    """batch_tools.batch_rollout_resources (status 只读)"""
    from tools.batch_tools import batch_rollout_resources
    from services.factory import get_k8s_advanced_service
    svc = get_k8s_advanced_service()
    deploys = await svc.batch_list_resources(["deployments"], namespace="default")
    if not deploys.get("success") or not deploys["success"]:
        return "SKIP (no deployments)"
    items = deploys["success"][0].get("items", []) if deploys["success"] else []
    if not items:
        return "SKIP (no deployments)"
    name = items[0]["name"]
    ops = json.dumps([{"kind": "Deployment", "name": name, "action": "status"}])
    result = await batch_rollout_resources(operations=ops, namespace="default")
    data = json.loads(result)
    assert "success" in data
    return "OK"


async def test_check_cluster_health():
    """diagnostic_tools.check_cluster_health"""
    from tools.diagnostic_tools import check_cluster_health
    result = await check_cluster_health()
    data = json.loads(result)
    assert data.get("success") is True and "overall_status" in data
    return "OK"


async def test_check_node_health():
    """diagnostic_tools.check_node_health"""
    from tools.diagnostic_tools import check_node_health
    result = await check_node_health()
    data = json.loads(result)
    assert data.get("success") is True
    return "OK"


async def test_check_pod_health():
    """diagnostic_tools.check_pod_health"""
    from tools.diagnostic_tools import check_pod_health
    result = await check_pod_health(namespace="default", only_failed=False)
    data = json.loads(result)
    assert data.get("success") is True
    assert data.get("summary", {}).get("total_pods") == len(data.get("pod_details", []))
    return "OK"


async def test_get_cluster_resource_usage():
    """diagnostic_tools.get_cluster_resource_usage"""
    from tools.diagnostic_tools import get_cluster_resource_usage
    result = await get_cluster_resource_usage(namespace="default")
    data = json.loads(result)
    assert data.get("success") is True
    return "OK"


async def test_get_cluster_events():
    """diagnostic_tools.get_cluster_events"""
    from tools.diagnostic_tools import get_cluster_events
    result = await get_cluster_events(namespace="default", limit=5)
    data = json.loads(result)
    assert data.get("success") is True
    return "OK"


async def test_list_backups():
    """backup_tools.list_backups"""
    from tools.backup_tools import list_backups
    result = await list_backups()
    data = json.loads(result)
    assert data.get("success") is True and "backups" in data
    return "OK"


async def test_list_clusters():
    """cluster_tools.list_clusters"""
    from tools.cluster_tools import list_clusters
    result = await list_clusters()
    data = json.loads(result)
    assert data.get("success") is True and "clusters" in data
    return "OK"


async def test_list_kubeconfigs():
    """cluster_tools.list_kubeconfigs"""
    from tools.cluster_tools import list_kubeconfigs
    result = await list_kubeconfigs()
    data = json.loads(result)
    assert data.get("success") is True and "kubeconfigs" in data
    return "OK"


async def test_get_cluster():
    """cluster_tools.list_clusters(name=...)"""
    from tools.cluster_tools import list_clusters
    list_result = await list_clusters()
    list_data = json.loads(list_result)
    if not list_data.get("clusters"):
        return "SKIP (no clusters)"
    name = list_data["clusters"][0]["name"]
    result = await list_clusters(name=name)
    data = json.loads(result)
    assert data.get("success") is True and "cluster" in data
    return "OK"


async def test_batch_list_all():
    """batch_tools.batch_list_resources resource_types=all"""
    from tools.batch_tools import batch_list_resources
    result = await batch_list_resources(resource_types="all", namespace="default")
    data = json.loads(result)
    assert "success" in data
    return "OK"


async def test_cluster_config_singleton():
    """ClusterConfigManager 单例"""
    from utils.cluster_config import get_cluster_config_manager
    c1 = get_cluster_config_manager()
    c2 = get_cluster_config_manager()
    assert c1 is c2
    return "OK"


# ==================== batch_tools 扩展 ====================

async def test_batch_create_resources():
    """batch_tools.batch_create_resources（空列表）"""
    from tools.batch_tools import batch_create_resources
    result = await batch_create_resources(resources="[]", namespace="default")
    data = json.loads(result)
    assert "success" in data
    return "OK"


async def test_batch_update_resources():
    """batch_tools.batch_update_resources（空列表）"""
    from tools.batch_tools import batch_update_resources
    result = await batch_update_resources(resources="[]", namespace="default")
    data = json.loads(result)
    assert "success" in data
    return "OK"


async def test_batch_delete_resources():
    """batch_tools.batch_delete_resources（不存在的资源）"""
    from tools.batch_tools import batch_delete_resources
    spec = json.dumps([{"kind": "Pod", "metadata": {"name": "regression-test-nonexistent-xyz"}, "spec": {}}])
    result = await batch_delete_resources(resources=spec, namespace="default")
    data = json.loads(result)
    assert "success" in data or "failed" in data
    return "OK"


async def test_batch_restart_resources():
    """batch_tools.batch_restart_resources（不存在的资源）"""
    from tools.batch_tools import batch_restart_resources
    spec = json.dumps([{"kind": "Deployment", "metadata": {"name": "regression-test-nonexistent-xyz"}, "spec": {"replicas": 1}}])
    result = await batch_restart_resources(resources=spec, namespace="default")
    data = json.loads(result)
    assert "success" in data or "failed" in data
    return "OK"


# ==================== backup_tools 扩展 ====================

async def test_backup_namespace():
    """backup_tools.backup_namespace（使用回归测试临时目录，测试后自动清理）"""
    from tools.backup_tools import backup_namespace
    result = await backup_namespace(namespace="default")
    data = json.loads(result)
    assert data.get("success") is True and "backup_file" in data
    return "OK"


async def test_backup_resource():
    """backup_tools.backup_resource（使用回归测试临时目录，测试后自动清理）"""
    from tools.backup_tools import backup_resource
    from services.factory import get_k8s_api_service
    deploys = await get_k8s_api_service().list_deployments(namespace="default")
    if not deploys:
        return "SKIP (no deployments)"
    name = deploys[0]["name"]
    result = await backup_resource(resource_type="deployment", resource_name=name, namespace="default")
    data = json.loads(result)
    assert data.get("success") is True and "backup_file" in data
    return "OK"


async def test_restore_from_backup():
    """backup_tools.restore_from_backup"""
    from tools.backup_tools import list_backups, restore_from_backup
    list_result = await list_backups()
    list_data = json.loads(list_result)
    backups = list_data.get("backups", [])
    if not backups:
        return "SKIP (no backups)"
    backup_file = backups[0].get("file_path") or backups[0].get("relative_path")
    if not backup_file:
        return "SKIP (no backup path)"
    # 使用备份的原始命名空间，避免命名空间不匹配错误
    target_ns = backups[0].get("namespace") or "default"
    result = await restore_from_backup(backup_file=backup_file, target_namespace=target_ns)
    data = json.loads(result)
    assert "success" in data or "error" in data
    return "OK"


# ==================== cluster_tools 扩展 ====================

async def test_test_cluster_connection():
    """cluster_tools.test_cluster_connection"""
    from tools.cluster_tools import list_clusters, test_cluster_connection
    list_result = await list_clusters()
    list_data = json.loads(list_result)
    if not list_data.get("clusters"):
        return "SKIP (no clusters)"
    name = list_data["clusters"][0]["name"]
    result = await test_cluster_connection(name=name)
    data = json.loads(result)
    assert "success" in data
    return "OK"


async def test_load_kubeconfig():
    """cluster_tools.load_kubeconfig"""
    from tools.cluster_tools import list_kubeconfigs, load_kubeconfig
    list_result = await list_kubeconfigs()
    list_data = json.loads(list_result)
    kubeconfigs = list_data.get("kubeconfigs", [])
    if not kubeconfigs:
        return "SKIP (no kubeconfigs)"
    name = kubeconfigs[0].get("name") or os.path.splitext(os.path.basename(kubeconfigs[0].get("path", "")))[0]
    result = await load_kubeconfig(name=name, mask_sensitive=True)
    data = json.loads(result)
    assert data.get("success") is True and "content" in data
    return "OK"


async def test_get_kubeconfig_info():
    """cluster_tools.get_kubeconfig_info"""
    from tools.cluster_tools import list_kubeconfigs, get_kubeconfig_info
    list_result = await list_kubeconfigs()
    list_data = json.loads(list_result)
    kubeconfigs = list_data.get("kubeconfigs", [])
    if not kubeconfigs:
        return "SKIP (no kubeconfigs)"
    name = kubeconfigs[0].get("name") or os.path.splitext(os.path.basename(kubeconfigs[0].get("path", "")))[0]
    result = await get_kubeconfig_info(name=name)
    data = json.loads(result)
    assert "success" in data or "error" in data
    return "OK"


# ==================== k8s_tools 扩展 ====================

async def test_copy_pod_files():
    """k8s_tools.copy_pod_files (from_pod)"""
    from tools.k8s_tools import copy_pod_files
    from services.factory import get_k8s_api_service
    pods = await get_k8s_api_service().list_pods(namespace="default")
    if not pods:
        return "SKIP (no pods)"
    result = await copy_pod_files(
        pod_name=pods[0]["name"], direction="from_pod",
        pod_paths="/etc/hostname", namespace="default"
    )
    data = json.loads(result)
    assert data.get("success") is True and "files" in data
    return "OK"


# ==================== 工具导入覆盖 ====================

def test_all_tools_importable():
    """验证所有 tools 模块可导入"""
    from tools import k8s_tools, batch_tools, cluster_tools, diagnostic_tools, backup_tools, auth_tools
    tools_modules = [k8s_tools, batch_tools, cluster_tools, diagnostic_tools, backup_tools, auth_tools]
    for m in tools_modules:
        assert m is not None
    return "OK"


def test_tools_have_expected_attrs():
    """验证各 tools 模块导出预期函数"""
    from tools import k8s_tools, batch_tools, cluster_tools, diagnostic_tools, backup_tools, auth_tools
    expected = {
        "k8s_tools": ["get_cluster_info", "get_pod_logs", "exec_pod_command", "copy_pod_files", "port_forward"],
        "batch_tools": ["batch_list_resources", "batch_create_resources", "batch_update_resources", "batch_delete_resources",
                        "batch_describe_resources", "batch_restart_resources", "batch_rollout_resources", "batch_top_resources"],
        "cluster_tools": ["list_clusters", "list_kubeconfigs",
                          "import_cluster", "delete_cluster", "set_default_cluster", "test_cluster_connection",
                          "load_kubeconfig", "delete_kubeconfig", "get_kubeconfig_info"],
        "diagnostic_tools": ["check_cluster_health", "check_node_health", "check_pod_health", "manage_node",
                             "get_cluster_resource_usage", "get_cluster_events"],
        "backup_tools": ["backup_namespace", "backup_resource", "restore_from_backup", "list_backups"],
        "auth_tools": ["whoami", "admin_manage_users", "admin_manage_profiles"],
    }
    for mod_name, attrs in expected.items():
        mod = {"k8s_tools": k8s_tools, "batch_tools": batch_tools, "cluster_tools": cluster_tools,
               "diagnostic_tools": diagnostic_tools, "backup_tools": backup_tools, "auth_tools": auth_tools}[mod_name]
        for attr in attrs:
            assert hasattr(mod, attr), f"{mod_name}.{attr} not found"
    return "OK"


# ==================== 运行 ====================

def run_sync():
    print("=" * 50, flush=True)
    print("同步测试", flush=True)
    print("=" * 50, flush=True)
    for name, fn in [
        ("导入与工厂", test_imports_and_factory),
        ("资源构建器", test_resource_builders),
        ("k8s_helpers 直接导入", test_k8s_helpers_direct),
        ("param_parsers", test_param_parsers),
        ("validate_kubeconfig", test_validate_kubeconfig_tool),
        ("全部 tools 可导入", test_all_tools_importable),
        ("tools 导出预期属性", test_tools_have_expected_attrs),
    ]:
        try:
            r = fn()
            print(f"  [PASS] {name}: {r}", flush=True)
        except Exception as e:
            print(f"  [FAIL] {name}: {e}", flush=True)
            raise


async def run_async():
    if SKIP_ASYNC:
        print("\n" + "=" * 50, flush=True)
        print("异步测试已跳过（REGRESSION_SKIP_ASYNC=1）", flush=True)
        print("=" * 50, flush=True)
        return
    print("\n" + "=" * 50, flush=True)
    print("异步测试（需集群连接，单测超时 %ds）" % ASYNC_TEST_TIMEOUT, flush=True)
    print("=" * 50, flush=True)
    for name, fn in [
        ("factory_cache", test_factory_cache),
        ("get_cluster_info", test_get_cluster_info),
        ("get_pod_logs", test_get_pod_logs),
        ("exec_pod_command", test_exec_pod_command),
        ("batch_list_resources", test_batch_list_resources),
        ("batch_describe_resources", test_batch_describe_resources),
        ("batch_top_resources", test_batch_top_resources),
        ("batch_rollout_status", test_batch_rollout_status),
        ("check_cluster_health", test_check_cluster_health),
        ("check_node_health", test_check_node_health),
        ("check_pod_health", test_check_pod_health),
        ("get_cluster_resource_usage", test_get_cluster_resource_usage),
        ("get_cluster_events", test_get_cluster_events),
        ("list_backups", test_list_backups),
        ("list_clusters", test_list_clusters),
        ("list_kubeconfigs", test_list_kubeconfigs),
        ("list_clusters(name=...)", test_get_cluster),
        ("batch_list_all", test_batch_list_all),
        ("ClusterConfigManager 单例", test_cluster_config_singleton),
        ("batch_create_resources", test_batch_create_resources),
        ("batch_update_resources", test_batch_update_resources),
        ("batch_delete_resources", test_batch_delete_resources),
        ("batch_restart_resources", test_batch_restart_resources),
        ("backup_namespace", test_backup_namespace),
        ("backup_resource", test_backup_resource),
        ("restore_from_backup", test_restore_from_backup),
        ("test_cluster_connection", test_test_cluster_connection),
        ("load_kubeconfig", test_load_kubeconfig),
        ("get_kubeconfig_info", test_get_kubeconfig_info),
        ("copy_pod_files", test_copy_pod_files),
    ]:
        try:
            # 直接运行。注：run_in_executor+asyncio.run() 在子线程中可能死锁导致卡住；
            # 服务层 API 为 sync 阻塞，wait_for 超时在阻塞时无效，集群可达时直接跑即可
            r = await asyncio.wait_for(fn(), timeout=ASYNC_TEST_TIMEOUT)
            print(f"  [PASS] {name}: {r}", flush=True)
        except asyncio.TimeoutError:
            _print_cluster_hint()
            print(f"  [FAIL] {name}: 超时（%ds），集群可能不可达" % ASYNC_TEST_TIMEOUT, flush=True)
            raise
        except Exception as e:
            print(f"  [FAIL] {name}: {e}", flush=True)
            raise


if __name__ == "__main__":
    try:
        run_sync()
        asyncio.run(run_async())
        print("\n" + "=" * 50, flush=True)
        print("全部通过", flush=True)
        print("=" * 50, flush=True)
    finally:
        _cleanup_regression_tmp()
