"""
HotspotHunter 包：用于捕捉社交平台热搜榜的负面舆情，并提供给 RiskAnalyzer。

模块结构：
- llm: 各类大模型客户端与解析工具
- tools: 热搜榜爬取与工具集合
- utils: 通用工具函数与配置
- state: Agent 状态管理
- agent: 热点猎手代理类实现
"""

# 版本信息
__version__ = "1.0.0"

# 组件可用性标志
_is_available = True

# 使用try-except包装导入，增加容错性
try:
    from .llm import LLMClient
except ImportError as e:
    print(f"HotspotHunter: LLM模块导入失败: {e}")
    _is_available = False
    LLMClient = None

try:
    from .tools import hotlist_crawler
except ImportError as e:
    print(f"HotspotHunter: 工具模块导入失败: {e}")
    _is_available = False
    hotlist_crawler = None

try:
    from .agent import HotspotHunterAgent
except ImportError as e:
    print(f"HotspotHunter: Agent模块导入失败: {e}")
    _is_available = False
    HotspotHunterAgent = None

# 公共API导出列表
__all__ = [
    "LLMClient",
    "hotlist_crawler",
    "HotspotHunterAgent",
    "__version__",
    "is_available"
]

def is_available() -> bool:
    """
    检查HotspotHunter组件是否可用
    
    Returns:
        bool: 组件是否可用
    """
    return _is_available
