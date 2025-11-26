"""
llm 模块：负责各类大模型客户端与统一输出解析。

该模块提供标准化的大语言模型接入接口，
用于热点舆情分析和处理。
"""

from .llm import LLMClient

__all__ = [
    "LLMClient"
]
