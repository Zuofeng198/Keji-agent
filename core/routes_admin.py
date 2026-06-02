"""管理员：用户管理与全员对话查看。"""

from __future__ import annotations

import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.database.db import get_db
from core.security.deps import require_admin
from core.security.users import ROLES, CurrentUser, hash_password

router = APIRouter(prefix="/api/admin", tags=["admin"])


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    role: str = Field(default="member")
    display_name: str = Field(default="")


class UpdateUserRequest(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)


@router.get("/users")
def admin_list_users(_admin: CurrentUser = Depends(require_admin)):
    db = get_db()
    users = [db.user_to_public(u) for u in db.list_users()]
    return {"users": users}


@router.post("/users")
def admin_create_user(req: CreateUserRequest, admin: CurrentUser = Depends(require_admin)):
    if req.role not in ROLES:
        raise HTTPException(400, f"无效角色，可选: {', '.join(sorted(ROLES))}")
    db = get_db()
    if db.get_user_by_username(req.username):
        raise HTTPException(400, "用户名已存在")
    uid = db.create_user(
        username=req.username,
        password_hash=hash_password(req.password),
        role=req.role,
        display_name=req.display_name or req.username,
    )
    try:
        from core.workspace import ensure_user_dir

        ensure_user_dir(uid)
    except Exception:
        pass
    row = db.get_user_by_id(uid)
    return {"status": "ok", "user": db.user_to_public(row)}


@router.delete("/users/{user_id}")
def admin_delete_user(user_id: str, admin: CurrentUser = Depends(require_admin)):
    if user_id == admin.id:
        raise HTTPException(400, "不能删除当前登录的管理员账号")
    db = get_db()
    target = db.get_user_by_id(user_id)
    if not target:
        raise HTTPException(404, "用户不存在")
    if target["role"] == "admin":
        admins = [u for u in db.list_users() if u.get("role") == "admin" and u.get("is_active")]
        if len(admins) <= 1:
            raise HTTPException(400, "不能删除唯一的管理员账号")
    try:
        from nanobot.session.manager import SessionManager
        from pathlib import Path
        from core.security.users import user_session_key

        sm = SessionManager(Path(__file__).resolve().parent.parent)
        for conv in db.list_conversations(limit=500, owner_user_id=user_id):
            cid = conv["id"]
            sm.delete_session(cid)
            sm.delete_session(user_session_key(user_id, cid))
    except Exception:
        pass
    db.delete_user(user_id)
    return {"status": "ok", "message": "用户已删除"}


@router.patch("/users/{user_id}")
def admin_update_user(
    user_id: str,
    req: UpdateUserRequest,
    admin: CurrentUser = Depends(require_admin),
):
    if user_id == admin.id and req.is_active is False:
        raise HTTPException(400, "不能禁用当前登录的管理员账号")
    if req.role is not None and req.role not in ROLES:
        raise HTTPException(400, f"无效角色，可选: {', '.join(sorted(ROLES))}")
    db = get_db()
    if not db.get_user_by_id(user_id):
        raise HTTPException(404, "用户不存在")
    pw_hash = hash_password(req.password) if req.password else None
    active = None if req.is_active is None else (1 if req.is_active else 0)
    db.update_user(
        user_id,
        display_name=req.display_name,
        role=req.role,
        is_active=active,
        password_hash=pw_hash,
    )
    row = db.get_user_by_id(user_id)
    return {"status": "ok", "user": db.user_to_public(row)}


@router.get("/conversations")
def admin_list_all_conversations(
    _admin: CurrentUser = Depends(require_admin),
    limit: int = Query(100, ge=1, le=500),
    user_id: str = Query("", description="按用户筛选"),
):
    from core.routes import _merge_all_nanobot_conversations_for_admin

    db = get_db()
    owner = user_id.strip() or None
    convs = db.list_conversations(limit=limit, owner_user_id=owner)
    _merge_all_nanobot_conversations_for_admin(convs, owner_filter=owner)
    users_by_id = {u["id"]: u for u in db.list_users()}
    for c in convs:
        c["created_at"] = datetime.datetime.fromtimestamp(c["created_at"]).strftime(
            "%Y-%m-%d %H:%M"
        )
        c["updated_at"] = datetime.datetime.fromtimestamp(c["updated_at"]).strftime(
            "%Y-%m-%d %H:%M"
        )
        oid = c.get("owner_user_id")
        owner = users_by_id.get(oid) if oid else None
        c["owner_username"] = owner["username"] if owner else ""
        c["owner_display_name"] = owner.get("display_name", "") if owner else "（未归属）"
    return {"conversations": convs}


@router.get("/conversations/{conv_id}")
def admin_get_conversation(
    conv_id: str,
    _admin: CurrentUser = Depends(require_admin),
):
    from core.routes import get_conversation

    return get_conversation(conv_id, _admin)
