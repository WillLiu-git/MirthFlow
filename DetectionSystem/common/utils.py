"""
公共工具函数模块
包含系统所有组件的通用工具函数
"""

import os
import json
import time
import random
import string
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


class JsonEncoder(json.JSONEncoder):
    """
    自定义JSON编码器，支持datetime等特殊类型
    """
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(obj, bytes):
            return obj.decode('utf-8', errors='replace')
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        else:
            return super().default(obj)


def safe_json_dump(data: Any, file_path: str, ensure_ascii: bool = False, indent: int = 2) -> bool:
    """
    安全保存JSON数据到文件
    
    Args:
        data: 要保存的数据
        file_path: 文件路径
        ensure_ascii: 是否确保ASCII编码
        indent: 缩进空格数
        
    Returns:
        是否保存成功
    """
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent, cls=JsonEncoder)
        return True
    except Exception as e:
        print(f"[Utils] 保存JSON文件失败: {e}")
        return False


def safe_json_load(file_path: str) -> Optional[Any]:
    """
    安全加载JSON文件
    
    Args:
        file_path: 文件路径
        
    Returns:
        加载的数据，失败返回None
    """
    try:
        if not os.path.exists(file_path):
            print(f"[Utils] JSON文件不存在: {file_path}")
            return None
        
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"[Utils] JSON文件解析失败: {e}")
        return None
    except Exception as e:
        print(f"[Utils] 加载JSON文件失败: {e}")
        return None


def generate_unique_id(prefix: str = "", length: int = 8) -> str:
    """
    生成唯一ID
    
    Args:
        prefix: 前缀
        length: 随机字符串长度
        
    Returns:
        唯一ID
    """
    timestamp = str(int(time.time() * 1000))
    random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=length))
    return f"{prefix}{timestamp}_{random_str}" if prefix else f"{timestamp}_{random_str}"


def get_current_time(format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    获取当前时间字符串
    
    Args:
        format: 时间格式
        
    Returns:
        当前时间字符串
    """
    return datetime.now().strftime(format)


def calculate_weighted_score(factors: List[Dict[str, Any]]) -> float:
    """
    计算加权分数
    
    Args:
        factors: 因素列表，每个因素包含name, value, weight
        
    Returns:
        加权分数
    """
    total_score = 0.0
    total_weight = 0.0
    
    for factor in factors:
        value = factor.get('value', 0.0)
        weight = factor.get('weight', 1.0)
        total_score += value * weight
        total_weight += weight
    
    return total_score / total_weight if total_weight > 0 else 0.0


def normalize_score(score: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """
    归一化分数到0-1范围
    
    Args:
        score: 原始分数
        min_val: 最小值
        max_val: 最大值
        
    Returns:
        归一化后的分数
    """
    if max_val <= min_val:
        return 0.0
    return max(0.0, min(1.0, (score - min_val) / (max_val - min_val)))


def get_random_sleep_time(min_time: float = 2.0, max_time: float = 5.0) -> float:
    """
    获取随机休眠时间
    
    Args:
        min_time: 最小休眠时间（秒）
        max_time: 最大休眠时间（秒）
        
    Returns:
        随机休眠时间
    """
    return random.uniform(min_time, max_time)


def format_file_size(size: int, unit: str = "B") -> str:
    """
    格式化文件大小
    
    Args:
        size: 文件大小（字节）
        unit: 初始单位
        
    Returns:
        格式化后的文件大小字符串
    """
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    unit_index = units.index(unit.upper())
    
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    
    return f"{size:.2f} {units[unit_index]}"


def safe_mkdir(dir_path: str) -> bool:
    """
    安全创建目录
    
    Args:
        dir_path: 目录路径
        
    Returns:
        是否创建成功
    """
    try:
        os.makedirs(dir_path, exist_ok=True)
        return True
    except Exception as e:
        print(f"[Utils] 创建目录失败: {e}")
        return False


def safe_rm_file(file_path: str) -> bool:
    """
    安全删除文件
    
    Args:
        file_path: 文件路径
        
    Returns:
        是否删除成功
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
        return True
    except Exception as e:
        print(f"[Utils] 删除文件失败: {e}")
        return False


def safe_move_file(src_path: str, dst_path: str) -> bool:
    """
    安全移动文件
    
    Args:
        src_path: 源文件路径
        dst_path: 目标文件路径
        
    Returns:
        是否移动成功
    """
    try:
        # 确保目标目录存在
        safe_mkdir(os.path.dirname(dst_path))
        
        # 如果目标文件存在，先删除
        safe_rm_file(dst_path)
        
        # 移动文件
        os.rename(src_path, dst_path)
        return True
    except Exception as e:
        print(f"[Utils] 移动文件失败: {e}")
        return False


def get_file_modified_time(file_path: str) -> Optional[datetime]:
    """
    获取文件修改时间
    
    Args:
        file_path: 文件路径
        
    Returns:
        文件修改时间，不存在返回None
    """
    try:
        if not os.path.exists(file_path):
            return None
        
        mtime = os.path.getmtime(file_path)
        return datetime.fromtimestamp(mtime)
    except Exception as e:
        print(f"[Utils] 获取文件修改时间失败: {e}")
        return None


def validate_dict_keys(data: Dict[str, Any], required_keys: List[str]) -> Tuple[bool, str]:
    """
    验证字典是否包含所有必需的键
    
    Args:
        data: 要验证的字典
        required_keys: 必需的键列表
        
    Returns:
        (是否验证通过, 错误信息)
    """
    if not isinstance(data, dict):
        return False, "数据类型不是字典"
    
    missing_keys = [key for key in required_keys if key not in data]
    if missing_keys:
        return False, f"缺少必需的键: {', '.join(missing_keys)}"
    
    return True, "验证通过"


def truncate_string(s: str, max_length: int, suffix: str = "...") -> str:
    """
    截断字符串
    
    Args:
        s: 要截断的字符串
        max_length: 最大长度
        suffix: 后缀
        
    Returns:
        截断后的字符串
    """
    if len(s) <= max_length:
        return s
    
    return s[:max_length - len(suffix)] + suffix


def mask_sensitive_info(data: Any, sensitive_keys: List[str] = None) -> Any:
    """
    脱敏敏感信息
    
    Args:
        data: 要脱敏的数据
        sensitive_keys: 敏感键列表
        
    Returns:
        脱敏后的数据
    """
    if sensitive_keys is None:
        sensitive_keys = ["password", "token", "api_key", "secret"]
    
    if isinstance(data, dict):
        masked_data = {}
        for key, value in data.items():
            if key.lower() in [sk.lower() for sk in sensitive_keys]:
                masked_data[key] = "***脱敏***"
            else:
                masked_data[key] = mask_sensitive_info(value, sensitive_keys)
        return masked_data
    elif isinstance(data, list):
        return [mask_sensitive_info(item, sensitive_keys) for item in data]
    else:
        return data
