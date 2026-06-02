"""工具结果剪枝（无 LLM），供 nanobot 与 legacy agent 共用。"""

from __future__ import annotations

import json

_TAIL_TOKEN_BUDGET = 20000
_HEAD_PROTECT_COUNT = 4
_CHARS_PER_TOKEN = 4


def summarize_tool_result(tool_name: str, result: str, args: dict | None = None) -> str:
    if not result:
        return f"[{tool_name}] 返回空"

    content_len = len(result)
    line_count = result.count("\n") + 1 if result.strip() else 0
    args = args or {}

    if tool_name == "get_time":
        return f"[get_time] {result[:60]}"
    if tool_name == "calculator":
        return f"[calculator] {result[:80]}"
    if tool_name == "read_file":
        return f"[read_file] 读取 {args.get('filename', '?')} ({content_len:,} 字符)"
    if tool_name == "web_search":
        return f"[web_search] 搜索 '{args.get('query', '?')}' ({content_len:,} 字符结果)"
    if tool_name == "browse_files":
        return f"[browse_files] 浏览 {args.get('path', '?')} ({line_count} 项)"
    if tool_name == "search_files":
        return f"[search_files] 搜索 '{args.get('pattern', '?')}' ({line_count} 行)"
    if tool_name == "read_document":
        return f"[read_document] 读取 {args.get('path', '?')} ({content_len:,} 字符)"
    if tool_name == "query_knowledge":
        return f"[query_knowledge] 检索 '{args.get('query', '?')}' ({line_count} 条)"

    first_arg = ""
    for k, v in list(args.items())[:2]:
        first_arg += f" {k}={str(v)[:40]}"
    return f"[{tool_name}]{first_arg} ({content_len:,} 字符, {line_count} 行)"


def should_prune_messages(messages: list[dict]) -> bool:
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    for m in messages:
        for tc in m.get("tool_calls", []):
            total_chars += len(str(tc.get("function", {}).get("arguments", "")))
    return total_chars // _CHARS_PER_TOKEN > _TAIL_TOKEN_BUDGET * 1.5


def prune_tool_results(messages: list[dict]) -> list[dict]:
    n = len(messages)
    if n <= _HEAD_PROTECT_COUNT + 3:
        return messages

    result = [m.copy() for m in messages]
    call_id_to_tool: dict[str, tuple[str, str]] = {}
    for msg in result:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls", []):
                if isinstance(tc, dict):
                    cid = tc.get("id", "")
                    fn = tc.get("function", {})
                else:
                    cid = getattr(tc, "id", "") or ""
                    fn = getattr(tc, "function", None) or {}
                name = fn.get("name", "unknown") if isinstance(fn, dict) else "unknown"
                args_str = fn.get("arguments", "") if isinstance(fn, dict) else ""
                if cid:
                    call_id_to_tool[cid] = (name, args_str)

    accumulated = 0
    cut_idx = n
    min_tail = 3
    for i in range(n - 1, _HEAD_PROTECT_COUNT - 1, -1):
        msg = result[i]
        raw = msg.get("content") or ""
        content_len = len(raw) if isinstance(raw, str) else len(str(raw))
        msg_tokens = content_len // _CHARS_PER_TOKEN + 10
        for tc in msg.get("tool_calls", []):
            if isinstance(tc, dict):
                args = tc.get("function", {}).get("arguments", "")
                msg_tokens += len(args) // _CHARS_PER_TOKEN
        if accumulated + msg_tokens > _TAIL_TOKEN_BUDGET and (n - i) >= min_tail:
            break
        accumulated += msg_tokens
        cut_idx = i

    for i in range(_HEAD_PROTECT_COUNT, cut_idx):
        msg = result[i]
        if msg.get("role") != "tool":
            continue
        content = msg.get("content", "")
        if not content or not isinstance(content, str) or len(content) < 200:
            continue
        call_id = msg.get("tool_call_id", "")
        tool_name, tool_args_str = call_id_to_tool.get(call_id, ("unknown", "{}"))
        try:
            args = json.loads(tool_args_str) if tool_args_str else {}
        except (json.JSONDecodeError, TypeError):
            args = {}
        summary = summarize_tool_result(tool_name, content, args)
        result[i] = {**msg, "content": summary}

    return result
