# test_run.py — 手动运行 Hotspot Hunter Agent 并打印预警结果

import os
import sys
import json
import time

# 让 Python 识别 HotspotHunter 这个包
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

from agent import HotspotHunterAgent
from llm import LLMClient


def main():
    print("🚀 正在初始化 Hotspot Hunter Agent...\n")

    # 先创建LLM客户端
    llm_client = LLMClient()
    
    # 使用LLM客户端实例化Agent
    agent = HotspotHunterAgent(llm_client=llm_client)

    print("👉 开始执行单次舆情检测...\n")

    # 跑一次完整流程（爬取 → LLM 分析 → 输出预警）
    result = agent.run_once()

    print("\n===== 📢 舆情预警结果 =====")
    print(result)
    print("=========================\n")


if __name__ == "__main__":
    main()
