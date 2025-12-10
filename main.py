#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
舆情监测系统主启动文件

这是舆情监测系统的入口点，负责：
1. 初始化和管理所有系统组件
2. 协调组件之间的交互
3. 提供配置管理和日志记录
4. 实现系统的启动、停止和监控功能
"""

import os
import sys
import json
import time
import logging
import threading
import signal
from pathlib import Path
from typing import Dict, Any, List, Optional

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# --- 导入系统组件 --- 
# 定义组件可用性标志
HOTSPOT_HUNTER_AVAILABLE = False
RISK_ANALYZER_AVAILABLE = False
VIDEOS_COMMENTS_SPOTTER_AVAILABLE = False

# 定义全局配置默认值
# 使用相对于当前文件的路径，确保输出在项目内部
BASE_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
INTELLIGENCE_FILE = os.path.join(BASE_OUTPUT_DIR, "intelligence_feed.json")
OUTPUT_DIRECTORY = BASE_OUTPUT_DIR
HOTSPOT_HUNTER_INTERVAL = 300

# 先添加DetectionSystem到sys.path，确保组件能正确导入
DETECTION_SYSTEM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DetectionSystem")
sys.path.insert(0, DETECTION_SYSTEM_DIR)

# 导入HotspotHunter组件
try:
    from HotspotHunter.agent import HotspotHunterAgent
    from HotspotHunter.llm.llm import LLMClient as HH_LLMClient
    HOTSPOT_HUNTER_AVAILABLE = True
except ImportError as e:
    HOTSPOT_HUNTER_AVAILABLE = False

# 导入RiskAnalyzer组件
try:
    from RiskAnalyzer.agent import RiskAnalyzer
    from RiskAnalyzer.llm.llm import LLMClient as RA_LLMClient
    RISK_ANALYZER_AVAILABLE = True
except ImportError as e:
    RISK_ANALYZER_AVAILABLE = False

# 导入VideosCommentsSpotter组件
try:
    from VideosCommentsSpotter.agent import VideosCommentsSpotterAgent
    from VideosCommentsSpotter.llm.llm import LLMClient as VCS_LLMClient
    VIDEOS_COMMENTS_SPOTTER_AVAILABLE = True
except ImportError as e:
    VIDEOS_COMMENTS_SPOTTER_AVAILABLE = False

# 导入配置常量
try:
    from HotspotHunter.utils.config import OUTPUT_DIRECTORY, HOTSPOT_HUNTER_INTERVAL
except ImportError as e:
    pass

# 模拟模板加载函数（替代不存在的prompt模块）
def load_template(template_name, **kwargs):
    """模板加载函数模拟实现"""
    return f"[模板: {template_name}]" + " ".join([f"{k}={v}" for k, v in kwargs.items()])


# --- 全局配置管理 --- 
class GlobalConfig:
    """
    系统全局配置管理类
    """
    def __init__(self):
        # 系统配置
        self.system_name = "舆情监测系统 - MirthFlow"
        self.version = "1.0.0"
        
        # 基础路径
        self.base_dir = Path(__file__).parent
        
        # 组件路径
        self.detection_system_dir = self.base_dir / "DetectionSystem"
        
        # 配置文件路径
        self.config_file = self.base_dir / "config.json"
        
        # 文件路径配置
        # 为每个组件创建resource文件夹，保存各自的输出文件
        self.hotspot_hunter_resource_dir = self.detection_system_dir / "HotspotHunter" / "resource"
        self.risk_analyzer_resource_dir = self.detection_system_dir / "RiskAnalyzer" / "resource"
        self.vcs_agent_resource_dir = self.detection_system_dir / "VideosCommentsSpotter" / "resource"
        
        # 输出文件保存在各自的resource文件夹里
        self.output_dir = self.base_dir / "output"  # 保留全局输出目录
        self.intelligence_file = self.hotspot_hunter_resource_dir / "intelligence_feed.json"
        self.alerts_file = self.risk_analyzer_resource_dir / "system_alerts.json"
        
        # 日志配置
        self.log_dir = self.base_dir / "logs"
        self.system_log_file = self.log_dir / "system.log"
        self.error_log_file = self.log_dir / "error.log"
        
        # 组件日志保存在各自组件目录下的resource文件夹里
        self.hotspot_hunter_log_dir = self.hotspot_hunter_resource_dir
        self.risk_analyzer_log_dir = self.risk_analyzer_resource_dir
        self.vcs_agent_log_dir = self.vcs_agent_resource_dir
        
        # 运行模式配置
        self.debug_mode = os.environ.get("DEBUG_MODE", "0") == "1"
        self.run_interval = 60  # 主循环间隔（秒）
        
        # 组件配置
        self.hotspot_hunter_interval = HOTSPOT_HUNTER_INTERVAL or 300  # 热点检测间隔
        self.risk_analyzer_interval = 300  # 默认5分钟
        self.vcs_interval = 1200  # 默认20分钟
        self.max_concurrent_tasks = 3  # 最大并发任务数
        
        # 组件状态
        self.enable_hotspot_hunter = True
        self.enable_risk_analyzer = True
        self.enable_vcs_agent = True
        
        # 日志配置选项
        self.log_level = "DEBUG" if self.debug_mode else "INFO"
        self.log_rotation = "daily"
        self.log_max_bytes = 10*1024*1024  # 10MB
        self.log_backup_count = 7
        
        # 分析配置
        self.max_intelligence_items = 500
        self.alert_retention_days = 30
        
        # 加载配置文件
        self._load_config()
        
        # 确保目录存在
        self._ensure_directories()
        
        # 注释掉自动保存默认配置，避免在根目录创建不必要的文件
        # self._save_default_config()
    
    def _load_config(self):
        """
        从配置文件加载配置
        """
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                
                # 读取配置项
                if "run_interval" in config:
                    self.run_interval = config["run_interval"]
                
                if "hotspot_hunter_interval" in config:
                    self.hotspot_hunter_interval = config["hotspot_hunter_interval"]
                
                if "risk_analyzer_interval" in config:
                    self.risk_analyzer_interval = config["risk_analyzer_interval"]
                
                if "vcs_interval" in config:
                    self.vcs_interval = config["vcs_interval"]
                
                if "components" in config:
                    self.enable_hotspot_hunter = config["components"].get("enable_hotspot_hunter", True)
                    self.enable_risk_analyzer = config["components"].get("enable_risk_analyzer", True)
                    self.enable_vcs_agent = config["components"].get("enable_vcs_agent", True)
                
                if "logging" in config:
                    self.log_level = config["logging"].get("level", "DEBUG" if self.debug_mode else "INFO")
                    self.log_rotation = config["logging"].get("rotation", "daily")
                    self.log_max_bytes = config["logging"].get("max_bytes", 10*1024*1024)
                    self.log_backup_count = config["logging"].get("backup_count", 7)
                
                if "analysis" in config:
                    self.max_intelligence_items = config["analysis"].get("max_intelligence_items", 500)
                    self.alert_retention_days = config["analysis"].get("alert_retention_days", 30)
            except json.JSONDecodeError as e:
                # 配置文件解析错误记录到日志，不影响启动
                pass
            except Exception as e:
                # 配置文件加载错误记录到日志，不影响启动
                pass
    
    def _save_default_config(self):
        """
        保存默认配置到文件（如果不存在）
        """
        if not self.config_file.exists():
            try:
                default_config = {
                    "run_interval": self.run_interval,
                    "hotspot_hunter_interval": self.hotspot_hunter_interval,
                    "risk_analyzer_interval": self.risk_analyzer_interval,
                    "vcs_interval": self.vcs_interval,
                    "components": {
                        "enable_hotspot_hunter": self.enable_hotspot_hunter,
                        "enable_risk_analyzer": self.enable_risk_analyzer,
                        "enable_vcs_agent": self.enable_vcs_agent
                    },
                    "logging": {
                        "level": self.log_level,
                        "rotation": self.log_rotation,
                        "max_bytes": self.log_max_bytes,
                        "backup_count": self.log_backup_count
                    },
                    "analysis": {
                        "max_intelligence_items": self.max_intelligence_items,
                        "alert_retention_days": self.alert_retention_days
                    }
                }
                
                with open(self.config_file, "w", encoding="utf-8") as f:
                    json.dump(default_config, f, ensure_ascii=False, indent=2)
            except Exception as e:
                # 配置文件保存错误静默处理
                pass
    
    def _ensure_directories(self):
        """
        确保必要的目录存在
        """
        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 确保日志目录存在
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 确保各个组件的resource目录存在
        self.hotspot_hunter_resource_dir.mkdir(parents=True, exist_ok=True)
        self.risk_analyzer_resource_dir.mkdir(parents=True, exist_ok=True)
        self.vcs_agent_resource_dir.mkdir(parents=True, exist_ok=True)
        
        # 确保情报站目录存在
        self.intelligence_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 确保alerts文件目录存在
        self.alerts_file.parent.mkdir(parents=True, exist_ok=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """将配置转换为字典"""
        return {
            "system_name": self.system_name,
            "version": self.version,
            "debug_mode": self.debug_mode,
            "run_interval": self.run_interval,
            "hotspot_hunter_interval": self.hotspot_hunter_interval,
            "risk_analyzer_interval": self.risk_analyzer_interval,
            "vcs_interval": self.vcs_interval,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "output_dir": str(self.output_dir),
            "intelligence_file": str(self.intelligence_file),
            "alerts_file": str(self.alerts_file),
            "system_log_file": str(self.system_log_file),
            "log_level": self.log_level,
            "config_file": str(self.config_file)
        }


# --- 日志系统配置 --- 
def setup_logging(config: GlobalConfig):
    """
    设置系统日志
    """
    import logging.handlers
    
    # 创建主日志器
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, config.log_level))
    
    # 清除现有处理器
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 创建格式化器 - 详细日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 添加控制台处理器，显示INFO及以上级别的日志
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 创建文件处理器 - 系统日志
    if config.log_rotation == "daily":
        system_file_handler = logging.handlers.TimedRotatingFileHandler(
            config.system_log_file,
            when="midnight",
            interval=1,
            backupCount=config.log_backup_count,
            encoding="utf-8"
        )
    else:
        system_file_handler = logging.handlers.RotatingFileHandler(
            config.system_log_file,
            maxBytes=config.log_max_bytes,
            backupCount=config.log_backup_count,
            encoding="utf-8"
        )
    
    system_file_handler.setLevel(getattr(logging, config.log_level))
    system_file_handler.setFormatter(formatter)
    logger.addHandler(system_file_handler)
    
    # 创建错误日志处理器
    error_file_handler = logging.handlers.RotatingFileHandler(
        config.error_log_file,
        maxBytes=config.log_max_bytes,
        backupCount=config.log_backup_count,
        encoding="utf-8"
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(formatter)
    logger.addHandler(error_file_handler)
    
    # 设置各个组件的logger
    for component in ["HotspotHunter", "RiskAnalyzer", "VideosCommentsSpotter", "SystemManager"]:
        component_logger = get_component_logger(component, config)
        component_logger.setLevel(getattr(logging, config.log_level))
    
    # 控制第三方库日志级别
    third_party_loggers = ["httpx", "urllib3", "requests"]
    for logger_name in third_party_loggers:
        third_party_logger = logging.getLogger(logger_name)
        third_party_logger.setLevel(logging.WARNING)  # 只显示警告和错误信息
    
    main_logger = logging.getLogger("SystemManager")
    main_logger.info("日志系统已初始化")
    main_logger.info(f"日志级别: {config.log_level}")
    main_logger.info(f"系统日志: {config.system_log_file}")
    main_logger.info(f"错误日志: {config.error_log_file}")
    
    return main_logger

def get_component_logger(component_name, config):
    """
    获取组件专用日志器
    """
    import logging.handlers
    import os
    
    # 根据组件名称选择对应的日志目录
    if component_name == "HotspotHunter":
        component_log_dir = config.hotspot_hunter_resource_dir
    elif component_name == "RiskAnalyzer":
        component_log_dir = config.risk_analyzer_resource_dir
    elif component_name == "VideosCommentsSpotter":
        component_log_dir = config.vcs_agent_resource_dir
    else:
        # 默认使用系统日志目录
        component_log_dir = config.log_dir
    
    # 确保日志目录存在
    os.makedirs(component_log_dir, exist_ok=True)
    
    # 创建组件日志文件
    component_log_file = component_log_dir / f"{component_name}.log"
    
    # 创建组件日志器
    logger = logging.getLogger(component_name)
    logger.setLevel(getattr(logging, config.log_level))
    
    # 清除现有处理器
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 创建格式化器
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 创建组件日志处理器
    component_file_handler = logging.handlers.RotatingFileHandler(
        component_log_file,
        maxBytes=config.log_max_bytes,
        backupCount=config.log_backup_count,
        encoding="utf-8"
    )
    
    component_file_handler.setLevel(getattr(logging, config.log_level))
    component_file_handler.setFormatter(formatter)
    logger.addHandler(component_file_handler)
    
    return logger


# --- 系统管理器 --- 
class SystemManager:
    """
    系统管理器，负责协调各个组件的工作
    """
    def __init__(self):
        self.config = GlobalConfig()
        self.logger = setup_logging(self.config)
        self.running = False
        self.threads = []
        # 系统状态文件路径
        self.state_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.system_state')
        
        # 组件实例
        self.hotspot_hunter: Optional[HotspotHunterAgent] = None
        self.risk_analyzer: Optional[RiskAnalyzer] = None
        self.vcs_agent: Optional[VideosCommentsSpotterAgent] = None
        
        # 系统状态
        self.status = {
            "started_at": None,
            "uptime": 0,
            "components": {
                "hotspot_hunter": {"status": "stopped", "last_scan": None},
                "risk_analyzer": {"status": "stopped", "last_analysis": None},
                "vcs_agent": {"status": "stopped", "last_task": None}
            },
            "metrics": {
                "total_scans": 0,
                "total_analyses": 0,
                "total_alerts": 0
            }
        }
    
    def is_paused(self):
        """检查系统是否被暂停"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    state = f.read().strip()
                    return state == 'paused'
            except:
                return False
        return False
    
    def wait_if_paused(self):
        """如果系统被暂停，等待直到恢复"""
        while self.is_paused() and self.running:
            time.sleep(1)  # 每秒检查一次
    
    def initialize_components(self):
        """
        初始化所有系统组件
        """
        try:
            # 初始化配置目录
            self.config.output_dir.mkdir(parents=True, exist_ok=True)
            self.config.log_dir.mkdir(parents=True, exist_ok=True)
            
            # 确保各个组件的resource目录存在
            self.config.hotspot_hunter_resource_dir.mkdir(parents=True, exist_ok=True)
            self.config.risk_analyzer_resource_dir.mkdir(parents=True, exist_ok=True)
            self.config.vcs_agent_resource_dir.mkdir(parents=True, exist_ok=True)
            
            # 初始化HotspotHunter组件
            hotspot_hunter_status = "stopped"
            if self.config.enable_hotspot_hunter and HOTSPOT_HUNTER_AVAILABLE:
                try:
                    # 导入HotspotHunter的LLM配置
                    from DetectionSystem.common.config import HOTSPOT_HUNTER_LLM_CONFIG
                    # 创建LLM客户端（使用正确配置）
                    hh_llm_client = HH_LLMClient(
                        api_key=HOTSPOT_HUNTER_LLM_CONFIG["api_key"],
                        model_name=HOTSPOT_HUNTER_LLM_CONFIG["model_name"],
                        base_url=HOTSPOT_HUNTER_LLM_CONFIG["base_url"]
                    )
                    self.hotspot_hunter = HotspotHunterAgent(
                        llm_client=hh_llm_client,
                        crawl_interval=self.config.hotspot_hunter_interval
                    )
                    hotspot_hunter_status = "running"
                    self.status["components"]["hotspot_hunter"]["status"] = "running"
                except Exception as e:
                    self.logger.error(f"初始化HotspotHunter组件失败: {str(e)}")
                    hotspot_hunter_status = "error"
                    self.status["components"]["hotspot_hunter"]["status"] = "error"
            elif not HOTSPOT_HUNTER_AVAILABLE:
                hotspot_hunter_status = "disabled"
                self.status["components"]["hotspot_hunter"]["status"] = "disabled"
            else:
                hotspot_hunter_status = "disabled"
                self.status["components"]["hotspot_hunter"]["status"] = "disabled"
            
            # 初始化RiskAnalyzer组件
            risk_analyzer_status = "stopped"
            self.risk_analyzer = None
            if self.config.enable_risk_analyzer:
                if RISK_ANALYZER_AVAILABLE:
                    try:
                        # RiskAnalyzer会自己创建LLM客户端
                        self.risk_analyzer = RiskAnalyzer()
                        risk_analyzer_status = "running"
                        self.status["components"]["risk_analyzer"]["status"] = "running"
                    except Exception as e:
                        self.logger.error(f"初始化RiskAnalyzer组件失败: {str(e)}")
                        risk_analyzer_status = "error"
                        self.status["components"]["risk_analyzer"]["status"] = "error"
                        self.risk_analyzer = None
                        return False
                else:
                    self.logger.error("RiskAnalyzer组件不可用，无法启动系统")
                    risk_analyzer_status = "disabled"
                    self.status["components"]["risk_analyzer"]["status"] = "disabled"
            else:
                risk_analyzer_status = "disabled"
                self.status["components"]["risk_analyzer"]["status"] = "disabled"
            
            # 初始化VideosCommentsSpotter组件
            vcs_agent_status = "stopped"
            self.vcs_agent = None
            if self.config.enable_vcs_agent and VIDEOS_COMMENTS_SPOTTER_AVAILABLE:
                try:
                    # 导入VideosCommentsSpotter的LLM配置
                    from DetectionSystem.common.config import VIDEOS_COMMENTS_SPOTTER_LLM_CONFIG
                    # 创建LLM客户端（使用正确配置）
                    vcs_llm_client = VCS_LLMClient(
                        api_key=VIDEOS_COMMENTS_SPOTTER_LLM_CONFIG["api_key"],
                        model_name=VIDEOS_COMMENTS_SPOTTER_LLM_CONFIG["model_name"],
                        base_url=VIDEOS_COMMENTS_SPOTTER_LLM_CONFIG["base_url"]
                    )
                    self.vcs_agent = VideosCommentsSpotterAgent(llm_client=vcs_llm_client)
                    vcs_agent_status = "running"
                    self.status["components"]["vcs_agent"]["status"] = "running"
                except Exception as e:
                    self.logger.error(f"初始化VideosCommentsSpotter组件失败: {str(e)}")
                    vcs_agent_status = "error"
                    self.status["components"]["vcs_agent"]["status"] = "error"
            elif not VIDEOS_COMMENTS_SPOTTER_AVAILABLE:
                vcs_agent_status = "disabled"
                self.status["components"]["vcs_agent"]["status"] = "disabled"
            else:
                vcs_agent_status = "disabled"
                self.status["components"]["vcs_agent"]["status"] = "disabled"
            
            # 只显示三个agent的启动信息
            print(f" [HotspotHunter Agent] 状态: {hotspot_hunter_status}")
            print(f" [RiskAnalyzer Agent] 状态: {risk_analyzer_status}")
            print(f" [VideosCommentsSpotter Agent] 状态: {vcs_agent_status}")
            
            self.logger.info("所有组件初始化完成")
            return True
            
        except Exception as e:
            self.logger.error(f"系统组件初始化过程中发生未知错误: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def start_hotspot_hunter(self):
        """
        启动HotspotHunter线程
        """
        def hotspot_hunter_loop():
            self.logger.info("HotspotHunter开始运行")
            self.status["components"]["hotspot_hunter"]["status"] = "running"
            
            try:
                while self.running:
                    # 检查是否暂停
                    self.wait_if_paused()
                    if not self.running:
                        break
                    
                    start_time = time.time()
                    self.logger.info(f"HotspotHunter开始扫描...")
                    
                    try:
                        # 执行实际的热点扫描
                        # 分析热点数据并写入情报站
                        # 调用HotspotHunter的主方法
                        # 注意：这里根据实际的HotspotHunter实现调用适当的方法
                        # 假设HotspotHunterAgent有一个run方法
                        # 初始化热点报告
                        hotspot_report = {
                            "scan_id": f"HH-{int(time.time())}",
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "summary": "未发现有效风险项目",
                            "topics": [],
                            "overall_sentiment": {"negative": 0.7, "neutral": 0.2, "positive": 0.1},
                            "risk_signals": []
                        }
                        
                        # 调用run_once方法执行单次爬取和分析
                        if hasattr(self.hotspot_hunter, 'run_once'):
                            result = self.hotspot_hunter.run_once()
                            
                            # 过滤掉系统分析失败的项目
                            valid_items = []
                            # HotspotHunter的run_once方法返回topics字段，不是items字段
                            for item in result.get('topics', result.get('items', [])):
                                # 检查item的结构，处理不同的字段名
                                topic_title = item.get('topic', item.get('title', ''))
                                if topic_title != '系统分析失败':
                                    valid_items.append(item)
                            
                            # 更新热点报告
                            hotspot_report["summary"] = result.get('summary', '无摘要')
                            hotspot_report["topics"] = valid_items
                            hotspot_report["risk_signals"] = ["新发现的风险话题"] if valid_items else []
                        else:
                            # 如果没有明确的运行方法，执行基本的爬取和分析
                            from DetectionSystem.HotspotHunter.tools.hotlist_crawler import hotlist_crawler
                            from DetectionSystem.HotspotHunter.utils.config import TOPHUB_URLS
                            
                            self.logger.info("开始爬取热点列表...")
                            # 爬取热点列表 - 循环处理每个URL
                            all_scraped_data = []
                            if isinstance(TOPHUB_URLS, list):
                                for url in TOPHUB_URLS:
                                    try:
                                        scraped_data = hotlist_crawler(url)
                                        if scraped_data:
                                            all_scraped_data.append(scraped_data)
                                            self.logger.info(f"成功爬取 {url}")
                                    except Exception as e:
                                        self.logger.error(f"爬取URL失败 {url}: {str(e)}")
                            else:
                                # 如果TOPHUB_URLS是单个URL
                                scraped_data = hotlist_crawler(TOPHUB_URLS)
                                if scraped_data:
                                    all_scraped_data.append(scraped_data)
                                    self.logger.info(f"成功爬取 {TOPHUB_URLS}")
                            
                            # 分析收集到的所有数据
                            all_valid_items = []
                            if all_scraped_data and hasattr(self.hotspot_hunter, '_analyze_hotspot'):
                                self.logger.info("开始分析热点数据...")
                                # 这里简化处理，实际可能需要更复杂的数据合并逻辑
                                for i, data in enumerate(all_scraped_data):
                                    try:
                                        scraped_data_json = json.dumps(data, ensure_ascii=False)
                                        self.logger.info(f"分析第 {i+1}/{len(all_scraped_data)} 批数据...")
                                        risk_report = self.hotspot_hunter._analyze_hotspot(scraped_data_json)
                                        self.logger.info(f"分析完成，摘要: {risk_report.get('summary', '无摘要')}")
                                        risk_count = len(risk_report.get('items', []))
                                        self.logger.info(f"发现风险项目: {risk_count}")
                                        # 写入情报站
                                        if 'risk_items' in risk_report and hasattr(self.hotspot_hunter, '_append_to_intelligence'):
                                            self.hotspot_hunter._append_to_intelligence(risk_report['risk_items'])
                                            self.logger.info(f"成功写入 {len(risk_report['risk_items'])} 条风险数据到情报站")
                                            all_valid_items.extend(risk_report['risk_items'])
                                            # 只在发现风险时输出到终端
                                            if risk_report['risk_items']:
                                                print(f"[HotspotHunter] 发现 {len(risk_report['risk_items'])} 个风险项目")
                                    except Exception as e:
                                        self.logger.error(f"分析热点数据失败: {str(e)}")
                            
                            # 更新热点报告
                            hotspot_report["summary"] = f"分析了 {len(all_scraped_data)} 个数据源"
                            hotspot_report["topics"] = all_valid_items
                            hotspot_report["risk_signals"] = ["新发现的风险话题"] if all_valid_items else []
                        
                        # 更新状态
                        self.status["components"]["hotspot_hunter"]["last_scan"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        self.status["metrics"]["total_scans"] += 1
                        risk_count = len(hotspot_report.get("topics", []))
                        self.logger.info(f"HotspotHunter扫描完成，发现 {risk_count} 个风险项目")
                        
                        # 只在发现风险时输出到终端
                        if risk_count > 0:
                            print(f"[HotspotHunter] 扫描完成，发现 {risk_count} 个风险项目")
                        
                        # 无论是否有风险项目，都将热点报告传递给RiskAnalyzer进行分析
                        if self.risk_analyzer and self.config.enable_risk_analyzer:
                            try:
                                self.analyze_hotspot_report(hotspot_report)
                            except Exception as e:
                                self.logger.error(f"调用RiskAnalyzer失败: {e}")
                                import traceback
                                traceback.print_exc()
                        else:
                            self.logger.info("RiskAnalyzer不可用或未启用，跳过分析")
                        
                    except Exception as e:
                        self.logger.error(f"HotspotHunter扫描失败: {str(e)}")
                        print(f"[HotspotHunter] 扫描失败: {str(e)}")
                        import traceback
                        traceback.print_exc()
                    
                    # 等待下一次扫描（检查暂停状态）
                    elapsed = time.time() - start_time
                    wait_time = max(0, self.config.hotspot_hunter_interval - elapsed)
                    self.logger.info(f"休眠 {wait_time:.1f}秒，准备下次扫描...")
                    # 分段等待，以便及时响应暂停信号
                    for _ in range(int(wait_time)):
                        if not self.running or self.is_paused():
                            break
                        time.sleep(1)
                    if wait_time > int(wait_time):
                        time.sleep(wait_time - int(wait_time))
                    
            except Exception as e:
                self.logger.error(f"HotspotHunter线程异常: {str(e)}")
                import traceback
                traceback.print_exc()
            finally:
                self.status["components"]["hotspot_hunter"]["status"] = "stopped"
                self.logger.info("HotspotHunter已停止")
        
        thread = threading.Thread(target=hotspot_hunter_loop, daemon=True)
        thread.start()
        self.threads.append(thread)
    
    def start_risk_analyzer(self):
        """
        启动RiskAnalyzer线程
        """
        def risk_analyzer_loop():
            self.logger.info("RiskAnalyzer开始运行")
            self.status["components"]["risk_analyzer"]["status"] = "running"
            
            # 记录已处理的情报ID
            processed_ids = set()
            
            try:
                while self.running:
                    # 检查是否暂停
                    self.wait_if_paused()
                    if not self.running:
                        break
                    
                    start_time = time.time()
                    
                    # 检查情报文件是否存在
                    if self.config.intelligence_file.exists():
                        try:
                            # 读取情报数据
                            with open(self.config.intelligence_file, "r", encoding="utf-8") as f:
                                intelligence_data = json.load(f)
                            
                            if intelligence_data and isinstance(intelligence_data, list):
                                self.logger.info(f"RiskAnalyzer正在分析 {len(intelligence_data)} 条情报")
                                
                                # 处理未处理的情报
                                new_intelligence = []
                                for item in intelligence_data:
                                    # 生成唯一ID（如果没有）
                                    item_id = item.get("id", f"{item.get('timestamp', '')}-{hash(str(item))}")
                                    if item_id not in processed_ids:
                                        new_intelligence.append(item)
                                        processed_ids.add(item_id)
                                
                                # 限制已处理ID的数量
                                if len(processed_ids) > 500:
                                    # 保留最新的500个
                                    processed_ids = set(list(processed_ids)[-500:])
                                
                                # 处理新情报
                                for risk_item in new_intelligence:
                                    try:
                                        self.logger.info(f"处理新情报项: {risk_item.get('title', '未知标题')}")
                                        
                                        # 构建HotspotHunter报告格式
                                        hotspot_report = {
                                            "scan_id": f"HH-{int(time.time())}",
                                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                            "summary": "新发现的风险话题",
                                            "topics": [risk_item] if isinstance(risk_item, dict) else [],
                                            "overall_sentiment": {"negative": 0.7, "neutral": 0.2, "positive": 0.1},
                                            "risk_signals": ["新发现的风险话题"]
                                        }
                                        
                                        # 调用RiskAnalyzer的完整分析流程
                                        if hasattr(self.risk_analyzer, 'run_full_analysis_flow'):
                                            self.logger.info(f"开始分析情报项: {risk_item.get('title', '未知标题')}")
                                            analysis_result = self.risk_analyzer.run_full_analysis_flow(hotspot_report)
                                            
                                            self.logger.info(f"分析结果状态: {analysis_result.get('status', '失败')}")
                                            
                                            # 检查是否需要调用VideosCommentsSpotter
                                            if analysis_result.get("status") == "success":
                                                # 每次成功分析都增加计数
                                                self.status["metrics"]["total_analyses"] += 1
                                                
                                                # 记录决策结果到日志
                                                decision_result = analysis_result.get("decision_result", {})
                                                global_risk_level = decision_result.get('global_risk_level', '未知')
                                                risk_summary = decision_result.get('risk_summary', '无摘要')
                                                self.logger.info(f"全局风险等级: {global_risk_level}, 风险摘要: {risk_summary}")
                                                
                                                # 记录风险项目到日志
                                                risk_items = decision_result.get("risk_items", [])
                                                if risk_items:
                                                    self.logger.info(f"发现风险项目 ({len(risk_items)}):")
                                                    for i, item in enumerate(risk_items):
                                                        self.logger.info(f"  {i+1}. {item.get('title', '未知')} - {item.get('level', '未知')}风险: {item.get('reason', '无')}")
                                                
                                                # 获取预警报告
                                                alert_report = analysis_result.get("alert_report", {})
                                                alert_level = alert_report.get('alert_level', '未知')
                                                risk_level = alert_report.get('risk_level', '未知')
                                                alert_id = alert_report.get('alert_id', '未知')
                                                
                                                self.logger.info(f"生成预警报告: ID={alert_id}, 预警等级={alert_level}, 风险等级={risk_level}")
                                                self.logger.info(f"预警摘要: {alert_report.get('summary', '无摘要')}")
                                                
                                                # 记录风险因素到日志
                                                risk_factors = alert_report.get("risk_factors", [])
                                                if risk_factors:
                                                    self.logger.info(f"风险因素 ({len(risk_factors)}): {', '.join(risk_factors[:5])}")
                                                
                                                # 记录建议到日志
                                                recommendations = alert_report.get("recommendations", [])
                                                if recommendations:
                                                    self.logger.info(f"建议: {', '.join(recommendations)}")
                                                
                                                # 如果决策要求调用VCS且需要深入调研
                                                if alert_report.get("alert_level") in ["紧急", "重要"]:
                                                    # 调用VideosCommentsSpotter进行深入调研
                                                    self.logger.info("调用VideosCommentsSpotter进行深入调研")
                                                    self._call_videos_comments_spotter(risk_item, alert_report)
                                                
                                                # 保存预警报告
                                                self._save_alert(alert_report)
                                                self.status["metrics"]["total_alerts"] += 1
                                                
                                                # 只在生成预警时输出到终端
                                                print(f"[RiskAnalyzer] 生成预警: {alert_level} | 风险等级: {risk_level} | {alert_report.get('summary', '无摘要')[:50]}")
                                                self.logger.info(f"预警已保存: {alert_id}")
                                            else:
                                                error_msg = analysis_result.get('error', '未知错误')
                                                self.logger.error(f"分析失败: {error_msg}")
                                                print(f"[RiskAnalyzer] 分析失败: {error_msg}")
                                    except Exception as e:
                                        self.logger.error(f"处理情报项失败: {str(e)}")
                                        import traceback
                                        traceback.print_exc()
                                
                        except json.JSONDecodeError as e:
                            self.logger.error(f"解析情报文件失败: {str(e)}")
                        except Exception as e:
                            self.logger.error(f"RiskAnalyzer分析失败: {str(e)}")
                            import traceback
                            traceback.print_exc()
                    
                    # 更新运行时间
                    self.status["uptime"] = int(time.time() - self.start_time)
                    
                    # 等待下一次检查（检查暂停状态）
                    elapsed = time.time() - start_time
                    wait_time = max(0, self.config.run_interval - elapsed)
                    # 分段等待，以便及时响应暂停信号
                    for _ in range(int(wait_time)):
                        if not self.running or self.is_paused():
                            break
                        time.sleep(1)
                    if wait_time > int(wait_time):
                        time.sleep(wait_time - int(wait_time))
                    
            except Exception as e:
                self.logger.error(f"RiskAnalyzer线程异常: {str(e)}")
                import traceback
                traceback.print_exc()
            finally:
                self.status["components"]["risk_analyzer"]["status"] = "stopped"
                self.logger.info("RiskAnalyzer已停止")
        
        thread = threading.Thread(target=risk_analyzer_loop, daemon=True)
        thread.start()
        self.threads.append(thread)
    
    def start_videos_comments_spotter(self):
        """
        启动VideosCommentsSpotter线程
        """
        def videos_comments_spotter_loop():
            self.logger.info("VideosCommentsSpotter开始运行")
            self.status["components"]["vcs_agent"]["status"] = "running"
            
            try:
                while self.running:
                    # 检查是否暂停
                    self.wait_if_paused()
                    if not self.running:
                        break
                    
                    # VideosCommentsSpotter主要是被动调用，不需要主动轮询
                    # 这里保持线程运行，等待被调用
                    time.sleep(5)  # 每5秒检查一次运行状态
                    
            except Exception as e:
                self.logger.error(f"VideosCommentsSpotter线程异常: {str(e)}")
                import traceback
                traceback.print_exc()
            finally:
                self.status["components"]["vcs_agent"]["status"] = "stopped"
                self.logger.info("VideosCommentsSpotter已停止")
        
        thread = threading.Thread(target=videos_comments_spotter_loop, daemon=True)
        thread.start()
        self.threads.append(thread)
        
    def _call_videos_comments_spotter(self, risk_topic: Dict[str, Any], alert_report: Dict[str, Any]):
        """
        调用VideosCommentsSpotter进行深入调研
        """
        try:
            if not self.vcs_agent:
                self.logger.warning("VideosCommentsSpotter组件未初始化")
                return
            
            topic_title = risk_topic.get('title', '未知话题')
            self.logger.info(f"开始深入调研: {topic_title}")
            
            # 调用VCS生成关键词
            self.logger.info("生成关键词...")
            keywords_result = self.vcs_agent.generate_keywords(risk_topic)
            
            self.logger.info(f"关键词生成结果: {json.dumps(keywords_result, ensure_ascii=False)}")
            
            # 使用生成的关键词进行爬取和分析
            if keywords_result and 'keywords' in keywords_result:
                keywords = keywords_result['keywords']
                self.logger.info(f"使用关键词 {', '.join(keywords[:5])}... 进行分析")
                
                # 使用VCS agent的process_topic方法处理风险话题
                vcs_result = self.vcs_agent.process_topic(risk_topic)
            else:
                # 如果没有生成关键词，直接处理话题
                vcs_result = self.vcs_agent.process_topic(risk_topic)
            
            status = '成功' if vcs_result.get('status') == 'success' else '失败'
            self.logger.info(f"调研结果状态: {status}")
            
            # 更新风险分析结果
            if vcs_result.get('status') == 'success':
                # 记录详细分析结果到日志
                if 'key_findings' in vcs_result:
                    key_findings = vcs_result['key_findings']
                    self.logger.info(f"关键发现项: {len(key_findings)}")
                    for i, finding in enumerate(key_findings):
                        self.logger.info(f"  {i+1}. {finding}")
                
                # 记录风险评估到日志
                if 'risk_assessment' in vcs_result:
                    risk_assessment = vcs_result['risk_assessment']
                    self.logger.info(f"风险评估: 等级={risk_assessment.get('level', '未知')}, 因素={', '.join(risk_assessment.get('factors', []))}")
                
                # 记录统计信息到日志
                if 'data_statistics' in vcs_result:
                    stats = vcs_result['data_statistics']
                    self.logger.info(f"统计信息: 平台={stats.get('total_platforms', 0)}, 关键词={stats.get('total_keywords', 0)}, 内容={stats.get('total_items', 0)}, 评论={stats.get('total_comments', 0)}")
                
                # 记录总结到日志
                if 'summary' in vcs_result:
                    self.logger.info(f"总结: {vcs_result['summary']}")
                
                # 记录建议到日志
                if 'recommendations' in vcs_result:
                    recommendations = vcs_result['recommendations']
                    self.logger.info(f"建议: {', '.join(recommendations)}")
                
                findings_count = len(vcs_result.get('key_findings', []))
                self.logger.info(f"VideosCommentsSpotter调研完成，发现: {findings_count} 个关键发现")
                
                # 只在成功时输出简要信息到终端
                print(f"[VideosCommentsSpotter] 调研完成: 发现 {findings_count} 个关键发现")
                
                # 更新状态
                self.status["components"]["vcs_agent"]["last_task"] = time.strftime("%Y-%m-%d %H:%M:%S")
            else:
                print(f"[VideosCommentsSpotter] 调研失败")
                        
        except Exception as e:
            self.logger.error(f"调用VideosCommentsSpotter失败: {str(e)}")
            print(f"[VideosCommentsSpotter] 调用失败: {str(e)}")
    
    def analyze_hotspot_report(self, hotspot_report: Dict[str, Any]):
        """
        分析热点报告，调用RiskAnalyzer进行完整分析流程
        RiskAnalyzer负责：
        1. 分析热点报告并生成决策结果
        2. 调用VideosCommentsSpotter进行深入调研
        3. 整合VCS调研结果生成最终预警
        
        Args:
            hotspot_report: HotspotHunter生成的热点报告
        """
        self.logger.info(f"开始分析热点报告: {hotspot_report.get('scan_id', '未知ID')}")
        
        try:
            if hasattr(self.risk_analyzer, 'run_full_analysis_flow'):
                # 调用RiskAnalyzer的完整分析流程，包括VCS调研和预警生成
                analysis_result = self.risk_analyzer.run_full_analysis_flow(hotspot_report)
                
                # 检查分析结果
                if analysis_result.get("status") == "success":
                    # 更新分析计数
                    self.status["metrics"]["total_analyses"] += 1
                    
                    # 获取预警报告
                    alert_report = analysis_result.get("alert_report")
                    if alert_report:
                        # 保存预警报告
                        self._save_alert(alert_report)
                        self.status["metrics"]["total_alerts"] += 1
                        
                        # 打印预警报告信息
                        self.logger.info(f"生成预警: {alert_report.get('alert_id', '未知ID')}, 等级: {alert_report.get('alert_level', '未知')}")
                        self.logger.info(f"预警摘要: {alert_report.get('summary', '无摘要')}")
                        self.logger.info(f"针对话题: {', '.join(alert_report.get('target_topics', []))[:100]}...")
            else:
                self.logger.error("RiskAnalyzer没有run_full_analysis_flow方法")
        except Exception as e:
            self.logger.error(f"分析热点报告失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def _save_alert(self, alert_report: Dict[str, Any]):
        """
        保存预警报告到文件
        """
        try:
            # 读取现有预警
            existing_alerts = []
            if self.config.alerts_file.exists():
                with open(self.config.alerts_file, "r", encoding="utf-8") as f:
                    try:
                        existing_alerts = json.load(f)
                        if not isinstance(existing_alerts, list):
                            existing_alerts = []
                    except json.JSONDecodeError:
                        existing_alerts = []
            
            # 添加新预警
            existing_alerts.append(alert_report)
            
            # 限制文件大小，只保留最近100条预警
            if len(existing_alerts) > 100:
                existing_alerts = existing_alerts[-100:]
            
            # 保存预警文件
            with open(self.config.alerts_file, "w", encoding="utf-8") as f:
                json.dump(existing_alerts, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            self.logger.error(f"保存预警报告失败: {str(e)}")
    
    def start(self):
        """
        启动整个系统
        """
        try:
            # 显示系统启动信息
            print("\n" + "="*60)
            print(" 舆情监测系统启动成功")
            print("="*60)
            
            self.logger.info(f"启动{self.config.system_name} v{self.config.version}")
            self.logger.info(f"配置: {json.dumps(self.config.to_dict(), ensure_ascii=False, indent=2)}")
            
            # 初始化组件
            if not self.initialize_components():
                self.logger.error("组件初始化失败，无法启动系统")
                print("[错误] 组件初始化失败，无法启动系统")
                return False
            
            # 设置运行状态
            self.running = True
            self.start_time = time.time()
            self.status["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            
            # 启动各个组件的线程
            agent_status = []
            
            # 启动HotspotHunter线程
            if self.hotspot_hunter:
                self.start_hotspot_hunter()
                agent_status.append("HotspotHunter")
                self.logger.info("HotspotHunter线程启动成功")
            
            # 启动RiskAnalyzer线程
            if self.risk_analyzer:
                self.start_risk_analyzer()
                agent_status.append("RiskAnalyzer")
                self.logger.info("RiskAnalyzer线程启动成功")
            
            # 启动VideosCommentsSpotter线程
            if self.vcs_agent:
                self.start_videos_comments_spotter()
                agent_status.append("VideosCommentsSpotter")
                self.logger.info("VideosCommentsSpotter线程启动成功")
            
            # 显示已启动的组件
            if agent_status:
                print(f"已启动组件: {', '.join(agent_status)}")
            print("="*60 + "\n")
            
            # 主循环，保持系统运行
            try:
                # 记录上次输出系统状态的时间
                last_status_time = time.time()
                
                while self.running:
                    # 检查是否暂停
                    self.wait_if_paused()
                    if not self.running:
                        break
                    
                    # 定期打印系统状态（每10分钟一次）
                    current_time = time.time()
                    if current_time - last_status_time >= 600:  # 600秒 = 10分钟
                        self._log_system_status()
                        last_status_time = current_time
                    
                    # 分段等待，以便及时响应暂停信号
                    for _ in range(60):
                        if not self.running or self.is_paused():
                            break
                        time.sleep(1)
                    
            except KeyboardInterrupt:
                self.logger.info("接收到中断信号，正在停止系统...")
                print("\n[系统] 接收到中断信号，正在停止系统...")
            finally:
                self.stop()
                
            return True
            
        except Exception as e:
            self.logger.error(f"系统启动失败: {str(e)}")
            print(f"\n[系统] 系统启动失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def stop(self):
        """
        停止整个系统
        """
        try:
            self.logger.info("正在停止系统...")
            
            # 设置运行状态为False
            self.running = False
            
            # 等待所有线程结束
            for thread in self.threads:
                if thread.is_alive():
                    thread.join(timeout=5.0)  # 等待最多5秒
            
            # 更新状态
            for component in self.status["components"]:
                self.status["components"][component]["status"] = "stopped"
            
            self.logger.info("系统已停止")
            
        except Exception as e:
            self.logger.error(f"停止系统时出错: {str(e)}")
    
    def _log_system_status(self):
        """
        记录系统状态
        """
        # 直接计算当前运行时长
        current_time = time.time()
        uptime_seconds = int(current_time - self.start_time)
        uptime_hours = uptime_seconds // 3600
        uptime_mins = (uptime_seconds % 3600) // 60
        uptime_str = f"{uptime_hours}时{uptime_mins}分" if uptime_hours > 0 else f"{uptime_mins}分"
        
        # 更新status中的uptime
        self.status['uptime'] = uptime_seconds
        
        # 只输出简洁的系统状态
        status_str = f"[系统状态] 运行时长: {uptime_str} | 扫描: {self.status['metrics']['total_scans']} | 分析: {self.status['metrics']['total_analyses']} | 预警: {self.status['metrics']['total_alerts']}"
        # 使用print输出到终端，让用户看到关键状态信息
        print(status_str)
        # 同时记录到日志文件
        self.logger.info(status_str)


# --- 信号处理 --- 
def handle_signal(signum, frame):
    """
    处理系统信号
    """
    global system_manager
    if system_manager and system_manager.running:
        system_manager.logger.info(f"接收到信号 {signum}，正在优雅关闭系统...")
        system_manager.stop()
        sys.exit(0)


# --- 主函数 --- 
def main():
    """
    主函数
    """
    global system_manager
    
    # 创建系统管理器实例
    system_manager = SystemManager()
    
    # 设置信号处理
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    # 启动系统
    return system_manager.start()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)