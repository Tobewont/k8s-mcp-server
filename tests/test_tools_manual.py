"""
手动测试 get_cluster_events 和 port_forward 工具
运行: python -m tests.test_tools_manual
"""
import asyncio
import json
import sys
import os

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_get_cluster_events():
    """测试 get_cluster_events - 验证 namespace=all 能获取所有命名空间事件"""
    from tools.diagnostic_tools import get_cluster_events

    print("=" * 60)
    print("测试 get_cluster_events (namespace='all')")
    print("=" * 60)

    try:
        result = await get_cluster_events(namespace="all", limit=10)
        data = json.loads(result)
        if data.get("success"):
            print(f"[OK] 成功获取事件")
            print(f"   命名空间: {data.get('namespace')}")
            print(f"   事件总数: {data.get('total_events')}")
            print(f"   事件统计: {data.get('event_statistics', {})}")
            if data.get("events"):
                print(f"   前3条事件:")
                for i, evt in enumerate(data["events"][:3], 1):
                    ns = evt.get("namespace", "?")
                    reason = evt.get("reason", "?")
                    msg = (evt.get("message", "") or "")[:50]
                    print(f"     {i}. [{ns}] {reason}: {msg}...")
        else:
            print(f"[FAIL] 失败: {data.get('error', 'Unknown')}")
    except Exception as e:
        print(f"[FAIL] 异常: {e}")
        raise


async def test_port_forward():
    """测试 port_forward - 验证能启动真实端口转发"""
    from tools.k8s_tools import port_forward
    from services.k8s_api_service import KubernetesAPIService

    print("\n" + "=" * 60)
    print("测试 port_forward")
    print("=" * 60)

    # 先获取一个可用的 Pod
    k8s = KubernetesAPIService()
    k8s.load_config()
    pods = await k8s.list_pods(namespace="default")
    if not pods:
        print("[WARN] default 命名空间无 Pod，尝试 kube-system...")
        pods = await k8s.list_pods(namespace="kube-system")

    if not pods:
        print("[WARN] 集群中无可用 Pod，跳过 port_forward 测试")
        return

    pod_name = pods[0]["name"]
    namespace = pods[0].get("namespace", "default")
    # 使用常见端口 80 或 8080
    pod_port = 80
    local_port = 18080

    print(f"   使用 Pod: {pod_name} (ns: {namespace}), 转发 {local_port} -> {pod_port}")

    try:
        result = await port_forward(
            pod_name=pod_name,
            local_port=local_port,
            pod_port=pod_port,
            namespace=namespace,
        )
        data = json.loads(result)
        if data.get("success"):
            print(f"[OK] 端口转发已启动")
            print(f"   {data.get('forward_info', {}).get('message', '')}")
            print(f"   说明: {data.get('forward_info', {}).get('note', '')}")
            # 尝试连接验证
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            try:
                sock.connect(("127.0.0.1", local_port))
                print(f"   [OK] 本地端口 {local_port} 已可连接")
            except (ConnectionRefusedError, socket.timeout, OSError) as e:
                print(f"   [WARN] 连接测试: {e} (Pod 可能无 {pod_port} 端口，但转发已启动)")
            finally:
                sock.close()
        else:
            print(f"[FAIL] 失败: {data.get('error', 'Unknown')}")
    except Exception as e:
        print(f"[FAIL] 异常: {e}")
        raise


async def main():
    print("\n[k8s-mcp-server] 工具测试\n")
    await test_get_cluster_events()
    await test_port_forward()
    print("\n[OK] 测试完成\n")


if __name__ == "__main__":
    asyncio.run(main())
