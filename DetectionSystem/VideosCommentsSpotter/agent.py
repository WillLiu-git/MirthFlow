# VideosCommentsSpotter/agent.py

import os
import sys
import json
import time
import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Any

# 配置日志系统
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resource', 'VideosCommentsSpotter.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- 导入策略：先导入所有不需要MediaCrawler的模块 ---

# 1. 确保当前目录在sys.path中
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# 2. 导入VideosCommentsSpotter自己的模块（不包括爬虫模块）
from llm import LLMClient
from utils.config import LLM_CONFIG, OUTPUT_DIRECTORY
from prompts.prompts import VCS_KEYWORD_PROMPT, VCS_ANALYSIS_PROMPT

# 3. 导入爬虫模块的特殊处理
# 3.1 获取爬虫模块的完整路径
crawler_file_path = os.path.join(current_dir, 'tools', 'videoscomments_crawler.py')

# 3.2 检查文件是否存在
if not os.path.exists(crawler_file_path):
    raise FileNotFoundError(f"爬虫模块文件不存在: {crawler_file_path}")

# 3.3 使用更高效的导入方式
VideoCommentSpotter = None

try:
    # 直接导入爬虫类，提高导入效率
    from tools.videoscomments_crawler import VideoCommentSpotter
    # 只在实际运行时才输出日志，导入时不输出
    # logger.info("✅ 成功使用直接导入方式导入VideoCommentSpotter")
except ImportError:
    # 如果直接导入失败，尝试动态导入
    import importlib.util
    logger.warning("⚠️  直接导入失败，尝试动态导入")
    try:
        # 创建一个模块规范
        spec = importlib.util.spec_from_file_location("videoscomments_crawler", crawler_file_path)
        
        # 创建一个模块对象
        videoscomments_crawler = importlib.util.module_from_spec(spec)
        
        # 将模块添加到sys.modules中
        sys.modules["videoscomments_crawler"] = videoscomments_crawler
        
        # 执行模块的代码
        spec.loader.exec_module(videoscomments_crawler)
        
        # 从模块中获取VideoCommentSpotter类
        VideoCommentSpotter = videoscomments_crawler.VideoCommentSpotter
        
        # 只在实际运行时才输出日志，导入时不输出
        # logger.info("✅ 成功使用动态导入方式导入VideoCommentSpotter")
        
    except Exception as e:
        logger.error(f"无法动态导入VideoCommentSpotter: {e}")
        # 提供更详细的错误信息
        import traceback
        traceback.print_exc()
        # 创建一个模拟的VideoCommentSpotter类，以便代码可以继续运行
        class MockVideoCommentSpotter:
            def __init__(self, platform="dy"):
                self.platform = platform
                self.crawlers = {}
            
            def search_multiple(self, keywords, max_count=20, max_retries=3, max_concurrency=3, platform_config=None):
                logger.warning(f"模拟爬虫: 在{self.platform}平台上搜索关键词 {keywords}，但实际爬虫未导入")
                return {
                    "results": [],
                    "total_items": 0,
                    "total_comments": 0,
                    "platform": self.platform,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
            
            def search(self, keyword, max_count=None, max_retries=None, enable_get_comments=None, platform_config=None):
                logger.warning(f"模拟爬虫: 在{self.platform}平台上搜索关键词 {keyword}，但实际爬虫未导入")
                return {
                    "keyword": keyword,
                    "platform": self.platform,
                    "error": "实际爬虫未导入，使用模拟爬虫",
                    "items": [],
                    "total_items": 0,
                    "total_comments": 0,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
        
        VideoCommentSpotter = MockVideoCommentSpotter
        logger.warning("⚠️  使用模拟的VideoCommentSpotter类，爬虫功能将不可用")


class VideosCommentsSpotterAgent:
    """
    Videos & Comments Spotter Agent (侦察兵/分析者):
    1. 接收Risk Analyzer传来的危险话题
    2. 使用LLM分析话题生成关键词
    3. 调用MediaCrawler爬取相关视频和评论
    4. 分析爬取内容生成汇总报告
    5. 返回报告给Risk Analyzer
    """

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        self.output_dir = Path(OUTPUT_DIRECTORY)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.memory_file = self.output_dir / "vcs_memory.json"
        self.memory: List[Dict] = self._load_memory()
        
    def _load_memory(self) -> List[Dict]:
        """加载历史记忆"""
        if self.memory_file.exists():
            with open(self.memory_file, "r", encoding="utf-8") as f:
                try:
                    # 只加载最近200条记忆
                    return json.load(f)[-200:]
                except json.JSONDecodeError:
                    return []
        return []
    
    def _save_memory(self):
        """保存历史记忆"""
        with open(self.memory_file, "w", encoding="utf-8") as f:
            # 只保存最近1000条记忆
            json.dump(self.memory[-1000:], f, ensure_ascii=False, indent=2)
    
    def generate_keywords(self, risk_topic: Dict[str, Any]) -> Dict[str, Any]:
        """
        使用LLM分析危险话题，生成适合爬取的关键词和爬取参数
        
        Args:
            risk_topic: 来自Risk Analyzer的危险话题
            
        Returns:
            包含关键词、爬取参数的配置
        """
        system_prompt = "你是一个专业的舆情分析助手，擅长从复杂话题中提取关键信息并制定搜索策略。请严格按照指定格式输出JSON结果。"
        
        # 获取原话题文本，用于后续关键词验证
        original_topic = risk_topic.get('topic', '').strip() or '未命名话题'
        
        # 修改用户提示，要求生成的关键词更加严格地基于原话题
        user_prompt = VCS_KEYWORD_PROMPT
        user_prompt = user_prompt.replace('{risk_topic}', json.dumps(risk_topic, ensure_ascii=False))
        
        # 增强提示词，要求关键词更加精准，同时提升预警阈值
        user_prompt += "\n\n特别要求："
        user_prompt += "1. 生成的关键词必须直接来自原话题，或者是原话题的核心组成部分"
        user_prompt += "2. 只生成与原话题高度相关的关键词，避免生成无关或弱相关的扩展关键词"
        user_prompt += "3. 关键词数量控制在3-5个，确保每个关键词都具有高度相关性"
        user_prompt += f"4. 原话题是 '{original_topic}'，请确保所有关键词都紧密围绕这个话题"
        user_prompt += "5. 生成的关键词应优先考虑那些可能包含负面舆情的词汇"
        user_prompt += "6. 提高风险预警阈值，只关注真正可能存在风险的内容"
        
        try:
            response = self.llm.invoke(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_mode=True,
                temperature=0.1  # 大幅降低温度，确保关键词严格基于原话题，减少幻觉
            )
            
            result = json.loads(response)
            
            # 验证结果格式
            if isinstance(result, dict) and 'keywords_config' in result:
                # 对生成的关键词进行过滤和验证（更严格的验证）
                filtered_keywords = []
                for kw_config in result['keywords_config']:
                    keyword = kw_config.get('keyword', '').strip()
                    
                    # 1. 检查关键词是否为空
                    if not keyword:
                        logger.warning(f"过滤掉空关键词")
                        continue
                    
                    # 2. 检查关键词长度（太短或太长都不合适）
                    if len(keyword) < 2 or len(keyword) > 20:
                        logger.warning(f"过滤掉长度不合适的关键词: {keyword} (长度: {len(keyword)})")
                        continue
                    
                    # 3. 检查关键词是否与原话题高度相关
                    if self._is_keyword_relevant(keyword, original_topic):
                        # 4. 验证爬取参数是否合理
                        max_video_count = kw_config.get('max_video_count', 5)
                        max_comment_count = kw_config.get('max_comment_count', 15)
                        
                        # 限制爬取数量，避免过度爬取
                        max_video_count = min(max_video_count, 5)
                        max_comment_count = min(max_comment_count, 15)
                        
                        kw_config['max_video_count'] = max_video_count
                        kw_config['max_comment_count'] = max_comment_count
                        filtered_keywords.append(kw_config)
                        logger.info(f"✅ 验证通过的关键词: {keyword}")
                    else:
                        logger.warning(f"❌ 过滤掉不相关的关键词: {keyword} (原话题: {original_topic})")
                
                # 如果过滤后没有关键词，使用原话题的核心部分作为默认关键词
                if not filtered_keywords:
                    # 提取原话题的核心部分（去除常见停用词）
                    stop_words = ['的', '了', '在', '是', '有', '和', '与', '及', '或', '但', '而', '等', '问题', '事件', '情况']
                    topic_words = [w for w in original_topic if w not in stop_words and len(w) >= 2]
                    if topic_words:
                        # 取前3个核心词作为关键词
                        core_keyword = ''.join(topic_words[:3])
                    else:
                        core_keyword = original_topic[:10]  # 如果无法提取，使用前10个字符
                    
                    logger.warning(f"所有生成的关键词都被过滤，使用原话题核心部分作为默认关键词: {core_keyword}")
                    filtered_keywords = [{'keyword': core_keyword, 'max_video_count': 5, 'max_comment_count': 15}]
                
                # 将过滤后的关键词映射到内部配置格式
                crawl_config = {
                    'keywords_config': filtered_keywords,
                    'keywords': [kw['keyword'] for kw in filtered_keywords],
                    'platforms': ['dy'],  # 只爬取抖音平台
                    'retries': result.get('max_retries', 3)
                }
                
                # 打印关键词及参数报告
                logger.info(f"\n🔑 关键词及参数报告")
                logger.info(f"目标话题: {original_topic}")
                logger.info(f"生成关键词数量: {len(crawl_config['keywords'])}")
                logger.info(f"目标平台: {'抖音'}")
                logger.info(f"爬取重试次数: {crawl_config['retries']}")
                
                # 打印每个关键词的详细配置
                logger.info(f"\n📋 关键词配置详情:")
                for i, kw_config in enumerate(crawl_config['keywords_config']):
                    logger.info(f"{i+1}. 关键词: {kw_config['keyword']}")
                    logger.info(f"    爬取视频数量: {kw_config['max_video_count']}")
                    logger.info(f"    每个视频爬取评论数量: {kw_config['max_comment_count']}")
                
                return crawl_config
            else:
                # 返回默认配置
                base_keyword = original_topic
                return {
                    'keywords_config': [{'keyword': base_keyword, 'max_video_count': 8, 'max_comment_count': 20}],
                    'keywords': [base_keyword],
                    'platforms': ['dy'],  # 只爬取抖音平台
                    'retries': 3
                }
        except Exception as e:
            logger.error(f"生成关键词失败: {e}")
            # 返回基础关键词作为后备
            base_keyword = original_topic
            return {
                'keywords_config': [{'keyword': base_keyword, 'max_video_count': 8, 'max_comment_count': 20}],
                'keywords': [base_keyword],
                'platforms': ['dy'],  # 只爬取抖音平台
                'retries': 3
            }
    
    def _is_keyword_relevant(self, keyword: str, original_topic: str) -> bool:
        """
        验证关键词是否与原话题高度相关（更严格的验证）
        
        Args:
            keyword: 生成的关键词
            original_topic: 原话题
            
        Returns:
            bool: 关键词是否相关
        """
        # 去除空格和标点符号，便于比较
        keyword_clean = keyword.strip().replace(' ', '').replace('，', '').replace(',', '')
        topic_clean = original_topic.strip().replace(' ', '').replace('，', '').replace(',', '')
        
        # 1. 关键词完全等于原话题（或包含原话题的核心部分）
        if keyword_clean == topic_clean or keyword_clean in topic_clean:
            return True
        
        # 2. 原话题包含关键词（关键词是原话题的子串）
        if keyword_clean in topic_clean:
            return True
        
        # 3. 检查关键词是否包含原话题中的核心字符（中文按字符匹配）
        # 提取原话题中的核心字符（长度>=2的字符序列）
        # 对于中文，我们检查关键词是否包含原话题中的关键字符序列
        if len(original_topic) >= 2 and len(keyword) >= 2:
            # 检查关键词中是否包含原话题中的2-4字符序列
            for i in range(len(original_topic) - 1):
                for length in [2, 3, 4]:
                    if i + length <= len(original_topic):
                        topic_substring = original_topic[i:i+length]
                        if topic_substring in keyword:
                            return True
        
        # 4. 检查关键词是否包含原话题中的关键字符（至少包含3个连续字符）
        if len(keyword_clean) >= 3 and len(topic_clean) >= 3:
            for i in range(len(topic_clean) - 2):
                substring = topic_clean[i:i+3]
                if substring in keyword_clean:
                    return True
        
        # 5. 过滤掉明显的无关词汇
        irrelevant_words = ['测试', '示例', '例子', 'test', 'example', '问题', '事件', '情况', '事情']
        if any(irr in keyword_clean for irr in irrelevant_words):
            return False
        
        # 如果都不满足，则认为不相关
        return False
    
    def analyze_content(self, crawl_results: Dict[str, Any], risk_topic: Dict[str, Any]) -> Dict[str, Any]:
        """
        使用LLM分析爬取的视频和评论内容
        
        Args:
            crawl_results: 爬取结果
            risk_topic: 原始危险话题
            
        Returns:
            分析报告
        """
        logger.info(f"开始分析内容，主题: {risk_topic.get('topic', '未命名')}，爬取平台数: {len(crawl_results.get('platform_results', {})) if crawl_results else 0}")
        
        try:
            # 预处理爬取结果，提取关键信息
            logger.debug(f"预处理爬取数据，原始数据大小: {len(json.dumps(crawl_results)) if crawl_results else 0} 字节")
            processed_data = self._preprocess_crawl_data(crawl_results)
            logger.info(f"数据预处理完成，处理后的内容数: {processed_data.get('total_content_count', 0)}")
            
            # 准备系统提示词
            system_prompt = "你是一个专业的舆情分析师，请基于爬取的内容，深入分析话题的发展趋势、公众情绪和潜在风险。请严格按照指定格式输出JSON结果。"
            
            # 准备用户提示
            logger.debug("生成分析提示词")
            user_prompt = self._generate_analysis_prompt(risk_topic, processed_data)
            
            # 调用LLM进行分析
            logger.info("调用LLM进行内容分析")
            start_time = time.time()
            response = self.llm.invoke(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_mode=True,
                temperature=0.1  # 大幅降低温度，确保分析严格基于事实，减少幻觉
            )
            end_time = time.time()
            logger.info(f"LLM分析完成，耗时: {(end_time - start_time):.2f} 秒")
            
            # 解析和验证响应
            logger.debug("解析并验证LLM返回的报告")
            analysis = self._parse_and_validate_report(response)
            
            # 添加元数据
            analysis.update({
                'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
                'source_topic': risk_topic.get('topic', ''),
                'data_count': processed_data.get('total_content_count', 0),
                'comment_count': processed_data.get('total_comment_count', 0),
                'confidence_score': analysis.get('confidence_score', 0.5)
            })
            
            logger.info(f"内容分析完成，报告生成成功，风险等级: {analysis.get('risk_assessment', {}).get('level', 'unknown')}")
            return analysis
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"分析内容失败: {error_msg}", exc_info=True)
            # 返回错误报告
            error_report = self._generate_error_report(risk_topic, error_msg)
            logger.warning(f"生成错误报告，主题: {risk_topic.get('topic', '未命名')}")
            return error_report
    
    def _preprocess_crawl_data(self, crawl_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        预处理爬取结果，提取关键信息
        
        Args:
            crawl_results: 原始爬取结果
            
        Returns:
            处理后的结构化数据
        """
        processed = {
            "platforms": list(crawl_results.get("platform_results", {}).keys()),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "items": [],
            "total_content_count": 0,
            "total_comment_count": 0
        }
        
        # 从各平台提取内容
        platform_results = crawl_results.get("platform_results", {})
        for platform, data in platform_results.items():
            platform_items = data.get("items", [])
            for item in platform_items:
                processed_item = {
                    "platform": platform,
                    "title": item.get("title", ""),
                    "content": item.get("content", ""),
                    "author": item.get("author", "anonymous"),
                    "likes": item.get("likes_count", 0),
                    "comments": item.get("comments", [])[:20]  # 限制评论数量以避免上下文过长
                }
                processed["items"].append(processed_item)
                processed["total_comment_count"] += len(item.get("comments", []))
        
        processed["total_content_count"] = len(processed["items"])
        
        # 限制内容总量
        max_items = 10  # 最多分析10个内容项
        processed["items"] = processed["items"][:max_items]
        
        return processed
    
    def _generate_analysis_prompt(self, risk_topic: Dict[str, Any], processed_data: Dict[str, Any]) -> str:
        """
        生成分析提示词，优化以提高预警阈值
        
        Args:
            risk_topic: 危险话题
            processed_data: 处理后的爬取数据
            
        Returns:
            格式化的分析提示词
        """
        topic = risk_topic.get('topic', '')
        
        prompt = f"""请分析以下关于话题'{topic}'的爬取内容：
        平台: {', '.join(processed_data['platforms'])}
        抓取时间: {processed_data['timestamp']}
        内容数量: {processed_data['total_content_count']}
        评论数量: {processed_data['total_comment_count']}
        
        话题详情: {json.dumps(risk_topic, ensure_ascii=False)}
        
        详细内容:
        {json.dumps(processed_data['items'], ensure_ascii=False, indent=2)}
        
        请生成一份详细的分析报告，重点关注：
        1. 摘要：简要概括爬取内容的主要内容和范围
        2. 关键发现：识别出的重要信息、热点讨论和趋势
        3. 情绪分析：分析整体情绪倾向，包括正面/负面/中性比例
        4. 风险评估：
           - 风险等级：只能是"低"、"中"、"高"、"极高"中的一个
           - 风险因素：详细说明风险产生的原因
           - 提高预警阈值，只关注真正可能存在风险的内容
           - 严格区分事实和推测，只将有明确依据的内容标记为风险
        5. 趋势预测：预测话题的发展趋势
        6. 建议措施：基于分析结果提供具体、可操作的建议
        7. 置信度评分：对分析结果的可信度进行0-1的评分，分数越高表示可信度越高
        
        特别要求：
        - 提高风险预警阈值，避免将正常内容误判为风险
        - 严格基于事实进行分析，不得添加任何未提及的信息
        - 只将有明确证据支持的内容标记为风险
        - 风险评估应严谨，避免过度敏感
        
        请使用以下格式输出：
        {{"summary": "", "key_findings": [], "sentiment_analysis": {{"positive": 0, "neutral": 0, "negative": 0}}, "risk_assessment": {{"level": "", "factors": []}}, "trend_prediction": "", "recommendations": [], "confidence_score": 0.5}}
        """
        return prompt
    
    def _parse_and_validate_report(self, response: Any) -> Dict[str, Any]:
        """
        解析并验证分析报告
        
        Args:
            response: LLM响应
            
        Returns:
            标准化的分析报告
        """
        # 默认报告结构
        default_report = {
            'summary': '分析报告摘要',
            'key_findings': [],
            'sentiment_analysis': {'positive': 0, 'neutral': 0, 'negative': 0},
            'risk_assessment': {'level': 'medium', 'factors': []},
            'trend_prediction': '暂无趋势预测',
            'recommendations': [],
            'confidence_score': 0.5
        }
        
        # 解析响应
        try:
            if isinstance(response, dict):
                report = response
            else:
                report = json.loads(response)
            
            # 验证和标准化报告结构
            validated_report = default_report.copy()
            
            # 提取和验证各个字段
            validated_report["summary"] = str(report.get("summary", ""))
            
            # 确保key_findings是列表
            key_findings = report.get("key_findings", [])
            validated_report["key_findings"] = list(key_findings) if isinstance(key_findings, (list, tuple)) else [str(key_findings)]
            
            # 确保sentiment_analysis是字典并包含必要字段
            sentiment = report.get("sentiment_analysis", {})
            if isinstance(sentiment, dict):
                validated_report["sentiment_analysis"] = {
                    "positive": float(sentiment.get("positive", 0)),
                    "neutral": float(sentiment.get("neutral", 0)),
                    "negative": float(sentiment.get("negative", 0))
                }
            
            # 确保risk_assessment是字典并包含必要字段
            risk_assessment = report.get("risk_assessment", {})
            if isinstance(risk_assessment, dict):
                validated_report["risk_assessment"] = {
                    "level": risk_assessment.get("level", "medium"),
                    "factors": list(risk_assessment.get("factors", [])) if isinstance(risk_assessment.get("factors"), (list, tuple)) else [str(risk_assessment.get("factors", ""))]
                }
            
            # 设置其他字段
            validated_report["trend_prediction"] = str(report.get("trend_prediction", "暂无趋势预测"))
            
            # 确保recommendations是列表
            recommendations = report.get("recommendations", [])
            validated_report["recommendations"] = list(recommendations) if isinstance(recommendations, (list, tuple)) else [str(recommendations)]
            
            # 确保confidence_score是0-1之间的浮点数
            confidence = report.get("confidence_score", 0.5)
            try:
                confidence_score = float(confidence)
                validated_report["confidence_score"] = max(0.0, min(1.0, confidence_score))  # 限制在0-1之间
            except ValueError:
                validated_report["confidence_score"] = 0.5
            
            return validated_report
            
        except Exception as e:
            print(f"[VCS] 报告解析失败: {str(e)}")
            default_report["summary"] = f"报告解析失败: {str(e)}"
            return default_report
    
    def _generate_error_report(self, risk_topic: Dict[str, Any], error_message: str) -> Dict[str, Any]:
        """
        生成错误情况下的报告
        
        Args:
            risk_topic: 危险话题
            error_message: 错误信息
            
        Returns:
            错误报告
        """
        return {
            'summary': f"对话题 '{risk_topic.get('topic', '未命名')}' 的分析失败",
            'key_findings': ['分析过程中出现错误'],
            'sentiment_analysis': {'positive': 0, 'neutral': 0, 'negative': 0},
            'risk_assessment': {'level': 'unknown', 'factors': [f'分析失败: {error_message}']},
            'trend_prediction': '无法预测',
            'recommendations': ['请检查爬虫是否正常工作', '确认爬取结果格式是否正确', '验证LLM服务是否可用'],
            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
            'source_topic': risk_topic.get('topic', ''),
            'data_count': 0,
            'comment_count': 0,
            'confidence_score': 0.0
        }
    
    def _summarize_sub_reports(self, sub_reports: List[Dict[str, Any]], risk_topic: Dict[str, Any], important_videos: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        汇总所有小报告，生成最终报告
        
        Args:
            sub_reports: 所有关键词的小报告列表
            risk_topic: 原始风险话题
            important_videos: 重要视频来源列表
            
        Returns:
            最终的综合分析报告
        """
        logger.info(f"开始汇总 {len(sub_reports)} 个小报告")
        
        # 如果没有小报告，返回默认报告
        if not sub_reports:
            return {
                'summary': f"未生成任何小报告，无法汇总分析",
                'key_findings': [],
                'sentiment_analysis': {'positive': 0, 'neutral': 0, 'negative': 0},
                'risk_assessment': {'level': 'unknown', 'factors': ['未生成任何小报告']},
                'trend_prediction': '无法预测',
                'recommendations': ['请检查爬虫是否正常工作'],
                'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
                'source_topic': risk_topic.get('topic', ''),
                'data_count': 0,
                'comment_count': 0,
                'confidence_score': 0.0,
                'important_videos': important_videos
            }
        
        try:
            # 准备系统提示词
            system_prompt = "你是一个专业的舆情分析专家，擅长综合多个小报告生成最终的分析报告。请严格按照指定格式输出JSON结果，提高预警阈值，只关注真正可能存在风险的内容。"
            
            # 准备用户提示词
            user_prompt = f"""
            请根据以下多个关键词的小报告，综合生成一份最终的舆情分析报告。
            
            ## 风险话题信息
            {json.dumps(risk_topic, ensure_ascii=False)}
            
            ## 小报告列表
            {json.dumps(sub_reports, ensure_ascii=False)}
            
            ## 重要视频来源
            {json.dumps(important_videos, ensure_ascii=False)}
            
            ## 分析要求
            1. 综合所有小报告的关键发现，避免重复
            2. 对整个话题的风险等级进行综合评估
            3. 分析整体情绪倾向
            4. 预测话题的发展趋势
            5. 提供具体、可操作的建议
            6. 对分析结果的可信度进行评分（0-1）
            7. 在报告中包含重要视频来源信息
            
            ## 输出格式
            请严格按照JSON格式输出，包含以下字段：
            - "summary": "报告摘要"
            - "key_findings": ["发现1", "发现2", ...]
            - "sentiment_analysis": {{"positive": 0.0, "neutral": 0.0, "negative": 0.0}}
            - "risk_assessment": {{"level": "低/中/高/极高", "factors": ["因素1", "因素2", ...]}}
            - "trend_prediction": "趋势预测"
            - "recommendations": ["建议1", "建议2", ...]
            - "confidence_score": 0.0-1.0
            - "important_videos": [{{"keyword": "关键词", "platform": "平台", "title": "标题", "url": "链接", "likes": 数字, "comments": 数字, "create_time": "时间"}}, ...]
            """
            
            # 调用LLM生成最终报告
            response = self.llm.invoke(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_mode=True,
                temperature=0.1  # 大幅降低温度，确保报告严格基于事实，减少幻觉
            )
            
            final_report = json.loads(response)
            
            # 验证并补充报告字段
            if isinstance(final_report, dict):
                # 确保必要字段存在
                if 'summary' not in final_report:
                    final_report['summary'] = "未生成摘要"
                if 'key_findings' not in final_report:
                    final_report['key_findings'] = []
                if 'sentiment_analysis' not in final_report:
                    final_report['sentiment_analysis'] = {'positive': 0, 'neutral': 0, 'negative': 0}
                if 'risk_assessment' not in final_report:
                    final_report['risk_assessment'] = {'level': 'unknown', 'factors': []}
                if 'trend_prediction' not in final_report:
                    final_report['trend_prediction'] = "无法预测"
                if 'recommendations' not in final_report:
                    final_report['recommendations'] = []
                if 'confidence_score' not in final_report:
                    final_report['confidence_score'] = 0.5
                if 'important_videos' not in final_report:
                    final_report['important_videos'] = important_videos
                
                # 添加元数据
                final_report['timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S")
                final_report['source_topic'] = risk_topic.get('topic', '')
                
                # 计算总数据量
                total_data_count = sum(sub_report.get('data_count', 0) for sub_report in sub_reports)
                total_comment_count = sum(sub_report.get('comment_count', 0) for sub_report in sub_reports)
                final_report['data_count'] = total_data_count
                final_report['comment_count'] = total_comment_count
                
                return final_report
            else:
                # 从sub_reports中提取数据
                total_data_count = sum(sub_report.get('data_count', 0) for sub_report in sub_reports)
                total_comment_count = sum(sub_report.get('comment_count', 0) for sub_report in sub_reports)
                
                # 提取所有关键发现
                all_key_findings = []
                for sub_report in sub_reports:
                    if 'key_findings' in sub_report and isinstance(sub_report['key_findings'], list):
                        all_key_findings.extend(sub_report['key_findings'])
                
                # 提取所有风险因素
                all_risk_factors = []
                for sub_report in sub_reports:
                    if 'risk_factors' in sub_report and isinstance(sub_report['risk_factors'], list):
                        all_risk_factors.extend(sub_report['risk_factors'])
                
                # 返回包含sub_reports数据的默认报告
                return {
                    'summary': f"汇总报告生成失败，使用默认报告",
                    'key_findings': all_key_findings if all_key_findings else [],
                    'sentiment_analysis': {'positive': 0, 'neutral': 0, 'negative': 0},
                    'risk_assessment': {'level': 'unknown', 'factors': all_risk_factors if all_risk_factors else ['汇总报告生成失败']},
                    'trend_prediction': '无法预测',
                    'recommendations': ['请检查LLM服务是否可用'],
                    'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
                    'source_topic': risk_topic.get('topic', ''),
                    'data_count': total_data_count,
                    'comment_count': total_comment_count,
                    'confidence_score': 0.0,
                    'important_videos': important_videos
                }
        except Exception as e:
            logger.error(f"汇总小报告失败: {str(e)}", exc_info=True)
            # 从sub_reports中提取数据
            total_data_count = sum(sub_report.get('data_count', 0) for sub_report in sub_reports)
            total_comment_count = sum(sub_report.get('comment_count', 0) for sub_report in sub_reports)
            
            # 提取所有关键发现
            all_key_findings = []
            for sub_report in sub_reports:
                if 'key_findings' in sub_report and isinstance(sub_report['key_findings'], list):
                    all_key_findings.extend(sub_report['key_findings'])
            
            # 提取所有风险因素
            all_risk_factors = []
            for sub_report in sub_reports:
                if 'risk_factors' in sub_report and isinstance(sub_report['risk_factors'], list):
                    all_risk_factors.extend(sub_report['risk_factors'])
            
            # 返回包含sub_reports数据的默认报告
            return {
                'summary': f"汇总报告生成失败，原因: {str(e)}",
                'key_findings': all_key_findings if all_key_findings else [],
                'sentiment_analysis': {'positive': 0, 'neutral': 0, 'negative': 0},
                'risk_assessment': {'level': 'unknown', 'factors': all_risk_factors if all_risk_factors else [f'汇总报告生成失败: {str(e)}']},
                'trend_prediction': '无法预测',
                'recommendations': ['请检查LLM服务是否可用'],
                'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
                'source_topic': risk_topic.get('topic', ''),
                'data_count': total_data_count,
                'comment_count': total_comment_count,
                'confidence_score': 0.0,
                'important_videos': important_videos
            }
    
    def process_topic(self, risk_topic: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理单个危险话题的完整流程
        
        Args:
            risk_topic: 来自Risk Analyzer的危险话题
            
        Returns:
            完整的分析报告
        """
        # 记录开始时间
        start_time = time.time()
        topic_name = risk_topic.get("topic", "未命名话题")
        logger.info(f"开始处理话题: {topic_name}")
        
        try:
            # 1. 生成关键词和爬取配置
            logger.info("步骤1: 生成关键词和爬取配置")
            crawl_config = self.generate_keywords(risk_topic)
            
            if not crawl_config or "keywords_config" not in crawl_config or len(crawl_config["keywords_config"]) == 0:
                raise ValueError("无法生成有效的关键词配置")
            
            # 记录生成的关键词（限制显示数量，避免过长）
            keywords_str = ', '.join([kw['keyword'] for kw in crawl_config['keywords_config'][:5]])
            if len(crawl_config['keywords_config']) > 5:
                keywords_str += '...'
            logger.info(f"成功生成 {len(crawl_config['keywords_config'])} 个关键词: {keywords_str}")
            logger.info(f"目标平台: {', '.join(crawl_config.get('platforms', []))}")
            
            # 2. 边爬取边分析，为每个关键词生成小报告
            logger.info("步骤2: 开始边爬取边分析")
            crawl_start_time = time.time()
            
            # 存储所有平台的爬取结果
            all_results = {
                'platform_results': {},
                'total_items': 0,
                'total_comments': 0
            }
            
            # 存储所有小报告
            sub_reports = []
            
            # 存储重要视频来源
            important_videos = []
            
            # 遍历每个关键词，为每个关键词单独指定爬取参数
            for keyword_config in crawl_config['keywords_config']:
                keyword = keyword_config['keyword']
                max_video_count = keyword_config['max_video_count']
                max_comment_count = keyword_config['max_comment_count']
                max_retries = crawl_config.get('retries', 3)
                
                logger.info(f"处理关键词: {keyword}，计划爬取 {max_video_count} 个视频/帖子，每条内容 {max_comment_count} 条评论")
                
                # 为当前关键词创建爬取结果容器
                keyword_results = {
                    'platform_results': {},
                    'total_items': 0,
                    'total_comments': 0
                }
                
                # 遍历所有平台
                for platform in crawl_config['platforms']:
                    try:
                        logger.debug(f"在{platform}平台上爬取关键词: {keyword}")
                        # 初始化爬虫
                        crawler = VideoCommentSpotter(platform=platform)
                        
                        # 即使没有可用的爬虫，也继续执行，以便使用模拟数据
                        # VideoCommentSpotter类没有crawlers属性，直接跳过检查
                        logger.debug(f"平台 {platform} 爬虫初始化完成，将使用模拟数据")
                        
                        # 创建爬取配置，传递给爬虫
                        search_config = {
                            "crawler_max_notes_count": max_video_count,
                            "crawler_max_comments_count_single_notes": max_comment_count,
                            "enable_get_comments": True,
                            "max_retries": max_retries
                        }
                        
                        # 爬取当前关键词
                        logger.info(f"开始爬取关键词: {keyword}，平台: {platform}")
                        
                        platform_results = crawler.search(
                            keyword=keyword,
                            max_count=max_video_count,
                            max_retries=max_retries,
                            enable_get_comments=True,
                            platform_config=search_config
                        )
                        
                        # 合并到关键词结果
                        keyword_results['platform_results'][platform] = platform_results
                        platform_items = platform_results.get('total_items', 0)
                        platform_comments = platform_results.get('total_comments', 0)
                        keyword_results['total_items'] += platform_items
                        keyword_results['total_comments'] += platform_comments
                        
                        # 合并到总结果
                        if platform not in all_results['platform_results']:
                            all_results['platform_results'][platform] = {
                                'results': [],
                                'total_items': 0,
                                'total_comments': 0,
                                'platform': platform
                            }
                        
                        if 'results' in platform_results:
                            all_results['platform_results'][platform]['results'].extend(platform_results['results'])
                        elif 'items' in platform_results:
                            # 处理单个关键词爬取结果
                            all_results['platform_results'][platform]['results'].append(platform_results)
                        
                        all_results['platform_results'][platform]['total_items'] += platform_items
                        all_results['platform_results'][platform]['total_comments'] += platform_comments
                        all_results['total_items'] += platform_items
                        all_results['total_comments'] += platform_comments
                        
                        # 打印爬取完成日志
                        logger.info(f"✅ {platform}平台关键词 {keyword} 爬取完成")
                        logger.info(f"📊 爬取结果统计:")
                        logger.info(f"   实际获取内容数: {platform_items} 条")
                        logger.info(f"   实际获取评论数: {platform_comments} 条")
                        
                        logger.info(f"{platform}平台关键词 {keyword} 爬取完成，获取 {platform_items} 条内容，{platform_comments} 条评论")
                        
                        # 提取重要视频来源（根据点赞数、评论数、观看量等综合判断）
                        if 'items' in platform_results:
                            for item in platform_results['items']:
                                likes = item.get('likes', 0)
                                comments = len(item.get('comments', []))
                                views = item.get('views', 0)
                                
                                # 更严格的过滤条件：
                                # 1. 点赞数 > 200 且评论数 > 20
                                # 2. 或者观看量 > 5000 且互动率 > 1%（互动率 = (点赞+评论)/观看量）
                                engagement_rate = ((likes + comments) / views) * 100 if views > 0 else 0
                                
                                if (likes > 200 and comments > 20) or (views > 5000 and engagement_rate > 1):
                                    important_videos.append({
                                        'keyword': keyword,
                                        'platform': platform,
                                        'title': item.get('title', ''),
                                        'url': item.get('url', ''),
                                        'likes': likes,
                                        'comments': comments,
                                        'views': views,
                                        'create_time': item.get('create_time', '')
                                    })
                    except Exception as e:
                        logger.error(f"{platform}平台爬取关键词 {keyword} 失败: {str(e)}", exc_info=True)
                        keyword_results['platform_results'][platform] = {
                            'error': str(e),
                            'total_items': 0,
                            'total_comments': 0
                        }
                        
                        if platform not in all_results['platform_results']:
                            all_results['platform_results'][platform] = {
                                'results': [],
                                'total_items': 0,
                                'total_comments': 0,
                                'platform': platform
                            }
                    
                # 立即分析当前关键词的爬取结果，生成小报告
                logger.info(f"开始分析关键词 {keyword} 的爬取结果")
                sub_report = self.analyze_content(keyword_results, risk_topic)
                sub_report['keyword'] = keyword
                sub_report['keyword_config'] = keyword_config
                sub_reports.append(sub_report)
                
                # 打印分析结果到控制台，方便用户查看
                logger.info(f"\n关键词 {keyword} 分析结果:")
                logger.info(f"风险等级: {sub_report.get('risk_assessment', {}).get('level', 'unknown')}")
                logger.info(f"置信度: {sub_report.get('confidence_score', 0.5):.2f}")
                logger.info(f"关键发现: {len(sub_report.get('key_findings', []))} 项")
                if sub_report.get('key_findings'):
                    for i, finding in enumerate(sub_report['key_findings'][:3]):
                        logger.info(f"发现 {i+1}: {finding[:50]}...")
                
                logger.info(f"关键词 {keyword} 分析完成，风险等级: {sub_report.get('risk_assessment', {}).get('level', 'unknown')}")

            # 计算爬取时间
            crawl_time = round(time.time() - crawl_start_time, 2)
            logger.info(f"所有平台爬取完成，总耗时: {crawl_time} 秒，总计 {all_results['total_items']} 条内容，{all_results['total_comments']} 条评论")
            
            if all_results['total_items'] == 0:
                logger.warning("警告: 未爬取到任何内容")
            
            # 处理重要视频列表：去重、排序和限制数量
            if important_videos:
                logger.info(f"原始重要视频数量: {len(important_videos)}")
                
                # 去重：基于URL或标题
                unique_videos = {}
                for video in important_videos:
                    # 使用视频URL或标题作为唯一键
                    key = video.get('url', '') or video.get('title', '')
                    if key not in unique_videos:
                        unique_videos[key] = video
                
                # 转换回列表
                important_videos = list(unique_videos.values())
                logger.info(f"去重后重要视频数量: {len(important_videos)}")
                
                # 排序：按互动量（点赞+评论）降序
                important_videos.sort(key=lambda x: x.get('likes', 0) + x.get('comments', 0), reverse=True)
                
                # 限制数量，最多显示10个重要视频
                important_videos = important_videos[:10]
                logger.info(f"排序和限制后重要视频数量: {len(important_videos)}")
            
            # 3. 汇总所有小报告，生成最终报告
            logger.info("步骤3: 汇总所有小报告，生成最终报告")
            final_report = self._summarize_sub_reports(sub_reports, risk_topic, important_videos)
            
            analysis_time = round(time.time() - crawl_start_time, 2)
            total_time = round(time.time() - start_time, 2)
            logger.info(f"最终报告生成完成，风险等级: {final_report.get('risk_assessment', {}).get('level', 'unknown')}")
            
            # 打印最终汇总报告到控制台，方便用户查看
            # 记录最终汇总报告信息到日志
            logger.info(f"最终汇总报告: 话题-{topic_name}, 处理时间-{total_time}秒, 风险等级-{final_report.get('risk_assessment', {}).get('level', 'unknown')}")
            logger.info(f"总爬取内容-{all_results['total_items']}条, 总评论数-{all_results['total_comments']}条")
            
            # 记录平台爬取统计到日志
            for platform, result in all_results['platform_results'].items():
                logger.info(f"平台爬取统计: {platform}: {result['total_items']} 条内容, {result['total_comments']} 条评论")
            
            # 记录风险评估结果到日志
            risk_factors = final_report.get('risk_assessment', {}).get('factors', [])
            logger.info(f"风险评估结果: 风险等级-{final_report.get('risk_assessment', {}).get('level', 'unknown')}, 置信度-{final_report.get('confidence_score', 0.5):.2f}")
            if risk_factors:
                logger.info(f"风险因素: {len(risk_factors)} 项")
                for i, factor in enumerate(risk_factors):
                    logger.info(f"风险因素 {i+1}: {factor}")
            
            # 记录情感分析结果到日志
            sentiment = final_report.get('sentiment_analysis', {})
            emotion_score = sentiment.get('negative', 0) * 100
            logger.info(f"情感分析: 情感打分-{emotion_score:.0f}/100")
            
            # 记录关键发现到日志
            key_findings = final_report.get('key_findings', [])
            logger.info(f"关键发现: {len(key_findings)} 项")
            for i, finding in enumerate(key_findings[:3]):
                logger.info(f"关键发现 {i+1}: {finding[:50]}...")
            
            # 记录趋势预测和建议到日志
            logger.info(f"趋势预测: {final_report.get('trend_prediction', '无法预测')}")
            recommendations = final_report.get('recommendations', [])
            logger.info(f"建议: {len(recommendations)} 条")
            
            # 记录重要视频来源到日志
            logger.info(f"重要视频来源: {len(important_videos)} 个")
            for i, video in enumerate(important_videos[:3]):  # 只记录前3个
                title = video.get('title', '')[:40]
                logger.info(f"重要视频 {i+1}: {title}..., 平台-{video.get('platform', '')}")
            
            # 4. 更新记忆
            logger.info("步骤4: 更新记忆")
            memory_item = {
                'timestamp': time.time(),
                'topic': topic_name,
                'keywords': [kw['keyword'] for kw in crawl_config['keywords_config']],
                'total_items': all_results['total_items'],
                'risk_level': final_report.get('risk_assessment', {}).get('level', 'medium')
            }
            self.memory.append(memory_item)
            try:
                self._save_memory()
                logger.debug("记忆保存成功")
            except Exception as e:
                logger.error(f"记忆保存失败: {str(e)}", exc_info=True)
            
            # 5. 保存完整报告
            logger.info("步骤5: 保存分析报告")
            full_report = {
                'risk_topic': risk_topic,
                'crawl_config': crawl_config,
                'crawl_results': all_results,
                'sub_reports': sub_reports,
                'analysis': final_report,
                'important_videos': important_videos
            }
            
            # 保存报告到文件
            report_filename = f"vcs_report_{time.strftime('%Y%m%d_%H%M%S')}.json"
            report_path = self.output_dir / report_filename
            try:
                with open(report_path, 'w', encoding='utf-8') as f:
                    json.dump(full_report, f, ensure_ascii=False, indent=2)
                logger.info(f"分析报告已成功保存到: {report_path}")
            except Exception as e:
                logger.error(f"保存报告失败: {str(e)}", exc_info=True)
            
            # 计算执行时间
            execution_time = round(time.time() - start_time, 2)
            logger.info(f"话题 '{topic_name}' 处理完成，总耗时 {execution_time} 秒")
            
            # 6. 返回给Risk Analyzer的详尽报告
            return {
                'status': 'success',
                'source_topic': risk_topic,
                'summary': final_report['summary'],
                'key_findings': final_report['key_findings'],
                'risk_assessment': final_report['risk_assessment'],
                'analysis': final_report,  # 包含完整的分析报告
                'data_statistics': {
                    'total_platforms': len(crawl_config['platforms']),
                    'total_keywords': len(crawl_config['keywords_config']),
                    'total_items': all_results['total_items'],
                    'total_comments': all_results['total_comments']
                },
                'report_path': str(report_path),
                'execution_time': execution_time,
                'timestamp': final_report['timestamp'],
                'important_videos': important_videos
            }
            
        except KeyError as ke:
            error_msg = f"缺少必要字段: {str(ke)}"
            logger.error(f"处理话题 '{topic_name}' 时出错: {error_msg}", exc_info=True)
        except ValueError as ve:
            error_msg = str(ve)
            logger.error(f"处理话题 '{topic_name}' 时出现值错误: {error_msg}", exc_info=True)
        except Exception as e:
            error_msg = str(e)
            logger.error(f"处理话题 '{topic_name}' 时出错: {error_msg}", exc_info=True)
        
        # 生成错误报告
        error_report = self._generate_error_report(risk_topic, error_msg)
        
        # 保存错误报告
        full_error_report = {
            'risk_topic': risk_topic,
            'error': error_msg,
            'analysis': error_report
        }
        error_report_filename = f"vcs_error_report_{time.strftime('%Y%m%d_%H%M%S')}.json"
        error_report_path = self.output_dir / error_report_filename
        
        try:
            with open(error_report_path, 'w', encoding='utf-8') as f:
                json.dump(full_error_report, f, ensure_ascii=False, indent=2)
            logger.info(f"错误报告已保存到: {error_report_path}")
        except Exception as e:
            logger.error(f"保存错误报告失败: {str(e)}", exc_info=True)
        
        # 计算执行时间
        execution_time = round(time.time() - start_time, 2)
        logger.info(f"话题 '{topic_name}' 处理失败，总耗时 {execution_time} 秒")
        
        return {
            'status': 'error',
            'error': error_msg,
            'error_report': error_report,
            'report_path': str(error_report_path),
            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
        }

    def handle_risk_analyzer_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理来自Risk Analyzer的请求，标准化接口
        
        Args:
            request_data: 来自Risk Analyzer的数据，必须包含topic字段
            
        Returns:
            标准化的响应数据，包含分析结果和元数据
        """
        request_id = request_data.get("request_id", str(int(time.time())))
        logger.info(f"收到来自Risk Analyzer的请求，请求ID: {request_id}")
        
        try:
            # 使用专用方法验证请求格式
            is_valid, error_msg = self.validate_risk_topic_format(request_data)
            if not is_valid:
                logger.warning(f"请求验证失败，请求ID: {request_id}，错误: {error_msg}")
                raise ValueError(error_msg)
            
            # 记录请求信息（敏感信息脱敏）
            topic_name = request_data.get("topic", "未命名")
            priority = request_data.get("priority", "medium")
            logger.info(f"处理风险话题: {topic_name} (优先级: {priority})，请求ID: {request_id}")
            logger.debug(f"完整请求数据: {json.dumps(request_data, ensure_ascii=False, default=str)}")
            
            # 执行完整的话题处理流程
            start_time = time.time()
            process_result = self.process_topic(request_data)
            process_time = time.time() - start_time
            
            # 标准化响应格式
            response = {}
            if process_result.get("status") == "success":
                # 成功情况的标准化响应 - 返回详尽报告
                response = {
                    "status": "success",
                    "data": {
                        "risk_topic": request_data,
                        "analysis_summary": process_result.get("summary", ""),
                        "key_findings": process_result.get("key_findings", []),
                        "risk_assessment": process_result.get("risk_assessment", {}),
                        "sentiment_analysis": process_result.get("analysis", {}).get("sentiment_analysis", {}),
                        "trend_prediction": process_result.get("analysis", {}).get("trend_prediction", ""),
                        "recommendations": process_result.get("analysis", {}).get("recommendations", []),
                        "confidence_score": process_result.get("analysis", {}).get("confidence_score", 0.5),
                        "important_videos": process_result.get("important_videos", []),
                        "detailed_report": process_result.get("analysis", {})
                    },
                    "metadata": {
                        "processing_time": round(process_time, 2),
                        "data_statistics": process_result.get("data_statistics", {}),
                        "report_path": process_result.get("report_path", ""),
                        "timestamp": process_result.get("timestamp", time.strftime("%Y-%m-%d %H:%M:%S")),
                        "request_id": request_id,
                        "total_items": process_result.get("data_statistics", {}).get("total_items", 0),
                        "total_comments": process_result.get("data_statistics", {}).get("total_comments", 0),
                        "total_keywords": process_result.get("data_statistics", {}).get("total_keywords", 0),
                        "total_platforms": process_result.get("data_statistics", {}).get("total_platforms", 0)
                    },
                    "error": None
                }
                risk_level = process_result.get("risk_assessment", {}).get("level", "medium")
                logger.info(f"话题 '{topic_name}' 分析成功，风险等级: {risk_level}，请求ID: {request_id}")
            else:
                # 失败情况的标准化响应
                response = {
                    "status": "error",
                    "data": None,
                    "metadata": {
                        "timestamp": process_result.get("timestamp", time.strftime("%Y-%m-%d %H:%M:%S")),
                        "report_path": process_result.get("report_path", ""),
                        "processing_time": round(process_time, 2),
                        "request_id": request_id
                    },
                    "error": {
                        "message": process_result.get("error", "处理失败"),
                        "code": "PROCESSING_FAILED"
                    }
                }
                logger.error(f"话题 '{topic_name}' 分析失败，错误: {response['error']['message']}，请求ID: {request_id}")
            
            logger.debug(f"响应数据: {json.dumps(response, ensure_ascii=False, default=str)}")
            return response
                
        except ValueError as ve:
            error_msg = str(ve)
            logger.warning(f"请求验证失败，请求ID: {request_id}，错误: {error_msg}")
            return {
                "status": "error",
                "data": None,
                "metadata": {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "request_id": request_id
                },
                "error": {
                    "message": error_msg,
                    "code": "VALIDATION_ERROR"
                }
            }
        except KeyError as ke:
            error_msg = f"缺少必要字段: {str(ke)}"
            logger.error(f"处理请求时缺少必要字段，请求ID: {request_id}，错误: {error_msg}", exc_info=True)
            return {
                "status": "error",
                "data": None,
                "metadata": {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "request_id": request_id
                },
                "error": {
                    "message": error_msg,
                    "code": "MISSING_FIELD"
                }
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"处理Risk Analyzer请求时发生未预期错误，请求ID: {request_id}，错误: {error_msg}", exc_info=True)
            return {
                "status": "error",
                "data": None,
                "metadata": {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "request_id": request_id
                },
                "error": {
                    "message": "处理请求时发生内部错误",
                    "code": "INTERNAL_ERROR"
                }
            }
    
    async def handle_risk_analyzer_request_async(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        异步处理来自Risk Analyzer的请求
        
        Args:
            request_data: 包含风险话题信息的请求数据
            
        Returns:
            标准化的响应数据
        """
        request_id = request_data.get("request_id", str(int(time.time())))
        topic_name = request_data.get("topic", "未命名")
        logger.info(f"开始异步处理来自Risk Analyzer的请求，请求ID: {request_id}，话题: {topic_name}")
        
        try:
            # 在事件循环中执行同步处理逻辑
            logger.debug(f"将请求提交到线程池执行，请求ID: {request_id}")
            return await asyncio.get_event_loop().run_in_executor(
                None, 
                self.handle_risk_analyzer_request, 
                request_data
            )
        except asyncio.TimeoutError:
            error_msg = "请求处理超时"
            logger.error(f"异步处理请求超时，请求ID: {request_id}")
            return {
                "status": "error",
                "data": None,
                "metadata": {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "request_id": request_id
                },
                "error": {
                    "message": error_msg,
                    "code": "TIMEOUT_ERROR"
                }
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"异步处理请求时出错，请求ID: {request_id}，错误: {error_msg}", exc_info=True)
            return {
                "status": "error",
                "data": None,
                "metadata": {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "request_id": request_id
                },
                "error": {
                    "message": "异步处理请求时发生内部错误",
                    "code": "ASYNC_PROCESSING_ERROR"
                }
            }
    
    def analyze_topic(self, keywords_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析话题，生成详细分析报告
        
        Args:
            keywords_result: 包含关键词的字典
            
        Returns:
            详细的分析报告
        """
        # 为了保持与main.py中调用的兼容性，这里实现analyze_topic方法
        # 实际上应该调用process_topic方法进行完整的处理流程
        topic = keywords_result.get('topic', '未命名话题')
        risk_topic = {
            'topic': topic,
            'platform': '社交媒体',
            'hotness': '高',
            'risk_level': 4,
            'category': '产品质量',
            'reason': '多个用户反映相关问题',
            'further_investigate': True
        }
        
        print(f"\n[VideosCommentsSpotter] 开始分析话题: {topic}")
        print(f"[VideosCommentsSpotter] 使用关键词: {', '.join(keywords_result.get('keywords', []))}")
        
        # 调用process_topic进行完整处理
        result = self.process_topic(risk_topic)
        
        # 打印分析结果
        print(f"\n[VideosCommentsSpotter] 话题分析完成")
        print(f"[VideosCommentsSpotter] 分析状态: {result.get('status', '未知')}")
        
        if result.get('status') == 'success':
            print(f"[VideosCommentsSpotter] 风险评估: {result.get('risk_assessment', {}).get('level', '未知')}")
            print(f"[VideosCommentsSpotter] 置信度: {result.get('confidence_score', 0.5):.2f}")
            print(f"[VideosCommentsSpotter] 关键发现: {len(result.get('key_findings', []))} 项")
        else:
            print(f"[VideosCommentsSpotter] 分析失败: {result.get('error', '未知错误')}")
        
        return result
    
    def validate_risk_topic_format(self, request_data: Dict[str, Any]) -> tuple[bool, str]:
        """
        验证风险话题请求的格式
        
        Args:
            request_data: 请求数据
            
        Returns:
            (是否有效, 错误信息)
        """
        logger.debug("开始验证请求格式")
        
        # 基础类型验证
        if not isinstance(request_data, dict):
            logger.warning("请求验证失败: 数据类型不是字典")
            return False, "请求数据必须是字典格式"
        
        # 必需字段验证
        required_fields = ["topic"]
        for field in required_fields:
            if field not in request_data:
                logger.warning(f"请求验证失败: 缺少必需字段 '{field}'")
                return False, f"缺少必要字段: {field}"
            if not request_data[field]:
                logger.warning(f"请求验证失败: 字段 '{field}' 的值为空")
                return False, f"字段 '{field}' 的值不能为空"
        
        # topic字段长度验证
        topic = request_data["topic"]
        if not isinstance(topic, str) or len(topic) > 500:
            logger.warning(f"请求验证失败: topic字段长度无效 (长度: {len(topic) if isinstance(topic, str) else '无效类型'})")
            return False, "topic字段长度必须在1-500个字符之间"
            
        # 可选字段验证
        if "priority" in request_data:
            if request_data["priority"] not in ["low", "medium", "high"]:
                logger.warning(f"请求验证失败: priority字段值无效 (值: {request_data['priority']})")
                return False, "priority字段值必须是: low, medium 或 high"
        
        # 可选的上下文信息验证
        if "context" in request_data and not isinstance(request_data["context"], dict):
            logger.warning("请求验证失败: context字段必须是字典格式")
            return False, "context字段必须是字典格式"
        
        logger.debug("请求格式验证通过")
        return True, ""


def main():
    """测试主函数"""
    # 初始化LLM客户端
    llm_client = LLMClient(config=LLM_CONFIG)
    
    # 初始化Agent
    agent = VideosCommentsSpotterAgent(llm_client=llm_client)
    
    # 测试示例话题
    test_topic = {
        "topic": "产品安全隐患",
        "platform": "社交媒体",
        "hotness": "高",
        "risk_level": 4,
        "category": "产品质量",
        "reason": "多个用户反映产品存在安全隐患",
        "further_investigate": True
    }
    
    # 使用接口函数处理话题
    print("[VCS] 测试接口调用...")
    result = agent.handle_risk_analyzer_request(test_topic)
    print("[VCS] 接口响应:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()