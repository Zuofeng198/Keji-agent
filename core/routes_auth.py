"""用户登录与当前账号信息。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.database.db import get_db
from core.security.deps import get_current_user
from core.security.users import (
    ROLES,
    CurrentUser,
    create_access_token,
    hash_password,
    verify_password,
)
from core.security.context import set_request_context

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


@router.post("/login")
def login(req: LoginRequest, request: Request):
    db = get_db()
    row = db.get_user_by_username(req.username)
    if not row or not row.get("is_active"):
        raise HTTPException(401, "用户名或密码错误")
    if not verify_password(req.password, row["password_hash"]):
        raise HTTPException(401, "用户名或密码错误")
    db.touch_user_login(row["id"])
    token, expires_in = create_access_token(row["id"], row["username"], row["role"])
    user = CurrentUser(
        id=row["id"],
        username=row["username"],
        role=row["role"],
        display_name=row.get("display_name") or row["username"],
    )
    request.state.user = user
    set_request_context(actor=user.username, client_ip=_client_ip(request))
    return {
        "token": token,
        "expires_in": expires_in,
        "user": db.user_to_public(row),
    }


@router.get("/me")
def auth_me(user: CurrentUser = Depends(get_current_user)):
    row = get_db().get_user_by_id(user.id)
    if not row or not row.get("is_active"):
        raise HTTPException(401, "账号已禁用或不存在")
    return {"user": get_db().user_to_public(row)}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""
