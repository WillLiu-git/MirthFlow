"""
HotspotHunter 包：用于捕捉社交平台热搜榜的负面舆情，并提供给 RiskAnalyzer。

模块结构：
- llm: 各类大模型客户端与解析工具
- tools: 热搜榜爬取与工具集合
- utils: 通用工具函数与配置
- state: Agent 状态管理
- agent: 热点猎手代理类实现
"""

from .llm import LLMClient
from .tools import hotlist_crawler
from .agent import HotspotHunterAgent

__all__ = [
    "LLMClient",
    "hotlist_crawler",
    "HotspotHunterAgent"
]
