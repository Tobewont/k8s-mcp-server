"""
集群和配置管理工具模块
整合集群管理和kubeconfig配置管理功能
"""
import os
import re
import yaml

from typing import Optional

from config import KUBECONFIGS_DIR
from utils.cluster_config import (
    ClusterInfo,
    get_cluster_config_manager,
    get_kubeconfig_path,
)
from utils.decorators import handle_tool_errors
from utils.operations_logger import log_operation
from utils.response import json_error, json_success

# 导入共享的MCP实例
from . import mcp

_CLUSTER_NAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._-]*$')


def _validate_cluster_name(name: str, strict: bool = False) -> Optional[str]:
    """
    校验集群名称。
    strict=True: 用于 import 等会创建文件的场景，仅允许字母、数字、点、下划线、连字符
    strict=False: 用于 get/delete 等仅查询场景，支持中文等 Unicode，仅禁止路径分隔符等特殊字符
    非法返回错误信息，合法返回 None
    """
    if not name or not str(name).strip():
        return "集群名称不能为空"
    s = str(name).strip()
    if strict:
        if not _CLUSTER_NAME_RE.match(s):
            return "集群名称只能包含字母、数字、点、下划线、连字符"
    else:
        if any(c in s for c in ('/', '\\', ':', '*', '?', '"', '<', '>', '|')):
            return "集群名称不能包含路径分隔符或特殊字符"
    return None

# ========================== 集群管理工具 ==========================

@mcp.tool()
@handle_tool_errors
async def import_cluster(name: str, kubeconfig: str, service_account: str = "default", 
                   namespace: str = "default", is_default: bool = False) -> str:
    """
    导入集群配置
    
    Args:
        name: 集群名称
        kubeconfig: kubeconfig文件内容或路径
        service_account: 服务账户名称，默认为default
        namespace: 默认命名空间，默认为default
        is_default: 是否设为默认集群，默认为False
    
    Returns:
        导入结果
    """
    err = _validate_cluster_name(name, strict=True)
    if err:
        return json_error(err)

    # 判断kubeconfig是文件路径还是内容
    kubeconfig_path = kubeconfig
    if not os.path.exists(kubeconfig):
        # 如果不是文件路径，则认为是内容，需要先保存到文件
        try:
            # 验证kubeconfig内容格式
            yaml.safe_load(kubeconfig)
            kubeconfig_path = get_cluster_config_manager().save_kubeconfig(name, kubeconfig)
        except yaml.YAMLError:
            return json_error("无效的kubeconfig格式")
    
    cluster_info = ClusterInfo(
        name=name,
        kubeconfig_path=kubeconfig_path,
        service_account=service_account,
        namespace=namespace,
        is_default=is_default
    )
    
    success = get_cluster_config_manager().add_cluster(cluster_info)
    log_operation("import_cluster", "import", {"name": name, "is_default": is_default}, success)

    if success:
        result = {
            "success": True,
            "message": f"集群 '{name}' 导入成功",
            "cluster": {
                "name": name,
                "service_account": service_account,
                "namespace": namespace,
                "is_default": is_default,
                "kubeconfig_path": kubeconfig_path
            }
        }
    else:
        result = {
            "success": False,
            "error": f"集群 '{name}' 已存在"
        }
    
    return json_success(result)

@mcp.tool()
@handle_tool_errors
async def list_clusters() -> str:
    """
    列出所有集群配置
    
    Returns:
        集群列表
    """
    clusters = get_cluster_config_manager().list_clusters()
    result = {
        "success": True,
        "clusters": [
            {
                "name": cluster.name,
                "service_account": cluster.service_account,
                "namespace": cluster.namespace,
                "is_default": cluster.is_default
            }
            for cluster in clusters
        ],
        "count": len(clusters)
    }
    
    return json_success(result)

@mcp.tool()
@handle_tool_errors
async def get_cluster(name: str) -> str:
    """
    获取指定集群配置
    
    Args:
        name: 集群名称
    
    Returns:
        集群配置信息
    """
    err = _validate_cluster_name(name, strict=False)
    if err:
        return json_error(err)
    cluster = get_cluster_config_manager().get_cluster(name)
    result = {
        "success": True,
        "cluster": {
            "name": cluster.name,
            "service_account": cluster.service_account,
            "namespace": cluster.namespace,
            "is_default": cluster.is_default
        }
    }
    
    return json_success(result)

@mcp.tool()
@handle_tool_errors
async def delete_cluster(name: str) -> str:
    """
    删除集群配置
    
    Args:
        name: 集群名称
    
    Returns:
        删除结果
    """
    err = _validate_cluster_name(name, strict=False)
    if err:
        return json_error(err)
    success = get_cluster_config_manager().remove_cluster(name)
    log_operation("delete_cluster", "delete", {"name": name}, success)

    if success:
        result = {
            "success": True,
            "message": f"集群 '{name}' 删除成功"
        }
    else:
        result = {
            "success": False,
            "error": f"集群 '{name}' 不存在"
        }
    
    return json_success(result)

@mcp.tool()
@handle_tool_errors
async def set_default_cluster(name: str) -> str:
    """
    设置默认集群
    
    Args:
        name: 集群名称
    
    Returns:
        设置结果
    """
    err = _validate_cluster_name(name, strict=False)  # 仅查找已有集群，支持中文名
    if err:
        return json_error(err)
    success = get_cluster_config_manager().set_default_cluster(name)
    log_operation("set_default_cluster", "update", {"name": name}, success)

    if success:
        result = {
            "success": True,
            "message": f"集群 '{name}' 已设置为默认集群"
        }
    else:
        result = {
            "success": False,
            "error": f"集群 '{name}' 不存在"
        }
    
    return json_success(result)

@mcp.tool()
@handle_tool_errors
async def test_cluster_connection(name: str) -> str:
    """
    测试集群连接
    
    Args:
        name: 集群名称
    
    Returns:
        连接测试结果
    """
    err = _validate_cluster_name(name, strict=True)
    if err:
        return json_error(err)
    from kubernetes import client, config
    cluster = get_cluster_config_manager().get_cluster(name)
    config.load_kube_config(config_file=cluster.kubeconfig_path)
    v1 = client.CoreV1Api()
    namespaces = v1.list_namespace()
    result = {
        "success": True,
        "message": f"集群 '{name}' 连接正常",
        "cluster_info": {
            "name": cluster.name,
            "namespace_count": len(namespaces.items),
            "default_namespace": cluster.namespace
        }
    }
    return json_success(result)

@mcp.tool()
@handle_tool_errors
async def get_default_cluster() -> str:
    """
    获取默认集群
    
    Returns:
        默认集群信息
    """
    default_cluster = get_cluster_config_manager().get_default_cluster()
    if default_cluster:
        result = {
            "success": True,
            "cluster": {
                "name": default_cluster.name,
                "service_account": default_cluster.service_account,
                "namespace": default_cluster.namespace,
                "is_default": default_cluster.is_default
            }
        }
    else:
        result = {
            "success": False,
            "error": "未设置默认集群"
        }
    
    return json_success(result)

# ========================== Kubeconfig 配置管理工具 ==========================

@mcp.tool()
@handle_tool_errors
async def save_kubeconfig(name: str, content: str) -> str:
    """
    保存kubeconfig文件
    
    Args:
        name: 配置名称
        content: kubeconfig文件内容
    
    Returns:
        保存结果
    """
    if not name or not str(name).strip():
        return json_error("配置名称不能为空")
    try:
        config_data = yaml.safe_load(content)
        if not isinstance(config_data, dict) or 'clusters' not in config_data:
            return json_error("无效的kubeconfig格式")
    except yaml.YAMLError as e:
        return json_error(f"YAML格式错误: {str(e)}")
    config_path = get_cluster_config_manager().save_kubeconfig(name, content)
    log_operation("save_kubeconfig", "create", {"name": name}, True)
    return json_success({"success": True, "message": f"kubeconfig '{name}' 保存成功", "path": config_path})

def _mask_kubeconfig_sensitive(content: str) -> str:
    """脱敏 kubeconfig 中的 token、证书等敏感字段（不修改原始数据）"""
    import copy
    try:
        data = yaml.safe_load(content)
        if not isinstance(data, dict) or "users" not in data:
            return content
        data = copy.deepcopy(data)
        for user in data.get("users", []):
            u = user.get("user", {})
            if "token" in u:
                u["token"] = "<masked>"
            if "client-certificate-data" in u:
                u["client-certificate-data"] = "<masked>"
            if "client-key-data" in u:
                u["client-key-data"] = "<masked>"
        return yaml.dump(data, allow_unicode=True, default_flow_style=False)
    except Exception:
        return content


@mcp.tool()
@handle_tool_errors
async def load_kubeconfig(name: str, mask_sensitive: bool = False) -> str:
    """
    加载kubeconfig文件
    
    注意：kubeconfig 包含集群认证凭据（token、证书等），请勿在不可信环境中暴露。
    可通过 mask_sensitive=True 脱敏 token、证书等敏感字段后再输出。
    
    Args:
        name: 配置名称
        mask_sensitive: 是否脱敏敏感字段（token、client-certificate-data、client-key-data），默认 False
    
    Returns:
        kubeconfig文件内容
    """
    if not name or not str(name).strip():
        return json_error("配置名称不能为空")
    config_path = get_kubeconfig_path(name)
    if not config_path:
        return json_error(f"kubeconfig '{name}' 不存在")
    with open(config_path, 'r', encoding='utf-8') as f:
        content = f.read()
    if mask_sensitive:
        content = _mask_kubeconfig_sensitive(content)
    return json_success({"success": True, "name": name, "content": content, "path": config_path, "masked": mask_sensitive})

@mcp.tool()
@handle_tool_errors
async def list_kubeconfigs() -> str:
    """
    列出所有保存的kubeconfig文件
    
    Returns:
        kubeconfig文件列表
    """
    if not os.path.exists(KUBECONFIGS_DIR):
        return json_success({"success": True, "kubeconfigs": [], "count": 0})
    kubeconfigs = []
    for filename in os.listdir(KUBECONFIGS_DIR):
        if filename.endswith('.yaml') or filename.endswith('.yml'):
            name = os.path.splitext(filename)[0]
            config_path = os.path.join(KUBECONFIGS_DIR, filename)
            stat = os.stat(config_path)
            kubeconfigs.append({"name": name, "path": config_path, "size": stat.st_size, "modified": stat.st_mtime})
    return json_success({"success": True, "kubeconfigs": kubeconfigs, "count": len(kubeconfigs)})

@mcp.tool()
@handle_tool_errors
async def delete_kubeconfig(name: str) -> str:
    """
    删除kubeconfig文件
    
    Args:
        name: 配置名称
    
    Returns:
        删除结果
    """
    try:
        config_path = get_kubeconfig_path(name)
        if not config_path:
            return json_error(f"kubeconfig '{name}' 不存在")
        
        os.remove(config_path)
        log_operation("delete_kubeconfig", "delete", {"name": name}, True)

        result = {
            "success": True,
            "message": f"kubeconfig '{name}' 删除成功"
        }
        
        return json_success(result)
        
    except Exception as e:
        return json_error(str(e))

@mcp.tool()
@handle_tool_errors
async def validate_kubeconfig(content: str) -> str:
    """
    验证kubeconfig文件格式
    
    Args:
        content: kubeconfig文件内容
    
    Returns:
        验证结果
    """
    try:
        config_data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        return json_error(f"YAML格式错误: {str(e)}", valid=False)
    if not isinstance(config_data, dict):
        return json_error("kubeconfig必须是一个字典对象", valid=False)
    required_fields = ['clusters', 'contexts', 'users']
    missing_fields = [f for f in required_fields if f not in config_data]
    if missing_fields:
        return json_error(f"缺少必需字段: {', '.join(missing_fields)}", valid=False)
    return json_success({
        "success": True, "valid": True, "message": "kubeconfig格式有效",
        "info": {
            "clusters_count": len(config_data.get('clusters', [])),
            "contexts_count": len(config_data.get('contexts', [])),
            "users_count": len(config_data.get('users', [])),
            "current_context": config_data.get('current-context', '')
        }
    })

@mcp.tool()
@handle_tool_errors
async def get_kubeconfig_info(name: str) -> str:
    """
    获取kubeconfig文件的详细信息
    
    Args:
        name: 配置名称
    
    Returns:
        kubeconfig详细信息
    """
    if not name or not str(name).strip():
        return json_error("配置名称不能为空")
    config_path = get_kubeconfig_path(name)
    if not config_path:
        return json_error(f"kubeconfig '{name}' 不存在")
    with open(config_path, 'r', encoding='utf-8') as f:
        content = f.read()
    try:
        config_data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        return json_error(f"YAML格式错误: {str(e)}")
    stat = os.stat(config_path)
    clusters = [{"name": c.get('name', ''), "server": c.get('cluster', {}).get('server', '')} for c in config_data.get('clusters', [])]
    contexts = [{"name": ctx.get('name', ''), "cluster": ctx.get('context', {}).get('cluster', ''), "user": ctx.get('context', {}).get('user', ''), "namespace": ctx.get('context', {}).get('namespace', 'default')} for ctx in config_data.get('contexts', [])]
    users = [{"name": u.get('name', ''), "auth_method": "token" if u.get('user', {}).get('token') else "cert" if u.get('user', {}).get('client-certificate') else "exec" if u.get('user', {}).get('exec') else "unknown"} for u in config_data.get('users', [])]
    return json_success({
        "success": True, "name": name, "path": config_path,
        "file_info": {"size": stat.st_size, "modified": stat.st_mtime},
        "config_info": {"current_context": config_data.get('current-context', ''), "clusters": clusters, "contexts": contexts, "users": users}
    })
