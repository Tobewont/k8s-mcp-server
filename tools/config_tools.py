"""
配置管理工具模块 - 使用FastMCP装饰器
"""
import os
import json
import yaml
from typing import Dict, List, Any, Optional

# 导入共享的MCP实例
from . import mcp

# 配置目录
CONFIG_DIR = "data/kubeconfigs"
os.makedirs(CONFIG_DIR, exist_ok=True)

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
        kubeconfig内容
    """
    try:
        config_path = os.path.join(CONFIG_DIR, f"{name}.yaml")
        
        if not os.path.exists(config_path):
            error_result = {"success": False, "error": f"kubeconfig '{name}' 不存在"}
            return json.dumps(error_result, ensure_ascii=False, indent=2)
        
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 验证并解析配置
        try:
            config_data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            error_result = {"success": False, "error": f"配置文件格式错误: {str(e)}"}
            return json.dumps(error_result, ensure_ascii=False, indent=2)
        
        result = {
            "success": True,
            "name": name,
            "path": config_path,
            "content": content,
            "clusters": [cluster['name'] for cluster in config_data.get('clusters', [])],
            "contexts": [context['name'] for context in config_data.get('contexts', [])]
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2)

@mcp.tool()
async def list_kubeconfigs() -> str:
    """
    列出所有保存的kubeconfig文件
    
    Returns:
        kubeconfig文件列表
    """
    try:
        if not os.path.exists(CONFIG_DIR):
            result = {"success": True, "configs": [], "count": 0}
            return json.dumps(result, ensure_ascii=False, indent=2)
        
        configs = []
        for filename in os.listdir(CONFIG_DIR):
            if filename.endswith('.yaml') or filename.endswith('.yml'):
                config_name = os.path.splitext(filename)[0]
                config_path = os.path.join(CONFIG_DIR, filename)
                
                # 获取文件信息
                stat = os.stat(config_path)
                
                config_info = {
                    "name": config_name,
                    "filename": filename,
                    "path": config_path,
                    "size": stat.st_size,
                    "modified": stat.st_mtime
                }
                
                # 尝试读取集群信息
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config_data = yaml.safe_load(f.read())
                    
                    config_info["clusters"] = len(config_data.get('clusters', []))
                    config_info["contexts"] = len(config_data.get('contexts', []))
                except:
                    config_info["clusters"] = 0
                    config_info["contexts"] = 0
                    config_info["status"] = "无法解析"
                
                configs.append(config_info)
        
        result = {
            "success": True,
            "configs": configs,
            "count": len(configs)
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
            error_result = {
                "success": False,
                "valid": False,
                "error": f"YAML格式错误: {str(e)}"
            }
            return json.dumps(error_result, ensure_ascii=False, indent=2)
        
        # 检查基本结构
        if not isinstance(config_data, dict):
            error_result = {
                "success": True,
                "valid": False,
                "error": "kubeconfig必须是一个字典"
            }
            return json.dumps(error_result, ensure_ascii=False, indent=2)
        
        required_fields = ['clusters', 'contexts', 'users']
        missing_fields = [field for field in required_fields if field not in config_data]
        
        if missing_fields:
            error_result = {
                "success": True,
                "valid": False,
                "error": f"缺少必需字段: {', '.join(missing_fields)}"
            }
            return json.dumps(error_result, ensure_ascii=False, indent=2)
        
        # 检查字段内容
        clusters = config_data.get('clusters', [])
        contexts = config_data.get('contexts', [])
        users = config_data.get('users', [])
        
        validation_info = {
            "clusters": len(clusters),
            "contexts": len(contexts),
            "users": len(users),
            "current_context": config_data.get('current-context'),
            "cluster_names": [cluster.get('name') for cluster in clusters],
            "context_names": [context.get('name') for context in contexts],
            "user_names": [user.get('name') for user in users]
        }
        
        result = {
            "success": True,
            "valid": True,
            "message": "kubeconfig格式正确",
            "info": validation_info
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
        配置详细信息
    """
    try:
        config_path = os.path.join(CONFIG_DIR, f"{name}.yaml")
        
        if not os.path.exists(config_path):
            error_result = {"success": False, "error": f"kubeconfig '{name}' 不存在"}
            return json.dumps(error_result, ensure_ascii=False, indent=2)
        
        # 读取文件
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 解析配置
        try:
            config_data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            error_result = {"success": False, "error": f"配置文件格式错误: {str(e)}"}
            return json.dumps(error_result, ensure_ascii=False, indent=2)
        
        # 获取文件信息
        stat = os.stat(config_path)
        
        # 提取详细信息
        clusters = config_data.get('clusters', [])
        contexts = config_data.get('contexts', [])
        users = config_data.get('users', [])
        
        cluster_details = []
        for cluster in clusters:
            cluster_info = {
                "name": cluster.get('name'),
                "server": cluster.get('cluster', {}).get('server'),
                "certificate_authority": 'certificate-authority' in cluster.get('cluster', {}),
                "insecure_skip_tls_verify": cluster.get('cluster', {}).get('insecure-skip-tls-verify', False)
            }
            cluster_details.append(cluster_info)
        
        context_details = []
        for context in contexts:
            context_info = {
                "name": context.get('name'),
                "cluster": context.get('context', {}).get('cluster'),
                "user": context.get('context', {}).get('user'),
                "namespace": context.get('context', {}).get('namespace', 'default')
            }
            context_details.append(context_info)
        
        user_details = []
        for user in users:
            user_info = {
                "name": user.get('name'),
                "auth_method": "token" if 'token' in user.get('user', {}) else "certificate"
            }
            user_details.append(user_info)
        
        result = {
            "success": True,
            "name": name,
            "path": config_path,
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "current_context": config_data.get('current-context'),
            "clusters": cluster_details,
            "contexts": context_details,
            "users": user_details
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return json.dumps(error_result, ensure_ascii=False, indent=2) 