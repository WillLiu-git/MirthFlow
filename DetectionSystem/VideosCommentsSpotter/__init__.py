"""
VideosCommentsSpotter 包：用于监控和分析视频平台评论区的舆情信息。

模块结构：
- tools: 视频平台数据爬取工具
  - videoscomments_crawler.py: 主要爬虫类实现
  - MediaCrawler: 多平台媒体爬虫实现
- llm: LLM客户端和配置
- prompts: 提示词模板
- utils: 通用工具函数
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
    检查VideosCommentsSpotter组件是否可用
    
    Returns:
        bool: 组件是否可用
    """
    return _is_available