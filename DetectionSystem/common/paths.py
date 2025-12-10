"""
统一路径配置模块
提供项目中所有路径的统一管理，避免硬编码路径
"""

import os
from pathlib import Path
from typing import Dict


def get_project_root() -> Path:
    """
    获取项目根目录
    
    Returns:
        项目根目录的Path对象
    """
    # 从当前文件位置向上查找，找到包含main.py的目录
    current_file = Path(__file__).resolve()
    # DetectionSystem/common/paths.py -> DetectionSystem -> 项目根目录
    detection_system_dir = current_file.parent.parent
    project_root = detection_system_dir.parent
    return project_root


def get_paths() -> Dict[str, Path]:
    """
    获取所有系统路径配置
    
    Returns:
        包含所有路径配置的字典
    """
    project_root = get_project_root()
    detection_system = project_root / "DetectionSystem"
    
    paths = {
        # 项目根目录
        "project_root": project_root,
        "detection_system": detection_system,
        
        # 日志目录
        "logs_dir": project_root / "logs",
        "system_log": project_root / "logs" / "system.log",
        "error_log": project_root / "logs" / "error.log",
        
        # HotspotHunter路径
        "hotspot_hunter_dir": detection_system / "HotspotHunter",
        "hotspot_hunter_resource": detection_system / "HotspotHunter" / "resource",
        "hotspot_hunter_log": detection_system / "HotspotHunter" / "resource" / "HotspotHunter.log",
        "hotspot_hunter_output": detection_system / "hotspot_hunter_output",
        "intelligence_feed": detection_system / "HotspotHunter" / "resource" / "intelligence_feed.json",
        
        # RiskAnalyzer路径
        "risk_analyzer_dir": detection_system / "RiskAnalyzer",
        "risk_analyzer_resource": detection_system / "RiskAnalyzer" / "resource",
        "risk_analyzer_log": detection_system / "RiskAnalyzer" / "resource" / "RiskAnalyzer.log",
        "system_alerts": detection_system / "RiskAnalyzer" / "resource" / "system_alerts.json",
        
        # VideosCommentsSpotter路径
        "vcs_dir": detection_system / "VideosCommentsSpotter",
        "vcs_resource": detection_system / "VideosCommentsSpotter" / "resource",
        "vcs_log": detection_system / "VideosCommentsSpotter" / "resource" / "VideosCommentsSpotter.log",
        "vcs_output": detection_system / "VideosCommentsSpotter" / "output",
        
        # 输出目录
        "output_dir": project_root / "output",
    }
    
    return paths


# 全局路径配置实例
_PATHS = None


def get_path(key: str) -> Path:
    """
    获取特定路径
    
    Args:
        key: 路径键名
        
    Returns:
        路径的Path对象
        
    Raises:
        KeyError: 如果键不存在
    """
    global _PATHS
    if _PATHS is None:
        _PATHS = get_paths()
    
    if key not in _PATHS:
        raise KeyError(f"路径键 '{key}' 不存在。可用键: {list(_PATHS.keys())}")
    
    return _PATHS[key]


def get_path_str(key: str) -> str:
    """
    获取特定路径的字符串形式
    
    Args:
        key: 路径键名
        
    Returns:
        路径字符串
    """
    return str(get_path(key))


# 便捷函数，直接获取常用路径
def get_log_paths() -> Dict[str, str]:
    """
    获取所有日志文件路径（用于Flask应用）
    
    Returns:
        日志路径字典
    """
    paths = get_paths()
    return {
        'HotspotHunter': str(paths['hotspot_hunter_log']),
        'RiskAnalyzer': str(paths['risk_analyzer_log']),
        'VideosCommentsSpotter': str(paths['vcs_log']),
        'System': str(paths['system_log'])
    }


def get_alerts_file() -> str:
    """
    获取预警文件路径
    
    Returns:
        预警文件路径字符串
    """
    return get_path_str('system_alerts')


def get_hotspot_hunter_output_dir() -> str:
    """
    获取HotspotHunter输出目录
    
    Returns:
        输出目录路径字符串
    """
    return get_path_str('hotspot_hunter_output')


def get_vcs_output_dir() -> str:
    """
    获取VideosCommentsSpotter输出目录
    
    Returns:
        输出目录路径字符串
    """
    return get_path_str('vcs_output')


def ensure_directories():
    """
    确保所有必要的目录存在
    """
    paths = get_paths()
    for key, path in paths.items():
        if key.endswith('_dir') or key.endswith('_resource') or key.endswith('_output'):
            path.mkdir(parents=True, exist_ok=True)
        elif key.endswith('_log') or key.endswith('_feed') or key.endswith('_alerts'):
            # 确保文件所在目录存在
            path.parent.mkdir(parents=True, exist_ok=True)


