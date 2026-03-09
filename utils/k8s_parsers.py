"""
Kubernetes 资源量解析工具
"""


def parse_cpu(cpu_str: str) -> float:
    """解析 CPU 字符串为核心数（支持 m、n 等单位），非法输入返回 0.0"""
    if not cpu_str:
        return 0.0
    try:
        cpu_str = str(cpu_str).strip().lower()
        if not cpu_str:
            return 0.0
        if cpu_str.endswith('m'):
            return float(cpu_str[:-1]) / 1000
        if cpu_str.endswith('n'):
            return float(cpu_str[:-1]) / 1000000000
        return float(cpu_str)
    except (ValueError, TypeError):
        return 0.0


def parse_memory(memory_str: str) -> int:
    """解析内存字符串为字节数，非法输入返回 0"""
    if not memory_str:
        return 0
    try:
        memory_str = str(memory_str).strip()
        if not memory_str:
            return 0
        units = {
            'Ki': 1024,
            'Mi': 1024**2,
            'Gi': 1024**3,
            'Ti': 1024**4,
            'K': 1000,
            'M': 1000**2,
            'G': 1000**3,
            'T': 1000**4
        }
        for unit, multiplier in units.items():
            if memory_str.endswith(unit):
                return int(float(memory_str[:-len(unit)]) * multiplier)
        return int(float(memory_str))
    except (ValueError, TypeError):
        return 0
