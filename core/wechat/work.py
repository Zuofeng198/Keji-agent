"""企业微信客户端 —— 自建应用消息收发

发送：HTTP API（通用）
接收：支持两种模式
  1. WebSocket 长连接（智能机器人，无需公网 URL）
  2. HTTP Callback（自建应用，需公网 URL/HTTPS）
"""

import json
import logging
import time
import threading
from typing import Optional, Callable
from dataclasses import dataclass, field

import requests

logger = logging.getLogger("keji.wechat.work")

API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"
TOKEN_EXPIRE_BUFFER = 300  # 提前 5 分钟刷新 Token


@dataclass
class WorkConfig:
    """企业微信配置"""
    corp_id: str = ""
    agent_id: str = ""
    corp_secret: str = ""


@dataclass
class WorkMessage:
    """企业微信消息"""
    from_user: str = ""
    content: str = ""
    msg_type: str = "text"
    msg_id: str = ""
    chat_type: str = "single"  # single / group


class WorkClient:
    """企业微信 API 客户端"""

    def __init__(self, config: WorkConfig = None):
        self.config = config or WorkConfig()
        self._token = ""
        self._token_expires = 0

    def is_configured(self) -> bool:
        return bool(self.config.corp_id and self.config.corp_secret)

    # ──── Token 管理 ────

    def _get_token(self) -> str:
        """获取 access_token（自动缓存刷新）"""
        if self._token and time.time() < self._token_expires:
            return self._token

        url = f"{API_BASE}/gettoken"
        params = {
            "corpid": self.config.corp_id,
            "corpsecret": self.config.corp_secret,
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            if data.get("errcode") == 0:
                self._token = data["access_token"]
                self._token_expires = time.time() + data["expires_in"] - TOKEN_EXPIRE_BUFFER
                logger.info("Token refreshed, expires in %ds", data["expires_in"])
                return self._token
            else:
                logger.error("Get token failed: %s", data)
                return ""
        except Exception as e:
            logger.error("Get token error: %s", e)
            return ""

    # ──── 发送消息 ────

    def send_text(self, to_user: str, content: str, agent_id: str = "") -> bool:
        """发送文本消息到企业微信"""
        token = self._get_token()
        if not token:
            return False

        url = f"{API_BASE}/message/send?access_token={token}"
        payload = {
            "touser": to_user,
            "msgtype": "text",
            "agentid": int(agent_id or self.config.agent_id),
            "text": {"content": content},
        }

        try:
            resp = requests.post(url, json=payload, timeout=15)
            data = resp.json()
            if data.get("errcode") == 0:
                logger.info("已发送消息到 %s: %.60s", to_user, content)
                return True
            else:
                logger.error("Send message failed: %s", data)
                return False
        except Exception as e:
            logger.error("Send message error: %s", e)
            return False

    def send_markdown(self, to_user: str, content: str, agent_id: str = "") -> bool:
        """发送 Markdown 消息"""
        token = self._get_token()
        if not token:
            return False

        url = f"{API_BASE}/message/send?access_token={token}"
        payload = {
            "touser": to_user,
            "msgtype": "markdown",
            "agentid": int(agent_id or self.config.agent_id),
            "markdown": {"content": content},
        }

        try:
            resp = requests.post(url, json=payload, timeout=15)
            data = resp.json()
            return data.get("errcode") == 0
        except Exception as e:
            logger.error("Send markdown error: %s", e)
            return False

    # ──── 连接测试 ────

    def test_connection(self) -> tuple[bool, str]:
        """测试企业微信连接是否正常"""
        token = self._get_token()
        if not token:
            return False, "获取 Token 失败，请检查 CorpID 和 Secret"

        # 简单测试：获取企业信息
        url = f"{API_BASE}/agent/get?access_token={token}&agentid={self.config.agent_id}"
        try:
            resp = requests.get(url, timeout=10)
            data = resp.json()
            if data.get("errcode") == 0:
                name = data.get("name", "未知应用")
                return True, f"连接成功！应用: {name}"
            else:
                return False, data.get("errmsg", "未知错误")
        except Exception as e:
            return False, str(e)


# ──── WebSocket 消息接收（智能机器人模式）────

class WorkWSReceiver:
    """企业微信 WebSocket 消息接收器

    通过长连接接收企业微信消息，无需公网 URL。
    需要企业微信后台启用「智能机器人」功能。
    """

    WS_URL = "wss://openws.work.weixin.qq.com"

    def __init__(self, bot_id: str = "", secret: str = ""):
        self.bot_id = bot_id
        self.secret = secret
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.on_message: Optional[Callable] = None

    def start(self):
        """启动 WebSocket 接收（暂未实现，需要 websocket 库）"""
        logger.info("WebSocket receiver: 需要安装 websocket-client 库")
        logger.info("pip install websocket-client")
        # TODO: 实现 WebSocket 长连接

    def stop(self):
        self._running = False
