import uuid
import time
import threading
from typing import Optional
from core.agent import CoreAgent
from core.logger import setup_logger

logger = setup_logger("keji.session")


class SessionManager:
    """会话管理器：多会话隔离，TTL 过期自动清理，支持流中断"""

    def __init__(self, ttl_seconds: int = 1800):
        self.ttl = ttl_seconds
        self.sessions: dict[str, dict] = {}
        self._cancel_flags: dict[str, bool] = {}
        self._lock = threading.Lock()

        # 启动后台清理线程
        self._cleaner = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleaner.start()

    def _get_model_tag(self) -> str:
        """获取当前模型配置的标识，用于检测变化"""
        from core.database.db import get_db
        db = get_db()
        mt = db.get_setting("model_type", "ollama")
        if mt == "openai":
            mn = db.get_setting("openai_model", "")
        else:
            mn = db.get_setting("chat_model", "qwen2.5:7b")
        return f"{mt}:{mn}"

    def get_or_create(self, session_id: Optional[str] = None) -> tuple[str, CoreAgent]:
        """获取或创建会话，返回 (session_id, agent)"""
        with self._lock:
            tag = self._get_model_tag()
            if session_id and session_id in self.sessions:
                s = self.sessions[session_id]
                s["last_access"] = time.time()
                # 模型配置变化时重建 Agent
                if s.get("model_tag") != tag:
                    s["agent"] = CoreAgent()
                    s["model_tag"] = tag
                    logger.info("Session agent recreated (config changed): %s -> %s", session_id, tag)
                return session_id, s["agent"]

            new_id = session_id or uuid.uuid4().hex[:12]
            agent = CoreAgent()
            self.sessions[new_id] = {
                "agent": agent,
                "model_tag": tag,
                "mode": "react",
                "created_at": time.time(),
                "last_access": time.time(),
            }
            logger.info("Session created: %s (total=%d) [%s]", new_id, len(self.sessions), tag)
            return new_id, agent

    def get(self, session_id: str) -> Optional[CoreAgent]:
        """获取已有会话的 agent"""
        with self._lock:
            if session_id in self.sessions:
                self.sessions[session_id]["last_access"] = time.time()
                return self.sessions[session_id]["agent"]
        return None

    def delete(self, session_id: str):
        """删除会话"""
        with self._lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
                logger.info("Session deleted: %s", session_id)

    def reset(self, session_id: str, conv_id: str = ""):
        """重置会话记忆（可指定对话 ID）"""
        agent = self.get(session_id)
        if agent:
            agent.reset(conv_id=conv_id)

    def get_mode(self, session_id: str) -> str:
        """获取会话模式"""
        with self._lock:
            s = self.sessions.get(session_id)
            return s.get("mode", "react") if s else "react"

    def set_mode(self, session_id: str, mode: str):
        """设置会话模式"""
        if mode not in ("react", "plan_execute"):
            return
        with self._lock:
            if session_id in self.sessions:
                self.sessions[session_id]["mode"] = mode
                logger.info("Session mode changed: %s -> %s", session_id, mode)

    def stats(self) -> dict:
        """会话统计"""
        with self._lock:
            return {
                "total_sessions": len(self.sessions),
                "sessions": [
                    {
                        "id": sid,
                        "created_at": s["created_at"],
                        "last_access": s["last_access"],
                        "memory_size": len(s["agent"].memory),
                    }
                    for sid, s in self.sessions.items()
                ],
            }

    # ---- 流式输出中断 ----

    def cancel_stream(self, session_id: str):
        """标记中断指定会话的流式输出"""
        with self._lock:
            self._cancel_flags[session_id] = True

    def is_cancelled(self, session_id: str) -> bool:
        """检查是否被中断"""
        return self._cancel_flags.get(session_id, False)

    def clear_cancel(self, session_id: str):
        """清除中断标记"""
        with self._lock:
            self._cancel_flags.pop(session_id, None)

    def _cleanup_loop(self):
        """后台清理过期会话"""
        while True:
            time.sleep(300)  # 每 5 分钟检查
            now = time.time()
            with self._lock:
                expired = [
                    sid for sid, s in self.sessions.items()
                    if now - s["last_access"] > self.ttl
                ]
                for sid in expired:
                    del self.sessions[sid]
                if expired:
                    logger.info("Cleaned %d expired sessions, %d remaining",
                                len(expired), len(self.sessions))


# 全局会话管理器
session_manager = SessionManager()
