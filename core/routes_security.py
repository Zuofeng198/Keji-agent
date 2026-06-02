"""安全相关 API：鉴权状态、审计查询。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from core.database.db import get_db
from core.security.auth import get_security_settings, verify_api_key
from core.security.audit import get_audit_logger

router = APIRouter(prefix="/api/security", tags=["security"])


@router.get("/status")
def security_status(request: Request):
    """公开：前端用于判断是否需携带 API Key。"""
    settings = get_security_settings()
    return {
        "auth_enabled": settings.enabled,
        "allow_localhost_without_auth": settings.allow_localhost_without_auth,
        "authenticated": verify_api_key(request, settings) if settings.enabled else True,
        "audit_enabled": get_audit_logger().enabled,
    }


@router.get("/audit/logs")
def list_audit_logs(
    request: Request,
    event_type: str = Query("", description="tool_call | file_access"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """查询审计日志（需鉴权）。"""
    settings = get_security_settings()
    if settings.enabled and not verify_api_key(request, settings):
        from fastapi import HTTPException
        raise HTTPException(401, "未授权")
    events = get_db().list_audit_events(event_type=event_type, limit=limit, offset=offset)
    return {"events": events, "limit": limit, "offset": offset}
