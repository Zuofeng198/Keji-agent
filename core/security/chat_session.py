"""聊天会话 ID 与用户隔离的 session key。"""

from __future__ import annotations

import uuid

from fastapi import Request

from core.database.db import get_db
from core.security.users import CurrentUser, user_session_key


def resolve_chat_ids(
    request: Request,
    *,
    session_id: str = "",
    conversation_id: str = "",
) -> tuple[str, str, CurrentUser | None]:
    """
    返回 (nanobot_session_key, conversation_id, user)。
    登录用户：session_key = user:{uid}:{conv_id}，并登记对话归属。
    """
    user: CurrentUser | None = getattr(request.state, "user", None)
    conv_id = (conversation_id or session_id or uuid.uuid4().hex[:12]).strip()
    if user and user.id not in ("anonymous", "localhost"):
        db = get_db()
        db.ensure_conversation_owned(conv_id, user.id)
        sk = user_session_key(user.id, conv_id)
        return sk, conv_id, user
    return conv_id, conv_id, user
