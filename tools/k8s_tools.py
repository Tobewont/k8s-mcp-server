"""
Kubernetes 工具集合
提供集群健康检查、查询功能和基本信息查询功能
"""
import json as _json
from typing import Optional

from services.factory import get_k8s_api_service
from utils.cluster_config import resolve_kubeconfig_path
from utils.decorators import handle_tool_errors
from utils.operations_logger import log_operation
from utils.response import json_error, json_success

# 导入共享的MCP实例
from . import mcp

# ========================== 集群信息工具 ==========================

@mcp.tool()
@handle_tool_errors
async def get_cluster_info(kubeconfig_path: Optional[str] = None,
                          cluster_name: Optional[str] = None) -> str:
    """
    获取Kubernetes集群信息
    
    Args:
        kubeconfig_path: kubeconfig 文件路径，不指定则使用 cluster_name 或默认集群
        cluster_name: 集群配置名称（clusters.json 中的 name），kubeconfig_path 未指定时使用
    
    Returns:
        集群信息
    """
    effective_path = resolve_kubeconfig_path(cluster_name, kubeconfig_path)
    k8s_service = get_k8s_api_service(effective_path)
    cluster_info = await k8s_service.get_cluster_info()
    return json_success({"success": True, "cluster_info": cluster_info})

# ========================== Pod 日志和操作工具 ==========================

@mcp.tool()
@handle_tool_errors
async def get_pod_logs(name: str, namespace: str = "default", lines: int = 100,
                       container: Optional[str] = None, previous: bool = False,
                       kubeconfig_path: Optional[str] = None,
                       cluster_name: Optional[str] = None) -> str:
    """
    获取Pod的日志
    
    Args:
        name: Pod名称
        namespace: Kubernetes命名空间，默认为default
        lines: 日志行数，默认为100
        container: 容器名称，如果Pod有多个容器则需要指定
        previous: 是否获取上一实例（崩溃/重启前）的日志，默认为False
        kubeconfig_path: kubeconfig 文件路径，不指定则使用 cluster_name 或默认集群
        cluster_name: 集群配置名称（clusters.json 中的 name），kubeconfig_path 未指定时使用
    
    Returns:
        包含Pod日志的结果
    """
    if not isinstance(lines, int) or lines < 1:
        return json_error("lines 必须为正整数")
    effective_path = resolve_kubeconfig_path(cluster_name, kubeconfig_path)
    k8s_service = get_k8s_api_service(effective_path)
    logs = await k8s_service.get_pod_logs(name=name, namespace=namespace, lines=lines, container=container, previous=previous)
    return json_success({"success": True, "logs": logs, "pod_name": name, "namespace": namespace, "container": container, "lines": lines, "previous": previous})

# ========================== 交互式操作工具 ==========================

@mcp.tool()
@handle_tool_errors
async def exec_pod_command(pod_name: str, command: list, namespace: str = "default",
                          container: Optional[str] = None, kubeconfig_path: Optional[str] = None,
                          cluster_name: Optional[str] = None) -> str:
    """
    在Pod中执行命令
    
    Args:
        pod_name: Pod名称
        command: 要执行的命令列表，如 ["ls", "-la"]
        namespace: Kubernetes命名空间，默认为default
        container: 容器名称，如果Pod有多个容器则需要指定
        kubeconfig_path: kubeconfig 文件路径，不指定则使用 cluster_name 或默认集群
        cluster_name: 集群配置名称（clusters.json 中的 name），kubeconfig_path 未指定时使用
    
    Returns:
        命令执行结果
    """
    if not command or not isinstance(command, (list, tuple)):
        return json_error("command 必须为非空列表")
    effective_path = resolve_kubeconfig_path(cluster_name, kubeconfig_path)
    k8s_service = get_k8s_api_service(effective_path)
    exec_result = await k8s_service.exec_pod_command(pod_name=pod_name, command=command, namespace=namespace, container=container)
    return json_success({"success": True, "pod_name": pod_name, "namespace": namespace, "container": container, "command": command, "output": exec_result})


@mcp.tool()
@handle_tool_errors
async def copy_pod_files(
    pod_name: str,
    direction: str,
    pod_paths: str,
    content: Optional[str] = None,
    encoding: str = "text",
    local_path: Optional[str] = None,
    namespace: str = "default",
    container: Optional[str] = None,
    kubeconfig_path: Optional[str] = None,
    cluster_name: Optional[str] = None,
) -> str:
    """
    Pod 与 MCP 客户端之间拷贝文件

    Args:
        pod_name: Pod 名称
        direction: 拷贝方向，"from_pod" 读取 Pod 文件内容，"to_pod" 将内容写入 Pod
        pod_paths: from_pod 时为 Pod 内文件路径（JSON 数组或单个路径，支持目录）；to_pod 时为 Pod 内目标文件路径
        content: to_pod 时必填（local_path 未指定时），要写入 Pod 的文件内容
        encoding: to_pod 时 content 的编码方式，"text"（默认）或 "base64"（二进制文件）
        local_path: 本地文件路径。from_pod 时指定则直接将解码后的文件保存到此目录（二进制文件不再需要中间 base64 文件）；to_pod 时指定则从此本地文件读取内容写入 Pod
        namespace: 命名空间，默认为 default
        container: 容器名称，多容器 Pod 需指定
        kubeconfig_path: kubeconfig 文件路径，不指定则使用 cluster_name 或默认集群
        cluster_name: 集群配置名称（clusters.json 中的 name），kubeconfig_path 未指定时使用

    Returns:
        from_pod: 文件内容或本地保存路径; to_pod: 写入确认
    """
    import os as _os
    import base64 as _b64

    if direction not in ("from_pod", "to_pod"):
        return json_error(f"direction 必须是 from_pod 或 to_pod，当前为 {direction}")
    if direction == "to_pod" and not content and not local_path:
        return json_error("to_pod 方向必须提供 content 或 local_path")
    if direction == "to_pod" and encoding not in ("text", "base64"):
        return json_error(f"encoding 必须是 text 或 base64，当前为 {encoding}")

    effective_path = resolve_kubeconfig_path(cluster_name, kubeconfig_path)
    k8s_service = get_k8s_api_service(effective_path)

    if direction == "from_pod":
        try:
            paths = _json.loads(pod_paths) if pod_paths.strip().startswith("[") else [pod_paths.strip()]
        except _json.JSONDecodeError:
            paths = [pod_paths.strip()]
        if not paths:
            return json_error("pod_paths 不能为空")

        files = await k8s_service.read_pod_files(
            pod_name=pod_name, pod_paths=paths, namespace=namespace, container=container,
        )

        if local_path:
            _os.makedirs(local_path, exist_ok=True)
            saved = []
            for f in files:
                if f.get("error"):
                    saved.append(f)
                    continue
                fname = _os.path.basename(f.get("path", "unknown"))
                dest = _os.path.join(local_path, fname)
                if f.get("encoding") == "base64":
                    with open(dest, "wb") as fh:
                        fh.write(_b64.b64decode(f["content"]))
                else:
                    with open(dest, "w", encoding="utf-8") as fh:
                        fh.write(f.get("content", ""))
                saved.append({
                    "path": f.get("path"),
                    "local_path": dest,
                    "encoding": f.get("encoding"),
                    "size": f.get("size"),
                })
            log_operation("copy_pod_files", "read_to_local", {
                "direction": "from_pod", "pod_name": pod_name,
                "pod_paths": paths, "local_path": local_path,
                "file_count": len(saved), "namespace": namespace,
            }, True)
            return json_success({
                "success": True, "direction": "from_pod",
                "saved_to": local_path, "files": saved,
            })

        log_operation("copy_pod_files", "read", {
            "direction": "from_pod", "pod_name": pod_name,
            "pod_paths": paths, "file_count": len(files), "namespace": namespace,
        }, True)
        return json_success({
            "success": True, "direction": "from_pod", "files": files,
            "hint": "文件内容已读取。如需保存到本地，请使用文件写入工具将 content 写入用户指定的路径；"
                    "或使用 local_path 参数直接保存到本地目录（二进制文件自动解码，无需中间 base64 文件）。",
        })

    # to_pod: 支持从 local_path 读取文件内容
    if local_path and not content:
        if not _os.path.isfile(local_path):
            return json_error(f"本地文件不存在: {local_path}")
        with open(local_path, "rb") as fh:
            raw = fh.read()
        try:
            content = raw.decode("utf-8")
            encoding = "text"
        except UnicodeDecodeError:
            content = _b64.b64encode(raw).decode("ascii")
            encoding = "base64"

    result_path = await k8s_service.write_pod_file(
        pod_name=pod_name, pod_path=pod_paths.strip(), content=content,
        encoding=encoding, namespace=namespace, container=container,
    )
    log_operation("copy_pod_files", "write", {
        "direction": "to_pod", "pod_name": pod_name,
        "pod_path": result_path, "namespace": namespace,
    }, True)
    return json_success({
        "success": True, "direction": "to_pod",
        "pod_path": result_path, "message": f"已写入 Pod 文件 {result_path}",
    })


import threading as _threading
import time as _time

_pf_sessions: dict = {}
_pf_lock = _threading.Lock()


def _get_pf_user() -> str:
    """获取当前用户 ID（非认证模式返回 '__anonymous__'）"""
    try:
        from config import MCP_AUTH_ENABLED
        if MCP_AUTH_ENABLED:
            from utils.auth_context import get_effective_user_id
            return get_effective_user_id()
    except Exception:
        pass
    return "__anonymous__"


@mcp.tool()
@handle_tool_errors
async def port_forward(
    action: str = "start",
    pod_name: Optional[str] = None,
    local_port: int = 0,
    pod_port: int = 0,
    namespace: str = "default",
    forward_id: Optional[str] = None,
    idle_timeout: int = 0,
    kubeconfig_path: Optional[str] = None,
    cluster_name: Optional[str] = None,
) -> str:
    """
    Pod 端口转发管理：启动、停止、列出转发会话

    Args:
        action: 操作类型 - "start"（启动转发）、"stop"（停止转发）、"list"（列出当前转发）
        pod_name: start 时必填，Pod 名称
        local_port: start 时必填，本地端口（1-65535）
        pod_port: start 时必填，Pod 端口（1-65535）
        namespace: Kubernetes 命名空间，默认 default
        forward_id: stop 时必填，要停止的转发会话 ID（由 start 返回或 list 查看）
        idle_timeout: start 时可选，空闲超时秒数（0=不超时）。超过此时间无连接活动则自动停止转发
        kubeconfig_path: kubeconfig 文件路径
        cluster_name: 集群配置名称

    Returns:
        start: 转发会话信息（含 forward_id）; stop: 停止确认; list: 所有活跃转发
    """
    uid = _get_pf_user()

    # ---------- list ----------
    if action == "list":
        with _pf_lock:
            user_sessions = []
            dead_ids = []
            for sid, s in _pf_sessions.items():
                if s["user"] != uid and uid != "__anonymous__":
                    continue
                alive = s["_run_flag"].get("running", False)
                if not alive:
                    dead_ids.append(sid)
                    continue
                user_sessions.append({
                    "forward_id": sid,
                    "pod_name": s["pod_name"],
                    "namespace": s["namespace"],
                    "local_port": s["local_port"],
                    "pod_port": s["pod_port"],
                    "started_at": s["started_at"],
                    "cluster_name": s.get("cluster_name"),
                })
            for sid in dead_ids:
                _pf_sessions.pop(sid, None)
        return json_success({"success": True, "action": "list", "forwards": user_sessions, "count": len(user_sessions)})

    # ---------- stop ----------
    if action == "stop":
        if not forward_id:
            return json_error("stop 操作需要 forward_id（可通过 action='list' 查看）")
        with _pf_lock:
            session = _pf_sessions.get(forward_id)
            if not session:
                return json_error(f"未找到转发会话: {forward_id}")
            if session["user"] != uid and uid != "__anonymous__":
                return json_error("无权停止其他用户的端口转发")
            session["_run_flag"]["running"] = False
            srv = session.get("_server_ref", {}).get("socket")
            if srv:
                try:
                    srv.close()
                except Exception:
                    pass
            info = {
                "forward_id": forward_id,
                "pod_name": session["pod_name"],
                "local_port": session["local_port"],
                "pod_port": session["pod_port"],
            }
            _pf_sessions.pop(forward_id, None)
        log_operation("port_forward", "stop", info, True)
        return json_success({"success": True, "action": "stop", **info, "message": "端口转发已停止"})

    # ---------- start ----------
    if action != "start":
        return json_error(f"不支持的 action: {action}，支持: start, stop, list")
    if not pod_name:
        return json_error("start 操作需要 pod_name")
    if not (1 <= local_port <= 65535) or not (1 <= pod_port <= 65535):
        return json_error("local_port 和 pod_port 必须在 1-65535 范围内")

    with _pf_lock:
        for s in _pf_sessions.values():
            if s["local_port"] == local_port and s["_run_flag"].get("running"):
                return json_error(f"本地端口 {local_port} 已被占用（forward_id={s['forward_id']}）")

    effective_path = resolve_kubeconfig_path(cluster_name, kubeconfig_path)
    k8s_service = get_k8s_api_service(effective_path)
    forward_result = await k8s_service.port_forward(
        pod_name=pod_name, local_port=local_port, pod_port=pod_port,
        namespace=namespace, idle_timeout=idle_timeout,
    )

    import secrets as _secrets
    fid = f"pf-{local_port}-{int(_time.time())}-{_secrets.token_hex(3)}"
    with _pf_lock:
        _pf_sessions[fid] = {
            "forward_id": fid,
            "user": uid,
            "pod_name": pod_name,
            "namespace": namespace,
            "local_port": local_port,
            "pod_port": pod_port,
            "cluster_name": cluster_name,
            "started_at": _time.strftime("%Y-%m-%d %H:%M:%S"),
            "_run_flag": forward_result.pop("_run_flag", {"running": True}),
            "_server_ref": forward_result.pop("_server_ref", {}),
        }

    log_operation("port_forward", "start", {
        "forward_id": fid, "pod_name": pod_name,
        "local_port": local_port, "pod_port": pod_port, "namespace": namespace,
    }, True)
    return json_success({
        "success": True, "action": "start", "forward_id": fid,
        "pod_name": pod_name, "namespace": namespace,
        "local_port": local_port, "pod_port": pod_port,
        "message": f"端口转发已启动: localhost:{local_port} -> {pod_name}:{pod_port}",
        "hint": f"停止转发: port_forward(action='stop', forward_id='{fid}')",
    })
