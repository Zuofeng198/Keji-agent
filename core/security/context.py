"""请求 / 会话上下文（供审计关联 session）。"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class RequestContext:
    session_id: str = ""
    actor: str = "api"
    client_ip: str = ""


_ctx: ContextVar[RequestContext | None] = ContextVar("keji_request_ctx", default=None)


def set_request_context(
    *,
    session_id: str = "",
    actor: str = "api",
    client_ip: str = "",
) -> None:
    _ctx.set(RequestContext(session_id=session_id, actor=actor, client_ip=client_ip))


def get_request_context() -> RequestContext:
    c = _ctx.get()
    if c is None:
        return RequestContext()
    return c


def clear_request_context() -> None:
    _ctx.set(None)
