import os

# ===============================
# LLM 客户端配置
# ===============================
# 支持统一配置 API KEY、模型名和基础URL

LLM_CONFIG = {
    "api_key": "your api key",  # <<-- 直接赋值密钥
    "model_name": "deepseek-ai/DeepSeek-V3",  # <<-- 直接赋值模型名称
    "base_url": "https://api.siliconflow.cn/v1",
    "timeout": float(os.getenv("LLM_TIMEOUT", 1800.0)),
}

# ===============================
# 日志配置（可选）
# ===============================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "hotspot_hunter.log")