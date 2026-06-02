"""API Key 鉴权中间件。"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from core.security.secrets import load_app_config, resolve_env_ref
from core.security.context import clear_request_context, set_request_context
from core.security.users import CurrentUser, decode_access_token

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_KEY_FILE = _PROJECT_ROOT / "data" / "security" / "api_key"

_DEFAULT_PUBLIC_PREFIXES = (
    "/",
    "/health",
    "/favicon.ico",
    "/static",
    "/api/security/status",
    "/api/auth/login",
    "/api/work",
)


@dataclass
class SecuritySettings:
    enabled: bool
    api_key: str
    allow_localhost_without_auth: bool
    public_prefixes: tuple[str, ...]
    auth_mode: str  # both | user_only | api_key_only


_settings_cache: SecuritySettings | None = None


def _read_or_create_api_key() -> str:
    if _KEY_FILE.is_file():
        return _KEY_FILE.read_text(encoding="utf-8").strip()
    key = secrets.token_urlsafe(32)
    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _KEY_FILE.write_text(key, encoding="utf-8")
    logger.warning(
        "已生成本地 API Key（请妥善保管）: {} — 建议设置环境变量 KEJI_API_KEY 覆盖",
        _KEY_FILE,
    )
    return key


def get_security_settings(reload: bool = False) -> SecuritySettings:
    global _settings_cache
    if _settings_cache is not None and not reload:
        return _settings_cache

    cfg = load_app_config()
    sec = cfg.get("security") or {}
    enabled = bool(sec.get("enabled", True))
    raw_key = sec.get("api_key", "${KEJI_API_KEY}")
    if isinstance(raw_key, str):
        api_key = resolve_env_ref(raw_key) if raw_key.startswith("${") else raw_key
    else:
        api_key = ""

    if not api_key and enabled:
        api_key = _read_or_create_api_key()

    extra_public = sec.get("public_paths") or []
    prefixes = tuple(_DEFAULT_PUBLIC_PREFIXES) + tuple(extra_public)

    auth_mode = str(sec.get("auth_mode", "both")).strip().lower()
    if auth_mode not in ("both", "user_only", "api_key_only"):
        auth_mode = "both"

    _settings_cache = SecuritySettings(
        enabled=enabled,
        api_key=api_key,
        allow_localhost_without_auth=bool(sec.get("allow_localhost_without_auth", False)),
        public_prefixes=prefixes,
        auth_mode=auth_mode,
    )
    return _settings_cache


def _is_public_path(path: str, prefixes: Iterable[str]) -> bool:
    for p in prefixes:
        if p == "/":
            if path == "/":
                return True
            continue
        if path == p or path.startswith(p.rstrip("/") + "/"):
            return True
    return False


def _is_localhost(request: Request) -> bool:
    if not request.client:
        return False
    host = request.client.host or ""
    return host in ("127.0.0.1", "::1", "localhost")


def _extract_api_key(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    header = request.headers.get("x-api-key")
    if header:
        return header.strip()
    return request.query_params.get("api_key")


def verify_api_key(request: Request, settings: SecuritySettings | None = None) -> bool:
    settings = settings or get_security_settings()
    if not settings.enabled:
        return True
    if settings.allow_localhost_without_auth and _is_localhost(request):
        return True
    if settings.auth_mode == "user_only":
        return False
    if not settings.api_key:
        return False
    provided = _extract_api_key(request)
    if not provided:
        return False
    return secrets.compare_digest(provided, settings.api_key)


def _looks_like_jwt(token: str) -> bool:
    return token.count(".") == 2


def authenticate_request(
    request: Request,
    settings: SecuritySettings | None = None,
) -> CurrentUser | None:
    """解析 JWT 或 API Key，返回当前用户。"""
    settings = settings or get_security_settings()
    if not settings.enabled:
        return CurrentUser(id="anonymous", username="guest", role="admin")

    token = _extract_api_key(request)
    if token:
        if settings.auth_mode != "api_key_only" and _looks_like_jwt(token):
            payload = decode_access_token(token)
            if payload and payload.get("sub"):
                from core.database.db import get_db

                row = get_db().get_user_by_id(str(payload["sub"]))
                if row and row.get("is_active"):
                    return CurrentUser(
                        id=row["id"],
                        username=row["username"],
                        role=row["role"],
                        display_name=row.get("display_name") or row["username"],
                    )
            if settings.auth_mode == "user_only":
                return None

        if settings.auth_mode != "user_only" and settings.api_key:
            if secrets.compare_digest(token, settings.api_key):
                return CurrentUser(
                    id="service",
                    username="api_key",
                    role="admin",
                    display_name="API Key",
                )

    if settings.allow_localhost_without_auth and _is_localhost(request):
        return CurrentUser(id="localhost", username="localhost", role="admin")
    return None


class APIKeyMiddleware(BaseHTTPMiddleware):
    """统一鉴权：登录 JWT + 可选服务 API Key。"""

    async def dispatch(self, request: Request, call_next):
        settings = get_security_settings()
        path = request.url.path
        client_ip = request.client.host if request.client else ""

        try:
            if not settings.enabled or _is_public_path(path, settings.public_prefixes):
                set_request_context(client_ip=client_ip, actor="api")
                return await call_next(request)

            user = authenticate_request(request, settings)
            if user is not None:
                request.state.user = user
                set_request_context(
                    client_ip=client_ip,
                    actor=user.username,
                    user_id=user.id,
                    role=user.role,
                )
                return await call_next(request)

            return JSONResponse(
                status_code=401,
                content={
                    "detail": "未授权：请登录（/api/auth/login）或使用有效 API Key",
                },
            )
        finally:
            clear_request_context()
