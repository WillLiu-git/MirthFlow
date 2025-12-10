#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RiskAnalyzer - 舆情风险分析指挥官模块

功能：
1. 接收HotspotHunter的热点报告
2. 分析潜在风险话题
3. 智能指挥MediaCrawler进行深入调研
4. 审查调研结果并生成舆情预警
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("RiskAnalyzer")

# 导入内部模块
try:
    from .llm.llm import LLMClient
    from .prompts.prompts import RA_DECISION_PROMPT
    from .utils.config import LLM_CONFIG
except ImportError:
    from llm.llm import LLMClient
    from prompts.prompts import RA_DECISION_PROMPT
    from utils.config import LLM_CONFIG


class RiskAnalyzer:
    """
    RiskAnalyzer主类 - 舆情风险分析指挥官
    负责分析热点报告、决策后续行动并生成预警
    """
    
    def __init__(self):
        """初始化RiskAnalyzer"""
        self.llm_client = LLMClient(
            api_key=LLM_CONFIG.get("api_key"),
            model_name=LLM_CONFIG.get("model_name"),
            base_url=LLM_CONFIG.get("base_url")
        )
        self.last_analysis_result = None
        self.hotspot_memory = []  # 记忆库，存储历史分析结果
        logger.info("RiskAnalyzer初始化完成")
    
    def receive_hotspot_report(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        接收并处理HotspotHunter的热点报告
        
        Args:
            report_data: HotspotHunter输出的结构化报告数据
                        应包含topics和summary字段
        
        Returns:
            Dict: 分析决策结果
        """
        try:
            logger.info(f"接收到HotspotHunter报告，包含{len(report_data.get('topics', []))}个话题")
            
            # 验证报告格式
            if not isinstance(report_data, dict) or 'topics' not in report_data:
                raise ValueError("无效的报告格式：缺少topics字段")
            
            # 将报告转换为字符串格式用于LLM处理
            hh_scan_result = json.dumps(report_data, ensure_ascii=False, indent=2)
            
            # 调用LLM进行分析决策
            decision_result = self._analyze_with_llm(hh_scan_result)
            
            # 保存分析结果
            self.last_analysis_result = decision_result
            
            # 更新记忆库
            self._update_memory(decision_result)
            
            logger.info(f"分析完成，全局风险等级：{decision_result.get('global_risk_level')}")
            return decision_result
            
        except Exception as e:
            logger.error(f"处理HotspotHunter报告时出错: {str(e)}")
            # 返回错误响应
            return {
                "risk_summary": "分析失败",
                "risk_items": [],
                "global_risk_level": "未知",
                "confidence": 0.0,
                "actions": {
                    "call_vcs": {"should_call": False},
                    "adjust_frequency": {"should_adjust": False},
                    "trigger_alert": {"should_alert": True, "alert_message": f"分析系统错误: {str(e)}"}
                }
            }
    
    def _analyze_with_llm(self, hh_scan_result: str) -> Dict[str, Any]:
        """
        使用LLM分析热点报告
        
        Args:
            hh_scan_result: HotspotHunter报告的JSON字符串
        
        Returns:
            Dict: 解析后的决策结果
        """
        try:
            # 构建用户提示
            user_prompt = RA_DECISION_PROMPT.format(hh_scan_result=hh_scan_result)
            
            # 调用LLM，使用json_mode确保返回JSON格式
            # 降低温度参数以减少幻觉，提高准确性
            response = self.llm_client.invoke(
                system_prompt="你是一个专业的舆情分析专家，擅长识别潜在风险。你必须严格基于输入数据进行分析，不得添加任何未提及的信息。",
                user_prompt=user_prompt,
                json_mode=True,
                temperature=0.2  # 降低温度以减少幻觉
            )
            
            # 解析JSON响应，添加更强的容错处理
            import re
            
            # 清理响应内容，移除可能的markdown格式或额外文本
            if isinstance(response, str):
                # 移除可能的JSON代码块标记
                response = response.strip()
                if response.startswith('```json'):
                    response = response[7:]
                if response.endswith('```'):
                    response = response[:-3]
                
                # 移除可能的换行符和多余空格，确保是干净的JSON字符串
                response = response.strip()
            
            # 解析JSON
            decision_data = json.loads(response)
            return decision_data
            
        except json.JSONDecodeError as e:
            logger.error(f"LLM返回的不是有效的JSON格式: {e}")
            logger.error(f"原始响应内容: {response}")
            # 尝试从原始热点报告中提取风险话题
            return self._extract_risk_items_from_report(hh_scan_result)
        except Exception as e:
            logger.error(f"LLM分析过程出错: {str(e)}")
            # 尝试从原始热点报告中提取风险话题
            return self._extract_risk_items_from_report(hh_scan_result)
    
    def _extract_risk_items_from_report(self, hh_scan_result: str) -> Dict[str, Any]:
        """
        从热点报告中直接提取风险话题，作为LLM分析失败的备选方案
        
        Args:
            hh_scan_result: HotspotHunter报告的JSON字符串
        
        Returns:
            Dict: 包含风险话题的决策结果
        """
        try:
            # 解析热点报告
            report_data = json.loads(hh_scan_result)
            topics = report_data.get('topics', [])
            
            # 提取所有话题作为风险话题
            risk_items = []
            for topic in topics:
                risk_items.append({
                    "title": topic.get('title', '未知话题'),
                    "reason": topic.get('summary', '无摘要'),
                    "level": "中风险"
                })
            
            # 构建决策结果
            return {
                "risk_summary": f"从热点报告中提取了 {len(risk_items)} 个风险话题",
                "risk_items": risk_items,
                "global_risk_level": "中",
                "confidence": 0.8,
                "actions": {
                    "call_vcs": {
                        "should_call": True,
                        "target_topics": [item["title"] for item in risk_items],
                        "search_keywords": [keyword for topic in topics for keyword in topic.get('keywords', [])]
                    },
                    "adjust_frequency": {
                        "should_adjust": False
                    },
                    "trigger_alert": {
                        "should_alert": False
                    }
                },
                "recommendations": []
            }
            
        except Exception as e:
            logger.error(f"从报告中提取风险话题时出错: {str(e)}")
            # 返回基础决策结果
            return {
                "risk_summary": "分析失败",
                "risk_items": [],
                "global_risk_level": "未知",
                "confidence": 0.0,
                "actions": {
                    "call_vcs": {
                        "should_call": False
                    },
                    "adjust_frequency": {
                        "should_adjust": False
                    },
                    "trigger_alert": {
                        "should_alert": False
                    }
                },
                "recommendations": []
            }
    
    def _update_memory(self, decision_result: Dict[str, Any]):
        """
        更新风险记忆库，用于历史对比
        
        Args:
            decision_result: 当前分析决策结果
        """
        try:
            memory_item = {
                "timestamp": datetime.now().isoformat(),
                "global_risk_level": decision_result.get("global_risk_level"),
                "risk_items": decision_result.get("risk_items", []),
                "key_risks": decision_result.get("memory_update", {}).get("key_risks_to_save", [])
            }
            
            # 添加到记忆库，限制历史记录数量
            self.hotspot_memory.append(memory_item)
            if len(self.hotspot_memory) > 10:  # 保留最近10次分析
                self.hotspot_memory = self.hotspot_memory[-10:]
                
            logger.info(f"记忆库更新成功，当前记录数: {len(self.hotspot_memory)}")
            
        except Exception as e:
            logger.error(f"更新记忆库时出错: {str(e)}")
    
    def get_last_analysis(self) -> Optional[Dict[str, Any]]:
        """
        获取上一次的分析结果
        
        Returns:
            Optional[Dict]: 上一次的分析决策结果
        """
        return self.last_analysis_result
    
    def command_media_crawler(self, decision_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        根据决策结果智能指挥VideosCommentsSpotter进行深入调研
        
        Args:
            decision_result: 分析决策结果
        
        Returns:
            Dict: VideosCommentsSpotter调研结果
        """
        try:
            # 导入必要的模块
            import sys
            import os
            
            # 检查是否需要调用VCS
            actions = decision_result.get("actions", {})
            call_vcs = actions.get("call_vcs", {})
            
            if not call_vcs.get("should_call", False):
                logger.info("不需要调用VideosCommentsSpotter进行深入调研")
                return {"success": False, "reason": "无需深入调研"}
            
            # 获取目标话题和关键词
            target_topics = call_vcs.get("target_topics", [])
            search_keywords = call_vcs.get("search_keywords", [])
            
            logger.info(f"准备调用VideosCommentsSpotter，调研{len(target_topics)}个话题，使用{len(search_keywords)}个关键词")
            
            # 实际调用VideosCommentsSpotter组件
            try:
                # 导入VideosCommentsSpotter组件
                sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
                from VideosCommentsSpotter.agent import VideosCommentsSpotterAgent
                from VideosCommentsSpotter.llm.llm import LLMClient
                from VideosCommentsSpotter.utils.config import LLM_CONFIG
                
                # 初始化LLM客户端
                llm_client = LLMClient(
                    api_key=LLM_CONFIG.get("api_key"),
                    model_name=LLM_CONFIG.get("model_name"),
                    base_url=LLM_CONFIG.get("base_url")
                )
                
                # 初始化VideosCommentsSpotterAgent
                vcs_agent = VideosCommentsSpotterAgent(llm_client)
                
                # 存储所有VCS调研结果
                all_vcs_results = []
                
                # 遍历每个目标话题，调用VCS进行调研
                for topic in target_topics:
                    # 构建风险话题对象
                    risk_topic = {
                        "topic": topic,
                        "description": f"对话题 '{topic}' 进行舆情调研",
                        "priority": "high"
                    }
                    
                    # 调用VCS进行调研
                    logger.info(f"调用VCS调研话题: {topic}")
                    vcs_result = vcs_agent.process_topic(risk_topic)
                    
                    # 处理VCS返回结果
                    if vcs_result.get("status") == "success":
                        all_vcs_results.append(vcs_result)
                        logger.info(f"VCS调研话题 '{topic}' 成功，发现 {len(vcs_result.get('key_findings', []))} 个关键发现")
                    else:
                        logger.warning(f"VCS调研话题 '{topic}' 失败: {vcs_result.get('error', '未知原因')}")
                
                # 构建统一的调研结果格式
                crawler_result = {
                    "success": True,
                    "target_topics": target_topics,
                    "search_keywords": search_keywords,
                    "vcs_results": all_vcs_results,
                    "total_topics": len(target_topics),
                    "successful_topics": len([r for r in all_vcs_results if r.get("status") == "success"]),
                    "timestamp": datetime.now().isoformat()
                }
                
            except Exception as vcs_e:
                logger.error(f"调用VideosCommentsSpotter时出错: {str(vcs_e)}")
                logger.warning(f"使用模拟数据进行后续分析")
                # 如果调用失败，使用模拟数据
                crawler_result = {
                    "success": False,
                    "reason": f"调用VCS失败: {str(vcs_e)}",
                    "target_topics": target_topics,
                    "search_keywords": search_keywords,
                    "vcs_results": [],
                    "timestamp": datetime.now().isoformat()
                }
            
            logger.info(f"VideosCommentsSpotter调研完成，成功调研{len([r for r in crawler_result.get('vcs_results', []) if r.get('status') == 'success'])}个话题")
            return crawler_result
            
        except Exception as e:
            logger.error(f"调用VideosCommentsSpotter时出错: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _simulate_media_crawler(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        模拟MediaCrawler返回结果（仅用于开发测试）
        
        Args:
            params: MediaCrawler调用参数
        
        Returns:
            Dict: 模拟的调研结果
        """
        # 构建模拟数据
        videos = []
        for keyword in params.get("search_keywords", [])[:3]:  # 限制返回数量便于测试
            for i in range(params.get("video_count", 1)):
                video = {
                    "video_id": f"video_{keyword}_{i}",
                    "title": f"关于{keyword}的热门视频 #{i+1}",
                    "platform": params["platforms"][i % len(params["platforms"])],
                    "author": f"用户{i}",
                    "view_count": 10000 + i * 500,
                    "like_count": 1000 + i * 100,
                    "comment_count": 200 + i * 20,
                    "publish_time": "2024-01-15 10:00:00",
                    "content": f"这是关于{keyword}的视频内容，包含了各种讨论和观点。",
                    "keywords": [keyword, "热点", "讨论"],
                    "sentiment_score": 0.5 - (i % 3) * 0.2,  # 模拟不同的情感倾向
                    "comments": []
                }
                
                # 添加模拟评论
                for j in range(params.get("comment_count", 1)):
                    comment = {
                        "comment_id": f"comment_{keyword}_{i}_{j}",
                        "content": f"关于{keyword}的评论 #{j+1}，表达了{'正面' if j % 2 == 0 else '负面'}的观点。",
                        "user": f"评论用户{j}",
                        "like_count": 10 + j,
                        "publish_time": "2024-01-15 11:00:00",
                        "sentiment_score": 0.7 if j % 2 == 0 else 0.3
                    }
                    video["comments"].append(comment)
                
                videos.append(video)
        
        return {
            "success": True,
            "params": params,
            "videos": videos,
            "total_videos": len(videos),
            "total_comments": sum(len(v["comments"]) for v in videos),
            "timestamp": datetime.now().isoformat()
        }
    
    def analyze_crawler_results(self, crawler_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析MediaCrawler返回的调研结果
        
        Args:
            crawler_result: MediaCrawler的调研结果
        
        Returns:
            Dict: 分析后的风险评估结果
        """
        try:
            if not crawler_result.get("success", False):
                return {"success": False, "risk_level": "未知", "reason": crawler_result.get("reason", "调研失败")}
            
            # 从VCS结果中提取信息
            vcs_results = crawler_result.get("vcs_results", [])
            
            # 合并所有VCS结果的关键发现和风险评估
            all_key_findings = []
            all_risk_factors = []
            all_sentiments = []
            total_data_count = 0
            total_comment_count = 0
            
            for vcs_result in vcs_results:
                if vcs_result.get("status") == "success":
                    # 合并关键发现
                    key_findings = vcs_result.get("key_findings", [])
                    all_key_findings.extend(key_findings)
                    
                    # 合并风险因素
                    risk_assessment = vcs_result.get("risk_assessment", {})
                    risk_factors = risk_assessment.get("factors", [])
                    all_risk_factors.extend(risk_factors)
                    
                    # 合并情感分析
                    sentiment = vcs_result.get("analysis", {}).get("sentiment_analysis", {})
                    if sentiment:
                        all_sentiments.append(sentiment)
                    
                    # 累加数据统计
                    data_stats = vcs_result.get("data_statistics", {})
                    total_data_count += data_stats.get("total_items", 0)
                    total_comment_count += data_stats.get("total_comments", 0)
            
            # 去重
            all_key_findings = list(dict.fromkeys(all_key_findings))
            all_risk_factors = list(dict.fromkeys(all_risk_factors))
            
            # 计算综合风险等级
            risk_level = "低风险"
            
            # 检查是否有高风险评估
            high_risk_count = 0
            medium_risk_count = 0
            
            for vcs_result in vcs_results:
                if vcs_result.get("status") == "success":
                    risk_assessment = vcs_result.get("risk_assessment", {})
                    level = risk_assessment.get("level", "低").lower()
                    if level == "高" or level == "极高":
                        high_risk_count += 1
                    elif level == "中":
                        medium_risk_count += 1
            
            # 综合判断风险等级
            if high_risk_count > 0:
                risk_level = "高风险"
            elif medium_risk_count > len(vcs_results) / 2:
                risk_level = "中风险"
            
            # 生成风险因素
            final_risk_factors = []
            if all_risk_factors:
                final_risk_factors = all_risk_factors
            elif high_risk_count > 0:
                final_risk_factors.append("VCS调研发现高风险内容")
            elif medium_risk_count > 0:
                final_risk_factors.append("VCS调研发现中等风险内容")
            
            # 统计热门观点
            hot_opinions = []
            for vcs_result in vcs_results[:3]:  # 分析前3个VCS结果
                if vcs_result.get("status") == "success":
                    summary = vcs_result.get("summary", "")
                    hot_opinions.append({
                        "topic": vcs_result.get("source_topic", {}).get("topic", "未知话题"),
                        "summary": summary[:100] + "..." if len(summary) > 100 else summary,
                        "risk_level": vcs_result.get("risk_assessment", {}).get("level", "未知")
                    })
            
            # 生成综合统计
            stats = {
                "total_topics": len(vcs_results),
                "total_data_count": total_data_count,
                "total_comment_count": total_comment_count,
                "successful_analyses": len([r for r in vcs_results if r.get("status") == "success"]),
                "key_findings_count": len(all_key_findings),
                "risk_factors_count": len(all_risk_factors)
            }
            
            return {
                "success": True,
                "risk_level": risk_level,
                "risk_factors": final_risk_factors,
                "key_findings": all_key_findings,
                "stats": stats,
                "hot_opinions": hot_opinions,
                "recommendation": self._generate_recommendation(risk_level, final_risk_factors)
            }
            
        except Exception as e:
            logger.error(f"分析调研结果时出错: {str(e)}")
            return {"success": False, "risk_level": "未知", "error": str(e)}
    
    def _generate_recommendation(self, risk_level: str, risk_factors: List[str]) -> str:
        """
        根据风险等级和因素生成建议
        
        Args:
            risk_level: 风险等级
            risk_factors: 风险因素列表
        
        Returns:
            str: 建议内容
        """
        if risk_level == "高风险":
            return (
                "建议立即采取危机公关措施：\n"
                "1. 密切监控舆情发展，每小时更新一次数据\n"
                "2. 准备官方声明，回应关键质疑点\n"
                "3. 考虑联系相关平台，请求协助管理不当言论\n"
                "4. 启动内部调查，核实相关情况"
            )
        elif risk_level == "中风险":
            return (
                "建议加强监控并准备应对：\n"
                "1. 每4小时更新一次舆情数据\n"
                "2. 准备回应话术，但暂不主动发布\n"
                "3. 关注意见领袖的观点动向\n"
                "4. 评估是否需要采取进一步行动"
            )
        else:
            return (
                "建议保持常规监控：\n"
                "1. 按照正常频率监控舆情\n"
                "2. 记录相关话题的发展趋势\n"
                "3. 定期汇总分析，形成报告"
            )
    
    def generate_risk_alert(self, hh_report: Dict[str, Any], decision_result: Dict[str, Any], 
                          crawler_analysis: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        生成最终的舆情预警报告
        即使没有VCS调研结果也可以生成预警
        
        Args:
            hh_report: HotspotHunter原始报告
            decision_result: 热点分析决策结果
            crawler_analysis: MediaCrawler调研分析结果（可选）
        
        Returns:
            Dict: 完整的舆情预警报告
        """
        try:
            # 确定最终风险等级
            final_risk_level = decision_result.get("global_risk_level", "低")
            risk_factors = []
            
            # 收集热点分析的风险因素
            for risk_item in decision_result.get("risk_items", []):
                risk_factors.append(f"{risk_item['title']}: {risk_item['reason']} ({risk_item['level']})")
            
            # 综合评估调研结果
            # 如果有crawler_analysis，考虑其风险等级和关键发现
            vcs_research_info = None
            if crawler_analysis and crawler_analysis.get("success", False):
                # 1. 整合VCS调研的风险等级
                crawler_risk_level = crawler_analysis.get("risk_level", "低风险")
                # 风险等级映射
                risk_mapping = {"低风险": "低", "中风险": "中", "高风险": "高", "极高风险": "高"}
                mapped_level = risk_mapping.get(crawler_risk_level, "低")
                
                # 取较高的风险等级
                level_priority = {"低": 0, "中": 1, "高": 2}
                if level_priority.get(mapped_level, 0) > level_priority.get(final_risk_level, 0):
                    final_risk_level = mapped_level
                
                # 2. 整合VCS调研的风险因素
                vcs_risk_factors = crawler_analysis.get("risk_factors", [])
                if vcs_risk_factors:
                    risk_factors.extend([f"VCS调研发现: {factor}" for factor in vcs_risk_factors])
                
                # 3. 整合VCS调研的关键发现
                vcs_key_findings = crawler_analysis.get("key_findings", [])
                if vcs_key_findings:
                    for finding in vcs_key_findings[:5]:  # 最多显示5个关键发现
                        risk_factors.append(f"关键发现: {finding}")
                
                # 4. 准备VCS调研信息
                stats = crawler_analysis.get("stats", {})
                vcs_research_info = {
                    "total_topics": stats.get("total_topics", 0),
                    "total_data_count": stats.get("total_data_count", 0),
                    "total_comment_count": stats.get("total_comment_count", 0),
                    "successful_analyses": stats.get("successful_analyses", 0),
                    "key_findings_count": stats.get("key_findings_count", 0)
                }
            
            # 生成预警等级和处理优先级
            alert_level = "普通"
            if final_risk_level == "高":
                alert_level = "紧急"
            elif final_risk_level == "中":
                alert_level = "重要"
            
            # 获取具体话题信息
            target_topics = decision_result.get("actions", {}).get("call_vcs", {}).get("target_topics", [])
            if not target_topics:
                # 如果没有target_topics，从risk_items中提取
                target_topics = [item["title"] for item in decision_result.get("risk_items", [])]
            
            # 生成预警报告
            alert_report = {
                "alert_id": f"RA-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "timestamp": datetime.now().isoformat(),
                "alert_level": alert_level,
                "risk_level": final_risk_level,
                "summary": decision_result.get("risk_summary", "未生成摘要"),
                "target_topics": target_topics,  # 明确针对的话题
                "risk_factors": risk_factors,
                "source_info": {
                    "hotspot_report": {
                        "topic_count": len(hh_report.get("topics", [])),
                        "scan_summary": hh_report.get("summary", "")
                    }
                },
                "actions": decision_result.get("actions", {}),
                "recommendations": [],
                "details": {}
            }
            
            # 如果有VCS调研信息，添加到预警报告中
            if vcs_research_info:
                alert_report["source_info"]["vcs_research"] = vcs_research_info
                
                # 添加深入调研结果详情
                if crawler_analysis:
                    alert_report["details"]["crawler_analysis"] = {
                        "stats": crawler_analysis.get("stats", {}),
                        "hot_opinions": crawler_analysis.get("hot_opinions", []),
                        "key_findings": crawler_analysis.get("key_findings", [])[:10],  # 最多显示10个关键发现
                        "crawler_recommendation": crawler_analysis.get("recommendation", "")
                    }
            
            # 生成针对用户的综合建议
            user_recommendations = self._generate_user_recommendations(final_risk_level, risk_factors, target_topics)
            alert_report["recommendations"].extend(user_recommendations)
            
            # 添加监控建议
            alert_report["recommendations"].append(self._generate_monitoring_suggestion(final_risk_level))
            
            logger.info(f"生成{alert_level}级别舆情预警，风险等级：{final_risk_level}，针对话题：{', '.join(target_topics)}")
            return alert_report
            
        except Exception as e:
            logger.error(f"生成舆情预警时出错: {str(e)}")
            # 返回基础预警信息
            return {
                "alert_id": f"RA-ERROR-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "timestamp": datetime.now().isoformat(),
                "alert_level": "重要",
                "risk_level": "未知",
                "summary": "舆情预警生成失败",
                "error": str(e)
            }
    
    def _generate_user_recommendations(self, risk_level: str, risk_factors: List[str], target_topics: List[str]) -> List[str]:
        """
        根据风险等级、风险因素和目标话题生成针对用户的建议
        
        Args:
            risk_level: 风险等级
            risk_factors: 风险因素列表
            target_topics: 目标话题列表
        
        Returns:
            List[str]: 针对用户的建议列表
        """
        # 生成针对具体话题的建议
        topic_specific_recommendations = []
        for topic in target_topics:
            topic_specific_recommendations.append(
                f"针对话题 '{topic}' 的建议：\n"
                f"1. 密切关注该话题在各平台的传播趋势\n"
                f"2. 收集并分析相关评论，了解公众真实态度\n"
                f"3. 准备针对性的回应策略，根据舆情发展及时调整\n"
                f"4. 考虑联系相关平台，请求协助管理不当言论（如风险较高）"
            )
        
        # 生成通用建议
        general_recommendations = []
        if risk_level == "高":
            general_recommendations.append(
                "通用建议：\n"
                "1. 立即成立危机公关小组，启动应急预案\n"
                "2. 准备官方声明，明确回应公众关切\n"
                "3. 主动联系权威媒体，传递正面信息\n"
                "4. 安排专人监控舆情，每小时更新一次数据\n"
                "5. 考虑采取法律手段，维护自身合法权益（如涉及恶意攻击）"
            )
        elif risk_level == "中":
            general_recommendations.append(
                "通用建议：\n"
                "1. 加强监控力度，每4小时更新一次舆情数据\n"
                "2. 准备回应话术，暂不主动发布\n"
                "3. 关注意见领袖的观点动向\n"
                "4. 定期汇总分析，评估风险变化趋势\n"
                "5. 考虑邀请第三方机构进行调查，提供客观报告"
            )
        else:
            general_recommendations.append(
                "通用建议：\n"
                "1. 保持常规监控频率，每日汇总分析\n"
                "2. 记录相关话题的发展趋势\n"
                "3. 定期生成分析报告，供决策参考\n"
                "4. 关注同类话题的发展情况，汲取经验教训\n"
                "5. 持续优化舆情监测系统，提高预警准确性"
            )
        
        # 生成风险因素针对性建议
        factor_specific_recommendations = []
        if risk_factors:
            factor_specific_recommendations.append(
                "风险因素针对性建议：\n"
                f"1. 针对{len(risk_factors)}项风险因素，逐一制定应对措施\n"
                "2. 重点关注负面评论比例较高的风险点\n"
                "3. 分析风险因素的关联性，制定综合解决方案\n"
                "4. 定期评估应对措施的有效性，及时调整"
            )
        
        # 合并所有建议
        return topic_specific_recommendations + general_recommendations + factor_specific_recommendations
    
    def _generate_monitoring_suggestion(self, risk_level: str) -> str:
        """
        根据风险等级生成监控建议
        
        Args:
            risk_level: 风险等级
        
        Returns:
            str: 监控建议
        """
        if risk_level == "高":
            return "监控建议：立即启动7x24小时专人监控，设置每小时自动检测机制，重点关注意见领袖言论和话题扩散速度。"
        elif risk_level == "中":
            return "监控建议：启动12小时重点监控，每4小时更新一次数据，关注话题热度变化趋势和主流媒体报道。"
        else:
            return "监控建议：保持日常监控频率，每日汇总分析报告，关注话题自然演化。"
    
    def run_full_analysis_flow(self, hotspot_report: Dict[str, Any]) -> Dict[str, Any]:
        """
        运行完整的分析流程
        1. 接收热点报告
        2. 分析决策
        3. 对所有风险话题进行深入调研（必须）
        4. 结合VCS调研结果生成最终预警
        
        Args:
            hotspot_report: HotspotHunter的热点报告
        
        Returns:
            Dict: 完整的分析结果和预警报告
        """
        try:
            # 1. 接收并分析热点报告
            logger.info("开始完整分析流程")
            
            # 检查热点报告是否包含话题
            topics = hotspot_report.get('topics', [])
            if not topics:
                logger.info("热点报告未包含任何话题，跳过风险分析")
                return {
                    "risk_summary": "未发现有效话题，跳过风险分析",
                    "risk_items": [],
                    "global_risk_level": "低",
                    "confidence": 0.0,
                    "actions": {
                        "call_vcs": {
                            "should_call": False
                        },
                        "adjust_frequency": {
                            "should_adjust": False
                        },
                        "trigger_alert": {
                            "should_alert": False
                        }
                    },
                    "recommendations": []
                }
            
            decision_result = self.receive_hotspot_report(hotspot_report)
            
            # 记录分析决策结果
            logger.info(f"分析决策结果: 全局风险等级-{decision_result.get('global_risk_level', '未知')}, 风险摘要-{decision_result.get('risk_summary', '无摘要')}")
            
            # 2. 智能筛选风险话题进行深入调研
            crawler_analysis = None
            risk_items = decision_result.get('risk_items', [])
            
            if risk_items:
                logger.info(f"发现 {len(risk_items)} 个风险话题")
                
                # 筛选策略：有选择性地选择话题，确保至少选择几个
                # 1. 优先选择高/中风险话题，降低证据要求
                # 2. 若高/中风险话题不足，则补充低风险话题
                # 3. 确保至少选择2-3个话题进行深入调研
                selected_items = []
                
                # 先收集所有高/中风险话题（降低证据要求）
                high_medium_risk_items = []
                low_risk_items = []
                
                for risk_item in risk_items:
                    risk_level = risk_item.get('level', '').lower()
                    reason = risk_item.get('reason', '').strip()
                    
                    # 检查风险等级
                    if '高' in risk_level or '中' in risk_level:
                        high_medium_risk_items.append(risk_item)
                    else:
                        low_risk_items.append(risk_item)
                
                # 优先选择高/中风险话题
                if high_medium_risk_items:
                    # 最多选择3个高/中风险话题
                    selected_items = high_medium_risk_items[:3]
                    logger.info(f"优先选择 {len(selected_items)} 个高/中风险话题进行深入调研")
                
                # 若高/中风险话题不足2个，则补充低风险话题
                if len(selected_items) < 2:
                    # 计算需要补充的数量
                    need_more = 2 - len(selected_items)
                    # 从低风险话题中选择补充
                    additional_items = low_risk_items[:need_more]
                    selected_items.extend(additional_items)
                    if additional_items:
                        logger.info(f"补充选择 {len(additional_items)} 个低风险话题进行深入调研")
                
                # 确保至少选择了一些话题
                if len(selected_items) < 2:
                    # 如果还是不够，从所有风险话题中选择前2个
                    selected_items = risk_items[:2]
                    logger.info(f"从所有风险话题中选择 {len(selected_items)} 个进行深入调研")
                
                if selected_items:
                    logger.info(f"最终选择 {len(selected_items)} 个话题进行深入调研")
                    
                    # 设置call_vcs为true，进行深入调研
                    decision_result.setdefault("actions", {})
                    decision_result["actions"].setdefault("call_vcs", {})
                    decision_result["actions"]["call_vcs"]["should_call"] = True
                    
                    # 提取选中的话题作为目标话题
                    target_topics = [item["title"] for item in selected_items]
                    decision_result["actions"]["call_vcs"]["target_topics"] = target_topics
                    
                    # 提取关键风险关键词
                    search_keywords = []
                    for risk_item in selected_items:
                        # 使用风险项目的标题作为主要关键词
                        search_keywords.append(risk_item["title"])
                        # 从风险项目的理由中提取额外关键词
                        if 'reason' in risk_item:
                            # 从理由中提取核心关键词，提高相关性
                            reason_words = risk_item['reason'].split()
                            # 只保留长度大于2的词，避免无意义的助词
                            for word in reason_words:
                                if len(word) > 2:
                                    search_keywords.append(word)
                    # 去重并限制数量，确保质量
                    search_keywords = list(set(search_keywords))[:5]  # 最多5个核心关键词
                    decision_result["actions"]["call_vcs"]["search_keywords"] = search_keywords
                    
                    # 3. 调用VCS agent进行深入调研
                    crawler_result = self.command_media_crawler(decision_result)
                    
                    # 4. 分析VCS调研结果
                    if crawler_result.get("success", False):
                        crawler_analysis = self.analyze_crawler_results(crawler_result)
                        logger.info(f"VCS agent 深入调研分析结果: 风险等级-{crawler_analysis.get('risk_level', '未知')}, 总视频数-{crawler_analysis.get('stats', {}).get('total_videos', 0)} 条")
                    else:
                        logger.info(f"VCS调研失败: {crawler_result.get('reason', '未知原因')}")
                        crawler_analysis = None
                else:
                    logger.info("无法选择足够的话题，跳过深入调研")
                    crawler_result = {"success": False, "reason": "无法选择足够的话题，跳过深入调研"}
                    crawler_analysis = None
            else:
                logger.info("未发现风险话题，跳过深入调研")
                crawler_result = {"success": False, "reason": "未发现风险话题，跳过深入调研"}
                crawler_analysis = None
            
            # 5. 生成预警报告，降低预警生成条件
            alert_report = None
            try:
                # 尝试生成预警报告，即使没有VCS调研结果也生成
                alert_report = self.generate_risk_alert(hotspot_report, decision_result, crawler_analysis)
                logger.info(f"生成预警报告: 预警等级-{alert_report.get('alert_level', '普通')}, 风险等级-{alert_report.get('risk_level', '低')}")
            except Exception as e:
                # 如果生成失败，记录日志并生成基础预警
                logger.warning(f"生成完整预警报告失败: {str(e)}, 将生成基础预警")
                
                # 生成基础预警报告
                final_risk_level = decision_result.get("global_risk_level", "低")
                
                # 生成预警等级
                alert_level = "普通"
                if final_risk_level == "高":
                    alert_level = "紧急"
                elif final_risk_level == "中":
                    alert_level = "重要"
                
                # 收集热点分析的风险因素
                risk_factors = []
                for risk_item in decision_result.get("risk_items", []):
                    risk_factors.append(f"{risk_item['title']}: {risk_item['reason']} ({risk_item['level']})")
                
                # 获取具体话题信息
                target_topics = [item["title"] for item in selected_items]
                
                # 生成基础预警报告
                alert_report = {
                    "alert_id": f"RA-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    "timestamp": datetime.now().isoformat(),
                    "alert_level": alert_level,
                    "risk_level": final_risk_level,
                    "summary": decision_result.get("risk_summary", "未生成摘要"),
                    "target_topics": target_topics,
                    "risk_factors": risk_factors,
                    "source_info": {
                        "hotspot_report": {
                            "topic_count": len(hotspot_report.get("topics", [])),
                            "scan_summary": hotspot_report.get("summary", "")
                        }
                    },
                    "actions": decision_result.get("actions", {}),
                    "recommendations": self._generate_user_recommendations(final_risk_level, risk_factors, target_topics),
                    "details": {}
                }
                
                logger.info(f"生成基础预警报告: 预警等级-{alert_report.get('alert_level', '普通')}, 风险等级-{alert_report.get('risk_level', '低')}")
            
            logger.info("完整分析流程完成")
            
            # 确保返回结果包含status字段，表示分析成功
            decision_result["status"] = "success"
            
            # 将生成的alert_report添加到返回结果中
            decision_result["decision_result"] = decision_result
            if alert_report:
                decision_result["alert_report"] = alert_report
            
            # 返回完整的分析结果，包含decision_result和alert_report
            return decision_result
            
        except Exception as e:
            logger.error(f"完整分析流程执行失败: {str(e)}")
            error_result = {
                "risk_summary": f"分析失败: {str(e)}",
                "risk_items": [],
                "global_risk_level": "未知",
                "confidence": 0.0,
                "actions": {
                    "call_vcs": {
                        "should_call": False
                    },
                    "adjust_frequency": {
                        "should_adjust": False
                    },
                    "trigger_alert": {
                        "should_alert": True,
                        "alert_message": f"分析系统错误: {str(e)}"
                    }
                },
                "recommendations": []
            }
            print(f"\n[RiskAnalyzer] 完整分析流程失败: {str(e)}")
            return error_result


# 测试代码
if __name__ == "__main__":
    # 示例HotspotHunter报告
    sample_report = {
        "topics": [
            {
                "title": "某明星偷税漏税事件",
                "platform": "微博",
                "hot_value": 985200,
                "trend": "rising",
                "keywords": ["偷税漏税", "明星", "税务调查"],
                "summary": "网传某知名演员涉嫌偷税漏税，金额巨大，已引起税务部门关注。"
            },
            {
                "title": "新款手机发布",
                "platform": "知乎",
                "hot_value": 452100,
                "trend": "stable",
                "keywords": ["手机", "发布", "新品"],
                "summary": "某科技公司发布新款旗舰手机，性能强劲，价格亲民。"
            }
        ],
        "summary": "今日热点主要集中在娱乐和科技领域，其中某明星偷税漏税事件热度最高，值得关注。"
    }
    
    # 创建RiskAnalyzer实例并测试
    analyzer = RiskAnalyzer()
    result = analyzer.receive_hotspot_report(sample_report)
    
    print("\n分析结果:")
    print(json.dumps(result, ensure_ascii=False, indent=2))