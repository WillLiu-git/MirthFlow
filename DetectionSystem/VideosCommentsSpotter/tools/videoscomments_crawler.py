# -*- coding: utf-8 -*-
import os
import json
import asyncio
import time
import re
from loguru import logger
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, asdict, fields

# MediaCrawler 依赖 - 先将MediaCrawler目录添加到sys.path最前面，确保其内部导入能正常工作
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_CRAWLER_PATH = os.path.join(BASE_DIR, "MediaCrawler")

import sys

# 确保MediaCrawler目录在sys.path的最前面，这样它的内部导入会优先被找到
if MEDIA_CRAWLER_PATH not in sys.path:
    sys.path.insert(0, MEDIA_CRAWLER_PATH)

@dataclass
class CrawlerConfig:
    """
    MediaCrawler 配置数据类，提供所有支持的配置参数
    所有参数都有合理的默认值
    """
    # 基础配置
    platform: str = "dy"
    crawler_type: str = "search"
    keywords: str = ""
    enable_get_comments: bool = True
    enable_get_media: bool = False  # 不爬视频源文件，更快
    crawler_max_notes_count: int = 5  # 默认爬 5 个视频/帖子
    crawler_max_comments_count_single_notes: int = 15
    save_data_option: str = "json"  # 保存到JSON文件

    # 平台特定配置
    doyin_sleep_time: int = 3
    xhs_sleep_time: int = 4
    weibo_search_page_count: int = 2

    # 重试配置
    max_retries: int = 3
    retry_wait_time: int = 2  # 初始重试等待时间

    # 其他配置
    wait_time_after_crawl: int = 5  # 爬取完成后的等待时间

    def to_dict(self) -> Dict[str, Any]:
        """将配置转换为字典"""
        return asdict(self)

    def update(self, **kwargs) -> "CrawlerConfig":
        """更新配置参数"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        return self

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "CrawlerConfig":
        """从字典创建配置实例"""
        # 过滤出有效的字段
        valid_fields = {f.name for f in fields(cls)}
        filtered_dict = {k: v for k, v in config_dict.items() if k in valid_fields}
        return cls(**filtered_dict)

class VideoCommentSpotter:
    """
    Video & Comments Spotter tool
    封装 MediaCrawler，提供关键字视频 + 评论采集能力
    """

    def __init__(self, platform="dy", config=None):
        """
        初始化VideoCommentSpotter

        Args:
            platform: dy | bili | ks | wb | zhihu | tieba
            config: 配置参数，可以是字典或CrawlerConfig实例
        """
        # 直接使用模拟实现，不依赖外部模块
        self.platform = platform
        self.config = CrawlerConfig.from_dict(config or {}).update(platform=platform)
        
        # 创建模拟配置对象
        self._config = type('Config', (), {
            'PLATFORM': self.platform,
            'CRAWLER_TYPE': 'search',
            'KEYWORDS': '',
            'ENABLE_GET_COMMENTS': True,
            'ENABLE_GET_MEIDAS': False,
            'CRAWLER_MAX_NOTES_COUNT': 5,
            'CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES': 15,
            'SAVE_DATA_OPTION': 'json',
            'DOYIN_SLEEP_TIME': 3,
            'XHS_SLEEP_TIME': 4,
            'WEIBO_SEARCH_PAGE_COUNT': 2,
            'LOGIN_TYPE': 'qrcode',
            'START_PAGE': 1,
            'ENABLE_GET_SUB_COMMENTS': False,
            'COOKIES': '',
            'HEADLESS': True,
            'ENABLE_CDP_MODE': False
        })()

        logger.info(f"Video Spotter 初始化，平台 = {self.platform}")
        logger.info(f"初始配置: {self.config.to_dict()}")

    def _apply_config_to_mediacrawler(self, crawler_config: CrawlerConfig):
        """
        将CrawlerConfig应用到模拟配置

        Args:
            crawler_config: 爬虫配置实例
        """
        # 基础配置
        self._config.PLATFORM = crawler_config.platform
        self._config.CRAWLER_TYPE = crawler_config.crawler_type
        self._config.KEYWORDS = crawler_config.keywords
        self._config.ENABLE_GET_COMMENTS = crawler_config.enable_get_comments
        self._config.ENABLE_GET_MEIDAS = crawler_config.enable_get_media
        self._config.CRAWLER_MAX_NOTES_COUNT = crawler_config.crawler_max_notes_count
        self._config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES = crawler_config.crawler_max_comments_count_single_notes
        self._config.SAVE_DATA_OPTION = crawler_config.save_data_option

        # 平台特定配置
        self._config.DOYIN_SLEEP_TIME = crawler_config.doyin_sleep_time
        self._config.XHS_SLEEP_TIME = crawler_config.xhs_sleep_time
        self._config.WEIBO_SEARCH_PAGE_COUNT = crawler_config.weibo_search_page_count

        logger.debug(f"应用配置: {crawler_config.to_dict()}")

    def search(self, keyword: str, max_count: int = None, max_retries: int = None,
               enable_get_comments: bool = None, platform_config: Union[Dict[str, Any], CrawlerConfig] = None) -> Dict[
        str, Any]:
        """
        使用关键词搜索视频/帖子，并带回评论
        返回结构：
        {
          "keyword": "...",
          "platform": "xhs",
          "items": [
              {
                  "title": "...",
                  "url": "...",
                  "comments": [...],
              }
          ]
        }

        Args:
            keyword: 搜索关键词
            max_count: 最大爬取数量（None表示使用当前配置）
            max_retries: 最大重试次数（None表示使用当前配置）
            enable_get_comments: 是否获取评论（None表示使用当前配置）
            platform_config: 本次搜索特定的平台配置，可以是字典或CrawlerConfig实例

        Returns:
            爬取结果字典
        """
        logger.info(f"[Video Spotter] 正在搜索: {keyword}")
        logger.info("使用纯模拟实现，避免外部依赖")

        # 保存当前配置以便恢复
        original_config = self.config

        # 创建临时配置用于本次搜索
        temp_config = CrawlerConfig(**original_config.to_dict())
        temp_config.keywords = keyword

        # 更新临时配置
        if max_count is not None:
            temp_config.crawler_max_notes_count = max_count
        if max_retries is not None:
            temp_config.max_retries = max_retries
        if enable_get_comments is not None:
            temp_config.enable_get_comments = enable_get_comments

        # 应用本次搜索的特定配置
        if platform_config:
            if isinstance(platform_config, CrawlerConfig):
                temp_config.update(**platform_config.to_dict())
            elif isinstance(platform_config, dict):
                temp_config.update(**platform_config)
            logger.info(f"[Video Spotter] 应用搜索特定配置: {temp_config.to_dict()}")

        # 使用纯模拟实现，不依赖任何外部模块
        try:
            # 生成模拟数据
            mock_items = []
            actual_count = min(temp_config.crawler_max_notes_count, 5)  # 限制模拟数据数量
            
            # 随机数生成器
            import random
            
            # 视频标题模板，增加多样性
            title_templates = [
                f"{keyword}现场实拍：{keyword}训练情况",
                f"震撼！{keyword}最新动态曝光",
                f"直击{keyword}现场，精彩瞬间",
                f"{keyword}最新训练视频出炉",
                f"深度解析：{keyword}背后的故事"
            ]
            
            for i in range(actual_count):
                # 生成模拟评论
                mock_comments = []
                if temp_config.enable_get_comments:
                    # 随机评论数量，更真实
                    max_comment = min(temp_config.crawler_max_comments_count_single_notes, 15)
                    comment_count = random.randint(3, max_comment)
                    
                    for j in range(comment_count):
                        # 随机评论内容模板
                        comment_templates = [
                            f"这个{keyword}视频太震撼了！",
                            f"{keyword}训练看起来很专业",
                            f"没想到{keyword}还有这样的一面",
                            f"支持{keyword}，为他们点赞",
                            f"这个视频拍得真不错，很有现场感"
                        ]
                        
                        mock_comments.append({
                            "user": f"用户{random.randint(1000, 9999)}",  # 随机用户ID
                            "text": random.choice(comment_templates),  # 随机评论内容
                            "likes": random.randint(0, 500),  # 随机点赞数
                            "time": time.strftime("%Y-%m-%d %H:%M:%S")
                        })
                
                # 选择随机标题模板
                title = random.choice(title_templates)
                
                # 生成模拟视频/帖子
                mock_items.append({
                    "title": title,
                    "url": f"https://{self.platform}.com/video/{random.randint(100000, 999999)}",  # 随机URL
                    "comments": mock_comments,
                    "platform": self.platform,
                    "create_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "likes": random.randint(100, 10000),  # 随机点赞数，范围更大
                    "views": random.randint(1000, 100000),  # 随机观看数
                    "author": f"创作者{random.randint(1000, 9999)}"  # 添加作者信息
                })
            
            # 构建结果
            result = {
                "keyword": keyword,
                "platform": self.platform,
                "items": mock_items,
                "total_items": len(mock_items),
                "total_comments": sum(len(item["comments"]) for item in mock_items),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # 保存爬取结果到文件
            self._save_results(result, keyword)
            
            logger.info(f"[Video Spotter] 模拟搜索完成，生成 {result['total_items']} 条数据，{result['total_comments']} 条评论")
            return result
            
        except Exception as e:
            logger.error(f"[Video Spotter] 模拟爬虫出错: {e}")
            import traceback
            traceback.print_exc()
            return {
                "keyword": keyword,
                "platform": self.platform,
                "error": str(e),
                "items": [],
                "total_items": 0,
                "total_comments": 0,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        finally:
            # 恢复原配置
            if 'original_config' in locals():
                self._apply_config_to_mediacrawler(original_config)

    def _save_results(self, results: Dict[str, Any], keyword: str):
        """
        保存处理后的结果到文件
        """
        try:
            # 创建保存目录
            save_dir = os.path.join(BASE_DIR, "crawler_results")
            os.makedirs(save_dir, exist_ok=True)

            # 生成文件名
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{self.platform}_{keyword}_{timestamp}.json"
            filepath = os.path.join(save_dir, filename)

            # 保存数据
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

            logger.info(f"[Video Spotter] 结果已保存到: {filepath}")

        except Exception as e:
            logger.error(f"[Video Spotter] 保存结果出错: {e}")

    def search_multiple(self, keywords: List[str], max_count: int = 5, max_retries: int = 3, max_concurrency: int = 3,
                        platform_config: Union[Dict[str, Any], CrawlerConfig] = None) -> Dict[str, Any]:
        """
        并发搜索多个关键词

        Args:
            keywords: 关键词列表
            max_count: 每个关键词的最大爬取数量
            max_retries: 最大重试次数
            max_concurrency: 最大并发数
            platform_config: 本次搜索特定的平台配置，可以是字典或CrawlerConfig实例

        Returns:
            包含所有关键词搜索结果的字典
        """
        if not keywords:
            return {"results": [], "total_items": 0, "total_comments": 0}

        logger.info(f"[Video Spotter] 开始并发搜索 {len(keywords)} 个关键词，最大并发数: {max_concurrency}")

        # 使用同步方式实现，避免异步依赖
        results = []
        total_items = 0
        total_comments = 0

        for keyword in keywords:
            try:
                result = self.search(
                    keyword=keyword,
                    max_count=max_count,
                    max_retries=max_retries,
                    platform_config=platform_config
                )
                results.append(result)
                total_items += result.get('total_items', 0)
                total_comments += result.get('total_comments', 0)
                logger.info(f"[Video Spotter] 关键词 {keyword} 搜索完成，获取 {result.get('total_items', 0)} 条数据")
            except Exception as e:
                logger.error(f"[Video Spotter] 关键词 {keyword} 搜索失败: {e}")
                results.append({
                    "keyword": keyword,
                    "platform": self.platform,
                    "error": str(e),
                    "items": [],
                    "total_items": 0,
                    "total_comments": 0
                })

        logger.info(f"[Video Spotter] 所有关键词搜索完成，总共获取 {total_items} 条数据，{total_comments} 条评论")

        return {
            "results": results,
            "total_items": total_items,
            "total_comments": total_comments,
            "platform": self.platform,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

# 测试代码
if __name__ == "__main__":
    # 示例使用
    logger.info("=== 示例: 使用模拟爬虫实现 ===")
    spotter = VideoCommentSpotter(platform="dy")
    results = spotter.search(keyword="科技", max_count=5)
    logger.info(f"示例结果: {results['total_items']} 个视频/帖子, {results['total_comments']} 条评论")
    logger.info(f"模拟搜索成功！")
