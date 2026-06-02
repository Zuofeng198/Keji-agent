"""FastAPI 依赖：当前登录用户。"""

from __future__ import annotations

from fastapi import HTTPException, Request

from core.security.users import CurrentUser


def get_current_user_optional(request: Request) -> CurrentUser | None:
    user = getattr(request.state, "user", None)
    if user is not None:
        return user
    return None


def get_current_user(request: Request) -> CurrentUser:
    user = get_current_user_optional(request)
    if user is None:
        raise HTTPException(status_code=401, detail="未登录，请先登录")
    return user


def require_admin(request: Request) -> CurrentUser:
    user = get_current_user(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
