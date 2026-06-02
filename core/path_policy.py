"""全局文件路径沙箱：与 MCP filesystem 共用 config.mcp 允许目录。"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from core.mcp_paths import _project_root, resolve_filesystem_allowed_dirs

_BOUNDARY_NOTE = (
    "（安全策略：仅允许访问设置中配置的文件目录，"
    "可在「设置 → MCP 文件访问范围」中调整）"
)


class PathPolicyError(PermissionError):
    """路径不在允许目录内。"""


def is_sandbox_enabled(config: dict | None = None) -> bool:
    if config is None:
        config = _load_config()
    sec = config.get("security") or {}
    if "filesystem_sandbox" in sec:
        return bool(sec.get("filesystem_sandbox"))
    return True


def _load_config() -> dict:
    from core.security.secrets import load_app_config
    return load_app_config(_project_root() / "config.yaml")


def get_allowed_roots(config: dict | None = None, project_root: Path | None = None) -> list[Path]:
    if config is None:
        config = _load_config()
    root = project_root or _project_root()
    try:
        from core.security.permissions import resolve_current_user
        from core.workspace import (
            ensure_layout,
            is_workspace_enabled,
            shared_dir,
            use_workspace_for_user,
            user_dir,
            workspace_root,
        )

        user = resolve_current_user()
        if user and use_workspace_for_user(user):
            ensure_layout()
            if user.is_admin:
                dirs = [workspace_root()]
                if is_sandbox_enabled(config):
                    for p in resolve_filesystem_allowed_dirs(config, root):
                        if not any(str(p).lower() == str(d).lower() for d in dirs):
                            dirs.append(p)
                return dirs
            return [shared_dir(), user_dir(user.id)]
    except Exception:
        pass
    if not is_sandbox_enabled(config):
        return []
    dirs = list(resolve_filesystem_allowed_dirs(config, root))
    try:
        from core.workspace import is_workspace_enabled, policy_roots, ensure_layout

        if is_workspace_enabled(config):
            ensure_layout()
            ws = policy_roots()[0]
            if not any(str(ws).lower() == str(d).lower() for d in dirs):
                dirs.append(ws)
    except Exception:
        pass
    return dirs


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def resolve_user_path(path: str, project_root: Path | None = None) -> Path:
    if not path or not str(path).strip():
        raise PathPolicyError("未提供路径")
    root = project_root or _project_root()
    p = Path(str(path).strip()).expanduser()
    if not p.is_absolute():
        p = root / p
    return p.resolve()


def assert_path_allowed(
    path: str,
    config: dict | None = None,
    project_root: Path | None = None,
    *,
    must_exist: bool = False,
    must_be_dir: bool = False,
    must_be_file: bool = False,
    write: bool = False,
) -> Path:
    """校验路径在允许目录下；通过则返回绝对路径。"""
    resolved = resolve_user_path(path, project_root)
    try:
        from core.security.permissions import resolve_current_user
        from core.workspace import use_workspace_for_user, assert_access as ws_assert

        user = resolve_current_user()
        if user and use_workspace_for_user(user):
            return ws_assert(
                str(resolved),
                user,
                must_exist=must_exist,
                must_be_dir=must_be_dir,
                must_be_file=must_be_file,
                write=write,
            )
    except Exception as e:
        if isinstance(e, PermissionError):
            raise PathPolicyError(str(e)) from e
        raise
    roots = get_allowed_roots(config, project_root)
    if roots and not any(is_under(resolved, r) for r in roots):
        allowed_hint = "、".join(str(r) for r in roots[:5])
        if len(roots) > 5:
            allowed_hint += " …"
        raise PathPolicyError(
            f"路径「{resolved}」不在允许访问范围内。允许目录：{allowed_hint} {_BOUNDARY_NOTE}"
        )
    if must_exist and not resolved.exists():
        raise PathPolicyError(f"路径不存在：{resolved}")
    if must_be_dir and resolved.exists() and not resolved.is_dir():
        raise PathPolicyError(f"不是文件夹：{resolved}")
    if must_be_file and resolved.exists() and not resolved.is_file():
        raise PathPolicyError(f"不是文件：{resolved}")
    return resolved


def check_path(
    path: str,
    config: dict | None = None,
    project_root: Path | None = None,
    **kwargs,
) -> tuple[str | None, str | None]:
    """工具友好接口：成功返回 (abspath, None)，失败返回 (None, 错误文案)。"""
    if not path or not str(path).strip():
        if kwargs.get("allow_empty"):
            roots = get_allowed_roots(config, project_root)
            if roots:
                return str(roots[0]), None
        return None, "错误：未提供路径"
    try:
        resolved = assert_path_allowed(path, config, project_root, **kwargs)
        return str(resolved), None
    except PathPolicyError as e:
        return None, f"错误：{e}"


def format_allowed_directories_text(
    config: dict | None = None,
    project_root: Path | None = None,
) -> str:
    """供系统提示或工具返回的人类可读目录列表。"""
    if config is None:
        config = _load_config()
    try:
        from core.security.permissions import resolve_current_user, role_permission_hint
        from core.workspace import use_workspace_for_user

        user = resolve_current_user()
        if user and use_workspace_for_user(user):
            roots = get_allowed_roots(config, project_root)
            lines = "\n".join(f"- {p}" for p in roots)
            hint = role_permission_hint(user)
            return f"允许访问的目录（共 {len(roots)} 个）：\n{lines}\n{hint}"
    except Exception:
        pass
    if not is_sandbox_enabled(config):
        return "文件沙箱已关闭：可访问本机任意路径（仍受操作系统权限限制）。"
    roots = get_allowed_roots(config, project_root)
    if not roots:
        return "文件沙箱已开启，但未配置允许目录；请在设置 → 文件访问范围中添加。"
    lines = "\n".join(f"- {p}" for p in roots)
    return f"允许访问的目录（共 {len(roots)} 个）：\n{lines}\n{_BOUNDARY_NOTE}"


def list_allowed_directories() -> str:
    """科吉内置工具：返回当前生效的全局允许目录。"""
    return format_allowed_directories_text()


def default_browse_path(config: dict | None = None, project_root: Path | None = None) -> str:
    roots = get_allowed_roots(config, project_root)
    if roots:
        return str(roots[0])
    return os.path.expanduser("~\\Desktop")


def run_code_sandbox_preamble(project_root: Path) -> str:
    """注入 run_code 子进程，限制 open() 读写路径。"""
    roots = get_allowed_roots(project_root=project_root)
    if not roots:
        return ""
    roots_repr = repr([str(p) for p in roots])
    return f"""
# --- 科吉文件沙箱（自动注入）---
import os as _os
from pathlib import Path as _Path

_SANDBOX_ROOTS = [{", ".join(repr(str(p)) for p in roots)}]

def _keji_under(_p, _root):
    try:
        _p.resolve().relative_to(_Path(_root).resolve())
        return True
    except ValueError:
        return False

def _keji_guard_path(_file):
    _p = _Path(_file)
    if not _p.is_absolute():
        _p = _Path({str(project_root)!r}) / _p
    _p = _p.resolve()
    if not any(_keji_under(_p, _r) for _r in _SANDBOX_ROOTS):
        raise PermissionError(
            "路径 " + str(_p) + " 不在允许目录内。允许: " + ", ".join(_SANDBOX_ROOTS)
        )
    return _p

_orig_open = open
def open(file, mode="r", *args, **kwargs):
    if isinstance(file, (str, _Path)):
        _m = mode or "r"
        if any(c in _m for c in "rwa+x"):
            _keji_guard_path(file)
    return _orig_open(file, mode, *args, **kwargs)
# --- 沙箱结束 ---
"""
