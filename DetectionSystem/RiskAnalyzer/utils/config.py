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
    # Import configurations from common config
    from common.config import (
        # Agent-specific API Configuration
        RISK_ANALYZER_LLM_CONFIG,
        
        # Risk Analyzer Configuration
        RISK_ANALYZER_CONFIG
    )
    
    # Use agent-specific LLM config
    LLM_CONFIG = RISK_ANALYZER_LLM_CONFIG
    
    # Log configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "risk_analyzer.log")
    
except ImportError as e:
    print(f"[ERROR] Failed to import common config: {e}")
    print("[ERROR] 无法加载统一配置，系统无法正常运行")
    print("[ERROR] 请检查 DetectionSystem/common/config.py 文件是否存在且可访问")
    raise ImportError(f"无法导入统一配置: {e}") from e