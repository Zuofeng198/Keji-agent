"""审计日志：工具调用与文件访问。"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from loguru import logger

from core.security.context import get_request_context
from core.security.secrets import mask_secrets

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_FILE_TOOL_NAMES = frozenset({
    "read_file", "write_file", "edit_file", "list_dir", "glob", "grep",
    "delete_file", "read_document", "create_document", "create_table",
    "create_presentation", "organize_files", "rename_files",
    "deduplicate_files", "browse_archive", "extract_archive", "create_archive",
    "ocr_image", "ocr_pdf", "ocr_batch", "index_knowledge",
})

_PATH_PARAM_KEYS = (
    "path", "save_path", "file_path", "directory", "dir", "source", "target",
    "src", "dst", "folder", "root", "filename",
)

_mcp_fs_prefix = "mcp_filesystem_"


class AuditLogger:
    def __init__(self, log_file: Path, enabled: bool = True, max_param_length: int = 500):
        self.enabled = enabled
        self.log_file = log_file
        self.max_param_length = max_param_length
        self._lock = threading.Lock()
        if enabled:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, record: dict[str, Any]) -> None:
        if not self.enabled:
            return
        record.setdefault("ts", time.time())
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        try:
            from core.database.db import get_db
            get_db().log_audit_event(
                event_type=record.get("event_type", ""),
                actor=record.get("actor", "api"),
                session_id=record.get("session_id", ""),
                tool_name=record.get("tool_name", ""),
                path=record.get("path", ""),
                action=record.get("action", ""),
                status=record.get("status", "ok"),
                detail=record.get("detail", "")[:2000],
                client_ip=record.get("client_ip", ""),
            )
        except Exception as exc:
            logger.debug("audit db write skipped: {}", exc)

    def log_tool_call(
        self,
        tool_name: str,
        params: dict[str, Any] | None,
        *,
        status: str = "ok",
        duration_ms: int = 0,
        error: str = "",
        result_preview: str = "",
    ) -> None:
        ctx = get_request_context()
        safe_params = mask_secrets(params or {})
        param_str = json.dumps(safe_params, ensure_ascii=False, default=str)
        if len(param_str) > self.max_param_length:
            param_str = param_str[: self.max_param_length] + "…"

        self._write({
            "event_type": "tool_call",
            "actor": ctx.actor,
            "session_id": ctx.session_id,
            "client_ip": ctx.client_ip,
            "tool_name": tool_name,
            "status": status,
            "duration_ms": duration_ms,
            "params": param_str,
            "error": error[:500] if error else "",
            "result_preview": (result_preview or "")[:300],
        })

        paths = _extract_paths(tool_name, params or {})
        for path, action in paths:
            self.log_file_access(path, action, status=status, tool_name=tool_name)

    def log_file_access(
        self,
        path: str,
        action: str,
        *,
        status: str = "ok",
        tool_name: str = "",
        detail: str = "",
    ) -> None:
        if not path:
            return
        ctx = get_request_context()
        self._write({
            "event_type": "file_access",
            "actor": ctx.actor,
            "session_id": ctx.session_id,
            "client_ip": ctx.client_ip,
            "tool_name": tool_name,
            "path": str(path)[:1024],
            "action": action,
            "status": status,
            "detail": detail[:500],
        })


def _extract_paths(tool_name: str, params: dict[str, Any]) -> list[tuple[str, str]]:
    paths: list[tuple[str, str]] = []
    action = _infer_file_action(tool_name)

    for key in _PATH_PARAM_KEYS:
        val = params.get(key)
        if isinstance(val, str) and val.strip():
            paths.append((val.strip(), action or key))

    if tool_name.startswith(_mcp_fs_prefix) or tool_name in _FILE_TOOL_NAMES:
        for k, v in params.items():
            if isinstance(v, str) and ("/" in v or "\\" in v) and len(v) < 512:
                if k not in {p for p, _ in paths}:
                    paths.append((v, action or tool_name))

    return paths


def _infer_file_action(tool_name: str) -> str:
    if "read" in tool_name or tool_name in ("glob", "grep", "list_dir", "browse_archive"):
        return "read"
    if "write" in tool_name or "create" in tool_name or "edit" in tool_name:
        return "write"
    if "delete" in tool_name:
        return "delete"
    if tool_name.startswith(_mcp_fs_prefix):
        if "read" in tool_name:
            return "read"
        if "write" in tool_name or "edit" in tool_name:
            return "write"
        if "list" in tool_name:
            return "list"
    return "access"


_audit: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    global _audit
    if _audit is not None:
        return _audit
    from core.security.secrets import load_app_config
    cfg = load_app_config()
    audit_cfg = cfg.get("audit") or {}
    log_path = audit_cfg.get("file", "logs/audit.jsonl")
    if not Path(log_path).is_absolute():
        log_path = _PROJECT_ROOT / log_path
    _audit = AuditLogger(
        log_file=Path(log_path),
        enabled=bool(audit_cfg.get("enabled", True)),
        max_param_length=int(audit_cfg.get("max_param_length", 500)),
    )
    return _audit


def audit_tool_call(
    tool_name: str,
    params: dict[str, Any] | None,
    *,
    status: str = "ok",
    duration_ms: int = 0,
    error: str = "",
    result_preview: str = "",
) -> None:
    get_audit_logger().log_tool_call(
        tool_name,
        params,
        status=status,
        duration_ms=duration_ms,
        error=error,
        result_preview=result_preview,
    )


def audit_file_access(
    path: str,
    action: str,
    *,
    status: str = "ok",
    tool_name: str = "",
    detail: str = "",
) -> None:
    get_audit_logger().log_file_access(
        path, action, status=status, tool_name=tool_name, detail=detail
    )
