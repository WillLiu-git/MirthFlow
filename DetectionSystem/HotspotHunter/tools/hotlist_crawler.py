# tools/hotspot_scraper.py

import requests
from bs4 import BeautifulSoup
import time
import pandas as pd
import json
import os
from datetime import datetime
import sys
from pathlib import Path

# 导入项目配置 - 支持相对和绝对导入
import sys
from pathlib import Path

# 添加项目根目录到Python路径
current_dir = Path(__file__).parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    # 尝试相对导入
    from ..utils.config import TOPHUB_URLS, REQUEST_HEADERS, TITLE_LINK_SELECTOR, HOTNESS_SELECTOR
except ImportError:
    # 回退到绝对导入
    from utils.config import TOPHUB_URLS, REQUEST_HEADERS, TITLE_LINK_SELECTOR, HOTNESS_SELECTOR


def hotlist_crawler(
        url: str,
        save_to_file: bool = False,
        output_dir: str = 'scraped_hot_lists_json',
        verbose: bool = True
) -> str | None:
    """
    爬取 Tophub 榜单数据，返回 JSON 字符串并可选择保存为文件。

    每条数据新增字段：
        scraped_at = 当前爬取时间
    """

    board_id = url.split('/')[-1]

    # 记录当前时间
    scraped_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 温和一点，减少被 Ban
    time.sleep(2)

    try:
        # 1. 获取网页内容
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
        response.raise_for_status()  # 检查请求是否成功

        # 2. 解析网页内容
        soup = BeautifulSoup(response.text, "html.parser")
        hot_topics_data = []

        # 查找所有热门话题条目
        items = soup.select("tr")

        # 打印爬取URL和ID（仅当verbose为True时）
        if verbose:
            print(f"[Tool] 开始爬取 URL: {url} (ID: {board_id})")

        # 跳过表头，从第2行开始
        for index, item in enumerate(items[1:], start=0):
            # 排名
            rank_cell = item.select_one("td:nth-child(1)")
            rank = rank_cell.get_text(strip=True).replace('.', '') if rank_cell else str(index + 1)

            # 标题 + 链接
            title_link_tag = item.select_one(TITLE_LINK_SELECTOR)
            if title_link_tag:
                title = title_link_tag.get_text(strip=True)
                link = title_link_tag.get("href")
            else:
                title = "N/A"
                link = "N/A"

            # 如果标题为空，尝试容错
            if title == "N/A":
                second_td = item.select_one("td:nth-child(2)")
                if second_td:
                    title = second_td.get_text(strip=True)

            # 热度
            hot_tag = item.select_one(HOTNESS_SELECTOR)
            hotness = hot_tag.get_text(strip=True) if hot_tag and hot_tag.text.strip() else "0"

            hot_topics_data.append({
                "rank": rank,
                "title": title,
                "hotness": hotness,
                "link": link,
                "source_url": url,
                "scraped_at": scraped_at   # 时间字段
            })

        # 4. 转为 JSON 字符串
        df = pd.DataFrame(hot_topics_data)
        json_result = df.to_json(orient="records", force_ascii=False)

        # 5. 保存文件
        if save_to_file:
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"tophub_{board_id}.json")

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(hot_topics_data, f, ensure_ascii=False, indent=4)

        # 仅当verbose为True时打印详细信息
        if verbose:
            print(f" [Tool] 提取成功，共 {len(hot_topics_data)} 条数据。")
            if save_to_file:
                print(f"[Tool] 数据已保存至: {output_path}")

        return json_result

    except requests.exceptions.RequestException as e:
        print(f"[Tool] 请求错误: {e}")
        return None


# --------------------------------------------------
if __name__ == "__main__":

    OUTPUT_DIR = "scraped_hot_lists_json"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 你要爬取的榜单（可自行扩展）
    urls = TOPHUB_URLS

    print(f"⭐ 本次将爬取 {len(urls)} 份榜单...\n")

    all_results = {}

    for url in urls:
        json_data = hotlist_crawler(
            url,
            save_to_file=True,  # 自动保存
            output_dir=OUTPUT_DIR
        )

        if json_data:
            board_id = url.split('/')[-1]
            all_results[board_id] = json_data

    print("\n🎉 全部爬取完成！")
    print("📊 已获取结果：", list(all_results.keys()))
