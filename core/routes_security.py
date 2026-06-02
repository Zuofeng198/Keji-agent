"""安全相关 API：鉴权状态、审计查询。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from core.database.db import get_db
from core.security.auth import authenticate_request, get_security_settings
from core.security.audit import get_audit_logger
from core.security.deps import require_admin
from core.security.users import CurrentUser

router = APIRouter(prefix="/api/security", tags=["security"])


@router.get("/status")
def security_status(request: Request):
    """公开：前端用于判断是否需登录。"""
    settings = get_security_settings()
    user = authenticate_request(request, settings) if settings.enabled else None
    payload = {
        "auth_enabled": settings.enabled,
        "auth_mode": settings.auth_mode,
        "allow_localhost_without_auth": settings.allow_localhost_without_auth,
        "authenticated": user is not None if settings.enabled else True,
        "audit_enabled": get_audit_logger().enabled,
        "user_login": True,
    }
    if user and user.id not in ("anonymous", "localhost", "service"):
        row = get_db().get_user_by_id(user.id)
        if row:
            payload["user"] = get_db().user_to_public(row)
    return payload


@router.get("/audit/logs")
def list_audit_logs(
    event_type: str = Query("", description="tool_call | file_access"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _admin: CurrentUser = Depends(require_admin),
):
    """查询审计日志（管理员 + 登录 JWT）。"""
    events = get_db().list_audit_events(event_type=event_type, limit=limit, offset=offset)
    return {"events": events, "limit": limit, "offset": offset}
