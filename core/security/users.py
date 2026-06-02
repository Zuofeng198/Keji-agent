"""本地用户账号、JWT、会话键。"""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import bcrypt
import jwt
from loguru import logger

from core.security.secrets import load_app_config, resolve_env_ref

ROLES = frozenset({"admin", "member", "readonly"})

_JWT_SECRET_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "security" / "jwt_secret"
_jwt_secret_runtime: str | None = None


@dataclass(frozen=True)
class CurrentUser:
    id: str
    username: str
    role: str
    display_name: str = ""

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _read_or_create_jwt_secret() -> str:
    global _jwt_secret_runtime
    if _jwt_secret_runtime:
        return _jwt_secret_runtime
    if _JWT_SECRET_FILE.is_file():
        _jwt_secret_runtime = _JWT_SECRET_FILE.read_text(encoding="utf-8").strip()
        return _jwt_secret_runtime
    secret = secrets.token_urlsafe(32)
    _JWT_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    _JWT_SECRET_FILE.write_text(secret, encoding="utf-8")
    _jwt_secret_runtime = secret
    logger.warning(
        "已生成本地 JWT 密钥: {} — 建议设置 KEJI_JWT_SECRET 或 security.jwt_secret",
        _JWT_SECRET_FILE,
    )
    return secret


def _jwt_settings() -> tuple[str, int]:
    cfg = load_app_config()
    sec = cfg.get("security") or {}
    raw = sec.get("jwt_secret") or os.environ.get("KEJI_JWT_SECRET") or ""
    if isinstance(raw, str) and raw.startswith("${"):
        raw = resolve_env_ref(raw)
    secret = (raw or "").strip() or _read_or_create_jwt_secret()
    hours = int(sec.get("jwt_expire_hours", 72))
    return secret, hours


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("ascii"),
        )
    except Exception:
        return False


def create_access_token(user_id: str, username: str, role: str) -> tuple[str, int]:
    secret, hours = _jwt_settings()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=hours)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "exp": int(expires.timestamp()),
        "iat": int(now.timestamp()),
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    if isinstance(token, bytes):
        token = token.decode("ascii")
    return token, int(hours * 3600)


def decode_access_token(token: str) -> dict[str, Any] | None:
    secret, _ = _jwt_settings()
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def user_session_key(user_id: str, conversation_id: str) -> str:
    """nanobot 会话文件键：按用户隔离。"""
    return f"user:{user_id}:{conversation_id}"


def parse_session_conversation_id(session_key: str, user_id: str) -> str | None:
    prefix = f"user:{user_id}:"
    if session_key.startswith(prefix):
        return session_key[len(prefix) :]
    return None


def bootstrap_admin_if_needed() -> None:
    """无用户时创建首个 admin（配置 security.bootstrap_admin）。"""
    from core.database.db import get_db

    db = get_db()
    if db.count_users() > 0:
        return

    cfg = load_app_config()
    sec = cfg.get("security") or {}
    boot = sec.get("bootstrap_admin") or {}
    username = (boot.get("username") or "admin").strip()
    raw_pw = boot.get("password") or os.environ.get("KEJI_ADMIN_PASSWORD") or ""
    if isinstance(raw_pw, str) and raw_pw.startswith("${"):
        raw_pw = resolve_env_ref(raw_pw)
    password = (raw_pw or "").strip()
    if not password:
        password = secrets.token_urlsafe(12)
        logger.warning(
            "已创建默认管理员 {} / 临时密码: {} — 请尽快在管理页修改密码",
            username,
            password,
        )
    display = boot.get("display_name") or "系统管理员"
    uid = db.create_user(
        username=username,
        password_hash=hash_password(password),
        role="admin",
        display_name=display,
    )
    try:
        from core.workspace import ensure_user_dir

        ensure_user_dir(uid)
    except Exception:
        pass
    logger.info("已初始化管理员账号: {} (id={})", username, uid)
