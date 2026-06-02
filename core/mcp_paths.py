"""MCP filesystem 允许目录：解析、校验与注入 server-filesystem 参数。"""

from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

_FILESYSTEM_SERVER = "@modelcontextprotocol/server-filesystem"
_DEFAULT_REL_DIRS = ("knowledge", "data")


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def get_mcp_config(config: dict) -> dict:
    return config.get("mcp") or {}


def default_allowed_dir_entries() -> list[str]:
    """设置页默认展示：知识库 + 数据目录（相对项目根）。"""
    return list(_DEFAULT_REL_DIRS)


def normalize_dir_entry(entry: str, project_root: Path | None = None) -> Path | None:
    """将配置项解析为绝对路径；无效则返回 None。"""
    if not entry or not str(entry).strip():
        return None
    root = project_root or _project_root()
    raw = str(entry).strip().strip('"').strip("'")
    # 禁止明显危险的系统根
    lowered = raw.replace("\\", "/").lower()
    if lowered in ("c:/", "c:", "d:/", "d:", "/", "\\"):
        logger.warning("跳过不安全的 MCP 目录: {}", raw)
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = (root / p).resolve()
    else:
        p = p.resolve()
    if not p.exists():
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning("MCP 目录不可用 {}: {}", p, e)
            return None
    if not p.is_dir():
        logger.warning("MCP 路径不是目录: {}", p)
        return None
    return p


def resolve_filesystem_allowed_dirs(
    config: dict,
    project_root: Path | None = None,
) -> list[Path]:
    """从 config.mcp.filesystem_allowed_dirs 解析去重后的绝对路径列表。"""
    root = project_root or _project_root()
    mcp_cfg = get_mcp_config(config)
    entries = mcp_cfg.get("filesystem_allowed_dirs")
    if not entries:
        entries = default_allowed_dir_entries()
    elif not isinstance(entries, list):
        entries = [str(entries)]

    if mcp_cfg.get("include_knowledge", True):
        entries = list(entries) + ["knowledge"]
    if mcp_cfg.get("include_data", True):
        entries = list(entries) + ["data"]

    seen: set[str] = set()
    out: list[Path] = []
    for entry in entries:
        p = normalize_dir_entry(str(entry), root)
        if p is None:
            continue
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    if not out:
        for rel in _DEFAULT_REL_DIRS:
            p = normalize_dir_entry(rel, root)
            if p:
                out.append(p)
    return out


def dirs_for_display(config: dict, project_root: Path | None = None) -> list[str]:
    """供 API/设置页展示的路径字符串（绝对路径）。"""
    return [str(p) for p in resolve_filesystem_allowed_dirs(config, project_root)]


def apply_filesystem_args_to_mcp_servers(
    mcp_servers: dict,
    config: dict,
    project_root: Path | None = None,
) -> dict:
    """复制 mcp_servers 并为 filesystem 注入允许目录（不修改原 config 对象）。"""
    if not mcp_servers:
        return mcp_servers
    allowed = resolve_filesystem_allowed_dirs(config, project_root)
    if not allowed:
        return mcp_servers

    root = project_root or _project_root()
    out = {}
    for name, cfg in mcp_servers.items():
        cfg = dict(cfg)
        if name != "filesystem":
            out[name] = cfg
            continue
        # 运行时注入目录，忽略 yaml 里旧的路径参数
        cfg["command"] = cfg.get("command") or "npx"
        cfg["args"] = ["-y", _FILESYSTEM_SERVER] + [str(p) for p in allowed]
        out[name] = cfg
        logger.info("MCP filesystem 允许目录 ({}): {}", len(allowed), ", ".join(str(p) for p in allowed))
    return out
