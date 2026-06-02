#!/usr/bin/env python3
"""科吉 × 微信 Bot — 桥接启动器

用法:
    python wechat_bridge.py            # 正常启动
    python wechat_bridge.py --reset    # 清除登录状态，重新扫码

流程:
    1. 加载/创建科吉 Agent
    2. 微信扫码登录（iLink Bot API）
    3. 开始轮询微信消息 → 调用科吉 → 回复
"""

import sys
import os
import logging
import argparse
import time

# 确保项目根目录在 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 解决 Windows 编码问题
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from core.wechat.bridge import WeChatBridge
from core.logger import setup_logger


def main():
    parser = argparse.ArgumentParser(description="科吉 × 微信 Bot 桥接")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="清除登录状态，重新扫码",
    )
    parser.add_argument(
        "--session",
        default="data/wechat_session.json",
        help="微信会话文件路径（默认 data/wechat_session.json）",
    )
    args = parser.parse_args()

    # 设置日志
    setup_logger("keji", level="INFO", log_file="logs/wechat.log")

    # 清除登录状态
    if args.reset:
        session_path = os.path.join(
            os.path.dirname(__file__), args.session
        )
        if os.path.exists(session_path):
            os.unlink(session_path)
            print("✅ 登录状态已清除")
        return

    print("=" * 50)
    print("  科吉 × 微信 Bot")
    print("  企业级 AI 助手 · 微信版")
    print("=" * 50)
    print()

    bridge = WeChatBridge(session_path=args.session)

    try:
        if bridge.start():
            print("\n✅ 科吉微信 Bot 已启动！")
            print("  现在可以去微信发消息了。")
            print("  按 Ctrl+C 停止服务\n")

            # 保持主线程运行
            while True:
                time.sleep(1)
        else:
            print("\n❌ 启动失败，请检查日志")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n正在停止...")
    finally:
        bridge.stop()
        print("科吉微信 Bot 已停止")


if __name__ == "__main__":
    main()
