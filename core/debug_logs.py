"""调试日志缓冲：在内存中保留最近 N 条日志，供前端调试面板拉取"""
import collections
import logging
import threading
import time


class MemoryLogHandler(logging.Handler):
    """将日志同时写入内存环形缓冲区"""

    def __init__(self, capacity: int = 200):
        super().__init__()
        self.buffer = collections.deque(maxlen=capacity)
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

    def emit(self, record):
        entry = {
            "timestamp": time.time(),
            "time": self.format(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        self.buffer.append(entry)

    def get_logs(self, since: float = 0, limit: int = 100) -> list[dict]:
        items = list(self.buffer)
        if since:
            items = [it for it in items if it["timestamp"] >= since]
        return items[-limit:]


_handler: MemoryLogHandler = None
_lock = threading.Lock()


def get_memory_handler() -> MemoryLogHandler:
    global _handler
    if _handler is None:
        with _lock:
            if _handler is None:
                _handler = MemoryLogHandler(capacity=300)
                _handler.setLevel(logging.DEBUG)
                # 挂到 root logger 上捕获所有日志
                root = logging.getLogger()
                root.addHandler(_handler)
    return _handler


# 启动时自动注册
get_memory_handler()
