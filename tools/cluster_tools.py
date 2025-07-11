"""
集群管理工具模块 - 使用FastMCP装饰器
"""
import json
import os
from typing import Dict, List, Any, Optional
from utils.cluster_config import ClusterConfigManager, ClusterInfo

# 导入共享的MCP实例
from . import mcp

# 初始化集群配置管理器
cluster_config = ClusterConfigManager()

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
        import os
        import yaml
        
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