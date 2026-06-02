"""对话持久化：nanobot 会话文件 + SQLite（供历史列表与管理页）。"""

from __future__ import annotations

from loguru import logger

from core.database.db import get_db
from core.security.users import parse_session_conversation_id


def parse_session_user_and_conv(session_key: str) -> tuple[str | None, str]:
    if session_key.startswith("user:") and session_key.count(":") >= 2:
        parts = session_key.split(":", 2)
        return parts[1], parts[2]
    return None, session_key


def sync_session_to_db(session_key: str, query: str, reply: str, thinking: str = "") -> None:
    """将一轮对话写入 SQLite，便于历史列表与管理员查看。"""
    user_id, conv_id = parse_session_user_and_conv(session_key)
    if not user_id:
        return
    db = get_db()
    title = (query or "").strip()[:50] or "新对话"
    db.ensure_conversation_owned(conv_id, user_id, title=title)
    if query:
        db.add_message(conv_id, "user", query)
    content = reply or ""
    if thinking and not content:
        content = f"（思考过程）\n{thinking[:2000]}"
    if content:
        db.add_message(conv_id, "assistant", content)


def persist_chat_turn(
    session_manager,
    session_key: str,
    query: str,
    run_result,
    *,
    thinking: str = "",
) -> None:
    """保存到 nanobot JSONL 并同步 DB。"""
    reply = (getattr(run_result, "final_content", None) or "") if run_result else ""
    try:
        session = session_manager.get_or_create(session_key)
        session.add_message("user", query)
        if reply or thinking:
            session.add_message(
                "assistant",
                reply,
                thinking=thinking or None,
            )
        session_manager.save(session)
        sync_session_to_db(session_key, query, reply, thinking=thinking)
    except Exception as e:
        logger.warning("Persist chat session {}: {}", session_key, e)
