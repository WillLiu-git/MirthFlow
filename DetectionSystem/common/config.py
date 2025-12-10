"""
Unified Configuration Management Module
Contains configuration information for all system components

安全说明：
- 所有API密钥必须通过环境变量配置
- 不要在代码中硬编码任何敏感信息
- 建议使用 .env 文件管理配置（不要提交到版本控制）
"""

import os
import sys
from typing import Optional, Dict, Any

# 尝试加载 python-dotenv 以支持 .env 文件
try:
    from dotenv import load_dotenv
    # 加载项目根目录下的 .env 文件
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env_path = os.path.join(project_root, '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"[Config] 已加载环境变量文件: {env_path}")
except ImportError:
    # python-dotenv 未安装，跳过
    pass

# Project root directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Output directory configuration
OUTPUT_DIRECTORY = os.path.join(BASE_DIR, "videoscommentsspotter", "output")

# 确保所有配置都从common/config.py统一管理，避免在其他文件中硬编码
# ===============================
# 统一配置说明
# ===============================
# 1. 所有Agent必须从common/config.py导入配置
# 2. 禁止在各个Agent的utils/config.py中硬编码配置
# 3. 所有API密钥必须通过环境变量或.env文件配置
# 4. 开发模式下可以使用占位符，但生产环境必须使用真实密钥
# 5. 定期更新配置，确保配置的一致性和安全性

# ===============================
# API密钥配置
# ===============================
# 用户请在此处填写API密钥
# ===============================

# HotspotHunter Agent API密钥配置
# 请将下方的 "your_api_key_here" 替换为您的实际API密钥
HOTSPOT_HUNTER_API_KEY = "your_api_key_here"
HOTSPOT_HUNTER_MODEL_NAME = "deepseek-ai/DeepSeek-V3"
HOTSPOT_HUNTER_BASE_URL = "https://api.siliconflow.cn/v1"
HOTSPOT_HUNTER_TIMEOUT = 1800

# RiskAnalyzer Agent API密钥配置
# 请将下方的 "your_api_key_here" 替换为您的实际API密钥
RISK_ANALYZER_API_KEY = "your_api_key_herep"
RISK_ANALYZER_MODEL_NAME = "deepseek-ai/DeepSeek-V3"
RISK_ANALYZER_BASE_URL = "https://api.siliconflow.cn/v1"
RISK_ANALYZER_TIMEOUT = 1800

# VideosCommentsSpotter Agent API密钥配置
# 请将下方的 "your_api_key_here" 替换为您的实际API密钥
VIDEOS_COMMENTS_SPOTTER_API_KEY = "your_api_key_here"
VIDEOS_COMMENTS_SPOTTER_MODEL_NAME = "Qwen/Qwen3-VL-235B-A22B-Thinking"
VIDEOS_COMMENTS_SPOTTER_BASE_URL = "https://api.siliconflow.cn/v1"
VIDEOS_COMMENTS_SPOTTER_TIMEOUT = 1800


# ===============================
# API密钥安全管理函数
# ===============================

def validate_api_key(api_key: str, agent_name: str) -> str:
    """
    验证API密钥是否已配置
    
    Args:
        api_key: API密钥字符串
        agent_name: Agent名称（用于错误提示）
        
    Returns:
        验证后的API密钥字符串
        
    Raises:
        ValueError: 如果API密钥未配置
    """
    api_key = api_key.strip()
    
    if not api_key or api_key == "your_api_key_here":
        error_msg = (
            f"\n{'='*60}\n"
            f"[安全错误] {agent_name} 的API密钥未配置！\n"
            f"请在 DetectionSystem/common/config.py 文件中直接填写API密钥\n"
            f"找到 {agent_name} 相关的配置项，将 'your_api_key_here' 替换为您的实际API密钥\n"
            f"{'='*60}\n"
        )
        print(error_msg)
        raise ValueError(f"{agent_name} API密钥未配置，请在config.py文件中直接填写")
    
    # 验证API密钥格式（基本检查）
    if len(api_key) < 10:
        print(f"[警告] {agent_name} API密钥长度异常（长度: {len(api_key)}），请检查配置")
    
    # 检查API密钥格式
    if not api_key.startswith("sk-"):
        print(f"[警告] {agent_name} API密钥格式可能不正确（通常以 'sk-' 开头）")
    
    return api_key


def mask_api_key(api_key: str, show_chars: int = 4) -> str:
    """
    脱敏API密钥，用于日志输出
    
    Args:
        api_key: 原始API密钥
        show_chars: 显示前N个字符
        
    Returns:
        脱敏后的API密钥字符串
    """
    if not api_key or len(api_key) <= show_chars:
        return "***"
    return api_key[:show_chars] + "*" * (len(api_key) - show_chars)


def validate_api_config(config: Dict[str, Any], agent_name: str) -> bool:
    """
    验证API配置是否完整
    
    Args:
        config: API配置字典
        agent_name: Agent名称
        
    Returns:
        是否验证通过
    """
    required_keys = ["api_key", "model_name", "base_url"]
    missing_keys = [key for key in required_keys if not config.get(key)]
    
    if missing_keys:
        print(f"[错误] {agent_name} 配置缺少必需项: {', '.join(missing_keys)}")
        return False
    
    return True


# ===============================
# Agent-Specific API Configurations
# ===============================
# 基于直接填写的API密钥创建配置字典

try:
    # Hotspot Hunter Agent API Configuration
    HOTSPOT_HUNTER_LLM_CONFIG = {
        "api_key": validate_api_key(HOTSPOT_HUNTER_API_KEY, "HotspotHunter"),
        "model_name": HOTSPOT_HUNTER_MODEL_NAME,
        "base_url": HOTSPOT_HUNTER_BASE_URL,
        "timeout": HOTSPOT_HUNTER_TIMEOUT
    }
    
    # Risk Analyzer Agent API Configuration
    RISK_ANALYZER_LLM_CONFIG = {
        "api_key": validate_api_key(RISK_ANALYZER_API_KEY, "RiskAnalyzer"),
        "model_name": RISK_ANALYZER_MODEL_NAME,
        "base_url": RISK_ANALYZER_BASE_URL,
        "timeout": RISK_ANALYZER_TIMEOUT
    }
    
    # Videos Comments Spotter Agent API Configuration
    VIDEOS_COMMENTS_SPOTTER_LLM_CONFIG = {
        "api_key": validate_api_key(VIDEOS_COMMENTS_SPOTTER_API_KEY, "VideosCommentsSpotter"),
        "model_name": VIDEOS_COMMENTS_SPOTTER_MODEL_NAME,
        "base_url": VIDEOS_COMMENTS_SPOTTER_BASE_URL,
        "timeout": VIDEOS_COMMENTS_SPOTTER_TIMEOUT
    }

    # 验证所有配置
    if not validate_api_config(HOTSPOT_HUNTER_LLM_CONFIG, "HotspotHunter"):
        sys.exit(1)
    if not validate_api_config(RISK_ANALYZER_LLM_CONFIG, "RiskAnalyzer"):
        sys.exit(1)
    if not validate_api_config(VIDEOS_COMMENTS_SPOTTER_LLM_CONFIG, "VideosCommentsSpotter"):
        sys.exit(1)

    # 在调试模式下，打印脱敏的配置信息
    if os.getenv("DEBUG_MODE", "0") == "1":
        print("[Config] API配置已加载（调试模式）")
        print(f"[Config] HotspotHunter API Key: {mask_api_key(HOTSPOT_HUNTER_LLM_CONFIG['api_key'])}")
        print(f"[Config] RiskAnalyzer API Key: {mask_api_key(RISK_ANALYZER_LLM_CONFIG['api_key'])}")
        print(f"[Config] VideosCommentsSpotter API Key: {mask_api_key(VIDEOS_COMMENTS_SPOTTER_LLM_CONFIG['api_key'])}")

except ValueError as e:
    # API密钥配置错误，打印详细说明
    print("\n" + "="*60)
    print("API密钥配置说明")
    print("="*60)
    print("1. 创建 .env 文件（推荐）")
    print("   在项目根目录创建 .env 文件，添加以下内容：")
    print("   HOTSPOT_HUNTER_API_KEY=your_api_key_here")
    print("   RISK_ANALYZER_API_KEY=your_api_key_here")
    print("   VIDEOS_COMMENTS_SPOTTER_API_KEY=your_api_key_here")
    print("\n2. 使用环境变量")
    print("   Windows: set HOTSPOT_HUNTER_API_KEY=your_api_key_here")
    print("   Linux/Mac: export HOTSPOT_HUNTER_API_KEY=your_api_key_here")
    print("\n3. 开发环境（仅测试）")
    print("   设置 ALLOW_PLACEHOLDER_API_KEYS=1 允许使用占位符")
    print("="*60 + "\n")
    raise

# ===============================
# Hotspot Hunter Agent Configuration
# ===============================
# Hotspot list URLs for crawling
TOPHUB_URLS = [
    # Douyin hot list
    "https://tophub.today/n/K7GdaMgdQy",
    # Weibo hot list
    "https://tophub.today/n/KqndgxeLl9",
    # Zhihu hot list
    "https://tophub.today/n/rx9oz6oXbq",
    # Toutiao hot list
    "https://tophub.today/n/x9ozB4KoXb"
]

# Request headers for crawler
REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Referer': 'https://tophub.today/'
}

# CSS selectors for crawler
CRAWLER_SELECTORS = {
    'title_link': 'td:nth-child(2) a',
    'hotness': 'td.ws'
}

# Hotspot Hunter specific configuration
HOTSPOT_HUNTER_CONFIG = {
    "schedule_interval": 3000,  # Scheduled crawling interval in seconds (default: 10 minutes)
    "platforms": ["dy"],  # Platforms to crawl, default: Douyin
    "max_hot_topics": 10,  # Maximum number of hot topics to crawl each time
    "hotness_threshold": 0.7,  # Hotness threshold for filtering topics
    "crawling_interval": 600,  # Crawling interval in seconds for HotspotHunter agent (10 minutes)
    "output_directory": os.path.join(BASE_DIR, "HotspotHunter", "resource", "scraped_hot_lists_json"),  # Output directory for HotspotHunter
}

# ===============================
# Crawler Configuration
# ===============================
CRAWLER_CONFIG = {
    "max_retries": 3,  # Maximum number of retries for failed requests
    "sleep_time_range": (2, 5),  # Range of sleep time between requests (seconds)
    "max_concurrency": 5,  # Maximum number of concurrent requests
    "default_platforms": ["dy"],  # Default platforms to crawl, only Douyin
    "crawler_max_notes_count": 15,  # Maximum number of notes to crawl per keyword
    "crawler_max_comments_count_single_notes": 30,  # Maximum number of comments to crawl per note
}

# ===============================
# Report Configuration
# ===============================
REPORT_CONFIG = {
    "max_report_length": 5000,  # Maximum length of generated reports
    "sentiment_threshold": 0.7,  # Threshold for sentiment analysis
    "risk_level_mapping": {
        "low": 1,
        "medium": 2,
        "high": 3,
        "extreme": 4
    }  # Mapping of risk levels to numerical values
}

# ===============================
# Risk Analyzer Configuration
# ===============================
RISK_ANALYZER_CONFIG = {
    "warning_threshold": 2,  # Risk level threshold for issuing warnings
    "multiple_investigation_threshold": 0.8,  # Confidence threshold for multiple investigations
    "max_investigations": 3,  # Maximum number of investigations for a single risk
    "investigation_interval": 3600,  # Interval between multiple investigations (seconds, default: 1 hour)
    "decision_factors": [  # Decision factors with weights
        {"name": "risk_level", "weight": 0.4},
        {"name": "hotness", "weight": 0.3},
        {"name": "confidence_score", "weight": 0.2},
        {"name": "comment_count", "weight": 0.1}
    ]
}

# ===============================
# Log Configuration
# ===============================
LOG_CONFIG = {
    "log_level": "INFO",  # Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
    "log_file": os.path.join(BASE_DIR, "videoscommentsspotter", "videos_comments_spotter.log"),  # Log file path
    "log_rotation": "10 MB",  # Log file size limit before rotation
    "log_retention": "7 days",  # Log retention period
}

# ===============================
# Communication Configuration
# ===============================
COMMUNICATION_CONFIG = {
    "protocol": "http",  # Communication protocol
    "host": "localhost",  # Communication host
    "port": 8000,  # Communication port
    "timeout": 300,  # Communication timeout in seconds
}

# ===============================
# Cache Configuration
# ===============================
CACHE_CONFIG = {
    "type": "local",  # Cache type: local | redis
    "redis_url": "redis://localhost:6379/0",  # Redis connection URL
    "cache_expiry": 3600,  # Cache expiry time in seconds
}
