# hotspot_scraper_test.py —— 一体化测试版
# ✔ 无外部依赖项
# ✔ 支持多个榜单
# ✔ 自动保存 JSON 文件
# ✔ 自动带 scraped_at 时间戳

import requests
from bs4 import BeautifulSoup
import time
import pandas as pd
import json
import os
from datetime import datetime

# --------------------------------------------------
# 全局请求 headers（模拟常规浏览器）
# --------------------------------------------------
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# CSS 选择器 —— 针对 TopHub 通用榜单
TITLE_LINK_SELECTOR = "td:nth-child(2) a"
HOTNESS_SELECTOR = "td:nth-child(3)"


# --------------------------------------------------
# 核心爬虫函数
# --------------------------------------------------
def scrape_tophub_hot_list(url: str, save_to_file: bool = False,
                           output_dir: str = 'scraped_hot_lists_json') -> str | None:
    """
    爬取单个 Tophub 榜单并返回 JSON 字符串
    """
    board_id = url.split('/')[-1]
    print(f"\n🚀 [Scraper] 开始爬取 {board_id} ...")

    scraped_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    time.sleep(2)  # 防止访问过快被 Ban

    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        rows = soup.select("table.table tbody tr")

        if not rows:
            print("⚠️ 未解析到榜单数据！")
            return None

        items = []

        for idx, row in enumerate(rows):
            # 排名
            rank_tag = row.select_one("td:nth-child(1)")
            rank = rank_tag.text.strip().replace('.', '') if rank_tag else str(idx + 1)

            # 标题 + 链接
            title_tag = row.select_one(TITLE_LINK_SELECTOR)
            if title_tag:
                title = title_tag.text.strip()
                link = title_tag.get("href")
            else:
                title = "N/A"
                link = "N/A"

            # 热度
            hot_tag = row.select_one(HOTNESS_SELECTOR)
            hotness = hot_tag.text.strip() if hot_tag and hot_tag.text.strip() else "0"

            items.append({
                "rank": rank,
                "title": title,
                "hotness": hotness,
                "link": link,
                "source_url": url,
                "scraped_at": scraped_at
            })

        print(f"✔ [Scraper] {board_id} 提取成功：{len(items)} 条数据")

        # 生成 JSON 字符串
        df = pd.DataFrame(items)
        json_str = df.to_json(orient="records", force_ascii=False)

        # 是否写入文件
        if save_to_file:
            os.makedirs(output_dir, exist_ok=True)
            filepath = os.path.join(output_dir, f"tophub_{board_id}.json")

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=4)

            print(f"📁 文件已保存到: {filepath}")

        return json_str

    except Exception as e:
        print(f"❌ [Scraper] 请求失败: {e}")
        return None


# --------------------------------------------------
# 主程序：自动爬取多个榜单
# --------------------------------------------------
if __name__ == "__main__":

    OUTPUT_DIR = "scraped_hot_lists_json"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 你要爬取的榜单（可自行扩展）
    urls = [
        "https://tophub.today/n/K7GdaMgdQy",  # 抖音
        "https://tophub.today/n/KqndgxeLl9",  # 微博
        "https://tophub.today/n/rx9oz6oXbq",  # 知乎
    ]

    print(f"⭐ 本次将爬取 {len(urls)} 份榜单...\n")

    all_results = {}

    for url in urls:
        json_data = scrape_tophub_hot_list(
            url,
            save_to_file=True,  # 自动保存
            output_dir=OUTPUT_DIR
        )

        if json_data:
            board_id = url.split('/')[-1]
            all_results[board_id] = json_data

    print("\n🎉 全部爬取完成！")
    print("📊 已获取结果：", list(all_results.keys()))
