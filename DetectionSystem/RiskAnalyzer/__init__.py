"""
RiskAnalyzer 包：用于分析和评估热点舆情的风险等级，并生成预警信息。

模块结构：
- agent: 风险分析代理
- llm: LLM客户端和配置
- prompts: 提示词模板
- utils: 通用工具函数
- config: 配置文件
"""

# 版本信息
__version__ = "1.0.0"

# 组件可用性标志
_is_available = True

# 公共API导出列表
__all__ = [
    "__version__",
    "is_available"
]

def is_available() -> bool:
    """
    检查RiskAnalyzer组件是否可用
    
    Returns:
        bool: 组件是否可用
    """
    return _is_available