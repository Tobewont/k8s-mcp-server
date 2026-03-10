"""
集群可达性诊断
运行: python -m tests.check_cluster_reachability

用于排查回归测试卡在异步测试时的原因。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    print("=" * 60)
    print("集群可达性诊断")
    print("=" * 60)

    # 1. 检查 clusters.json
    from config import CLUSTERS_CONFIG_FILE, KUBECONFIGS_DIR
    print(f"\n1. 配置文件路径: {CLUSTERS_CONFIG_FILE}")
    if not os.path.exists(CLUSTERS_CONFIG_FILE):
        print("   [警告] clusters.json 不存在")
    else:
        import json
        with open(CLUSTERS_CONFIG_FILE, 'r', encoding='utf-8') as f:
            clusters = json.load(f)
        default = next((c for c in clusters if c.get("is_default")), clusters[0] if clusters else None)
        print(f"   集群数量: {len(clusters)}")
        if default:
            print(f"   默认集群: {default.get('name')}")
            kc_path = default.get("kubeconfig_path", "")
            print(f"   kubeconfig 路径: {kc_path}")

    # 2. 检查 kubeconfig 文件
    from utils.cluster_config import get_cluster_config_manager
    try:
        mgr = get_cluster_config_manager()
        default_cluster = mgr.get_default_cluster()
        if not default_cluster:
            print("\n2. [问题] 未配置默认集群（clusters.json 中无 is_default: true）")
            return
        kc_path = default_cluster.kubeconfig_path
        abs_path = os.path.abspath(kc_path) if not os.path.isabs(kc_path) else kc_path
        print(f"\n2. 默认集群 kubeconfig: {abs_path}")
        if not os.path.isfile(abs_path):
            print(f"   [问题] 文件不存在（相对路径可能解析错误，cwd={os.getcwd()}）")
            return
        print("   文件存在: 是")
    except Exception as e:
        print(f"\n2. [错误] {e}")
        return

    # 3. 解析 kubeconfig 中的 server 地址
    try:
        import yaml
        with open(abs_path, 'r', encoding='utf-8') as f:
            kc = yaml.safe_load(f)
        server = None
        for cluster in kc.get("clusters", []):
            if "cluster" in cluster and "server" in cluster["cluster"]:
                server = cluster["cluster"]["server"]
                break
        if server:
            print(f"\n3. API Server 地址: {server}")
            # 检查是否内网地址
            if "192.168." in server or "10." in server or "172." in server:
                print("   [提示] 为内网地址，需确保当前网络可访问（如连接公司 VPN）")
        # 检查认证方式
        for user in kc.get("users", []):
            u = user.get("user", {})
            if "exec" in u:
                print("   [提示] 使用 exec 认证，可能触发外部命令导致阻塞")
            elif "client-certificate-data" in u:
                print("   认证方式: client-certificate")
    except Exception as e:
        print(f"\n3. 解析 kubeconfig 失败: {e}")

    # 4. 尝试连接（带超时）
    print("\n4. 尝试连接集群（5 秒超时）...")
    try:
        from kubernetes import client, config
        config.load_kube_config(config_file=abs_path)
        api = client.CoreV1Api()
        ret = api.list_namespace(_request_timeout=5)
        print(f"   [成功] 集群可达，命名空间数: {len(ret.items)}")
    except Exception as e:
        print(f"   [失败] {e}")
        print("\n可能原因:")
        print("  - 未连接公司 VPN，内网集群不可达")
        print("  - 集群已关机或网络不通")
        print("  - 防火墙阻止连接")
        print("\n建议: 设置 REGRESSION_SKIP_ASYNC=1 跳过异步测试")
    print("=" * 60)


if __name__ == "__main__":
    main()
