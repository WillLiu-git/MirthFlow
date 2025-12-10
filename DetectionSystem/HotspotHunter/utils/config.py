import os
import sys

# ===============================
# Import Configuration from Common Config
# ===============================
# This file imports all configuration from the central common/config.py
# to achieve unified configuration management across all agents.

# Add the project root to path to enable common config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    # Import all configurations from common config
    from common.config import (
        # API Configuration
        HOTSPOT_HUNTER_LLM_CONFIG,
        
        # Hotspot Hunter Configuration
        TOPHUB_URLS,
        REQUEST_HEADERS,
        CRAWLER_SELECTORS,
        HOTSPOT_HUNTER_CONFIG,
        
        # Output Directory
        OUTPUT_DIRECTORY as COMMON_OUTPUT_DIR
    )
    
    # Set LLM_CONFIG to agent-specific config
    LLM_CONFIG = HOTSPOT_HUNTER_LLM_CONFIG
    
    # Extract Hotspot Hunter specific configurations
    HOTSPOT_HUNTER_INTERVAL = HOTSPOT_HUNTER_CONFIG.get("crawling_interval", 30)
    OUTPUT_DIRECTORY = HOTSPOT_HUNTER_CONFIG.get("output_directory", 
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'resource', 'scraped_hot_lists_json'))
    
    # Extract CSS selectors for crawler
    TITLE_LINK_SELECTOR = CRAWLER_SELECTORS.get('title_link', 'td:nth-child(2) a')
    HOTNESS_SELECTOR = CRAWLER_SELECTORS.get('hotness', 'td.ws')
    
    # Log configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "hotspot_hunter.log")
    
except ImportError as e:
    print(f"[ERROR] Failed to import common config: {e}")
    print("[ERROR] 无法加载统一配置，系统无法正常运行")
    print("[ERROR] 请检查 DetectionSystem/common/config.py 文件是否存在且可访问")
    raise ImportError(f"无法导入统一配置: {e}") from e
