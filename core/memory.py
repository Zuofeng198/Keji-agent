from collections import deque
from core.logger import setup_logger

logger = setup_logger("keji.memory")


class ConversationMemory:
    """多对话记忆存储 —— 每个对话有独立的滑动窗口"""

    def __init__(self, max_messages: int = 40):
        self.max_messages = max_messages
        self._stores: dict[str, deque] = {}

    def get_all(self, conv_id: str) -> list[dict]:
        """获取指定对话的所有消息"""
        store = self._stores.get(conv_id)
        return list(store) if store else []

    def add(self, conv_id: str, role: str, content: str):
        """向指定对话追加消息"""
        if conv_id not in self._stores:
            self._stores[conv_id] = deque(maxlen=self.max_messages)
        self._stores[conv_id].append({"role": role, "content": content})

    def clear(self, conv_id: str):
        """清空指定对话的记忆"""
        if conv_id in self._stores:
            self._stores[conv_id].clear()
            logger.debug("Memory cleared: conv=%s", conv_id)

    def drop(self, conv_id: str):
        """彻底删除指定对话的记忆"""
        self._stores.pop(conv_id, None)

    def load_from_list(self, conv_id: str, messages: list[dict]):
        """从消息列表加载到指定对话的记忆（用于恢复历史）"""
        if not messages:
            return
        store = deque(maxlen=self.max_messages)
        for m in messages:
            store.append({"role": m["role"], "content": m["content"]})
        self._stores[conv_id] = store
        logger.debug("Memory loaded: conv=%s (%d messages)", conv_id, len(store))

    def __len__(self):
        return len(self._stores)


class SummaryMemory:
    """长对话摘要压缩记忆

    保留最近 k 轮完整对话 + 更早对话的摘要，避免 token 超限。
    """

    def __init__(self, recent_rounds: int = 4, max_summary_chars: int = 2000):
        self.recent_rounds = recent_rounds
        self.max_summary_chars = max_summary_chars
        self.full_history: list[dict] = []
        self.summary: str = ""

    def add(self, role: str, content: str):
        self.full_history.append({"role": role, "content": content})

    def get_all(self) -> list[dict]:
        return self.full_history

    def get_compressed(self) -> list[dict]:
        """返回压缩后的消息列表：摘要 + 最近轮次"""
        result = []
        if self.summary:
            result.append({
                "role": "system",
                "content": f"[历史对话摘要]\n{self.summary}",
            })
        recent = self.full_history[-(self.recent_rounds * 2):]
        result.extend(recent)
        return result

    def compress(self, model_adapter, prompt: str = ""):
        """调用模型对旧对话进行摘要压缩"""
        if len(self.full_history) <= self.recent_rounds * 2:
            return

        old = self.full_history[: -(self.recent_rounds * 2)]
        if not old:
            return

        old_text = "\n".join(
            f"{m['role']}: {m['content'][:300]}" for m in old
        )
        sys_prompt = prompt or "请用一段话（不超过300字）总结以下对话的核心内容和关键信息："
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"对话记录：\n{old_text}\n\n请总结："},
        ]

        try:
            self.summary = model_adapter.chat(messages)[: self.max_summary_chars]
            logger.info("Memory compressed: %d messages -> %d chars summary",
                         len(old), len(self.summary))
        except Exception as e:
            logger.warning("Memory compression failed: %s", e)

    def clear(self):
        self.full_history.clear()
        self.summary = ""

    def __len__(self):
        return len(self.full_history)
