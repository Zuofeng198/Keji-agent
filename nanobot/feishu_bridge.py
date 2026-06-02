"""飞书(Lark) ↔ KejiAdapter 桥接层

将飞书渠道收到的消息路由到 KejiAdapter 的 chat/chat_stream，
并把回复通过 FeishuChannel 的 CardKit 流式推送发回手机端。

设计原则：
- 不侵入 KejiAdapter 现有逻辑，Web 聊天不受影响
- 利用 FeishuChannel 已有的 WebSocket 长连接、消息解析、媒体下载
- 流式输出复用 chat_stream() 的 SSE 事件流，翻译为 CardKit 打字机效果
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus

if TYPE_CHECKING:
    from nanobot.adapter import KejiAdapter


class FeishuBridge:
    """将飞书消息路由到 KejiAdapter 并返回回复"""

    def __init__(self, adapter: KejiAdapter) -> None:
        self.adapter = adapter
        self.bus = MessageBus()
        self.channel: Any = None  # FeishuChannel 实例
        self._running = False
        self._feishu_task: asyncio.Task | None = None
        self._inbound_task: asyncio.Task | None = None
        # 每个 session 的串行锁，防止同一会话的并发写冲突
        self._session_locks: dict[str, asyncio.Lock] = {}

    async def start(self) -> None:
        """启动飞书桥接：从 Keji 配置读取飞书渠道配置并启动"""
        feishu_cfg = self.adapter.config.get("channels", {}).get("feishu", {})
        if not feishu_cfg.get("enabled"):
            logger.info("飞书渠道未启用（channels.feishu.enabled = false），跳过")
            return

        from nanobot.channels.feishu import FeishuChannel

        # 验证必要字段
        app_id = feishu_cfg.get("app_id", "")
        app_secret = feishu_cfg.get("app_secret", "")
        if not app_id or not app_secret:
            logger.error(
                "飞书渠道配置不完整：缺少 app_id 或 app_secret。"
                "请在 config.yaml 的 channels.feishu 中填写。"
            )
            return

        self._running = True

        # 创建 FeishuChannel，传入自主创建的 bus
        self.channel = FeishuChannel(feishu_cfg, self.bus)

        # 启动飞书 WebSocket 长连接（后台任务，会一直运行）
        self._feishu_task = asyncio.create_task(self.channel.start())

        # 启动入站消息轮询
        self._inbound_task = asyncio.create_task(self._inbound_loop())

        logger.info("✅ 飞书桥接层已启动，等待 WebSocket 连接...")

    async def stop(self) -> None:
        """停止飞书桥接"""
        self._running = False
        if self.channel:
            await self.channel.stop()
        for task in (self._feishu_task, self._inbound_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        logger.info("飞书桥接层已停止")

    async def _inbound_loop(self) -> None:
        """轮询 MessageBus，收到飞书消息后异步处理"""
        while self._running:
            try:
                msg = await asyncio.wait_for(
                    self.bus.consume_inbound(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            if msg.channel != "feishu":
                continue

            # 每个消息独立处理，不阻塞轮询
            asyncio.create_task(self._process_message(msg))

    async def _process_message(self, msg: InboundMessage) -> None:
        """处理一条飞书消息"""
        chat_id = msg.chat_id
        sid = msg.session_key
        content = msg.content or ""
        message_id = msg.metadata.get("message_id", "") if msg.metadata else ""

        # 加 session 锁，避免同一会话多条消息并发写历史
        lock = self._session_locks.setdefault(sid, asyncio.Lock())
        async with lock:
            try:
                await self._handle_with_stream(chat_id, sid, content, message_id, msg.media)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.exception("处理飞书消息失败 (chat_id={}): {}", chat_id, e)
                await self._send_error(chat_id, f"处理消息时出错：{str(e)[:100]}")

    async def _handle_with_stream(
        self,
        chat_id: str,
        sid: str,
        content: str,
        message_id: str,
        media: list[str] | None = None,
    ) -> None:
        """走流式对话，把输出实时推送到飞书"""
        has_any_output = False

        async for event_str in self.adapter.chat_stream(
            query=content, sid=sid, files=media or None
        ):
            try:
                event = json.loads(event_str)
            except json.JSONDecodeError:
                continue

            phase = event.get("phase", "")

            if phase == "think_token":
                token = event.get("token", "")
                if token:
                    has_any_output = True
                    await self._send_tool_hint(chat_id, token)

            elif phase == "answer":
                token = event.get("token", "")
                if token:
                    has_any_output = True
                    await self._send_delta(chat_id, token, message_id)

            elif phase == "error":
                err = event.get("message", "未知错误")
                await self._send_error(chat_id, err)
                # 错误时也要结束流，防止前端死等
                await self._send_stream_end(chat_id, message_id)
                return

            elif phase == "done":
                if not has_any_output:
                    # 没有任何输出但完成了 —— 说明是纯工具调用（无最终回答）
                    await self._send_delta(chat_id, "任务已完成 ✅", message_id)
                await self._send_stream_end(chat_id, message_id)
                return

        # 流意外结束（没有 done 事件）
        await self._send_stream_end(chat_id, message_id)

    # ── 飞书消息发送辅助 ──

    async def _send_delta(self, chat_id: str, text: str, message_id: str = "") -> None:
        """推送文本块（打字机效果）"""
        if not self.channel:
            return
        meta: dict[str, Any] = {}
        if message_id:
            meta["message_id"] = message_id
        try:
            await self.channel.send_delta(chat_id, text, meta)
        except Exception as e:
            logger.warning("飞书 send_delta 失败: {}", e)

    async def _send_tool_hint(self, chat_id: str, text: str) -> None:
        """推送工具调用提示"""
        if not self.channel:
            return
        try:
            await self.channel.send_delta(chat_id, text, {"_tool_hint": True})
        except Exception as e:
            logger.warning("飞书 tool_hint 发送失败: {}", e)

    async def _send_stream_end(self, chat_id: str, message_id: str = "") -> None:
        """结束流式推送"""
        if not self.channel:
            return
        meta: dict[str, Any] = {"_stream_end": True}
        if message_id:
            meta["message_id"] = message_id
        try:
            await self.channel.send_delta(chat_id, "", meta)
        except Exception as e:
            logger.warning("飞书 stream_end 发送失败: {}", e)

    async def _send_error(self, chat_id: str, err_msg: str) -> None:
        """发送错误消息"""
        if not self.channel:
            return
        try:
            await self.channel.send(
                OutboundMessage(
                    channel="feishu",
                    chat_id=chat_id,
                    content=f"❌ {err_msg}",
                )
            )
        except Exception as e:
            logger.warning("飞书错误消息发送失败: {}", e)
