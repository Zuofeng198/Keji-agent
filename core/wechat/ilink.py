"""iLink Bot API 客户端 —— 腾讯官方微信 ClawBot 插件协议

API 基础地址: https://ilinkai.weixin.qq.com
协议: HTTP/JSON, 长轮询消息接收
"""

import base64
import json
import os
import random
import time
import threading
import logging
from typing import Optional, Callable
from dataclasses import dataclass, field
from pathlib import Path

import requests

try:
    import qrcode
    from qrcode.image.pil import PilImage
    HAS_QR = True
except ImportError:
    HAS_QR = False

logger = logging.getLogger("keji.wechat.ilink")

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

BASE_URL = "https://ilinkai.weixin.qq.com"
CDN_URL = "https://novac2c.cdn.weixin.qq.com/c2c"
CHANNEL_VERSION = "1.0.2"
LONGPOLL_TIMEOUT = 35  # getupdates 长轮询超时（秒）
BOT_TYPE = 3  # 机器人类型

# 消息类型
MSG_TYPE_USER = 1       # 用户发出的消息
MSG_TYPE_BOT = 2        # Bot 发出的消息

MSG_STATE_NEW = 0       # 新消息
MSG_STATE_GENERATING = 1  # 正在生成
MSG_STATE_FINISH = 2    # 生成完成

# item_list 中的 type
ITEM_TEXT = 1
ITEM_IMAGE = 2
ITEM_VOICE = 3
ITEM_FILE = 4
ITEM_VIDEO = 5

# 错误码
ERR_SESSION_EXPIRED = -14  # bot_token 失效，需重新登录

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class BotSession:
    """持久化的 Bot 登录会话"""
    bot_token: str = ""
    base_url: str = BASE_URL
    bot_id: str = ""        # ilink_bot_id
    user_id: str = ""       # ilink_user_id
    updates_buf: str = ""   # getupdates 游标

    def is_valid(self) -> bool:
        return bool(self.bot_token)


@dataclass
class WeChatMessage:
    """解析后的微信消息"""
    from_user: str = ""
    to_user: str = ""
    text: str = ""
    msg_type: int = 0       # 原始 message_type
    context_token: str = ""
    group_id: str = ""
    items: list = field(default_factory=list)  # 原始 item_list

    def is_text(self) -> bool:
        return any(it.get("type") == ITEM_TEXT for it in self.items)

    def get_text(self) -> str:
        for it in self.items:
            if it.get("type") == ITEM_TEXT:
                return it.get("text_item", {}).get("text", "")
        return ""


# ---------------------------------------------------------------------------
# UIN 生成（每次请求不同）
# ---------------------------------------------------------------------------

def _make_uin() -> str:
    """生成 X-WECHAT-UIN 头"""
    uin = random.getrandbits(32)
    return base64.b64encode(str(uin).encode()).decode()


def _make_headers(bot_token: str) -> dict:
    return {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "X-WECHAT-UIN": _make_uin(),
        "Authorization": f"Bearer {bot_token}",
    }


# ---------------------------------------------------------------------------
# iLink Bot API 客户端
# ---------------------------------------------------------------------------

class ILinkClient:
    """iLink Bot API 客户端 — 登录 / 收消息 / 发消息 / 文件上传"""

    def __init__(self, session_path: str = "data/wechat_session.json"):
        self.session_path = Path(session_path)
        self.session = BotSession()
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._on_message: Optional[Callable] = None
        self._on_error: Optional[Callable] = None
        self._load_session()

    # ──── 会话持久化 ────

    def _load_session(self):
        """从磁盘加载持久化的 Bot 会话"""
        if self.session_path.exists():
            try:
                data = json.loads(self.session_path.read_text(encoding="utf-8"))
                self.session = BotSession(**data)
                logger.info("Session loaded: bot_id=%s", self.session.bot_id)
            except Exception as e:
                logger.warning("Failed to load session: %s", e)

    def _save_session(self):
        """将会话持久化到磁盘"""
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "bot_token": self.session.bot_token,
            "base_url": self.session.base_url,
            "bot_id": self.session.bot_id,
            "user_id": self.session.user_id,
            "updates_buf": self.session.updates_buf,
        }
        self.session_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        logger.info("Session saved: bot_id=%s", self.session.bot_id)

    # ──── 登录流程 ────

    def _get_qrcode(self) -> Optional[dict]:
        """获取登录二维码，返回 {qrcode, qrcode_img_content}"""
        try:
            resp = requests.get(
                f"{BASE_URL}/ilink/bot/get_bot_qrcode",
                params={"bot_type": BOT_TYPE},
                timeout=15,
            )
            data = resp.json()
            if data.get("ret") == 0:
                qrcode = data.get("qrcode", "")
                img_url = data.get("qrcode_img_content", "")
                logger.info("QR code obtained: %s...", qrcode[:20] if qrcode else "empty")
                return {"qrcode": qrcode, "img_url": img_url}
            else:
                logger.error("Get QR code failed: %s", data)
                return None
        except Exception as e:
            logger.error("Get QR code error: %s", e)
            return None

    def _poll_qrcode(self, qrcode: str) -> Optional[dict]:
        """轮询扫码状态，返回登录结果"""
        url = f"{BASE_URL}/ilink/bot/get_qrcode_status"
        for attempt in range(60):  # 最多等 60 轮
            try:
                resp = requests.get(url, params={"qrcode": qrcode}, timeout=35)
                data = resp.json()
                status = data.get("status", "")
                if status == "confirmed":
                    logger.info("QR code confirmed! Login success.")
                    return data  # { bot_token, baseurl, ilink_bot_id, ilink_user_id, ... }
                elif status == "expired":
                    logger.warning("QR code expired")
                    return None
                elif status == "scaned":
                    logger.info("QR code scanned, waiting for confirm...")
                # status == "wait" 继续轮询
            except Exception as e:
                logger.warning("QR poll error: %s", e)
            time.sleep(1)
        logger.warning("QR poll timeout")
        return None

    def login(self) -> bool:
        """完整登录流程：获取二维码 → 打印 → 轮询结果"""
        if self.session.is_valid():
            logger.info("Already logged in: bot_id=%s", self.session.bot_id)
            return True

        logger.info("=" * 50)
        logger.info("  微信登录")
        logger.info("  请使用微信扫描下方二维码")
        logger.info("=" * 50)

        qr_data = self._get_qrcode()
        if not qr_data:
            return False
        qrcode_id = qr_data["qrcode"]
        qr_url = qr_data["img_url"]

        logger.info("QR Code URL: %s", qr_url)
        print(f"\n  {'=' * 46}")
        print(f"  请使用微信扫描下方二维码")
        print(f"  {'=' * 46}\n")
        if HAS_QR:
            try:
                qr = qrcode.QRCode(border=2, box_size=1)
                qr.add_data(qr_url)
                qr.print_ascii(tty=True)
                print()
            except Exception as e:
                logger.debug("QR ascii failed: %s", e)
                print(f"  URL: {qr_url}\n")
        else:
            print(f"  URL: {qr_url}\n")

        result = self._poll_qrcode(qrcode_id)
        if not result:
            logger.error("Login failed or timeout")
            return False

        self.session.bot_token = result.get("bot_token", "")
        self.session.base_url = result.get("baseurl", BASE_URL)
        self.session.bot_id = result.get("ilink_bot_id", "")
        self.session.user_id = result.get("ilink_user_id", "")
        self.session.updates_buf = ""
        self._save_session()
        logger.info("Login success! bot_id=%s", self.session.bot_id)
        return True

    def logout(self):
        """清除登录状态"""
        self.session = BotSession()
        if self.session_path.exists():
            self.session_path.unlink()
        logger.info("Logged out")

    # ──── 消息接收（长轮询）────

    def get_updates(self) -> list[WeChatMessage]:
        """长轮询接收消息，返回消息列表"""
        if not self.session.is_valid():
            logger.error("Not logged in")
            return []

        url = f"{self.session.base_url}/ilink/bot/getupdates"
        payload = {
            "get_updates_buf": self.session.updates_buf,
            "base_info": {"channel_version": CHANNEL_VERSION},
        }

        try:
            resp = requests.post(
                url,
                headers=_make_headers(self.session.bot_token),
                json=payload,
                timeout=LONGPOLL_TIMEOUT + 5,
            )
            data = resp.json()
        except requests.Timeout:
            # 长轮询超时是正常情况
            return []
        except Exception as e:
            logger.warning("get_updates error: %s", e)
            return []

        # 检查 session 过期
        ret = data.get("ret", 0)
        if ret == ERR_SESSION_EXPIRED:
            logger.error("Session expired, need re-login")
            self.session = BotSession()
            self._save_session()
            if self._on_error:
                self._on_error("session_expired")
            return []

        if ret != 0:
            logger.warning("get_updates ret=%d: %s", ret, data.get("errmsg", ""))
            return []

        # 更新游标
        buf = data.get("get_updates_buf", "")
        if buf:
            self.session.updates_buf = buf
            self._save_session()

        # 解析消息
        raw_msgs = data.get("msgs", [])
        result = []
        for raw in raw_msgs:
            msg = WeChatMessage(
                from_user=raw.get("from_user_id", ""),
                to_user=raw.get("to_user_id", ""),
                msg_type=raw.get("message_type", 0),
                context_token=raw.get("context_token", ""),
                group_id=raw.get("group_id", ""),
                items=raw.get("item_list", []),
            )
            msg.text = msg.get_text()
            result.append(msg)

        return result

    # ──── 消息发送 ────

    def send_message(
        self,
        to_user: str,
        text: str,
        context_token: str = "",
    ) -> bool:
        """发送文本消息到微信"""
        if not self.session.is_valid():
            return False

        url = f"{self.session.base_url}/ilink/bot/sendmessage"
        payload = {
            "msg": {
                "to_user_id": to_user,
                "message_type": MSG_TYPE_BOT,
                "message_state": MSG_STATE_FINISH,
                "context_token": context_token,
                "item_list": [
                    {"type": ITEM_TEXT, "text_item": {"text": text}}
                ],
            },
            "base_info": {"channel_version": CHANNEL_VERSION},
        }

        try:
            resp = requests.post(
                url,
                headers=_make_headers(self.session.bot_token),
                json=payload,
                timeout=15,
            )
            data = resp.json()
            # 成功响应可能是空 {} 或包含 ret=0
            if data.get("ret") == 0 or data == {}:
                if data == {}:
                    logger.info("send_message success (empty response)")
                return True
            else:
                logger.warning("send_message failed: status=%d body=%s headers=%s",
                    resp.status_code, resp.text[:500], dict(resp.headers))
                return False
        except Exception as e:
            logger.warning("send_message error: %s", e)
            return False

    def send_typing(self, to_user: str):
        """发送"正在输入"状态"""
        if not self.session.is_valid():
            return

        url = f"{self.session.base_url}/ilink/bot/sendtyping"
        payload = {
            "to_user_id": to_user,
            "base_info": {"channel_version": CHANNEL_VERSION},
        }
        try:
            requests.post(
                url,
                headers=_make_headers(self.session.bot_token),
                json=payload,
                timeout=10,
            )
        except Exception:
            pass

    # ──── 文件上传（准备发送文件用）────

    def get_upload_url(self) -> Optional[dict]:
        """获取 CDN 预签名上传参数"""
        if not self.session.is_valid():
            return None

        url = f"{self.session.base_url}/ilink/bot/getuploadurl"
        payload = {"base_info": {"channel_version": CHANNEL_VERSION}}

        try:
            resp = requests.post(
                url,
                headers=_make_headers(self.session.bot_token),
                json=payload,
                timeout=15,
            )
            data = resp.json()
            if data.get("ret") == 0:
                return data.get("upload_param")  # 包含上传 URL 和表单字段
        except Exception as e:
            logger.warning("get_upload_url error: %s", e)
        return None

    # ──── 消息回调 ────

    def set_on_message(self, callback: Callable[[WeChatMessage], None]):
        """设置消息处理回调"""
        self._on_message = callback

    def set_on_error(self, callback: Callable[[str], None]):
        """设置错误回调"""
        self._on_error = callback

    # ──── 轮询循环 ────

    def start_polling(self):
        """启动后台消息轮询"""
        if self._running:
            return
        self._running = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        logger.info("Polling started")

    def stop_polling(self):
        """停止后台消息轮询"""
        self._running = False
        logger.info("Polling stopped")

    def _poll_loop(self):
        """后台轮询循环"""
        while self._running:
            if not self.session.is_valid():
                logger.warning("Session invalid in poll loop")
                time.sleep(5)
                continue

            try:
                msgs = self.get_updates()
                for msg in msgs:
                    if self._on_message:
                        try:
                            self._on_message(msg)
                        except Exception as e:
                            logger.error("Message handler error: %s", e)
            except Exception as e:
                logger.error("Poll loop error: %s", e)
                time.sleep(3)
