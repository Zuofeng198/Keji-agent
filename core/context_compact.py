"""会话上下文压缩：工具结果剪枝 + LLM 摘要（手动/自动）。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from core.context_prune import prune_tool_results, should_prune_messages


def estimate_messages_tokens(messages: list[dict]) -> int:
    total_chars = 0
    for m in messages:
        total_chars += len(str(m.get("content", "")))
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function", {}) if isinstance(tc, dict) else {}
            total_chars += len(str(fn.get("arguments", "")))
    return total_chars // 4


def get_context_settings(config: dict) -> dict[str, Any]:
    agent = config.get("agent") or {}
    return {
        "prune_tool_results": agent.get("context_prune_tool_results", True),
        "auto_compact_enabled": agent.get("context_auto_compact_enabled", True),
        "auto_compact_threshold": int(agent.get("context_auto_compact_threshold", 60000)),
        "compact_keep_recent": int(agent.get("context_compact_keep_recent", 8)),
        "compact_summary_max_messages": int(agent.get("context_compact_summary_max_messages", 40)),
    }


def prune_history_messages(history: list[dict], enabled: bool = True) -> list[dict]:
    if not enabled or not history:
        return history
    if not should_prune_messages(history):
        return history
    return prune_tool_results(history)


async def summarize_dialog(
    provider: Any,
    messages: list[dict],
    *,
    max_messages: int = 40,
) -> str:
    dialog = []
    for m in messages[-max_messages:]:
        role = m.get("role", "?")
        content = str(m.get("content", ""))[:800]
        if not content.strip():
            continue
        dialog.append(f"{role}: {content}")
    if not dialog:
        return "[无有效对话内容]"
    dialog_text = "\n\n".join(dialog)
    summary_prompt = (
        "请用简洁的中文概括以下对话的核心内容（400字以内），"
        "包括：用户需求、关键结论、已完成的操作、未解决的问题。\n\n"
        f"对话记录：\n{dialog_text}"
    )
    resp = await provider.chat([{"role": "user", "content": summary_prompt}])
    return (resp.content or "").strip()


async def compact_session_new(
    session_manager: Any,
    session_id: str,
    provider: Any,
    *,
    keep_recent: int = 8,
    max_summary_messages: int = 40,
) -> dict[str, str]:
    """LLM 摘要后创建新会话（原 /api/compact 行为）。"""
    data = session_manager.read_session_file(session_id)
    if not data:
        return {"text": "错误: 未找到会话", "new_session_id": ""}

    msgs = data.get("messages", [])
    if len(msgs) < 2:
        return {"text": "对话太短，无需压缩", "new_session_id": ""}

    summary = await summarize_dialog(provider, msgs, max_messages=max_summary_messages)
    new_key = f"compact:{session_id}:{datetime.now().strftime('%Y%m%d%H%M%S')}"
    new_session = session_manager.get_or_create(new_key)
    new_session.add_message(
        "user",
        f"[对话摘要] 以下是之前对话的摘要：\n\n{summary}\n\n---\n请输入你的新问题",
    )
    new_session.add_message(
        "assistant",
        "✅ 历史对话已压缩！原会话仍可查看。\n\n"
        f"**对话摘要**：\n{summary}\n\n"
        "请在下方继续提问，我会基于以上上下文回答。",
    )
    session_manager.save(new_session)
    return {
        "text": f"✅ 对话已压缩，切换到新会话。\n\n**摘要**：{summary}",
        "new_session_id": new_key,
    }


async def compact_session_inplace(
    session_manager: Any,
    session_id: str,
    provider: Any,
    *,
    keep_recent: int = 8,
    max_summary_messages: int = 40,
) -> bool:
    """在原会话内压缩：摘要 + 保留最近消息。返回是否执行了压缩。"""
    session = session_manager.get_or_create(session_id)
    msgs = list(session.messages or [])
    if len(msgs) < keep_recent + 2:
        return False

    old_part = msgs[:-keep_recent]
    recent = msgs[-keep_recent:]
    summary = await summarize_dialog(provider, old_part, max_messages=max_summary_messages)

    session.messages = [
        {
            "role": "user",
            "content": f"[对话摘要 · 自动压缩]\n\n{summary}",
            "timestamp": datetime.now().isoformat(),
        },
        {
            "role": "assistant",
            "content": "已自动压缩较早的对话，保留最近几轮原文。请继续。",
            "timestamp": datetime.now().isoformat(),
        },
        *recent,
    ]
    session_manager.save(session)
    logger.info(
        "会话 {} 自动压缩: {} 条 → 摘要 + {} 条最近消息",
        session_id,
        len(msgs),
        len(recent),
    )
    return True


async def maybe_auto_compact_before_chat(
    session_manager: Any,
    session_id: str,
    provider: Any,
    config: dict,
) -> str | None:
    """若超过阈值则原地压缩。返回提示文案（供 SSE）或 None。"""
    if not session_id:
        return None
    opts = get_context_settings(config)
    if not opts["auto_compact_enabled"]:
        return None

    session = session_manager.get_or_create(session_id)
    history = session.get_history(max_messages=200, include_timestamps=False)
    tokens = estimate_messages_tokens(history)
    if tokens < opts["auto_compact_threshold"]:
        return None

    ok = await compact_session_inplace(
        session_manager,
        session_id,
        provider,
        keep_recent=opts["compact_keep_recent"],
        max_summary_messages=opts["compact_summary_max_messages"],
    )
    if ok:
        return f"📦 对话较长（约 {tokens:,} tokens），已自动压缩历史上下文。"
    return None
