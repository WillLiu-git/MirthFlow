# HotspotHunter/agent.py

import time
import json
import logging
from pathlib import Path
from typing import List, Dict, Any
import sys
import os

# 配置日志记录器
logger = logging.getLogger('HotspotHunter')
logger.setLevel(logging.INFO)

# --- 导入依赖 (包含回退机制，用于兼容不同运行环境) ---
try:
    # 尝试相对导入（作为包的一部分时）
    from .llm import LLMClient
    from .utils.config import TOPHUB_URLS, OUTPUT_DIRECTORY, LLM_CONFIG, HOTSPOT_HUNTER_INTERVAL
    from .tools.hotlist_crawler import hotlist_crawler
    from .prompts.prompts import HH_SCAN_PROMPT
except ImportError:
    # 回退到绝对导入（直接运行时）
    from llm import LLMClient
    from utils.config import TOPHUB_URLS, OUTPUT_DIRECTORY, LLM_CONFIG, HOTSPOT_HUNTER_INTERVAL
    from tools.hotlist_crawler import hotlist_crawler
    from prompts.prompts import HH_SCAN_PROMPT


# 定义情报站文件路径 (核心交互文件)
INTELLIGENCE_FILE = Path(OUTPUT_DIRECTORY) / "intelligence_feed.json"
INTELLIGENCE_FILE.parent.mkdir(parents=True, exist_ok=True)


class HotspotHunterAgent:
    """
    Hotspot Hunter Agent (侦察兵/生产者):
    1. 定期爬取榜单，使用 LLM 进行结构化风险初筛。
    2. 将结构化风险话题写入情报站 (intelligence_feed.json)。
    """

    def __init__(self, llm_client: LLMClient, crawl_interval: int = 30):
        self.llm = llm_client
        self.interval = crawl_interval  # 可被 Risk Analyzer 动态修改
        self.memory_file = Path(OUTPUT_DIRECTORY) / "hh_memory.json"
        self.memory: List[Dict] = self._load_memory()

    def _load_memory(self) -> List[Dict]:
        if self.memory_file.exists():
            with open(self.memory_file, "r", encoding="utf-8") as f:
                try:
                    # 只加载最近 200 条记忆
                    return json.load(f)[-200:]
                except json.JSONDecodeError:
                    return []
        return []

    def _save_memory(self):
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.memory_file, "w", encoding="utf-8") as f:
            # 只保存最近 1000 条记忆
            json.dump(self.memory[-1000:], f, ensure_ascii=False, indent=2)

    def _append_to_intelligence(self, risk_topics: List[Dict[str, Any]]):
        """将 LLM 筛选出的风险话题追加到情报站文件。"""
        if not risk_topics:
            return

        # 确保risk_topics是一个列表
        if not isinstance(risk_topics, list):
            risk_topics = [risk_topics]

        current_data = []
        if INTELLIGENCE_FILE.exists():
            with open(INTELLIGENCE_FILE, "r", encoding="utf-8") as f:
                try:
                    current_data = json.load(f)
                    # 确保current_data是一个列表
                    if not isinstance(current_data, list):
                        current_data = []
                except json.JSONDecodeError:
                    current_data = []

        # 过滤掉非字典类型的数据
        valid_topics = [topic for topic in risk_topics if isinstance(topic, dict)]
        current_data.extend(valid_topics)

        # 限制文件大小，只保留最近100条记录
        if len(current_data) > 100:
            current_data = current_data[-100:]

        with open(INTELLIGENCE_FILE, "w", encoding="utf-8") as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"成功写入 {len(valid_topics)} 条有效风险数据到情报站")

    def _analyze_hotspot(self, scraped_data_json: str) -> Dict[str, Any]:
        """调用 LLM 对爬取数据进行分析，返回完整的结构化风险报告。"""
        # 增强的系统提示，明确要求严格的JSON格式和基于事实的分析
        system_prompt = """你是一个舆情风险侦察兵，请严格按照指定的JSON格式输出结果。

【核心原则 - 必须严格遵守】：
1. **严格基于事实**：只分析输入数据中明确提及的内容，不得添加任何未提及的信息
2. **避免幻觉**：不得推测、想象或添加任何未在输入数据中出现的信息
3. **提高风险阈值**：只将真正存在负面舆情风险的话题标记为风险，避免过度敏感
4. **证据导向**：每个风险判断必须有明确的证据支持，不能仅凭主观判断
5. **精准识别**：只识别那些具有明确负面倾向、争议性或潜在危害的话题

【输出要求】：
- 确保输出是有效的JSON对象，包含完整的'summary'和'items'字段
- 不包含任何额外的文本、标记或解释
- 如果输入数据中没有明显的风险话题，items 必须为空数组
- 每个风险项目的 reason 必须基于输入数据中的具体内容，不得添加未提及的信息"""

        # 传入历史记忆帮助LLM进行去重和趋势判断
        historical_data_json = json.dumps(self.memory[-10:], ensure_ascii=False)

        # 使用字符串拼接而不是format()方法，避免解析JSON模板中的{}字符
        user_prompt = HH_SCAN_PROMPT
        user_prompt = user_prompt.replace('{crawled_data}', scraped_data_json)
        user_prompt = user_prompt.replace('{historical_data}', historical_data_json)

        try:
            risk_json_str = self.llm.invoke(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_mode=True,
                temperature=0.1  # 大幅降低温度，确保分析严格基于事实，减少幻觉
            )
            
            # 尝试直接解析
            parsed_result = json.loads(risk_json_str)
            
            # 验证结果结构是否完整
            if isinstance(parsed_result, dict):
                # 确保返回的结果包含所有必要字段
                if 'summary' not in parsed_result:
                    parsed_result['summary'] = "未生成摘要"
                if 'items' not in parsed_result:
                    parsed_result['items'] = []
                
                # 验证和清理每个风险项目，确保严格基于事实
                valid_items = []
                for item in parsed_result['items']:
                    # 验证必要字段是否存在且有实际内容
                    topic = item.get('topic') or item.get('title', '')
                    reason = item.get('reason', '').strip()
                    
                    # 如果 topic 为空或 reason 为空，跳过该项目（避免幻觉）
                    if not topic or not reason:
                        logger.warning(f"跳过无效的风险项目: topic={topic}, reason={reason}")
                        continue
                    
                    # 验证 reason 是否包含具体证据（至少10个字符，避免空泛判断）
                    if len(reason) < 10:
                        logger.warning(f"跳过reason过短的风险项目: {topic}, reason长度={len(reason)}")
                        continue
                    
                    # 确保每个项目都有具体的风险等级
                    risk_level = item.get('risk_level')
                    if risk_level is None or risk_level == '未知' or (isinstance(risk_level, str) and risk_level.strip() == ''):
                        # 如果风险等级无效，根据reason中的负面关键词判断
                        negative_keywords = ['负面', '争议', '冲突', '问题', '风险', '隐患', '投诉', '批评', '不满', '质疑', '事故', '错误']
                        has_negative = any(keyword in reason for keyword in negative_keywords)
                        item['risk_level'] = 4 if has_negative else 2  # 有负面关键词则为中风险，否则为低风险
                    else:
                        # 确保风险等级是整数
                        try:
                            item['risk_level'] = int(risk_level)
                        except (ValueError, TypeError):
                            item['risk_level'] = 2  # 如果无法转换，默认为低风险
                    
                    # 设置其他必要字段
                    if 'category' not in item or not item['category']:
                        item['category'] = "普通热点"
                    if 'further_investigate' not in item:
                        # 只有中高风险才需要进一步调查
                        item['further_investigate'] = item['risk_level'] >= 4
                    
                    # 确保 title 字段存在
                    if 'topic' in item:
                        item['title'] = item['topic']
                    elif 'title' not in item:
                        item['title'] = topic
                    
                    # 设置其他默认字段
                    if 'platform' not in item:
                        item['platform'] = "抖音"
                    if 'hotness' not in item:
                        item['hotness'] = "中等"
                    
                    valid_items.append(item)
                
                # 使用验证后的项目列表
                parsed_result['items'] = valid_items
                
                if 'scout_summary' not in parsed_result:
                    # 添加默认的scout_summary
                    parsed_result['scout_summary'] = {
                        "overall_observation": "未生成综合分析",
                        "content_summary": "未生成内容汇总",
                        "content_analysis": "未生成内容分析",
                        "potential_risks": ["未识别到明显风险", "建议保持常规监控", "关注热点动态变化"],
                        "trend_prediction": "无法预测",
                        "recommendations": ["建议保持常规监控", "关注热点榜的动态变化", "重点监控高热度话题"],
                        "risk_overview": {
                            "high_risk_count": 0,
                            "medium_risk_count": 0,
                            "low_risk_count": 0,
                            "total_count": 0
                        }
                    }
                else:
                    # 确保scout_summary包含所有新字段
                    if 'content_summary' not in parsed_result['scout_summary']:
                        parsed_result['scout_summary']['content_summary'] = "未生成内容汇总"
                    if 'content_analysis' not in parsed_result['scout_summary']:
                        parsed_result['scout_summary']['content_analysis'] = "未生成内容分析"
                    if 'potential_risks' not in parsed_result['scout_summary']:
                        parsed_result['scout_summary']['potential_risks'] = ["未识别到明显风险", "建议保持常规监控", "关注热点动态变化"]
                    if 'risk_overview' not in parsed_result['scout_summary']:
                        parsed_result['scout_summary']['risk_overview'] = {
                            "high_risk_count": 0,
                            "medium_risk_count": 0,
                            "low_risk_count": 0,
                            "total_count": 0
                        }
                    else:
                        # 确保risk_overview包含total_count字段
                        if 'total_count' not in parsed_result['scout_summary']['risk_overview']:
                            parsed_result['scout_summary']['risk_overview']['total_count'] = 0
                
                # 计算风险等级分布
                high_risk = 0
                medium_risk = 0
                low_risk = 0
                total_count = len(parsed_result['items'])
                
                # 降低风险等级判断阈值
                for item in parsed_result['items']:
                    risk_level = item.get('risk_level', 2)
                    if risk_level >= 6:  # 降低高风险阈值
                        high_risk += 1
                    elif risk_level >= 3:  # 降低中风险阈值
                        medium_risk += 1
                    else:
                        low_risk += 1
                
                # 更新risk_overview
                parsed_result['scout_summary']['risk_overview'] = {
                    "high_risk_count": high_risk,
                    "medium_risk_count": medium_risk,
                    "low_risk_count": low_risk,
                    "total_count": total_count
                }
                
                return parsed_result
            else:
                # 尝试构建完整的报告结构
                if isinstance(parsed_result, list):
                    return {
                        "summary": "从爬取数据中识别出多个潜在风险话题",
                        "items": parsed_result
                    }
                elif isinstance(parsed_result, dict):
                    # 补充缺失的字段
                    if 'items' not in parsed_result:
                        parsed_result['items'] = []
                    if 'summary' not in parsed_result:
                        parsed_result['summary'] = "风险分析报告（部分字段缺失）"
                    return parsed_result
            
        except json.JSONDecodeError:
            # 尝试修复常见的JSON格式问题
            try:
                # 移除可能的前缀或后缀文本
                clean_str = risk_json_str.strip()
                if not clean_str.startswith('{'):
                    clean_str = clean_str[clean_str.find('{'):]
                if not clean_str.endswith('}'):
                    clean_str = clean_str[:clean_str.rfind('}')+1]
                
                # 尝试再次解析
                result = json.loads(clean_str)
                return result
            except Exception:
                pass
        except Exception as e:
            # LLM分析失败时，尝试从爬取的数据中提取基本风险项目
            logger.error(f"LLM分析失败，尝试从爬取数据中提取风险项目: {str(e)}")
            
            try:
                # 尝试直接解析爬取的数据
                scraped_data = json.loads(scraped_data_json)
                if isinstance(scraped_data, list) and len(scraped_data) > 0:
                    # 从爬取的数据中提取基本风险项目
                    risk_items = []
                    for item in scraped_data[:10]:  # 只提取前10个项目
                        risk_item = {
                            "title": item.get('title', item.get('topic', '未知话题')),
                            "platform": item.get('platform', '未知'),
                            "hotness": item.get('hotness', '未知'),
                            "risk_level": 3,  # 默认中风险
                            "category": "未分类",
                            "reason": "LLM分析失败，从爬取数据中提取",
                            "further_investigate": True
                        }
                        risk_items.append(risk_item)
                    
                    # 返回包含提取的风险项目的报告
                    return {
                        "summary": "从爬取数据中提取到风险项目",
                        "items": risk_items,
                        "scout_summary": {
                            "overall_observation": "LLM分析失败，从爬取数据中提取风险项目",
                            "content_summary": f"从爬取数据中提取了 {len(risk_items)} 个风险项目",
                            "content_analysis": "LLM分析失败，无法进行深入分析",
                            "potential_risks": ["LLM分析失败，从爬取数据中提取风险", "建议检查LLM配置"],
                            "trend_prediction": "无法预测",
                            "recommendations": ["建议检查LLM配置", "确保API密钥有效", "检查网络连接"],
                            "risk_overview": {
                                "high_risk_count": 0,
                                "medium_risk_count": len(risk_items),
                                "low_risk_count": 0,
                                "total_count": len(risk_items)
                            }
                        }
                    }
            except Exception as parse_error:
                logger.error(f"解析爬取数据失败: {str(parse_error)}")
        
        # LLM分析失败且无法从爬取数据中提取风险项目时，返回空的风险项目列表
        logger.error("LLM分析失败，无法从爬取数据中提取风险项目，返回空结果")
        return {
            "summary": "LLM分析失败，无法生成风险报告",
            "items": [],
            "scout_summary": {
                "overall_observation": "LLM分析失败",
                "content_summary": "无法生成内容汇总",
                "content_analysis": "无法生成内容分析",
                "potential_risks": ["LLM分析失败，无法识别风险", "建议检查LLM配置"],
                "trend_prediction": "无法预测",
                "recommendations": ["建议检查LLM配置", "确保API密钥有效", "检查网络连接"],
                "risk_overview": {
                    "high_risk_count": 0,
                    "medium_risk_count": 0,
                    "low_risk_count": 0,
                    "total_count": 0
                }
            }
        }

    def run_once(self) -> Dict[str, Any]:
        """执行一次完整的侦察任务：爬取 -> 分析 -> 写入情报站。"""
        all_reports = []  # 收集所有风险报告
        all_risk_items = []  # 收集所有风险项目
        llm_failed = False  # 标记是否有LLM分析失败
        
        # 简化启动日志
        logger.info(f"开始热点侦察，共扫描 {len(TOPHUB_URLS)} 个榜单")
        
        for url in TOPHUB_URLS:
            # 1. 爬取 - 简化输出
            scraped_json = hotlist_crawler(url, save_to_file=True, output_dir=OUTPUT_DIRECTORY, verbose=False)

            if scraped_json:
                # 解析爬取的数据，获取提取的数据数量
                try:
                    scraped_data = json.loads(scraped_json)
                    extracted_count = len(scraped_data)
                    logger.info(f"爬取 {url} 成功，提取 {extracted_count} 条数据")
                except:
                    extracted_count = 0
                    logger.warning(f"爬取 {url} 成功，但数据格式无法解析")
                
                # 2. 分析 - 现在返回完整的风险报告字典
                risk_report = self._analyze_hotspot(scraped_json)

                if risk_report and isinstance(risk_report, dict):
                    # 获取报告中的风险项目列表
                    risk_items = risk_report.get('items', [])
                    
                    # 检查是否有LLM分析失败
                    if risk_report.get('summary') == "LLM分析失败，无法生成风险报告":
                        llm_failed = True
                    
                    # 3. 上报情报 (生产者行为) - 只上报items列表
                    if risk_items:
                        self._append_to_intelligence(risk_items)
                        all_risk_items.extend(risk_items)
                    
                    # 4. 添加所有报告到all_reports，包括LLM分析失败的报告
                    all_reports.append(risk_report)
                else:
                    llm_failed = True

                # 5. 更新 memory (存储原始爬取数据) - 减少日志
                try:
                    data = json.loads(scraped_json)
                    self.memory.extend(data)
                except:
                    continue

        self._save_memory()
        
        # 打印总风险数量
        if all_risk_items:
            try:
                print(f"\n[HotspotHunter] 总共发现 {len(all_risk_items)} 个潜在风险")
            except UnicodeEncodeError:
                # 避免Windows终端编码问题
                pass
        
        # 生成综合报告作为舆情预警结果
        if all_reports:
            # 检查是否所有报告都失败了
            all_failed = all(report.get('summary') == "LLM分析失败，无法生成风险报告" for report in all_reports)
            
            if all_failed:
                # 所有报告都失败了，尝试从爬取的数据中提取基本风险项目
                if all_risk_items:
                    # 即使LLM分析失败，也要生成包含已发现风险项目的报告
                    comprehensive_report = {
                        "summary": "从爬取数据中提取到风险项目",
                        "topics": all_risk_items,
                        "report_count": len(all_reports),
                        "total_risk_items": len(all_risk_items),
                        "overall_sentiment": {"negative": 0.7, "neutral": 0.2, "positive": 0.1},
                        "risk_signals": ["新发现的风险话题"] if all_risk_items else []
                    }
                    
                    # 打印报告
                    print(f"\n[HotspotHunter] 热点榜分析报告")
                    print(f"[HotspotHunter] =======================================")
                    print(f"[HotspotHunter] 扫描URL: {len(TOPHUB_URLS)} 个")
                    print(f"[HotspotHunter] 发现风险: {len(all_risk_items)} 个")
                    print(f"[HotspotHunter] =======================================")
                    
                    return comprehensive_report
                else:
                    # 所有报告都失败了，生成简洁的失败报告
                    failed_report = {
                        "summary": "LLM分析失败，无法生成风险报告",
                        "items": [],
                        "report_count": len(all_reports),
                        "total_risk_items": 0
                    }
                    
                    # 打印简洁的LLM分析失败报告
                    print(f"\n[HotspotHunter] 热点榜分析报告")
                    print(f"[HotspotHunter] =======================================")
                    print(f"[HotspotHunter] 错误: LLM API调用失败 (无效令牌)")
                    print(f"[HotspotHunter] 扫描URL: {len(TOPHUB_URLS)} 个")
                    print(f"[HotspotHunter] 发现风险: {len(all_risk_items)} 个")
                    print(f"[HotspotHunter] 建议: 检查API密钥和配置")
                    print(f"[HotspotHunter] =======================================")
                    
                    return failed_report
            else:
                # 合并所有报告的摘要
                combined_summary = "\n".join([report.get('summary', '') for report in all_reports if report.get('summary') and report.get('summary') != "LLM分析失败，无法生成风险报告"])
                
                # 如果有成功的报告，构建综合报告
                comprehensive_report = {
                    "summary": combined_summary,
                    "topics": all_risk_items,
                    "report_count": len(all_reports),
                    "total_risk_items": len(all_risk_items),
                    "overall_sentiment": {"negative": 0.7, "neutral": 0.2, "positive": 0.1},
                    "risk_signals": ["新发现的风险话题"] if all_risk_items else []
                }
                
                # 合并scout_summary（只合并成功的报告）
                successful_reports = [report for report in all_reports if report.get('summary') != "LLM分析失败，无法生成风险报告"]
                if successful_reports:
                    # 合并scout_summary（这里简化处理，只取第一个成功报告的scout_summary）
                    comprehensive_report['scout_summary'] = successful_reports[0].get('scout_summary', {
                        "overall_observation": "综合分析完成",
                        "content_summary": "完成内容汇总",
                        "content_analysis": "完成内容分析",
                        "potential_risks": ["未识别到明显风险", "建议保持常规监控", "关注热点动态变化"],
                        "trend_prediction": "短期内舆情趋势平稳",
                        "recommendations": ["建议保持常规监控频率", "关注热点榜的动态变化", "重点监控高热度话题"],
                        "risk_overview": {
                            "high_risk_count": 0,
                            "medium_risk_count": 0,
                            "low_risk_count": 0,
                            "total_count": 0
                        }
                    })
                
                # 将报告内容添加到comprehensive_report中
                comprehensive_report['detailed_report'] = {
                    'scan_url_count': len(TOPHUB_URLS),
                    'total_risk_items': len(all_risk_items),
                    'risk_overview': comprehensive_report['scout_summary'].get('risk_overview', {})
                }
                
                # 保存综合报告到文件
                report_file_name = f"hotspot_report_{int(time.time())}_{os.urandom(4).hex()}.json"
                report_file_path = Path(OUTPUT_DIRECTORY) / report_file_name
                with open(report_file_path, 'w', encoding='utf-8') as f:
                    json.dump(comprehensive_report, f, ensure_ascii=False, indent=2)
                
                # 打印详细的热点榜分析报告
                print(f"\n[HotspotHunter] 热点榜分析报告")
                print(f"[HotspotHunter] =======================================")
                print(f"[HotspotHunter] 扫描URL: {len(TOPHUB_URLS)} 个")
                print(f"[HotspotHunter] 发现风险: {len(all_risk_items)} 个")
                
                # 打印风险等级概览 - 详细信息
                if 'scout_summary' in comprehensive_report:
                    risk_overview = comprehensive_report['scout_summary'].get('risk_overview', {})
                    print(f"[HotspotHunter] 风险概览:")
                    print(f"[HotspotHunter]    高风险: {risk_overview.get('high_risk_count', 0)} 个")
                    print(f"[HotspotHunter]    中风险: {risk_overview.get('medium_risk_count', 0)} 个")
                    print(f"[HotspotHunter]    低风险: {risk_overview.get('low_risk_count', 0)} 个")
                
                # 打印每个风险项目的关键信息 - 详细输出
                if all_risk_items:
                    print(f"[HotspotHunter] 风险项目 (显示前5个):")
                    for i, item in enumerate(all_risk_items[:5]):  # 只显示前5个
                        title = item.get('title', '未知标题')
                        risk_level = item.get('risk_level', '未知')
                        category = item.get('category', '未分类')
                        platform = item.get('platform', '未知')
                        print(f"[HotspotHunter]    {i+1}. {title} ({risk_level}/10, {category}, {platform})")
                    if len(all_risk_items) > 5:
                        print(f"[HotspotHunter]    ... 还有 {len(all_risk_items) - 5} 个风险项目")
                
                print(f"[HotspotHunter] =======================================")
                
                return comprehensive_report
        else:
            # 如果没有报告，返回真实反映情况的结果
            # 不再生成虚假的内容汇总和分析
            no_report_result = {
                "summary": "未生成任何风险报告",
                "topics": [],
                "report_count": 0,
                "total_risk_items": 0,
                "overall_sentiment": {"negative": 0.7, "neutral": 0.2, "positive": 0.1},
                "risk_signals": []
            }
            
            # 添加真实的scout_summary，不包含虚假内容
            no_report_result['scout_summary'] = {
                "overall_observation": "未生成任何风险报告，无法进行分析",
                "content_summary": "未生成内容汇总，没有可用的分析数据",
                "content_analysis": "未生成内容分析，没有可用的分析数据",
                "potential_risks": ["未生成任何风险报告", "建议检查系统配置", "确保所有组件正常运行"],
                "trend_prediction": "无法预测，没有可用的分析数据",
                "recommendations": ["建议检查系统配置", "确保所有组件正常运行", "重新启动系统尝试"],
                "risk_overview": {
                    "high_risk_count": 0,
                    "medium_risk_count": 0,
                    "low_risk_count": 0,
                    "total_count": 0
                }
            }
            
            # 打印简洁的无报告结果
            print(f"\n[HotspotHunter] 热点榜分析报告")
            print(f"[HotspotHunter] =======================================")
            print(f"[HotspotHunter] 扫描URL: {len(TOPHUB_URLS)} 个")
            print(f"[HotspotHunter] 发现风险: 0 个")
            print(f"[HotspotHunter] 建议: 检查系统配置")
            print(f"[HotspotHunter] =======================================")
            
            return no_report_result

    def run_loop(self):
        """持续侦察循环。"""
        print(f"Hotspot Hunter 侦察兵已就位，初始频率: {self.interval}s/次")
        while True:
            start_time = time.time()
            try:
                self.run_once()
            except Exception as e:
                print(f"[HotspotHunter] 发生错误: {e}")

            elapsed_time = time.time() - start_time
            sleep_time = max(0, self.interval - elapsed_time)

            print(f"💤 休眠 {sleep_time:.1f}s (当前设定间隔: {self.interval}s)...")
            time.sleep(sleep_time)


# Main entry point for direct execution
if __name__ == "__main__":
    # Create LLM client
    llm_client = LLMClient(LLM_CONFIG)
    
    # Create HotspotHunterAgent instance
    agent = HotspotHunterAgent(llm_client, crawl_interval=HOTSPOT_HUNTER_INTERVAL)
    
    # Run once for testing
    print("🚀 Starting Hotspot Hunter test run...")
    result = agent.run_once()
    print("✅ Test run completed!")
    
    # Print summary of results
    print(f"📊 Results: {result['total_risk_items']} risk items found")
    if result['items']:
        print("💡 Risk items details:")
        for i, item in enumerate(result['items'][:3]):  # Show first 3 items
            print(f"   {i+1}. {item.get('topic', 'Unknown')} (Risk Level: {item.get('risk_level', 'N/A')})")
            print(f"      Reason: {item.get('reason', 'No reason provided')}")
    if result.get('scout_summary'):
        print("📋 Scout Summary:")
        print(f"   Overall: {result['scout_summary'].get('overall_observation', 'No summary')}")
        print(f"   Content: {result['scout_summary'].get('content_summary', 'No content summary')}")