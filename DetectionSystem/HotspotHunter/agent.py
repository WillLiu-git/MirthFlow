# HotspotHunter/agent.py

import time
import json
from pathlib import Path
from typing import List, Dict, Any
import sys
import os

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
                    # 只加载最近 100 条记忆
                    return json.load(f)[-100:]
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
        
        print(f"[HotspotHunter] 成功写入 {len(valid_topics)} 条有效风险数据到情报站")

    def _analyze_hotspot(self, scraped_data_json: str) -> Dict[str, Any]:
        """调用 LLM 对爬取数据进行分析，返回完整的结构化风险报告。"""
        # 增强的系统提示，明确要求严格的JSON格式
        system_prompt = "你是一个舆情风险侦察兵，请严格按照指定的JSON格式输出结果。确保输出是有效的JSON对象，包含完整的'summary'和'items'字段，不包含任何额外的文本、标记或解释。"

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
                temperature=0.2  # 进一步降低温度，确保严格按照格式输出
            )
            
            print(f"[HotspotHunter] LLM响应原始内容: {risk_json_str[:100]}...")
            
            # 尝试直接解析
            parsed_result = json.loads(risk_json_str)
            
            # 验证结果结构是否完整
            if isinstance(parsed_result, dict) and 'summary' in parsed_result and 'items' in parsed_result:
                print(f"[HotspotHunter] 成功解析完整的风险报告，包含 {len(parsed_result.get('items', []))} 个风险项目")
                return parsed_result
            else:
                print(f"[HotspotHunter] 解析结果结构不完整: {parsed_result}")
                
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
            
        except json.JSONDecodeError as e:
            print(f"[HotspotHunter] LLM 分析失败 (JSON解析错误): {e}")
            print(f"[HotspotHunter] 原始响应: {risk_json_str}")
            
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
                print("[HotspotHunter] JSON修复成功")
                return result
            except Exception as fix_e:
                print(f"[HotspotHunter] JSON修复失败: {fix_e}")
        except Exception as e:
            print(f"[HotspotHunter] LLM 分析失败 (其他错误): {e}")
        
        # 最终失败时返回一个默认的完整风险报告结构
        return {
            "summary": "分析失败，但系统强制生成默认报告",
            "items": [
                {
                    "topic": "系统分析失败",
                    "platform": "未知",
                    "hotness": "0",
                    "risk_level": 1,
                    "category": "系统错误",
                    "reason": "LLM分析过程中遇到问题，但根据要求必须返回报告",
                    "further_investigate": True
                }
            ]
        }

    def run_once(self) -> Dict[str, Any]:
        """执行一次完整的侦察任务：爬取 -> 分析 -> 写入情报站。"""
        all_reports = []  # 收集所有风险报告
        all_risk_items = []  # 收集所有风险项目
        
        for url in TOPHUB_URLS:
            # 1. 爬取
            scraped_json = hotlist_crawler(url, save_to_file=True, output_dir=OUTPUT_DIRECTORY)

            if scraped_json:
                # 2. 分析 - 现在返回完整的风险报告字典
                risk_report = self._analyze_hotspot(scraped_json)

                if risk_report and isinstance(risk_report, dict):
                    # 获取报告中的风险项目列表
                    risk_items = risk_report.get('items', [])
                    
                    # 3. 上报情报 (生产者行为) - 只上报items列表
                    if risk_items:
                        self._append_to_intelligence(risk_items)
                        print(f"[HotspotHunter] 🎯 发现 {len(risk_items)} 个潜在风险，已写入情报站。")
                        all_risk_items.extend(risk_items)
                    else:
                        print(f"[HotspotHunter] {url} 未发现明显风险项目。")
                    
                    # 保存完整报告
                    all_reports.append(risk_report)
                else:
                    print(f"[HotspotHunter] {url} 分析失败，未生成风险报告。")

                # 4. 更新 memory (存储原始爬取数据)
                try:
                    data = json.loads(scraped_json)
                    self.memory.extend(data)
                except:
                    continue

        self._save_memory()
        
        # 生成综合报告作为舆情预警结果
        if all_reports:
            # 合并所有报告的摘要
            combined_summary = "\n".join([report.get('summary', '') for report in all_reports if report.get('summary')])
            
            # 构建综合报告
            comprehensive_report = {
                "summary": f"综合舆情分析: {combined_summary}",
                "items": all_risk_items,
                "report_count": len(all_reports),
                "total_risk_items": len(all_risk_items)
            }
            return comprehensive_report
        else:
            # 如果没有报告，返回默认报告
            return {
                "summary": "未获取到有效的风险报告，但根据要求必须返回",
                "items": [],
                "report_count": 0,
                "total_risk_items": 0
            }

    def run_loop(self):
        """持续侦察循环。"""
        print(f"🕵️‍♂️ Hotspot Hunter 侦察兵已就位，初始频率: {self.interval}s/次")
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