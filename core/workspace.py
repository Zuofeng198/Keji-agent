"""团队文件工作区：共享目录 + 每用户目录 + 按角色访问控制。"""

from __future__ import annotations

import os
import re
from pathlib import Path

from core.security.users import CurrentUser

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_WORKSPACE_REL = Path("data") / "workspace"
_SHARED = "shared"
_USERS = "users"


class WorkspaceError(PermissionError):
    pass


def project_root() -> Path:
    return _PROJECT_ROOT


def workspace_root() -> Path:
    return (_PROJECT_ROOT / _WORKSPACE_REL).resolve()


def shared_dir() -> Path:
    return (workspace_root() / _SHARED).resolve()


def users_root() -> Path:
    return (workspace_root() / _USERS).resolve()


def user_dir(user_id: str) -> Path:
    safe = re.sub(r"[^\w\-]", "", (user_id or "").strip())[:64]
    if not safe:
        raise WorkspaceError("无效用户 ID")
    return (users_root() / safe).resolve()


def is_workspace_enabled(config: dict | None = None) -> bool:
    if config is None:
        from core.security.secrets import load_app_config

        config = load_app_config()
    ws = config.get("workspace") or {}
    if "enabled" in ws:
        return bool(ws.get("enabled"))
    return True


def ensure_layout() -> Path:
    """创建 workspace/shared 与 workspace/users。"""
    root = workspace_root()
    shared = shared_dir()
    users = users_root()
    for p in (root, shared, users):
        p.mkdir(parents=True, exist_ok=True)
    readme = shared / "README.txt"
    if not readme.is_file():
        readme.write_text(
            "此目录为全员共享文件夹。\n"
            "所有登录用户可浏览、上传；管理员可管理全部用户目录。\n",
            encoding="utf-8",
        )
    return root


def ensure_user_dir(user_id: str) -> Path:
    ensure_layout()
    ud = user_dir(user_id)
    ud.mkdir(parents=True, exist_ok=True)
    return ud


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _real_user(user: CurrentUser | None) -> bool:
    return bool(
        user
        and user.id
        and user.id not in ("anonymous", "localhost", "service", "api_key")
    )


def use_workspace_for_user(user: CurrentUser | None, config: dict | None = None) -> bool:
    if not is_workspace_enabled(config):
        return False
    return _real_user(user)


def can_write(path: Path, user: CurrentUser) -> bool:
    if user.role == "readonly":
        return False
    resolved = path.resolve()
    if user.is_admin:
        return _is_under(resolved, workspace_root())
    mine = user_dir(user.id)
    return _is_under(resolved, shared_dir()) or _is_under(resolved, mine)


def assert_access(
    path: str,
    user: CurrentUser,
    *,
    must_exist: bool = False,
    must_be_dir: bool = False,
    must_be_file: bool = False,
    write: bool = False,
) -> Path:
    """校验用户对工作区路径的访问权限。"""
    if not path or not str(path).strip():
        raise WorkspaceError("未提供路径")
    resolved = Path(str(path).strip()).resolve()
    root = workspace_root()
    if not _is_under(resolved, root):
        raise WorkspaceError("只能访问团队文件工作区内的路径")

    if user.is_admin:
        allowed = True
    else:
        mine = user_dir(user.id)
        allowed = _is_under(resolved, shared_dir()) or _is_under(resolved, mine)

    if not allowed:
        raise WorkspaceError("无权访问该路径（仅可访问共享文件与您自己的文件夹）")

    if write and not can_write(resolved, user):
        raise WorkspaceError("当前账号无写入权限")

    if must_exist and not resolved.exists():
        raise WorkspaceError(f"路径不存在：{resolved}")
    if must_be_dir and resolved.exists() and not resolved.is_dir():
        raise WorkspaceError(f"不是文件夹：{resolved}")
    if must_be_file and resolved.exists() and not resolved.is_file():
        raise WorkspaceError(f"不是文件：{resolved}")

    return resolved


def list_roots(user: CurrentUser) -> list[dict]:
    ensure_layout()
    ensure_user_dir(user.id)
    roots = [
        {
            "id": "shared",
            "name": "共享文件",
            "path": str(shared_dir()),
            "icon": "shared",
            "can_write": user.role != "readonly",
        },
        {
            "id": "mine",
            "name": "我的文件",
            "path": str(user_dir(user.id)),
            "icon": "mine",
            "can_write": user.role != "readonly",
        },
    ]
    if user.is_admin:
        roots.append(
            {
                "id": "users",
                "name": "全部用户",
                "path": str(users_root()),
                "icon": "users",
                "can_write": True,
            }
        )
    return roots


def default_list_path(user: CurrentUser) -> str:
    return str(shared_dir())


def path_display(path: str, user: CurrentUser) -> str:
    """面包屑友好路径。"""
    try:
        p = Path(path).resolve()
        root = workspace_root()
        rel = p.relative_to(root)
        parts = list(rel.parts)
        if not parts:
            return "工作区"
        if parts[0] == _SHARED:
            parts[0] = "共享文件"
        elif parts[0] == _USERS:
            parts[0] = "用户文件"
            if len(parts) >= 2:
                from core.database.db import get_db

                row = get_db().get_user_by_id(parts[1])
                if row:
                    parts[1] = row.get("display_name") or row.get("username") or parts[1]
        return " / ".join(parts)
    except Exception:
        return path


def policy_roots() -> list[Path]:
    """供 path_policy / MCP 合并的允许根目录。"""
    ensure_layout()
    return [workspace_root()]


def check_workspace_path(
    path: str,
    user: CurrentUser | None,
    **kwargs,
) -> tuple[str | None, str | None]:
    write = kwargs.pop("write", False)
    try:
        resolved = assert_access(path, user, write=write, **kwargs)
        return str(resolved), None
    except WorkspaceError as e:
        return None, f"错误：{e}"
