"""按账号角色限制 Agent 工具与文件路径（对话 / 工具调用）。"""

from __future__ import annotations

from core.security.context import get_request_context
from core.security.users import CurrentUser

# 写入/删除/执行类工具（只读账号禁止）
WRITE_TOOL_NAMES = frozenset({
    "write_file",
    "edit_file",
    "create_folder",
    "delete_file",
    "create_document",
    "create_table",
    "create_presentation",
    "index_knowledge",
    "remove_from_knowledge",
    "run_code",
    "db_execute_query",
    "organize_files",
    "format_data",
    "clean_data",
    "convert_data",
    "mcp_filesystem_write_file",
    "mcp_filesystem_edit_file",
    "mcp_filesystem_move_file",
    "mcp_filesystem_create_directory",
})

WRITE_TOOL_PREFIXES = (
    "mcp_quack_export_",
    "mcp_engineer-your-data_create_",
    "mcp_engineer-your-data_clean_",
    "mcp_engineer-your-data_export_",
)

# 只读账号仍可使用（查询/读文件/知识库检索等）
READONLY_EXTRA_ALLOWED = frozenset({
    "selfcheck_run",
    "verify_output",
    "read_document",
    "query_knowledge",
    "knowledge_stats",
    "analyze_data",
    "web_search",
    "browse_files",
    "search_files",
    "read_file",
    "list_allowed_directories",
    "db_connect",
    "get_time",
    "calculator",
    "ocr_image",
    "ocr_pdf",
    "parse_email",
    "__tool__",
})


def resolve_current_user() -> CurrentUser | None:
    """从请求上下文解析当前登录用户。"""
    ctx = get_request_context()
    if not ctx.user_id or ctx.user_id in ("anonymous", "localhost", "service"):
        return None
    if ctx.role in ("admin", "member", "readonly"):
        return CurrentUser(
            id=ctx.user_id,
            username=ctx.actor or ctx.user_id,
            role=ctx.role,
            display_name=ctx.actor or ctx.user_id,
        )
    from core.database.db import get_db

    row = get_db().get_user_by_id(ctx.user_id)
    if not row or not row.get("is_active"):
        return None
    return CurrentUser(
        id=row["id"],
        username=row["username"],
        role=row["role"],
        display_name=row.get("display_name") or row["username"],
    )


def is_write_tool(tool_name: str) -> bool:
    if not tool_name:
        return False
    if tool_name in WRITE_TOOL_NAMES:
        return True
    if tool_name.startswith("mcp_filesystem_"):
        return tool_name not in {
            "mcp_filesystem_list_allowed_directories",
            "mcp_filesystem_list_directory",
            "mcp_filesystem_list_directory_with_sizes",
            "mcp_filesystem_directory_tree",
            "mcp_filesystem_get_file_info",
            "mcp_filesystem_read_text_file",
            "mcp_filesystem_read_file",
            "mcp_filesystem_read_media_file",
            "mcp_filesystem_read_multiple_files",
            "mcp_filesystem_search_files",
        }
    return any(tool_name.startswith(p) for p in WRITE_TOOL_PREFIXES)


def tool_allowed_for_user(tool_name: str, user: CurrentUser | None) -> bool:
    if not user:
        return True
    if user.is_admin:
        return True
    if user.role != "readonly":
        return True
    if tool_name == "__tool__":
        return True
    if tool_name in READONLY_EXTRA_ALLOWED:
        return True
    return not is_write_tool(tool_name)


def role_permission_hint(user: CurrentUser | None) -> str:
    if not user:
        return ""
    if user.is_admin:
        return "当前为管理员：可使用全部工具并访问工作区内所有路径。"
    if user.role == "readonly":
        return (
            "当前为只读账号：仅可查询/读取，不可创建、修改、删除文件或执行写入类工具；"
            "文件路径仅限「共享文件」与「我的文件」。"
        )
    return "当前为成员账号：可读写共享目录与个人目录，不可访问其他用户私人文件夹。"
