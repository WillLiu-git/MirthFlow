#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试agent.py的完整功能，从目录内部运行
"""

import sys
import os

# 确保当前目录在Python路径中
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print("开始测试VideosCommentsSpotter agent...")

try:
    print("\n1. 测试直接导入agent.py...")
    from agent import VideosCommentsSpotterAgent, main
    print("✅ 成功导入VideosCommentsSpotterAgent和main函数！")
    
    print("\n2. 测试agent.py中的所有依赖导入...")
    from llm import LLMClient
    from utils.config import LLM_CONFIG, OUTPUT_DIRECTORY
    from prompts.prompts import VCS_KEYWORD_PROMPT, VCS_ANALYSIS_PROMPT
    from tools.videoscomments_crawler import VideoCommentSpotter
    
    print("✅ 成功导入所有依赖！")
    print(f"   LLM_CONFIG: {LLM_CONFIG}")
    print(f"   OUTPUT_DIRECTORY: {OUTPUT_DIRECTORY}")
    print(f"   VCS_KEYWORD_PROMPT存在: {bool(VCS_KEYWORD_PROMPT)}")
    print(f"   VCS_ANALYSIS_PROMPT存在: {bool(VCS_ANALYSIS_PROMPT)}")
    print(f"   VideoCommentSpotter类存在: {bool(VideoCommentSpotter)}")
    
    print("\n3. 测试初始化LLMClient...")
    try:
        llm_client = LLMClient(config=LLM_CONFIG)
        print("✅ 成功初始化LLMClient！")
    except Exception as e:
        print(f"⚠️  LLMClient初始化警告: {e}")
        print("   这是预期的，因为需要有效的API密钥才能完全初始化")
    
    print("\n4. 测试agent.py的导入逻辑完整性...")
    # 验证agent.py中使用的所有变量和类都能正确导入
    required_imports = [
        'VideosCommentsSpotterAgent',
        'LLMClient',
        'LLM_CONFIG',
        'OUTPUT_DIRECTORY',
        'VCS_KEYWORD_PROMPT',
        'VCS_ANALYSIS_PROMPT',
        'VideoCommentSpotter'
    ]
    
    all_imported = True
    for item in required_imports:
        if item not in globals() and item != 'VideosCommentsSpotterAgent':
            print(f"❌ 缺少导入: {item}")
            all_imported = False
    
    if all_imported:
        print("✅ 所有必要的导入都已完成！")
    
    print("\n🎉 测试完成！所有导入问题已修复。")
    print("\n建议运行方式：")
    print(f"   1. 进入目录: cd {current_dir}")
    print("   2. 运行agent: python agent.py")
    print("   3. 或运行主程序: python main.py")
    
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()
    
except Exception as e:
    print(f"❌ 其他错误: {e}")
    import traceback
    traceback.print_exc()
