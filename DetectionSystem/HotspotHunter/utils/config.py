
import os

# ===============================
# 热搜榜 URL 列表（稳定有效）
# ===============================
TOPHUB_URLS = [
    # 抖音热搜榜
    "https://tophub.today/n/K7GdaMgdQy",
    # 微博热搜榜
    "https://tophub.today/n/KqndgxeLl9",
    # 知乎热榜
    "https://tophub.today/n/rx9oz6oXbq",
    #今日头条热榜
    "https://tophub.today/n/x9ozB4KoXb"
]

# ===============================
# 爬虫请求配置
# ===============================
REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Referer': 'https://tophub.today/'
}

# 爬虫 CSS 选择器
TITLE_LINK_SELECTOR = 'td:nth-child(2) a'
HOTNESS_SELECTOR = 'td.ws'

# 爬取结果 JSON 文件保存路径
OUTPUT_DIRECTORY = 'scraped_hot_lists_json'

# ===============================
# 热点监控 Agent 配置
# ===============================
# 爬取间隔（秒）
HOTSPOT_HUNTER_INTERVAL = 30

# ===============================
# LLM 客户端配置
# ===============================
# 支持统一配置 API KEY、模型名和基础 URL
LLM_CONFIG = {
    "api_key": os.getenv("LLM_API_KEY", "your-api-key-here"),
    "model_name": os.getenv("LLM_MODEL", "gpt-4"),
    "base_url": os.getenv("LLM_BASE_URL", None),  # 可选，支持 Gemini 或其他
    "timeout": float(os.getenv("LLM_TIMEOUT", 1800.0)),  # 请求超时时间
}

# ===============================
# 日志配置（可选）
# ===============================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "hotspot_hunter.log")
