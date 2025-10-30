"""
集群和配置管理工具模块
整合集群管理和kubeconfig配置管理功能
"""
import json
import os
import yaml
from typing import Dict, List, Any, Optional
from utils.cluster_config import ClusterConfigManager, ClusterInfo

# 导入共享的MCP实例
from . import mcp

# 初始化集群配置管理器
cluster_config = ClusterConfigManager()

# 配置目录
CONFIG_DIR = "data/kubeconfigs"
os.makedirs(CONFIG_DIR, exist_ok=True)

# ========================== 集群管理工具 ==========================

@mcp.tool()
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
    try:
        # 判断kubeconfig是文件路径还是内容
        kubeconfig_path = kubeconfig
        if not os.path.exists(kubeconfig):
            # 如果不是文件路径，则认为是内容，需要先保存到文件
            try:
                # 验证kubeconfig内容格式
                yaml.safe_load(kubeconfig)
                kubeconfig_path = cluster_config.save_kubeconfig(name, kubeconfig)
            except yaml.YAMLError:
                return json.dumps({
                    "success": False,
                    "error": "无效的kubeconfig格式"
                }, ensure_ascii=False, indent=2)
        
        cluster_info = ClusterInfo(
            name=name,
            kubeconfig_path=kubeconfig_path,
            service_account=service_account,
            namespace=namespace,
            is_default=is_default
        )
        
        success = cluster_config.add_cluster(cluster_info)
        
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
        
        return json.dumps(result, ensure_ascii=False, indent=2)
            
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def list_clusters(random_string: str = "") -> str:
    """
    列出所有集群配置
    
    Args:
        random_string: 临时参数，用于解决MCP框架兼容性问题
    
    Returns:
        集群列表
    """
    try:
        clusters = cluster_config.list_clusters()
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
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def get_cluster(name: str) -> str:
    """
    获取指定集群配置
    
    Args:
        name: 集群名称
    
    Returns:
        集群配置信息
    """
    try:
        cluster = cluster_config.get_cluster(name)
        result = {
            "success": True,
            "cluster": {
                "name": cluster.name,
                "service_account": cluster.service_account,
                "namespace": cluster.namespace,
                "is_default": cluster.is_default
            }
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except ValueError as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def delete_cluster(name: str) -> str:
    """
    删除集群配置
    
    Args:
        name: 集群名称
    
    Returns:
        删除结果
    """
    try:
        success = cluster_config.remove_cluster(name)
        
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
        
        return json.dumps(result, ensure_ascii=False, indent=2)
            
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def set_default_cluster(name: str) -> str:
    """
    设置默认集群
    
    Args:
        name: 集群名称
    
    Returns:
        设置结果
    """
    try:
        # 直接使用集群配置管理器的方法设置默认集群
        success = cluster_config.set_default_cluster(name)
        
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
        
        return json.dumps(result, ensure_ascii=False, indent=2)
            
    except ValueError as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def test_cluster_connection(name: str) -> str:
    """
    测试集群连接
    
    Args:
        name: 集群名称
    
    Returns:
        连接测试结果
    """
    try:
        from kubernetes import client, config
        
        # 获取集群配置
        cluster = cluster_config.get_cluster(name)
        
        # 加载kubeconfig
        config.load_kube_config(config_file=cluster.kubeconfig_path)
        
        # 测试连接
        v1 = client.CoreV1Api()
        # 尝试获取命名空间列表
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
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except ValueError as e:
        error_result = {"success": False, "error": f"集群不存在: {str(e)}"}
        return json.dumps(error_result, ensure_ascii=False, indent=2)
    except Exception as e:
        error_result = {"success": False, "error": f"连接失败: {str(e)}"}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def get_default_cluster(random_string: str = "") -> str:
    """
    获取默认集群
    
    Args:
        random_string: 临时参数，用于解决MCP框架兼容性问题
    
    Returns:
        默认集群信息
    """
    try:
        default_cluster = cluster_config.get_default_cluster()
        
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
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

# ========================== Kubeconfig 配置管理工具 ==========================

@mcp.tool()
async def save_kubeconfig(name: str, content: str) -> str:
    """
    保存kubeconfig文件
    
    Args:
        name: 配置名称
        content: kubeconfig文件内容
    
    Returns:
        保存结果
    """
    try:
        config_path = os.path.join(CONFIG_DIR, f"{name}.yaml")
        
        # 验证kubeconfig格式
        try:
            config_data = yaml.safe_load(content)
            if not isinstance(config_data, dict) or 'clusters' not in config_data:
                error_result = {"success": False, "error": "无效的kubeconfig格式"}
                return json.dumps(error_result, ensure_ascii=False, indent=2)
        except yaml.YAMLError as e:
            error_result = {"success": False, "error": f"YAML格式错误: {str(e)}"}
            return json.dumps(error_result, ensure_ascii=False, indent=2)
        
        # 保存文件
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        result = {
            "success": True,
            "message": f"kubeconfig '{name}' 保存成功",
            "path": config_path
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def load_kubeconfig(name: str) -> str:
    """
    加载kubeconfig文件
    
    Args:
        name: 配置名称
    
    Returns:
        kubeconfig文件内容
    """
    try:
        config_path = os.path.join(CONFIG_DIR, f"{name}.yaml")
        
        if not os.path.exists(config_path):
            error_result = {"success": False, "error": f"kubeconfig '{name}' 不存在"}
            return json.dumps(error_result, ensure_ascii=False, indent=2)
        
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        result = {
            "success": True,
            "name": name,
            "content": content,
            "path": config_path
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def list_kubeconfigs(random_string: str = "") -> str:
    """
    列出所有保存的kubeconfig文件
    
    Args:
        random_string: 临时参数，用于解决MCP框架兼容性问题
    
    Returns:
        kubeconfig文件列表
    """
    try:
        if not os.path.exists(CONFIG_DIR):
            result = {
                "success": True,
                "kubeconfigs": [],
                "count": 0
            }
            return json.dumps(result, ensure_ascii=False, indent=2)
        
        kubeconfigs = []
        for filename in os.listdir(CONFIG_DIR):
            if filename.endswith('.yaml') or filename.endswith('.yml'):
                name = os.path.splitext(filename)[0]
                config_path = os.path.join(CONFIG_DIR, filename)
                
                # 获取文件信息
                stat = os.stat(config_path)
                kubeconfigs.append({
                    "name": name,
                    "path": config_path,
                    "size": stat.st_size,
                    "modified": stat.st_mtime
                })
        
        result = {
            "success": True,
            "kubeconfigs": kubeconfigs,
            "count": len(kubeconfigs)
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def delete_kubeconfig(name: str) -> str:
    """
    删除kubeconfig文件
    
    Args:
        name: 配置名称
    
    Returns:
        删除结果
    """
    try:
        config_path = os.path.join(CONFIG_DIR, f"{name}.yaml")
        
        if not os.path.exists(config_path):
            error_result = {"success": False, "error": f"kubeconfig '{name}' 不存在"}
            return json.dumps(error_result, ensure_ascii=False, indent=2)
        
        os.remove(config_path)
        
        result = {
            "success": True,
            "message": f"kubeconfig '{name}' 删除成功"
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def validate_kubeconfig(content: str) -> str:
    """
    验证kubeconfig文件格式
    
    Args:
        content: kubeconfig文件内容
    
    Returns:
        验证结果
    """
    try:
        # 解析YAML
        try:
            config_data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            return json.dumps({
                "success": False,
                "valid": False,
                "error": f"YAML格式错误: {str(e)}"
            }, ensure_ascii=False, indent=2)
        
        # 验证基本结构
        if not isinstance(config_data, dict):
            return json.dumps({
                "success": False,
                "valid": False,
                "error": "kubeconfig必须是一个字典对象"
            }, ensure_ascii=False, indent=2)
        
        required_fields = ['clusters', 'contexts', 'users']
        missing_fields = []
        
        for field in required_fields:
            if field not in config_data:
                missing_fields.append(field)
        
        if missing_fields:
            return json.dumps({
                "success": False,
                "valid": False,
                "error": f"缺少必需字段: {', '.join(missing_fields)}"
            }, ensure_ascii=False, indent=2)
        
        # 统计信息
        clusters_count = len(config_data.get('clusters', []))
        contexts_count = len(config_data.get('contexts', []))
        users_count = len(config_data.get('users', []))
        current_context = config_data.get('current-context', '')
        
        result = {
            "success": True,
            "valid": True,
            "message": "kubeconfig格式有效",
            "info": {
                "clusters_count": clusters_count,
                "contexts_count": contexts_count,
                "users_count": users_count,
                "current_context": current_context
            }
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def get_kubeconfig_info(name: str) -> str:
    """
    获取kubeconfig文件的详细信息
    
    Args:
        name: 配置名称
    
    Returns:
        kubeconfig详细信息
    """
    try:
        config_path = os.path.join(CONFIG_DIR, f"{name}.yaml")
        
        if not os.path.exists(config_path):
            error_result = {"success": False, "error": f"kubeconfig '{name}' 不存在"}
            return json.dumps(error_result, ensure_ascii=False, indent=2)
        
        # 读取文件内容
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 解析配置
        try:
            config_data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            return json.dumps({
                "success": False,
                "error": f"YAML格式错误: {str(e)}"
            }, ensure_ascii=False, indent=2)
        
        # 获取文件信息
        stat = os.stat(config_path)
        
        # 提取集群信息
        clusters = []
        for cluster in config_data.get('clusters', []):
            clusters.append({
                "name": cluster.get('name', ''),
                "server": cluster.get('cluster', {}).get('server', '')
            })
        
        # 提取上下文信息
        contexts = []
        for context in config_data.get('contexts', []):
            contexts.append({
                "name": context.get('name', ''),
                "cluster": context.get('context', {}).get('cluster', ''),
                "user": context.get('context', {}).get('user', ''),
                "namespace": context.get('context', {}).get('namespace', 'default')
            })
        
        # 提取用户信息
        users = []
        for user in config_data.get('users', []):
            users.append({
                "name": user.get('name', ''),
                "auth_method": "token" if user.get('user', {}).get('token') else 
                             "cert" if user.get('user', {}).get('client-certificate') else
                             "exec" if user.get('user', {}).get('exec') else "unknown"
            })
        
        result = {
            "success": True,
            "name": name,
            "path": config_path,
            "file_info": {
                "size": stat.st_size,
                "modified": stat.st_mtime
            },
            "config_info": {
                "current_context": config_data.get('current-context', ''),
                "clusters": clusters,
                "contexts": contexts,
                "users": users
            }
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)
