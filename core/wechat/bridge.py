"""微信 ↔ 科吉 Agent 桥接路由

从微信接收消息 → 调用 CoreAgent 处理 → 回复发回微信
"""

import logging
import threading
import time
from typing import Optional

from nanobot.adapter import KejiAdapter
from core.wechat.ilink import ILinkClient, WeChatMessage

logger = logging.getLogger("keji.wechat.bridge")


class WeChatBridge:
    """微信桥接器：将微信消息路由到科吉 Agent"""

    def __init__(self, session_path: str = "data/wechat_session.json"):
        self.client = ILinkClient(session_path=session_path)
        self.adapter: Optional[KejiAdapter] = None
        self._conv_map: dict[str, str] = {}  # wechat_user_id → keji_conv_id

        # 注册回调
        self.client.set_on_message(self._handle_message)
        self.client.set_on_error(self._handle_error)

    # ──── 生命周期 ────

    def start(self):
        """启动微信桥接（登录 + 开始轮询消息）"""
        logger.info("Starting WeChat Bridge...")

        # 初始化 Agent
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.adapter = KejiAdapter()
        loop.close()
        logger.info("KejiAdapter initialized")

        # 登录
        if not self.client.login():
            logger.error("WeChat login failed")
            return False

        # 开始轮询消息
        self.client.start_polling()
        logger.info("WeChat Bridge started")
        return True

    def stop(self):
        """停止桥接"""
        self.client.stop_polling()
        logger.info("WeChat Bridge stopped")

    # ──── 消息处理 ────

    def _get_conv_id(self, wechat_user: str) -> str:
        """获取或创建科吉对话 ID"""
        if wechat_user not in self._conv_map:
            import uuid
            conv_id = f"wx_{uuid.uuid4().hex[:12]}"
            self._conv_map[wechat_user] = conv_id
            logger.info("New conversation for %s: %s", wechat_user, conv_id)
        return self._conv_map[wechat_user]

    def _handle_message(self, msg: WeChatMessage):
        """处理收到的微信消息"""
        if not self.adapter:
            return

        # 只处理文本消息
        text = msg.get_text()
        if not text:
            logger.debug("Skipping non-text message from %s", msg.from_user)
            return

        logger.info("WeChat << %s: %s", msg.from_user, text[:80])

        # 发送"正在输入"状态
        self.client.send_typing(msg.from_user)

        # 设置会话 ID，让科吉保持对话上下文
        conv_id = self._get_conv_id(msg.from_user)

        # 调用科吉 Agent 处理（非流式，微信不支持流式推送）
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            reply = loop.run_until_complete(self.adapter.chat(text, session_id=conv_id))
            loop.close()
        except Exception as e:
            logger.error("Agent chat error: %s", e)
            reply = f"抱歉，处理出错：{str(e)[:100]}"

        if not reply:
            reply = "抱歉，我没有理解你的意思。"

        # 发送回复到微信
        success = self.client.send_message(
            to_user=msg.from_user,
            text=reply,
            context_token=msg.context_token,
        )

        if success:
            logger.info("WeChat >> %s: %s", msg.from_user, reply[:80])
        else:
            logger.error("Failed to send reply to %s", msg.from_user)

    def _handle_error(self, error: str):
        """处理错误事件"""
        if error == "session_expired":
            logger.warning("Session expired, attempting re-login...")
            # 尝试自动重登
            if self.client.login():
                logger.info("Re-login success")
            else:
                logger.error("Re-login failed, please restart")
