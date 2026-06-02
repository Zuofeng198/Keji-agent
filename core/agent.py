import json
import re
import os
import yaml
import time
from typing import Generator, Optional

from core.models import ModelRouter
from core.tools import call_tools_parallel, list_tools
from core.memory import ConversationMemory, SummaryMemory
from core.logger import setup_logger
from core.rag.vector_store import get_vector_store
from core.database.db import get_db
from prompts.sys_prompt import get_system_prompt, get_json_retry_prompt

logger = setup_logger("keji.agent")


# ---------------------------------------------------------------------------
# Context compression — tool result pruning (no LLM call)
# ---------------------------------------------------------------------------

from core.context_prune import (  # noqa: E402
    prune_tool_results as _prune_tool_results,
    should_prune_messages as _should_compress,
    summarize_tool_result as _summarize_tool_result,
)


def _format_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def _summarize_messages(messages: list[dict]) -> str:
    """将消息列表格式化为简短的上下文摘要（用于注入回 system prompt）"""
    parts = []
    for m in messages:
        role = m.get("role", "unknown")
        content = m.get("content", "")
        if isinstance(content, str) and content:
            # 只取前 200 字符
            content = content[:200]
            parts.append(f"[{role}]: {content}")
        elif m.get("tool_calls"):
            tools = [tc.get("function", {}).get("name", "?") for tc in m.get("tool_calls", [])]
            parts.append(f"[{role}]: 调用了 {', '.join(tools)}")
    return "\n".join(parts[-20:])  # 只保留最近 20 条


MAX_JSON_RETRIES = 2

# ---------------------------------------------------------------------------
# Plan-and-Execute 规划提示词
# ---------------------------------------------------------------------------

PLANNING_PROMPT = """你是科吉，一个智能任务规划专家。

用户会给你一个任务请求。请分析这个任务，并制定一个详细的执行计划。

输出格式为 JSON，不要包含任何其他文字：
{
    "title": "一句话概括计划",
    "steps": [
        {
            "step": 1,
            "description": "步骤描述（简明扼要，让用户看懂要做什么）",
            "tool": "工具名",
            "arguments": {"参数名": "参数值"}
        }
    ]
}

规划原则（重要！）：
1. **宁可合并不要拆分** — 能用 run_code 一个步骤搞定的，不要拆成多个步骤
2. 每个 steps 只调用一个工具
3. 描述要写清楚做什么，让用户能看懂
4. 工具名必须是可用工具列表中的
5. **永远不要输出 steps: []** — 除非用户只是问了一个纯知识问题（比如"什么是AI"）。如果用户要求"做"任何事（创建文档、生成PPT、分析数据、整理文件、搜索信息等），必须调用相关工具
6. 对于"生成/创建文档/PPT/表格"等任务，必须使用 run_code 工具，在代码中调用 create_presentation / create_document / create_table 等函数完成
"""

# 前置强制过滤：命中任意关键词即强制要求调用工具
_MUST_CALL_KEYWORDS = frozenset({
    "查", "搜索", "获取", "执行", "运行", "修改", "写入", "读取",
    "生成", "下载", "上传", "处理", "计算", "统计", "分析", "同步",
    "创建", "删除", "复制", "移动", "重命名", "合并", "拆分",
    "制表", "做报表", "写报告", "做PPT", "做演示",
    "帮我", "给我", "请你", "帮我",
})


def _must_use_tool(query: str) -> bool:
    """前置强制过滤：命中硬编码规则 → 必须调用工具"""
    if not query:
        return False
    for keyword in _MUST_CALL_KEYWORDS:
        if keyword in query:
            return True
    # 匹配 "第X个" "X份" 等数量指令
    if re.search(r'[\d一二三四五六七八九十]+[份个张篇封份本]', query):
        return True
    return False


def _load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 从数据库读取动态模型配置，覆盖 config.yaml
    try:
        from core.database.db import get_db
        db = get_db()
        model_type = db.get_setting("model_type", "")
        if model_type in ("ollama", "openai"):
            config.setdefault("models", {})["default"] = model_type
            if model_type == "ollama":
                ollama_cfg = config.setdefault("models", {}).setdefault("ollama", {})
                url = db.get_setting("ollama_url", "")
                if url:
                    ollama_cfg["base_url"] = url
                model = db.get_setting("chat_model", "")
                if model:
                    ollama_cfg["model"] = model
            elif model_type == "openai":
                openai_cfg = config.setdefault("models", {}).setdefault("openai", {})
                url = db.get_setting("openai_base_url", "")
                if url:
                    openai_cfg["base_url"] = url
                key = db.get_setting("openai_api_key", "")
                if key:
                    openai_cfg["api_key"] = key
                model = db.get_setting("openai_model", "")
                if model:
                    openai_cfg["model"] = model
    except Exception:
        pass

    return config


def _extract_json_object(text: str) -> list[str]:
    """从文本中提取所有顶层 JSON 对象/数组，正确处理嵌套括号

    候选排序（按置信度从高到低）：
    1. ```json 代码块（必定是 JSON）
    2. 平衡括号匹配提取的 {} / []（人工检查是否含 name 键）
    3. 清理后的完整原文（兜底）
    """
    results = []

    # 1. 提取 ```json 代码块（置信度最高）
    for match in re.finditer(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL):
        candidate = match.group(1).strip()
        if candidate:
            results.append(candidate)

    # 2. 用平衡括号匹配提取顶层 JSON 对象/数组
    i = 0
    while i < len(text):
        if text[i] == '{':
            depth = 0
            start = i
            for j in range(i, len(text)):
                if text[j] == '{':
                    depth += 1
                elif text[j] == '}':
                    depth -= 1
                    if depth == 0:
                        results.append(text[start:j + 1])
                        i = j
                        break
        elif text[i] == '[':
            depth = 0
            start = i
            for j in range(i, len(text)):
                if text[j] == '[':
                    depth += 1
                elif text[j] == ']':
                    depth -= 1
                    if depth == 0:
                        results.append(text[start:j + 1])
                        i = j
                        break
        i += 1

    # 3. 清理后的完整原文作为兜底（纯 JSON 输出时直接命中）
    cleaned = text.strip().strip("`").strip()
    if cleaned.startswith("json"):
        cleaned = cleaned[4:].strip()
    if cleaned and cleaned not in results:
        results.append(cleaned)

    return results


def _normalize_tool_call(parsed) -> Optional[list[dict]]:
    """将解析后的 JSON 标准化为工具调用列表"""
    if isinstance(parsed, list):
        calls = []
        for item in parsed:
            if isinstance(item, dict) and "name" in item:
                args = item.get("arguments", {})
                if isinstance(args, list):
                    args = {f"arg{i}": v for i, v in enumerate(args)}
                calls.append({"name": item["name"], "arguments": args})
        return calls if calls else None
    elif isinstance(parsed, dict) and "name" in parsed:
        args = parsed.get("arguments", {})
        if isinstance(args, list):
            args = {f"arg{i}": v for i, v in enumerate(args)}
        return [{"name": parsed["name"], "arguments": args}]
    return None


def _parse_function_calls(text: str) -> tuple[list[dict], Optional[str]]:
    # 从文本中提取所有可能的 JSON 候选
    candidates = _extract_json_object(text)

    # 旧版 !TOOL: 格式
    if not candidates:
        for match in re.finditer(r'!TOOL:\s*(\{.*?\})', text, re.DOTALL):
            try:
                data = json.loads(match.group(1))
                return [{"name": data.get("tool"), "arguments": data.get("args", {})}], None
            except json.JSONDecodeError:
                pass

    # 依次尝试解析每个候选
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            calls = _normalize_tool_call(parsed)
            if calls:
                return calls, None
        except json.JSONDecodeError:
            continue

    # 自动修复常见 JSON 错误后再试
    for candidate in candidates:
        repaired = _repair_json(candidate)
        if repaired:
            try:
                parsed = json.loads(repaired)
                calls = _normalize_tool_call(parsed)
                if calls:
                    return calls, None
            except json.JSONDecodeError:
                continue

    return [], f"无法从输出中解析出有效的 JSON 工具调用。输出内容：{text[:300]}"


def _repair_json(text: str) -> Optional[str]:
    """尝试修复常见 JSON 错误，实在不行就返回 None"""
    candidates = [text]
    # 用反斜杠转义过的未闭合引号
    text2 = re.sub(r'(?<!\\)"(?=\s*[},\]])', '\\"', text)
    if text2 != text:
        candidates.append(text2)
    # 将单引号替换为双引号
    text3 = text.replace("'", '"')
    if text3 != text:
        candidates.append(text3)
    # 移除多余尾部逗号
    text4 = re.sub(r',\s*}', '}', text)
    text5 = re.sub(r',\s*]', ']', text4)
    if text5 != text:
        candidates.append(text5)
    # 给键名加引号: {name: "val"} -> {"name": "val"}
    text6 = re.sub(r'([{,]\s*)(\w+)(\s*:)', r'\1"\2"\3', text)
    if text6 != text:
        candidates.append(text6)

    for c in candidates:
        try:
            json.loads(c)
            return c
        except json.JSONDecodeError:
            continue
    return None


class CoreAgent:
    """科吉 Agent 核心引擎 —— ReAct 循环 + 并行工具 + 流式输出 + RAG"""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or _load_config()
        self.agent_config = self.config.get("agent", {})
        self.tools_config = self.config.get("tools", {})
        self.knowledge_config = self.config.get("knowledge", {})

        self.max_rounds = self.agent_config.get("max_tool_rounds", 5)
        self.temperature = self.agent_config.get("temperature", 0.7)
        self.enabled_tools = self.tools_config.get("enabled", [])
        self.use_knowledge = self.agent_config.get("use_knowledge", True)
        self.knowledge_top_k = self.agent_config.get("knowledge_top_k", 3)

        self.router = ModelRouter(self.config)
        self.model = self.router.get()

        self.memory = ConversationMemory(max_messages=40)
        self.summary_memory = SummaryMemory(recent_rounds=4)
        self._current_conv_id = ""
        self._pending_answer_tokens = None
        self._pending_decision = None
        self._gatekeeper_force_tool = False  # 前置过滤：是否强制调工具
        self._self_check_retries = 0  # 自检重试计数

    def _should_compress(self, messages: list[dict]) -> bool:
        """检查当前消息列表是否需要上下文压缩"""
        return _should_compress(messages)

    def _compress_context(self, messages: list[dict]) -> list[dict]:
        """执行上下文压缩：剪枝工具结果"""
        return _prune_tool_results(messages)

    def _get_knowledge_context(self, query: str) -> str:
        """从知识库检索相关上下文"""
        if not self.use_knowledge:
            return ""

        try:
            # 快速检查 Ollama 是否可用，不可用则跳过知识库
            try:
                import requests as _req
                _req.get("http://localhost:11434/api/tags", timeout=1)
            except Exception:
                return ""

            vs = get_vector_store()
            if vs.count() == 0:
                return ""
            results = vs.search(query, n_results=self.knowledge_top_k)
            if not results:
                return ""

            parts = []
            for i, r in enumerate(results, 1):
                meta = r.get("metadata", {})
                source = meta.get("file_name", "未知文档")
                parts.append(
                    f"[知识片段 {i}] 来源: {source}\n{r['content'][:600]}"
                )
            return "\n\n" + "\n---\n".join(parts)
        except Exception as e:
            logger.debug("Knowledge retrieval failed: %s", e)
            return ""

    def _build_tool_prompt(self) -> str:
        tools_info = list_tools(self.enabled_tools)
        if not tools_info:
            return ""

        # run_code 是主工具，其他是辅助
        main_tools = [t for t in tools_info if t["name"] == "run_code"]
        other_tools = [t for t in tools_info if t["name"] != "run_code"]

        lines = []
        if main_tools:
            lines.append("=== 主要工具：run_code ===")
            lines.append("写 Python 代码一次性完成所有操作。")
            lines.append('{"name": "run_code", "arguments": {"code": "你的Python代码"}}')

        if other_tools:
            names = ", ".join(t["name"] for t in other_tools)
            lines.append(f"\n=== 辅助工具：{names} ===")
            lines.append("简单查询可单独调用，格式同上。")

        lines.append("\n需要工具时只输出上述 JSON，不需要就直接回答。")
        return "\n".join(lines)


    def _has_json_attempt(self, text: str) -> bool:
        """检测模型是否真的输出了 JSON 格式的工具调用（而不是只提了工具名）"""
        # 明确输出 !TOOL: 前缀
        if re.search(r'!TOOL:', text):
            return True
        # ```json 代码块 + 大括号/方括号开头
        if re.search(r'```json\s*[\{\[]', text, re.DOTALL):
            return True
        # 纯 JSON 对象：以 { 开头且包含 "name" 键
        if re.search(r'^\s*\{\s*"name"\s*:', text, re.MULTILINE):
            return True
        # 纯 JSON 数组：以 [ 开头且元素包含 "name" 键
        if re.search(r'^\s*\[\s*\{\s*"name"\s*:', text, re.MULTILINE):
            return True
        # 行内出现 {"name": 或 [{"name":
        if re.search(r'\{"name"\s*:', text) or re.search(r'\[\s*\{\s*"name"\s*:', text):
            return True
        return False

    def _step_with_retry(self, messages: list[dict]) -> dict:
        enhanced = list(messages)
        for retry in range(MAX_JSON_RETRIES + 1):
            raw = self.model.chat(enhanced, temperature=self.temperature)
            calls, error = _parse_function_calls(raw)

            if calls:
                logger.debug("Parsed %d tool calls (retry=%d)", len(calls), retry)
                return {"content": raw, "function_calls": calls}

            if not self._has_json_attempt(raw):
                logger.debug("No JSON attempt detected, treating as plain answer")
                return {"content": raw, "function_calls": []}

            if retry < MAX_JSON_RETRIES and error:
                logger.warning("JSON parse failed (retry=%d): %.80s", retry, error)
                enhanced.append({"role": "assistant", "content": raw})
                enhanced.append({
                    "role": "user",
                    "content": get_json_retry_prompt(error),
                })
            else:
                logger.warning("JSON parse exhausted, treating as plain answer")
                return {"content": raw, "function_calls": []}

        return {"content": raw, "function_calls": []}

    def _stream_and_decode(self, messages: list[dict]) -> Generator[dict, None, None]:
        """流式获取模型输出，实时 yield token，最后决定是工具调用还是回答"""
        buffered = ""
        all_tokens = []

        for token in self.model.chat_stream(messages, temperature=self.temperature):
            buffered += token
            all_tokens.append(token)
            yield {"phase": "think_token", "token": token}

        calls, error = _parse_function_calls(buffered)
        if calls:
            yield {"phase": "think_done", "tool_call": True, "tools": [c["name"] for c in calls]}
            self._pending_decision = {"content": buffered, "function_calls": calls}
            return

        for retry in range(MAX_JSON_RETRIES):
            if not self._has_json_attempt(buffered):
                break
            retry_prompt = get_json_retry_prompt(error or "JSON格式错误")
            retry_messages = list(messages)
            retry_messages.append({"role": "assistant", "content": buffered})
            retry_messages.append({"role": "user", "content": retry_prompt})
            buffered = ""
            for token in self.model.chat_stream(retry_messages, temperature=self.temperature):
                buffered += token
                all_tokens.append(token)
                yield {"phase": "think_token", "token": token}
            calls, error = _parse_function_calls(buffered)
            if calls:
                yield {"phase": "think_done", "tool_call": True, "tools": [c["name"] for c in calls]}
                self._pending_decision = {"content": buffered, "function_calls": calls}
                return

        # 守门人逻辑：前置过滤判定必须调工具，但模型没调 → 强制重试
        if self._gatekeeper_force_tool:
            gatekeeper_prompt = (
                "【系统强制指令】你刚才没有调用任何工具，但当前请求必须使用工具才能完成。\n"
                "请立即选择正确的工具并输出 JSON 调用，不要用文字假装完成任务，不要输出任何解释。\n"
                "如果仍不调用工具，你的输出将被丢弃。"
            )
            gm = list(messages)
            gm.append({"role": "assistant", "content": buffered})
            gm.append({"role": "user", "content": gatekeeper_prompt})
            buffered = ""
            all_tokens = []
            for token in self.model.chat_stream(gm, temperature=self.temperature):
                buffered += token
                all_tokens.append(token)
                yield {"phase": "think_token", "token": token}
            calls, error = _parse_function_calls(buffered)
            if calls:
                yield {"phase": "think_done", "tool_call": True, "tools": [c["name"] for c in calls]}
                self._pending_decision = {"content": buffered, "function_calls": calls}
                return

        yield {"phase": "think_done", "tool_call": False}
        # 不 yield answer token，存到 _pending_answer_tokens 由调用方决定何时输出
        self._pending_answer_tokens = all_tokens

    def _emit_answer(self):
        """将缓存的 answer token 输出"""
        if self._pending_answer_tokens:
            for t in self._pending_answer_tokens:
                yield {"phase": "answer", "token": t}
            self._pending_answer_tokens = None

    def _react_loop_stream(self, user_query: str, files: Optional[list] = None) -> Generator[dict, None, None]:
        """流式 ReAct 循环，自动注入知识库上下文，流式显示思考过程"""
        system_prompt = get_system_prompt("assistant", self.enabled_tools)
        tool_prompt = self._build_tool_prompt()
        if tool_prompt:
            system_prompt += "\n\n" + tool_prompt
        messages = [{"role": "system", "content": system_prompt}]

        knowledge_ctx = self._get_knowledge_context(user_query)
        if knowledge_ctx:
            context_msg = (
                f"以下是知识库中与用户问题可能相关的参考资料：\n"
                f"{knowledge_ctx}\n\n"
                f"请参考以上资料回答用户问题，如果资料不相关则忽略。"
            )
            messages.append({"role": "system", "content": context_msg})
            yield {"phase": "knowledge", "context": knowledge_ctx[:200]}

        # 注入上传文件上下文
        file_ctx = self._get_file_context(files or [])
        if file_ctx:
            messages.append({"role": "system", "content": file_ctx})
            yield {"phase": "files", "count": len(files or [])}

        history = self.memory.get_all(self._current_conv_id)

        # 上下文中历史太多时，压缩旧工具结果释放空间
        if history and _should_compress(history):
            history = _prune_tool_results(history)
            logger.info("Context compressed: %d history messages pruned", len(history))

        messages.extend(history)
        messages.append({"role": "user", "content": user_query})

        # 重置状态
        self._gatekeeper_force_tool = _must_use_tool(user_query)
        self._self_check_done = False

        all_tool_results = []
        self._pending_decision = None

        for round_num in range(1, self.max_rounds + 1):
            logger.info("ReAct round %d/%d", round_num, self.max_rounds)
            yield {"phase": "thinking", "round": round_num}

            for event in self._stream_and_decode(messages):
                yield event

            decision = self._pending_decision
            self._pending_decision = None
            function_calls = decision.get("function_calls", []) if decision else []

            # 记录模型的工具调用输出，让模型知道自己操作过什么
            if decision and decision.get("content"):
                messages.append({"role": "assistant", "content": decision["content"]})

            # 已有工具结果后，模型边答边调新工具 → 画蛇添足，直接结束
            if function_calls and all_tool_results and decision and decision.get("content", "").strip():
                logger.info("Model answered while calling tools, breaking loop")
                break

            if not function_calls:
                # 自检（仅一次）：提示工具执行错误，之后让模型自己判断
                if all_tool_results and not getattr(self, "_self_check_done", False):
                    failed_tools = []
                    for r in all_tool_results:
                        if r["tool"] == "run_code":
                            continue
                        result = r["result"]
                        if result.startswith("错误：") or result.startswith("工具执行出错") or "执行超时" in result or "不存在" in result:
                            failed_tools.append(r["tool"])
                    if failed_tools:
                        self._self_check_done = True
                        yield {"phase": "self_check", "round": round_num}
                        check_msg = (
                            f"注意：以下工具执行出错了：{', '.join(failed_tools)}。"
                            f"如果需要可以修正参数重新调用，否则直接回答用户。"
                        )
                        messages.append({"role": "user", "content": check_msg})
                        for event in self._stream_and_decode(messages):
                            if event.get("phase") in ("think_token", "think_done"):
                                yield event
                        self._pending_answer_tokens = None
                        decision = self._pending_decision
                        self._pending_decision = None
                        function_calls = decision.get("function_calls", []) if decision else []
                        if not function_calls:
                            break
                        # 模型决定重试工具，继续循环
                    else:
                        # 工具全部成功→直接回答
                        break
                else:
                    # 没调过工具，或自检已完成→输出回答
                    for event in self._emit_answer():
                        yield event
                    return

            yield {"phase": "tool_call", "tools": [c["name"] for c in function_calls]}

            results = call_tools_parallel(function_calls)

            # 截断过长结果（OCR/文档/邮件等工具的结果内容是模型需要的，不截断）
            for r in results:
                if len(r["result"]) > 500 and r["tool"] not in (
                    "ocr_image", "ocr_pdf", "ocr_batch",
                    "read_document", "read_file",
                    "parse_email", "batch_parse_emails",
                ):
                    r["result"] = _summarize_tool_result(r["tool"], r["result"], r.get("args", {}))
            all_tool_results.extend(results)

            for r in results:
                yield {"phase": "tool_result", "tool": r["tool"], "result": r["result"]}

            tool_summary = "\n".join(
                f"[{r['tool']}]: {r['result']}" for r in results
            )

            messages.append({
                "role": "user",
                "content": f"[工具返回]\n{tool_summary}\n\n"
                           f"如果你已经从工具结果中获取了足够的信息，请直接给出最终答案。"
                           f"不要重复调用已经用过的工具，也不要调用无关工具。",
            })

        yield {"phase": "answering"}
        self._pending_answer_tokens = None  # 用最终回答取代缓存
        final_prompt = (
            f"用户原始问题：{user_query}\n\n"
            f"工具调用结果：\n{json.dumps(all_tool_results, ensure_ascii=False, indent=2)}\n\n"
            "请综合以上信息给出完整回答。"
        )
        final_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": final_prompt},
        ]
        for token in self.model.chat_stream(final_messages, temperature=self.temperature):
            yield {"phase": "answer", "token": token}

    def _save_conversation(self, query: str, reply: str):
        """保存对话到数据库"""
        self._save_conversation_with_id(self._current_conv_id, query, reply)

    def _save_conversation_with_id(self, conv_id: str, query: str, reply: str):
        """保存对话到数据库（使用指定的 conv_id）"""
        if not conv_id:
            logger.warning("Save conversation skipped: empty conv_id")
            return
        try:
            db = get_db()
            conv = db.get_conversation(conv_id)
            if not conv:
                title = query[:30] + ("..." if len(query) > 30 else "")
                db.create_conversation(conv_id, title)
                logger.info("Conversation created: %s -> %s", conv_id, title)
            db.add_message(conv_id, "user", query)
            db.add_message(conv_id, "assistant", reply)
            logger.info("Conversation saved: %s (%d chars reply)", conv_id, len(reply))
        except Exception as e:
            logger.warning("Save conversation failed: %s", e)

    def _auto_load_memory(self):
        """如果当前对话有历史但记忆为空，从 DB 自动加载"""
        if not self._current_conv_id:
            return
        if self.memory.get_all(self._current_conv_id):
            return  # 已有记忆
        try:
            from core.database.db import get_db
            db = get_db()
            msgs = db.get_messages(self._current_conv_id)
            if msgs:
                self.memory.load_from_list(self._current_conv_id, msgs)
                logger.info("Auto-loaded memory: conv=%s (%d msgs)", self._current_conv_id, len(msgs))
        except Exception as e:
            logger.debug("Auto-load memory failed: %s", e)

    def _get_file_context(self, files: list[str]) -> str:
        """为上传的文件生成上下文说明"""
        if not files:
            return ""

        parts = ["\n\n用户上传了以下文件，可以直接使用这些文件路径："]
        image_ext = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
        doc_ext = {".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".csv", ".md"}

        for fp in files:
            fp = os.path.abspath(fp)
            if not os.path.isfile(fp):
                continue
            fname = os.path.basename(fp)
            ext = os.path.splitext(fname)[1].lower()
            size = os.path.getsize(fp)
            size_str = _format_size(size)

            if ext in image_ext:
                parts.append(f"- 📷 {fname} ({size_str}) — 图片文件，如需提取文字请调用 ocr_image('{fp}')")
            elif ext == ".pdf":
                parts.append(f"- 📄 {fname} ({size_str}) — PDF 文档，可用 read_document('{fp}') 读取或 ocr_pdf('{fp}') 做文字识别")
            elif ext in doc_ext:
                parts.append(f"- 📄 {fname} ({size_str}) — 文档，可用 read_document('{fp}') 读取")
            else:
                parts.append(f"- 📎 {fname} ({size_str}) — 文件，可用 read_file('{fp}') 读取")

        parts.append("请根据文件类型选择合适的工具处理这些文件。")
        return "\n".join(parts)

    def chat(self, query: str, files: Optional[list] = None) -> str:
        logger.info("Chat: %s", query[:100])
        self._auto_load_memory()
        full_reply = ""
        try:
            for event in self._react_loop_stream(query, files=files or []):
                if event.get("phase") == "answer":
                    full_reply += event["token"]
        except Exception as e:
            logger.error("Chat error: %s", e, exc_info=True)
            full_reply = f"模型调用出错: {str(e)[:200]}"

        self.memory.add(self._current_conv_id, "user", query)
        self.memory.add(self._current_conv_id, "assistant", full_reply)
        self._save_conversation(query, full_reply)
        return full_reply

    def chat_stream(self, query: str, files: Optional[list] = None) -> Generator[str, None, None]:
        self._auto_load_memory()
        full_reply = ""
        try:
            for event in self._react_loop_stream(query, files=files or []):
                if event.get("phase") == "answer":
                    full_reply += event.get("token", "")
                yield json.dumps(event, ensure_ascii=False)
        except Exception as e:
            logger.error("Stream error: %s", e)
            yield json.dumps({"phase": "error", "message": str(e)}, ensure_ascii=False)

        self.memory.add(self._current_conv_id, "user", query)
        self.memory.add(self._current_conv_id, "assistant", full_reply)
        self._save_conversation(query, full_reply)
        yield json.dumps({"phase": "done"}, ensure_ascii=False)

    def reset(self, conv_id: str = ""):
        cid = conv_id or self._current_conv_id
        self.memory.clear(cid)
        self.summary_memory.clear()
        logger.info("Agent reset: conv=%s", cid)

    def load_conversation(self, conv_id: str):
        """从数据库加载历史消息到记忆"""
        from core.database.db import get_db
        db = get_db()
        messages = db.get_messages(conv_id)
        self.memory.load_from_list(conv_id, messages)
        self._current_conv_id = conv_id
        logger.info("Conversation loaded: conv=%s (%d msgs)", conv_id, len(messages))

    def get_tools(self) -> list[dict]:
        return list_tools(self.enabled_tools)

    # -------- Plan-and-Execute 模式 --------

    def generate_plan(self, query: str, files=None) -> dict:
        """生成执行计划（非流式）"""
        system_prompt = get_system_prompt("assistant", self.enabled_tools)
        messages = [{"role": "system", "content": system_prompt}]
        planning_prompt = PLANNING_PROMPT + chr(10) + "可用工具列表：" + chr(10)
        for t in list_tools(self.enabled_tools):
            planning_prompt += "- " + t["name"] + ": " + t["description"] + chr(10)
        messages.append({"role": "system", "content": planning_prompt})
        knowledge_ctx = self._get_knowledge_context(query)
        if knowledge_ctx:
            messages.append({"role": "system", "content": "相关参考资料：" + knowledge_ctx[:800]})
        file_ctx = self._get_file_context(files or [])
        if file_ctx:
            messages.append({"role": "system", "content": file_ctx})
        messages.append({"role": "user", "content": query})
        try:
            raw = self.model.chat(messages, temperature=0.3)
        except Exception as e:
            return {"title": "规划失败", "steps": [], "error": str(e)[:200]}
        plan = self._parse_plan_json(raw)
        if not plan or "steps" not in plan:
            return {"title": "自动执行", "steps": [], "raw": raw[:300]}
        return plan

    def generate_plan_stream(self, query: str, files=None):
        """流式生成计划，先输出 think_token 展示思考过程，最后 yield plan 事件"""
        system_prompt = get_system_prompt("assistant", self.enabled_tools)
        messages = [{"role": "system", "content": system_prompt}]
        planning_prompt = PLANNING_PROMPT + chr(10) + "可用工具列表：" + chr(10)
        for t in list_tools(self.enabled_tools):
            planning_prompt += "- " + t["name"] + ": " + t["description"] + chr(10)
        messages.append({"role": "system", "content": planning_prompt})
        knowledge_ctx = self._get_knowledge_context(query)
        if knowledge_ctx:
            messages.append({"role": "system", "content": "相关参考资料：" + knowledge_ctx[:800]})
        file_ctx = self._get_file_context(files or [])
        if file_ctx:
            messages.append({"role": "system", "content": file_ctx})
        messages.append({"role": "user", "content": query})
        buf = ""
        for token in self.model.chat_stream(messages, temperature=0.3):
            buf += token
            yield {"phase": "think_token", "token": token}
        plan = self._parse_plan_json(buf)
        if not plan or "steps" not in plan:
            plan = {"title": "自动执行", "steps": []}
        yield {"phase": "plan", "plan": plan}

    def _parse_plan_json(self, text: str):
        """从模型输出解析计划 JSON"""
        candidates = _extract_json_object(text)
        for candidate in candidates:
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict) and "steps" in obj:
                    return obj
                if isinstance(obj, list):
                    return {"title": "执行计划", "steps": obj}
            except json.JSONDecodeError:
                continue
        return None

    def execute_plan_stream(self, plan: dict, query: str):
        """执行计划：每步执行 + 可见评估 + 严格基于结果的最终回答"""
        steps = plan.get("steps", [])

        if not steps:
            yield {"phase": "plan_exec_start", "total_steps": 0, "fallback": True}
            yield {"phase": "plan_fallback", "message": "无需计划，直接执行"}
            for event in self._react_loop_stream(query):
                yield event
            return

        yield {"phase": "plan_exec_start", "total_steps": len(steps)}
        yield {"phase": "thinking", "round": "plan"}

        all_results = []

        for step_data in steps:
            step_num = step_data.get("step", 0)
            desc = step_data.get("description", "")
            tool_name = step_data.get("tool", "")
            args = step_data.get("arguments", {})

            yield {"phase": "plan_step", "step": step_num, "total": len(steps), "description": desc}
            yield {"phase": "tool_call", "tools": [tool_name]}

            if tool_name and tool_name in self.enabled_tools:
                from core.tools import call_tool
                logger.info("Plan step %d: calling %s args=%s", step_num, tool_name, str(args)[:200])
                raw_result = call_tool(tool_name, **args)
            else:
                logger.warning("Plan step %d: tool %s unavailable", step_num, tool_name)
                raw_result = "跳过：工具【" + tool_name + "】不可用"

            clean_lines = []
            for _line in raw_result.split(chr(10)):
                _s = _line.strip()
                if _s.startswith('{"timestamp"') and '"level"' in _s and '"logger"' in _s:
                    continue
                clean_lines.append(_line)
            result = chr(10).join(clean_lines).strip() or raw_result[:200]

            logger.info("Plan step %d: %s result=%s", step_num, tool_name, result[:150])
            yield {"phase": "tool_result", "tool": tool_name, "result": result[:2000]}
            all_results.append({"step": step_num, "tool": tool_name, "result": result[:500]})

            # 流式评估，展示模型思考过程
            yield {"phase": "plan_eval", "step": step_num, "message": "验证步骤 " + str(step_num) + " 结果..."}

            eval_system = (
                "你是步骤校验器。判断工具执行是否成功。\n"
                "规则：\n"
                "- 结果包含「成功」「已保存」「已创建」「已生成」→ 回复 OK\n"
                "- 结果包含文件路径（如 D:\\xxx\\file.docx）且无错误 → 回复 OK\n"
                "- 结果开头是「代码执行出错」→ 需要修正（只输出修正后的工具调用JSON）\n"
                "- 结果包含「(无输出)」→ 需要修正\n"
                "- 结果包含 AttributeError/SyntaxError/TypeError → 需要修正\n"
                "- 结果包含「错误：」「失败」「不存在」「超时」→ 需要修正\n"
                "- 输出格式：成功只回复 OK，失败只输出 JSON 工具调用\n"
                "- 不要输出任何解释"
            )
            eval_msgs = [
                {"role": "system", "content": eval_system},
                {"role": "user", "content":
                    "步骤 " + str(step_num) + "（" + desc + "）已执行。" + chr(10) +
                    "工具：" + tool_name + chr(10) +
                    "结果：\n" + result[:2000]},
            ]

            corrected = False
            try:
                eval_buf = ""
                for token in self.model.chat_stream(eval_msgs, temperature=0.2):
                    eval_buf += token
                    yield {"phase": "think_token", "token": token}
                logger.info("Plan step %d eval: %s", step_num, eval_buf[:120])
                calls, _ = _parse_function_calls(eval_buf)
                if calls:
                    corrected = True
                    yield {"phase": "plan_correction", "step": step_num, "tool": calls[0]["name"], "reason": "步骤 " + str(step_num) + " 异常，自动修正"}
                    from core.tools import call_tools_parallel
                    extra_results = call_tools_parallel(calls)
                    for r in extra_results:
                        logger.info("Plan step %d correction: %s -> %s", step_num, r["tool"], r["result"][:150])
                        yield {"phase": "tool_result", "tool": r["tool"], "result": r["result"][:2000]}
                        all_results.append({"step": step_num, "tool": r["tool"], "result": r["result"][:500]})
            except Exception as eval_err:
                logger.error("Plan step eval failed: %s", eval_err)

            yield {"phase": "plan_eval_done", "step": step_num, "ok": not corrected, "message": ("步骤 " + str(step_num) + " 验证通过" if not corrected else "步骤 " + str(step_num) + " 已修正")}

        # 最终回答：严格基于执行结果，禁止编造
        yield {"phase": "plan_answering", "message": "综合分析执行结果..."}
        yield {"phase": "answering"}

        if not all_results:
            logger.warning("Plan execute: all_results is empty, no tools were executed")
            empty_msg = "抱歉，执行计划中的步骤未能产生有效结果。请检查工具配置或重试。"
            yield {"phase": "answer", "token": empty_msg}
            return

        final_system = (
            "你是科吉，用户的智能AI助手。\n"
            "下面列出了已执行完毕的工具及其返回结果。请严格基于这些结果总结回答。\n"
            "纪律：\n"
            "- 只能汇报「执行结果」中已经完成的操作，严禁编造任何未执行的操作\n"
            "- 如果执行结果显示文件保存在某路径，就如实告知该路径\n"
            "- 用中文自然段落回答，不要输出 JSON、代码块、markdown表格\n"
            "- 简洁直接，3-5句话即可"
        )
        summary = ("任务：" + query + chr(10) + chr(10) +
                  "已执行的工具结果（这些是真实结果，不是模拟）：" + chr(10) +
                  chr(10).join("[" + r["tool"] + "]: " + r["result"] for r in all_results) + chr(10) + chr(10) +
                  "请严格基于以上真实结果给用户回答，不要编造任何信息。")
        final_msgs = [
            {"role": "system", "content": final_system},
            {"role": "user", "content": summary},
        ]
        logger.info("Plan execute: generating final answer from %d results", len(all_results))
        for token in self.model.chat_stream(final_msgs, temperature=0.5):
            yield {"phase": "answer", "token": token}
agent = CoreAgent()
