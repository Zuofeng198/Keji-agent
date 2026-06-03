"""科吉 FastAPI × nanobot AgentRunner 适配器"""

from __future__ import annotations

import asyncio
import json
import os
import re
import yaml
from pathlib import Path
from typing import Any, AsyncGenerator

from loguru import logger

from nanobot.agent.hook import AgentHook, AgentHookContext, CompositeHook
from nanobot.agent.runner import AgentRunner, AgentRunSpec
from nanobot.providers.base import LLMProvider, GenerationSettings, ToolCallRequest, LLMResponse
from nanobot.providers.openai_compat_provider import OpenAICompatProvider
from nanobot.session.manager import SessionManager
from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.web import WebSearchTool, WebFetchTool
from nanobot.agent.tools.filesystem import ReadFileTool
from nanobot.agent.tools.search import GlobTool, GrepTool
from nanobot.agent.tools.selfcheck import SelfCheckTool
from nanobot.selfcheck.runner import SelfCheckRunner
from nanobot.utils.helpers import estimate_prompt_tokens_chain
from core.skills import get_registry


def _ensure_usage(
    usage: dict[str, int] | None,
    provider: LLMProvider,
    model: str,
    messages: list[dict],
    tools: list | None,
    reply: str,
    *,
    reasoning_content: str | None = None,
    tool_calls_json: str | None = None,
) -> dict[str, int]:
    """如果 provider 没返回真实 usage，用 estimate_prompt_tokens_chain 精确估算"""
    if usage and usage.get("prompt_tokens") and usage.get("completion_tokens"):
        out = dict(usage)
        out["source"] = "api"
        return out
    cached = int((usage or {}).get("cached_tokens", 0) or 0)
    pt, _ = estimate_prompt_tokens_chain(provider, model, messages, tools)
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        # 计数包含：回复文本 + 思考内容 + 工具调用JSON
        text_to_count = (reply or "")
        if reasoning_content:
            text_to_count += "\n" + reasoning_content
        if tool_calls_json:
            text_to_count += "\n" + tool_calls_json
        ct = len(enc.encode(text_to_count))
    except Exception:
        ct = len(reply or "") // 4
    result = {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct, "source": "estimated"}
    if cached:
        result["cached_tokens"] = cached
    return result

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SYSTEM_PROMPT_CACHE: str | None = None


def load_system_prompt() -> str:
    """从 prompts/system.md 加载系统提示词"""
    global _SYSTEM_PROMPT_CACHE
    if _SYSTEM_PROMPT_CACHE is not None:
        return _SYSTEM_PROMPT_CACHE
    prompt_path = _PROJECT_ROOT / "prompts" / "system.md"
    try:
        _SYSTEM_PROMPT_CACHE = prompt_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        _SYSTEM_PROMPT_CACHE = "你是科吉，智能AI助手。"
    return _SYSTEM_PROMPT_CACHE


def load_config() -> dict:
    from core.security.secrets import load_app_config
    return load_app_config(_PROJECT_ROOT / "config.yaml")


def _make_provider(config: dict) -> tuple[LLMProvider, str, int]:
    """从 config.yaml 读取模型配置，作为唯一真实来源"""
    models_cfg = config.get("models", {})
    default = models_cfg.get("default", "ollama")
    provider_cfg = models_cfg.get(default, {})

    base_url = (provider_cfg.get("base_url") or "").rstrip("/")
    api_key = provider_cfg.get("api_key", "")
    model = provider_cfg.get("model", "")

    # 解析环境变量引用 ${VAR_NAME}
    if isinstance(api_key, str) and api_key.startswith("${") and api_key.endswith("}"):
        api_key = os.environ.get(api_key[2:-1], "")

    if default in ("deepseek", "openai") and not (api_key or "").strip():
        env_name = "DEEPSEEK_API_KEY" if default == "deepseek" else "OPENAI_API_KEY"
        logger.error(
            "未配置 {} API Key：请在 .env 设置 {}，或在设置页保存 API Key 后重启",
            default, env_name,
        )

    if not model:
        model = "gpt-4o-mini" if default == "openai" else "qwen2.5:7b"

    logger.info("Using provider: {} | {} model={}", default, base_url, model)
    p = OpenAICompatProvider(api_key=api_key or None, api_base=base_url, default_model=model)
    p.generation = GenerationSettings(temperature=0.7, max_tokens=8192)
    return p, model, 65536


# ── 工具调用翻译层：当模型未返回tool_calls时，从文本JSON提取 ──

def _parse_json_calls(text: str) -> list[dict]:
    """从文本中提取 JSON 工具调用"""
    for match in re.finditer(r'\{\s*"name"\s*:\s*"(\w+)"\s*,\s*"arguments"\s*:\s*(\{.*?\}|".*?")\s*\}', text, re.DOTALL):
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict) and "name" in obj and "arguments" in obj:
                args = obj["arguments"]
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"value": args}
                if isinstance(args, dict):
                    yield {"name": obj["name"], "arguments": args}
        except json.JSONDecodeError:
            continue


class TranslatorProvider(LLMProvider):
    """Provider 包装：deepseek-r1 不支持原生 tools，剥离 tools 参数，从文本 JSON 解析工具调用"""

    def __init__(self, inner: LLMProvider):
        self._inner = inner
        self.generation = inner.generation

    def get_default_model(self) -> str:
        return self._inner.get_default_model()

    async def chat(self, messages=None, tools=None, model=None, **kwargs):
        # deepseek 云端支持原生 function calling，先正常调
        resp = await self._inner.chat(messages=messages, tools=tools, model=model, **kwargs)
        # 兜底：如果没有原生 tool_calls，从文本 JSON 解析
        if not resp.has_tool_calls and resp.content:
            parsed = list(_parse_json_calls(resp.content))
            if parsed:
                resp.tool_calls = [ToolCallRequest(id=f"t{i}", name=p["name"], arguments=p["arguments"])
                                   for i, p in enumerate(parsed)]
                logger.info("Translator: 从文本提取 {} 个调用: {}", len(parsed), [p["name"] for p in parsed])
        return resp

    async def chat_stream(self, messages=None, tools=None, model=None, **kwargs):
        """流式输出，deepseek JSON fallback，捕获 reasoning_content"""
        on_delta = kwargs.pop("on_content_delta", None)
        model_id = model or self._inner.get_default_model()
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 8192)

        # 补全 reasoning_content（deepseek 要求传回）
        for msg in (messages or []):
            if msg.get("role") == "assistant" and "reasoning_content" not in msg:
                msg["reasoning_content"] = ""

        content_buf = ""
        reasoning_buf = ""
        tool_calls: list[ToolCallRequest] = []
        finish_reason = "stop"
        usage = {}

        try:
            stream = await self._inner._client.chat.completions.create(
                model=model_id,
                messages=messages,
                tools=tools or [],
                stream=True,
                stream_options={"include_usage": True},
                temperature=temperature,
                max_tokens=max_tokens,
            )
            async for chunk in stream:
                if not chunk.choices:
                    if hasattr(chunk, "usage") and chunk.usage:
                        extracted = OpenAICompatProvider._extract_usage(chunk.usage)
                        if extracted:
                            usage = extracted
                    continue
                delta = chunk.choices[0].delta
                fr = chunk.choices[0].finish_reason
                if fr:
                    finish_reason = fr

                # deepseek 思考链：逐 chunk 实时推送并保存
                rc = getattr(delta, "reasoning_content", None)
                if rc:
                    reasoning_buf += rc
                    if on_delta:
                        await on_delta(rc)

                # 正式内容
                text = getattr(delta, "content", None)
                if text:
                    content_buf += text
                    if on_delta:
                        await on_delta(text)

                # 工具调用：流式累积原始参数字符串，不解析 JSON
                tc_delta = getattr(delta, "tool_calls", None)
                if tc_delta:
                    for tc in tc_delta:
                        idx = getattr(tc, "index", 0)
                        if not hasattr(self, "_tc_raw"):
                            self._tc_raw = {}
                        if idx not in self._tc_raw:
                            self._tc_raw[idx] = {"name": "", "raw": ""}
                        if tc.function:
                            if tc.function.name:
                                self._tc_raw[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                self._tc_raw[idx]["raw"] += tc.function.arguments

            # 流式接收完成，解析累积的工具调用参数
            tc_raw = getattr(self, "_tc_raw", {})
            for idx in sorted(tc_raw.keys()):
                b = tc_raw[idx]
                name = b.get("name", "")
                raw = b.get("raw", "")
                args = {}
                if raw:
                    try:
                        args = json.loads(raw)
                    except json.JSONDecodeError:
                        try:
                            import json_repair
                            args = json_repair.loads(raw)
                        except Exception:
                            args = {"raw": raw}
                if isinstance(args, dict) and name:
                    tool_calls.append(ToolCallRequest(id=f"call_{idx}", name=name, arguments=args))
            self._tc_raw = {}
        except Exception as e:
            logger.error("Stream error: {}", e)
            return LLMResponse(content=f"Stream error: {e}", finish_reason="error")

        # 兜底：文本JSON解析工具调用
        if not tool_calls and content_buf:
            parsed = list(_parse_json_calls(content_buf))
            if parsed:
                tool_calls = [ToolCallRequest(id=f"t{i}", name=p["name"], arguments=p["arguments"])
                             for i, p in enumerate(parsed)]

        return LLMResponse(
            content=content_buf or None,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            reasoning_content=reasoning_buf or None,
        )


# ── SSE Hook ──

class SSEHook(AgentHook):
    def __init__(self, q: asyncio.Queue):
        super().__init__(); self.q = q
        self.thinking_content = ""  # 累积所有思考 token
    def wants_streaming(self) -> bool: return True

    def emit(self, phase: str, **data) -> None:
        """发送 SSE 事件到前端队列（非阻塞，异常安全）"""
        try:
            self.q.put_nowait(json.dumps({"phase": phase, **data}, ensure_ascii=False))
        except Exception:
            pass

    async def before_iteration(self, ctx: AgentHookContext) -> None:
        await self.q.put(json.dumps({"phase": "thinking", "round": ctx.iteration + 1}, ensure_ascii=False))

    async def on_stream(self, ctx: AgentHookContext, delta: str) -> None:
        if delta:
            self.thinking_content += delta
            await self.q.put(json.dumps({"phase": "think_token", "token": delta}, ensure_ascii=False))

    async def before_execute_tools(self, ctx: AgentHookContext) -> None:
        tools = [tc.name for tc in ctx.tool_calls]
        # 尝试从参数中提取实际工具名（__tool__ 的分发目标）
        actual_names = []
        for tc in ctx.tool_calls:
            args = tc.arguments or {}
            actual = args.get("tool", tc.name)
            actual_names.append(actual)
        counts = {}
        for t in actual_names:
            counts[t] = counts.get(t, 0) + 1
        summary = ", ".join(f"{t}×{c}" if c > 1 else t for t, c in counts.items())
        msg = f"\n🔧 调用工具: {summary}\n"
        await self.q.put(json.dumps({"phase": "think_token", "token": msg}, ensure_ascii=False))

    async def after_iteration(self, ctx: AgentHookContext) -> None:
        # 显示工具结果
        actual_names = []
        for tc in ctx.tool_calls:
            args = tc.arguments or {}
            actual = args.get("tool", tc.name)
            actual_names.append(actual)
        lines = []
        for i, r in enumerate(ctx.tool_results or []):
            raw = str(r) if r is not None else ""
            n = actual_names[i] if i < len(actual_names) else "?"
            short = raw[:200]
            lines.append(f"  [{n}] {short}")
        if lines:
            msg = "\n".join(lines) + "\n"
            await self.q.put(json.dumps({"phase": "think_token", "token": msg}, ensure_ascii=False))


class RolePermissionHook(AgentHook):
    """按登录角色拦截写入类工具（只读账号仅查询/读文件）。"""

    @staticmethod
    def _tool_name(tc) -> str:
        if tc.name == "__tool__":
            args = tc.arguments or {}
            return str(args.get("tool", "") or "")
        return tc.name or ""

    async def before_execute_tools(self, ctx: AgentHookContext) -> None:
        from core.security.permissions import resolve_current_user, tool_allowed_for_user

        user = resolve_current_user()
        if not user or user.is_admin:
            return
        kept = []
        blocked: list[str] = []
        for tc in ctx.tool_calls:
            name = self._tool_name(tc)
            if tool_allowed_for_user(name, user):
                kept.append(tc)
            else:
                blocked.append(name or tc.name)
        if blocked:
            ctx.tool_calls = kept
            msg = (
                f"账号「{user.display_name or user.username}」为只读权限，"
                f"已阻止写入类工具: {', '.join(blocked)}。"
                "请改用读取、检索、分析类能力，或请管理员处理文件变更。"
            )
            pos = 1 if (ctx.messages and ctx.messages[0].get("role") == "system") else 0
            ctx.messages.insert(pos, {"role": "system", "content": f"[权限限制]\n\n{msg}"})


class ComplianceHook(AgentHook):
    """自动执行自检和验证提醒 — 在复杂工具执行前注入健康报告。

    修复要点（2026-05）:
    - _selfcheck_done 改为自检通过后才锁定（A1）
    - 通过 SSE 事件向用户展示自检进度（A2）
    - 每 N 轮复检 + 工具出错触发的复检（A3）
    - 扩展复杂工具检测前缀覆盖度（A4）
    """

    COMPLEX_TOOLS = frozenset({"run_code", "db_execute_query", "create_document", "create_table"})
    # 只读/查询类工具不触发自检，避免阻断 list_allowed_directories 等
    SAFE_TOOLS = frozenset({
        "list_allowed_directories",
        "browse_files",
        "search_files",
        "read_document",
        "read_file",
        "create_folder",
        "delete_file",
        "mcp_filesystem_list_allowed_directories",
        "mcp_filesystem_list_directory",
        "mcp_filesystem_get_file_info",
        "mcp_filesystem_read_text_file",
        "mcp_filesystem_read_file",
        "mcp_filesystem_read_media_file",
        "mcp_filesystem_read_multiple_files",
        "mcp_filesystem_create_directory",
        "mcp_filesystem_write_file",
        "mcp_filesystem_edit_file",
        "mcp_filesystem_move_file",
    })
    # A4: 数据分析/办公类 MCP 触发自检；filesystem 已由全局沙箱约束，不再拦截建目录等
    COMPLEX_PREFIXES = frozenset({
        "mcp_quack_", "mcp_engineer-your-data_",
        "mcp_excel_", "mcp_doc-tools_",
        "mcp_charts_", "mcp_memdb_", "mcp_image-gen_",
    })
    REPORT_TOOLS = frozenset({"create_document", "create_table", "create_presentation"})
    # A3: 每 N 轮复杂工具触发一次复检（值越小复检越频繁）
    RECHECK_INTERVAL = 3

    # 验证工具名（允许通过的验证相关工具）
    VERIFY_TOOLS = frozenset({"verify_output", "selfcheck_run", "__tool__"})

    def __init__(self, tool_registry: ToolRegistry, project_root: Path, config: dict,
                 sse_hook: SSEHook | None = None):
        super().__init__()
        self._runner = SelfCheckRunner(tool_registry, project_root, config)
        self._selfcheck_done = False
        self._selfcheck_round_count = 0  # A3: 自检后复杂工具调用计数
        self._verification_reminded = False
        self._verification_pending = False  # 强制验证：等待验证通过
        self._sse = sse_hook  # A2: SSE 事件发射器

    @staticmethod
    def _resolve_names(tool_calls: list) -> list[str]:
        names = []
        for tc in tool_calls:
            if tc.name == "__tool__":
                args = tc.arguments or {}
                names.append(args.get("tool", ""))
            else:
                names.append(tc.name)
        return names

    def _has_complex(self, names: list[str]) -> bool:
        for n in names:
            if n in self.SAFE_TOOLS:
                continue
            if n in self.COMPLEX_TOOLS:
                return True
            for p in self.COMPLEX_PREFIXES:
                if n.startswith(p):
                    return True
        return False

    def _has_report(self, names: list[str]) -> bool:
        return any(n in self.REPORT_TOOLS for n in names)

    def _only_safe_tools(self, names: list[str]) -> bool:
        if not names:
            return False
        for n in names:
            if n in self.SAFE_TOOLS:
                continue
            if n in self.COMPLEX_TOOLS:
                return False
            for p in self.COMPLEX_PREFIXES:
                if n.startswith(p):
                    return False
        return True

    # A3: 判断是否需要复检
    def _should_recheck(self) -> bool:
        """自检通过后，每 RECHECK_INTERVAL 轮复杂工具调用复检一次。"""
        if not self._selfcheck_done:
            return False
        self._selfcheck_round_count += 1
        return self._selfcheck_round_count >= self.RECHECK_INTERVAL

    async def after_iteration(self, ctx: AgentHookContext) -> None:
        """A3: 检测工具执行错误，提前触发复检。"""
        if not ctx.tool_results:
            return
        for r in ctx.tool_results:
            s = str(r or "")[:20]
            if any(kw in s for kw in ("错误", "Error", "失败", "timeout", "拒绝")):
                # 工具出错了 → 下次 before_execute_tools 会触发复检
                self._selfcheck_round_count = self.RECHECK_INTERVAL
                break

    async def before_finalize(self, ctx: AgentHookContext) -> None:
        """拦截模型直接输出答案：如果验证待定，重定向到工具执行。"""
        if self._verification_pending:
            # 注入一个 verify_output 调用到 tool_calls，迫使模型执行验证
            inject_msg = ("【强制验证】你当前有未完成的 verify_output 验证。\n"
                          "请先调用 verify_output 验证输出文件再回答。")
            self._inject(ctx.messages, "FORCED VERIFICATION", inject_msg)
            # 清空原始内容，让模型继续迭代
            ctx.final_content = None
            ctx.stop_reason = None
            ctx.streamed_content = False
            if self._sse:
                self._sse.emit("selfcheck_result", passed=False,
                               summary="强制验证: 必须先验证才能输出答案")

    async def after_iteration(self, ctx: AgentHookContext) -> None:
        """A3: 检测工具执行错误，提前触发复检。"""
        if not ctx.tool_results:
            return
        for r in ctx.tool_results:
            s = str(r or "")[:20]
            if any(kw in s for kw in ("错误", "Error", "失败", "timeout", "拒绝")):
                # 工具出错了 → 下次 before_execute_tools 会触发复检
                self._selfcheck_round_count = self.RECHECK_INTERVAL
                break

        # 连续工具失败计数，触发快速复检
        has_failure = False
        if ctx.tool_results:
            fails = sum(1 for r in ctx.tool_results if any(kw in str(r or "")[:20]
                        for kw in ("错误", "Error", "失败", "timeout", "拒绝", "McpError", "FAIL")))
            if fails >= 2:  # 同一轮有>=2个工具失败 → 立刻触发复检
                self._selfcheck_round_count = self.RECHECK_INTERVAL

        # 检测 verify_output 的结果，清除强制验证状态
        if self._verification_pending:
            for r in ctx.tool_results:
                rs = str(r or "")[:10]
                if rs.startswith("PASS"):
                    self._verification_pending = False
                    if self._sse:
                        self._sse.emit("selfcheck_result", passed=True,
                                       summary="验证通过")
                elif rs.startswith("FAIL"):
                    # 验证失败，保持 pending，下一轮继续要求验证
                    if self._sse:
                        self._sse.emit("selfcheck_result", passed=False,
                                       summary="验证失败，请修复后重试")

    async def before_execute_tools(self, ctx: AgentHookContext) -> None:
        names = self._resolve_names(ctx.tool_calls)
        is_complex = self._has_complex(names)

        # A3: 检测是否需要复检（自检 done 后的周期性检查）
        if self._selfcheck_done and is_complex:
            if self._should_recheck():
                self._selfcheck_done = False
                self._selfcheck_round_count = 0

        need_selfcheck = is_complex and not self._selfcheck_done
        need_verify = self._has_report(names)
        if not need_selfcheck and not need_verify:
            # 强制验证：当验证待定时，只允许验证工具通过
            if self._verification_pending:
                if not any(n in self.VERIFY_TOOLS or n.startswith("verify_") for n in names):
                    ctx.tool_calls.clear()
                    self._inject(ctx.messages, "⚠️ 强制验证",
                                 "你必须先调用 verify_output 验证刚才生成的报告。\n"
                                 "验证通过后才能进行下一步。")
                    if self._sse:
                        self._sse.emit("selfcheck_result", passed=False,
                                       summary="强制验证: 请先调用 verify_output")
            return

        # A2: 自检开始 — 发送 SSE 事件
        if need_selfcheck and self._sse:
            self._sse.emit("selfcheck_start")

        if need_selfcheck:
            # A1: 将 _selfcheck_done = True 移到成功之后
            try:
                loop = asyncio.get_event_loop()
                report = await loop.run_in_executor(None, self._runner.run)
                if report.is_all_pass:
                    self._selfcheck_done = True
                    self._selfcheck_round_count = 0
                    label, content = "SELF-CHECK PASSED", report.format_text()
                    if self._sse:
                        self._sse.emit("selfcheck_result", passed=True,
                                       summary=f"通过 {report.passed_count}/{len(report.results)} 项")
                else:
                    failed = [r.label for r in report.results if not r.passed]
                    if self._only_safe_tools(names):
                        label = "SELF-CHECK WARNING"
                        content = (
                            report.format_text()
                            + f"\n\n未通过: {', '.join(failed)}。"
                            "当前为文件/目录类操作，已放行执行（不依赖可选 MCP）。"
                        )
                        self._selfcheck_done = True
                        if self._sse:
                            self._sse.emit(
                                "selfcheck_result",
                                passed=True,
                                summary=f"警告放行 {report.passed_count}/{len(report.results)}",
                            )
                    else:
                        ctx.tool_calls.clear()
                        label = "SELF-CHECK FAILED — 工具已阻止"
                        content = (report.format_text() +
                                   f"\n\n以下检查项未通过: {', '.join(failed)}。"
                                   "工具执行已被自动阻止。请先向用户报告异常，等待指示。")
                        if self._sse:
                            self._sse.emit(
                                "selfcheck_result",
                                passed=False,
                                summary=f"失败 {report.failed_count}/{len(report.results)} 项",
                            )
            except Exception as e:
                # A1: 异常时保持 _selfcheck_done = False，允许后续重试
                self._selfcheck_done = False
                msg = f"自检执行异常: {e}"
                self._inject(ctx.messages, "SELF-CHECK ERROR", msg)
                if self._sse:
                    self._sse.emit("selfcheck_result", passed=False, summary=msg)
                return

            self._inject(ctx.messages, label, content)

        if need_verify:
            self._verification_reminded = True
            self._verification_pending = True  # 启动强制验证
            self._inject(ctx.messages, "⚠️ 强制验证",
                         "你刚刚创建或修改了数据交付物，现在必须调用 verify_output 进行独立验证。\n"
                         "验证内容：文件是否存在、行数、关键字段空值、合计一致性。\n"
                         "verify_output 返回 PASS 才能继续。\n"
                         "在验证完成前，其他工具调用将被阻止。")

    @staticmethod
    def _inject(messages: list, label: str, content: str) -> None:
        pos = 1 if (messages and messages[0].get("role") == "system") else 0
        messages.insert(pos, {"role": "system", "content": f"[{label}]\n\n{content}"})


# ── 懒加载工具发现 ──

class _LazyTool(Tool):
    """单个元工具：LLM 通过它调用所有工具，大幅节省定义 token"""

    def __init__(self, full_registry: ToolRegistry):
        self._registry = full_registry
        self._all_names = list(full_registry._tools.keys())
        super().__init__()

    @property
    def name(self) -> str:
        return "__tool__"

    @property
    def description(self) -> str:
        return "万能工具执行器。通过 tool 选工具、arguments 传参（JSON字符串）。\n可直接调用的工具（无需 __tool__）:\n- 自检: selfcheck_run(系统全面自检，复杂任务前必须执行)\n- 文档/表格: create_document(创建Word), create_table(创建Excel), read_document(读取)\n- 知识库/分析: query_knowledge(检索), analyze_data(分析), web_search(搜索)\n- 数据库: db_connect(连接), db_execute_query(查询)\n\n通过 __tool__ 调用的常用工具:\n办公: create_presentation(创建PPT)\n文件: delete_file(删除文件), organize_files(整理文件), browse_archive(浏览压缩包)\n数据处理: format_data(格式化), clean_data(清洗), convert_data(转换)\nDuckDB数据分析(全部15个):\n  - 加载数据: mcp_quack_load_csv(加载单个CSV), mcp_quack_load_multiple_csvs(加载多个CSV), mcp_quack_load_excel(加载Excel), mcp_quack_load_multiple_excels(加载多个Excel)\n  - 探查: mcp_quack_list_tables(列出表), mcp_quack_describe_table(查看表结构), mcp_quack_analyze_csv(列统计), mcp_quack_discover_csv_files(搜索CSV文件), mcp_quack_discover_excel_files(搜索Excel文件)\n  - 查询: mcp_quack_query_csv(SQL查询,支持JOIN/GROUP BY/WHERE)\n  - 智能分析: mcp_quack_detect_anomalies(异常检测:重复/空值/离群值), mcp_quack_optimize_expenses(费用优化报告)\n  - 导出: mcp_quack_export_csv(表→CSV文件), mcp_quack_export_json(SQL→JSON文件)\n  - 数据库: mcp_quack_attach_database(挂载DuckDB文件,跨库查询)\n数据质量: mcp_engineer-your-data_validate_schema(验证表结构), mcp_engineer-your-data_check_nulls(空值检测), mcp_engineer-your-data_data_quality_report(数据质量报告), mcp_engineer-your-data_detect_duplicates(重复检测)\n数据清洗/转换: mcp_engineer-your-data_clean_data(清洗), mcp_engineer-your-data_filter_data(过滤), mcp_engineer-your-data_aggregate_data(聚合), mcp_engineer-your-data_join_data(关联), mcp_engineer-your-data_pivot_data(透视), mcp_engineer-your-data_analyze_data_schema(模式分析)\n图表: mcp_engineer-your-data_create_chart(生成图表), mcp_engineer-your-data_data_summary(数据摘要), mcp_engineer-your-data_export_visualization(导出可视化)\nOCR: ocr_image(图片OCR), ocr_pdf(PDF OCR)\n邮件: parse_email(解析邮件), batch_parse_emails(批量解析)\n知识库: index_knowledge(索引), knowledge_stats(统计)\n其他: run_code(执行代码), get_time(时间), calculator(计算器)"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool": {
                    "type": "string",
                    "enum": self._all_names,
                    "description": "要执行的工具名，从上方列表中选择",
                },
                "arguments": {
                    "type": "string",
                    "description": "该工具的参数，必须是 JSON 字符串格式。例如 {\"path\": \"D:\\\\data\\\\file.csv\"}。不要传对象，必须传字符串。",
                },
            },
            "required": ["tool", "arguments"],
        }

    async def execute(self, tool: str = "", arguments: str = "", **kwargs: Any) -> str:
        actual = tool or kwargs.get("tool", "")
        args = {}
        if arguments:
            try:
                args = json.loads(arguments)
            except (json.JSONDecodeError, TypeError):
                args = {"raw": arguments}
        if not isinstance(args, dict):
            args = {}
        if not actual:
            return "错误：请指定 tool 参数"
        from core.security.permissions import resolve_current_user, tool_allowed_for_user

        user = resolve_current_user()
        if user and not tool_allowed_for_user(actual, user):
            return (
                f"错误：当前账号（{user.role}）无权使用写入类工具「{actual}」。"
                "只读账号仅可查询与读取；成员可读写共享目录与个人目录；管理员无此限制。"
            )
        t = self._registry.get(actual)
        if not t:
            return f"错误：工具 '{actual}' 不存在"
        logger.info("Lazy exec: {} args={}", actual, str(args)[:200])
        try:
            result = await self._registry.execute(actual, args)
            return str(result)[:4000]
        except Exception as e:
            return f"错误: {type(e).__name__}: {str(e)[:200]}"


# ── Adapter ──

class KejiAdapter:
    def __init__(self):
        self.config = load_config()
        self.project_root = _PROJECT_ROOT
        raw_provider, self.model, ctx_window = _make_provider(self.config)
        self.provider = TranslatorProvider(raw_provider)
        self.session_manager = SessionManager(self.project_root)

        # 全量工具注册表（用于执行）
        self.tools = self._build_tools()
        # 懒加载工具注册表（用于 LLM 对话，只有少量工具）
        self.lazy_tools = self._build_lazy_tools()

        self.max_iterations = self.config.get("agent", {}).get("max_tool_rounds", 15)
        self.max_tool_result_chars = 8000
        self._mcp_stacks: dict[str, Any] = {}
        self._mcp_task: asyncio.Task | None = None
        try:
            self._mcp_task = asyncio.create_task(self._connect_mcp_servers())
        except Exception:
            pass
        logger.info("KejiAdapter ready: {} tools total, {} native + __tool__ dispatcher",
                    len(self.tools._tools), len(self.lazy_tools._tools) - 1)

        # 技能系统：按 session_id 记录已激活的技能名列表
        self._active_skills: dict[str, list[str]] = {}
        # 记录已向模型通知过的技能状态（避免重复通知）
        self._skill_notified: dict[str, set[str]] = {}
        # 默认技能（新会话自动激活）
        self._default_skills: list[str] = self.config.get("agent", {}).get("default_skills", [])

        # ── 飞书桥接实例（可空） ──
        self._feishu_bridge: Any = None

        # ── 取消事件：session_id → asyncio.Event ──
        self._cancel_events: dict[str, asyncio.Event] = {}

    # ── 飞书渠道集成 ──

    async def start_feishu_bridge(self) -> None:
        """启动飞书桥接层（如果 config.yaml 中 channels.feishu.enabled = true）"""
        try:
            from nanobot.feishu_bridge import FeishuBridge
            bridge = FeishuBridge(self)
            await bridge.start()
            self._feishu_bridge = bridge
        except ImportError:
            logger.warning("FeishuBridge 不可用（缺少依赖或文件）")
        except Exception as e:
            logger.error("启动飞书桥接层失败: {}", e)

    async def stop_feishu_bridge(self) -> None:
        """停止飞书桥接层"""
        if self._feishu_bridge:
            await self._feishu_bridge.stop()
            self._feishu_bridge = None

    def _ensure_default_skills(self, sid: str):
        """新会话若尚无技能记录，自动激活默认技能"""
        if sid and sid not in self._active_skills:
            self._active_skills[sid] = list(self._default_skills)

    def _make_cost_callback(self, session_key: str):
        """创建一个成本回调闭包，将工具调用统计写入数据库。

        返回一个 async callable，兼容 runner.py 的 cost_callback 接口。
        """
        model = self.model
        async def _cb(tool_name="", status="", duration_ms=0,
                      prompt_tokens=0, completion_tokens=0, cached_tokens=0,
                      estimated_cost=0.0, model=model, session_key=session_key,
                      turn_id=""):
            try:
                from core.database.db import get_db, estimate_tool_cost
                db = get_db()
                cost = estimated_cost or estimate_tool_cost(
                    model, prompt_tokens, completion_tokens, cached_tokens,
                )
                db.log_tool_usage(
                    session_id=session_key,
                    turn_id=turn_id,
                    tool_name=tool_name,
                    status=status,
                    duration_ms=duration_ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cached_tokens=cached_tokens,
                    estimated_cost=cost,
                    model=model,
                )
            except Exception as exc:
                logger.debug("Cost callback error: {}", exc)
        return _cb

    def _build_lazy_tools(self) -> ToolRegistry:
        """构建混合注册表：高频工具直接暴露 + __tool__ 兜底"""
        # 直接暴露的高频工具（原生 function calling，参数结构化，减少 JSON 嵌套错误）
        DIRECT_TOOLS = [
            "selfcheck_run",     # 系统自检（复杂任务前必须执行）
            "verify_output",     # 输出验证
            "create_document",   # 参数最多、最常用
            "create_table",      # 办公常用
            "read_document",     # 高频读取
            "query_knowledge",   # 核心 RAG 功能
            "analyze_data",      # 数据分析常用
            "db_connect",        # 数据库连接
            "db_execute_query",  # 数据库查询
        ]
        t = ToolRegistry()
        # 直接工具：原生 function calling
        for name in DIRECT_TOOLS:
            tool = self.tools.get(name)
            if tool:
                t.register(tool)
        # web_search 直接暴露（查询类常用），复用 _build_tools 中已配好 provider 的实例
        ws_tool = self.tools.get("web_search")
        if ws_tool:
            t.register(ws_tool)
        else:
            ws_cfg = self.config.get("web_search", {})
            ws_provider = ws_cfg.get("provider", "duckduckgo")
            ws_api_key = ws_cfg.get("api_key", "") or os.environ.get("TAVILY_API_KEY", "")
            if ws_provider == "tavily" and ws_api_key:
                from nanobot.config.schema import WebSearchConfig
                t.register(WebSearchTool(config=WebSearchConfig(provider="tavily", api_key=ws_api_key)))
            else:
                t.register(WebSearchTool())
        # __tool__ 万能分发器：其余所有文件/文档/数据处理等操作
        t.register(_LazyTool(self.tools))
        logger.info("Lazy tools: {} direct + __tool__ dispatcher", len(DIRECT_TOOLS) + 1)
        return t

    def _mcp_tool_prefix(self, server_name: str) -> str:
        return f"mcp_{server_name}_"

    async def _close_mcp_server(self, server_name: str) -> None:
        """仅关闭并注销某一 MCP 服务的工具。"""
        stack = self._mcp_stacks.pop(server_name, None)
        if stack is not None:
            try:
                await stack.aclose()
            except Exception:
                pass
        prefix = self._mcp_tool_prefix(server_name)
        n = self.tools.unregister_prefix(prefix)
        if n:
            logger.info("MCP {}: 已注销 {} 个工具", server_name, n)
        self._refresh_lazy_tool_names()

    def _refresh_lazy_tool_names(self) -> None:
        for tool in self.lazy_tools._tools.values():
            if hasattr(tool, "_all_names"):
                tool._all_names = list(self.tools._tools.keys())
                break

    @staticmethod
    def _mcp_server_config_from_dict(cfg: dict):
        from dataclasses import dataclass

        @dataclass
        class _MCPServerConfig:
            type: str | None = None
            command: str = ""
            args: list = None
            env: dict = None
            url: str = ""
            headers: dict = None
            tool_timeout: int = 30
            enabled_tools: list = None

            def __post_init__(self):
                if self.args is None:
                    self.args = []
                if self.env is None:
                    self.env = {}
                if self.headers is None:
                    self.headers = {}
                if self.enabled_tools is None:
                    self.enabled_tools = ["*"]

        return _MCPServerConfig(
            type=cfg.get("type"),
            command=cfg.get("command", ""),
            args=cfg.get("args", []),
            env=cfg.get("env", {}),
            url=cfg.get("url", ""),
            headers=cfg.get("headers", {}),
            tool_timeout=cfg.get("tool_timeout", 30),
            enabled_tools=cfg.get("enabled_tools", ["*"]),
        )

    async def reload_filesystem_mcp(self) -> list[str]:
        """仅重连 filesystem MCP（改目录时够用，避免重连全部 npx 服务）。"""
        from core.mcp_paths import apply_filesystem_args_to_mcp_servers, dirs_for_display

        await self._close_mcp_server("filesystem")

        mcp_servers = apply_filesystem_args_to_mcp_servers(
            self.config.get("mcp_servers", {}),
            self.config,
            self.project_root,
        )
        fs_cfg = mcp_servers.get("filesystem")
        if not fs_cfg:
            return dirs_for_display(self.config, self.project_root)

        try:
            import mcp  # noqa: F401
        except ImportError:
            logger.warning("MCP package not installed, skipping filesystem reload")
            return dirs_for_display(self.config, self.project_root)

        from nanobot.agent.tools.mcp import connect_mcp_servers

        server = self._mcp_server_config_from_dict(fs_cfg)
        stacks = await connect_mcp_servers({"filesystem": server}, self.tools)
        self._mcp_stacks.update(stacks)
        self._refresh_lazy_tool_names()
        logger.info("MCP filesystem: 已单独重连")
        return dirs_for_display(self.config, self.project_root)

    async def reload_mcp_servers(self, *, full: bool = False) -> list[str]:
        """重连 MCP。默认仅 filesystem；full=True 时重连全部（较慢）。"""
        if not full:
            return await self.reload_filesystem_mcp()
        await self.close_mcp()
        await self._connect_mcp_servers()
        from core.mcp_paths import dirs_for_display
        return dirs_for_display(self.config, self.project_root)

    async def _prepare_session_for_chat(self, session_id: str) -> str | None:
        """自动压缩过长会话；返回可展示给用户的提示。"""
        if not session_id:
            return None
        from core.context_compact import maybe_auto_compact_before_chat
        return await maybe_auto_compact_before_chat(
            self.session_manager, session_id, self.provider, self.config,
        )

    async def _connect_mcp_servers(self):
        """连接配置的 MCP 服务器并注册其工具"""
        from core.mcp_paths import apply_filesystem_args_to_mcp_servers
        mcp_servers = apply_filesystem_args_to_mcp_servers(
            self.config.get("mcp_servers", {}),
            self.config,
            self.project_root,
        )
        if not mcp_servers:
            return
        # 检查 mcp 包是否安装
        try:
            import mcp  # noqa
        except ImportError:
            logger.warning("MCP package not installed, skipping MCP servers")
            return
        from nanobot.agent.tools.mcp import connect_mcp_servers
        try:
            servers = {
                name: self._mcp_server_config_from_dict(cfg)
                for name, cfg in mcp_servers.items()
            }
            if servers:
                self._mcp_stacks = await connect_mcp_servers(servers, self.tools)
                self._refresh_lazy_tool_names()
                # quack/excel 工具通过 __tool__ 的枚举调用，不单独注册为独立 function，
                # 减少 LLM 收到的函数定义数量，避免模型过载。
                for name in servers:
                    logger.info("MCP connected: {}", name)
        except Exception as e:
            logger.error("MCP connection error: {}", e)

    async def close_mcp(self):
        """关闭所有 MCP 连接"""
        for name, stack in self._mcp_stacks.items():
            try:
                await stack.aclose()
            except Exception:
                pass
        self._mcp_stacks.clear()

    def get_mcp_servers_config(self) -> list[dict]:
        """获取当前配置的 MCP 服务器列表"""
        return [
            {"name": k, **v}
            for k, v in self.config.get("mcp_servers", {}).items()
        ]

    def cancel_chat(self, session_id: str) -> bool:
        """取消指定会话的正在执行的 Agent 循环。

        返回 True 表示找到了对应的取消事件并触发。
        """
        ev = self._cancel_events.get(session_id)
        if ev is not None:
            ev.set()
            logger.info("Cancel event triggered for session: {}", session_id)
            return True
        logger.warning("No active session found for cancel: {}", session_id)
        return False

    def _filesystem_allowed_roots(self) -> list[Path]:
        from core.path_policy import get_allowed_roots
        return get_allowed_roots(self.config, self.project_root)

    def _build_tools(self) -> ToolRegistry:
        t = ToolRegistry()
        roots = self._filesystem_allowed_roots()
        root_strs = [str(p) for p in roots]
        t.register(ExecTool(
            working_dir=str(self.project_root),
            timeout=60,
            allowed_roots=root_strs,
        ))
        # 从 config.yaml 读取搜索配置
        ws_cfg = self.config.get("web_search", {})
        ws_provider = ws_cfg.get("provider", "duckduckgo")
        ws_api_key = ws_cfg.get("api_key", "") or os.environ.get("TAVILY_API_KEY", "")
        if ws_provider == "tavily" and ws_api_key:
            from nanobot.config.schema import WebSearchConfig
            t.register(WebSearchTool(config=WebSearchConfig(provider="tavily", api_key=ws_api_key)))
            logger.info("Web search: Tavily (api_key configured)")
        else:
            t.register(WebSearchTool())
            if ws_provider == "tavily" and not ws_api_key:
                logger.warning("Web search: tavily configured but no api_key, falling back to duckduckgo")
        t.register(WebFetchTool())
        fs_kw = dict(workspace=self.project_root)
        if roots:
            fs_kw["allowed_dir"] = roots[0]
            if len(roots) > 1:
                fs_kw["extra_allowed_dirs"] = roots[1:]
        from nanobot.agent.tools.filesystem import (
            EditFileTool,
            ListDirTool,
            WriteFileTool,
        )
        t.register(ReadFileTool(**fs_kw))
        t.register(WriteFileTool(**fs_kw))
        t.register(EditFileTool(**fs_kw))
        t.register(ListDirTool(**fs_kw))
        t.register(GlobTool(**fs_kw))
        t.register(GrepTool(**fs_kw))
        t.register(SelfCheckTool(
            tool_registry=t,
            project_root=self.project_root,
            config=self.config,
        ))
        from nanobot.adapter_tools import register_keji_tools
        register_keji_tools(t, self.project_root)
        return t

    def _build_msgs(self, query: str, sid: str = "", files: list[str] | None = None):
        content = query
        if files:
            content += "\n\n上传文件:\n" + "\n".join(f"- {f}" for f in files)
        history = []
        try:
            from core.context_compact import get_context_settings, prune_history_messages
            s = self.session_manager.get_or_create(sid or "cli:default")
            history = s.get_history(max_messages=20, include_timestamps=False)
            opts = get_context_settings(self.config)
            history = prune_history_messages(history, opts["prune_tool_results"])
        except Exception:
            pass
        import datetime
        today = datetime.date.today().strftime("%Y年%m月%d日")
        sys_prompt = load_system_prompt() + f"\n\n## 当前日期\n今天是 {today}。搜索新闻时务必使用今天的日期作为搜索关键词。"
        roots = self._filesystem_allowed_roots()
        if roots:
            dirs_text = "\n".join(f"- {p}" for p in roots)
            sys_prompt += (
                "\n\n## 文件访问范围（全局沙箱）\n"
                "仅可读写下列目录及其子目录；访问其他路径会被拒绝。\n"
                f"{dirs_text}\n"
                "查询完整列表可调用工具 `list_allowed_directories`（优先于 MCP 同名工具）。"
                "列目录请使用绝对路径或 `knowledge`/`data` 等相对路径，勿对 `glob` 使用 `.`（表示项目根，可能越界）。"
            )
        try:
            from core.security.permissions import resolve_current_user, role_permission_hint

            _u = resolve_current_user()
            _rh = role_permission_hint(_u)
            if _rh:
                sys_prompt += f"\n\n## 当前账号权限\n{_rh}\n"
        except Exception:
            pass
        msgs = [{"role": "system", "content": sys_prompt}]

        # 新会话自动填充默认技能
        self._ensure_default_skills(sid)

        # 检测技能状态变更，通知模型
        skill_names = self._active_skills.get(sid, [])
        skill_set = set(skill_names)
        prev_notified = self._skill_notified.get(sid, set())
        if skill_set != prev_notified:
            activated = skill_set - prev_notified
            deactivated = prev_notified - skill_set
            note_parts = []
            if activated:
                note_parts.append(f"用户已激活技能：「{'」、「'.join(activated)}」")
            if deactivated:
                note_parts.append(f"用户已卸载技能：「{'」、「'.join(deactivated)}」")
            if note_parts:
                logger.info("[技能通知] session={} 变更: {}", sid, "; ".join(note_parts))
                msgs.append({
                    "role": "system",
                    "content": "；".join(note_parts) + "。用户可能会在后续对话中要求使用这些技能。"
                })
            self._skill_notified[sid] = set(skill_set)

        # 注入当前会话激活的技能指令
        if skill_names:
            registry = get_registry()
            for name in skill_names:
                skill = registry.get_skill(name)
                if skill and skill.instructions:
                    msgs.append({
                        "role": "system",
                        "content": f"## 技能：{skill.name}\n\n{skill.instructions}"
                    })
        msgs.extend(history)
        msgs.append({"role": "user", "content": content})
        return msgs, sid or "cli:default"

    @staticmethod
    def _merge_request_context(session_id: str) -> None:
        from core.security.context import get_request_context, set_request_context

        ctx = get_request_context()
        set_request_context(
            session_id=session_id or ctx.session_id,
            actor=ctx.actor or "api",
            client_ip=ctx.client_ip,
            user_id=ctx.user_id,
            role=ctx.role,
        )

    def _prepare_run_result_usage(self, run_result, *, thinking: str = "") -> None:
        """补全 run_result.usage（流式未返回时估算，保留 cached_tokens）。"""
        if not run_result:
            return
        reasoning = thinking or ""
        tc_json = None
        reply = run_result.final_content or ""
        for m in reversed(run_result.messages or []):
            if m.get("role") == "assistant":
                if not reasoning:
                    reasoning = m.get("reasoning_content") or m.get("thinking") or ""
                if m.get("tool_calls"):
                    import json as _j
                    tc_json = _j.dumps(m["tool_calls"], ensure_ascii=False)
                break
        inner = getattr(self.provider, "_inner", self.provider)
        original = dict(run_result.usage or {})
        run_result.usage = _ensure_usage(
            run_result.usage,
            inner,
            self.model,
            run_result.messages or [],
            None,
            reply,
            reasoning_content=reasoning or None,
            tool_calls_json=tc_json,
        )
        if original.get("prompt_tokens") and original.get("completion_tokens"):
            run_result.usage["source"] = "api"

    async def chat(self, query: str, sid: str = "", files: list[str] | None = None) -> str:
        sk_pre = sid or "cli:default"
        await self._prepare_session_for_chat(sk_pre)
        msgs, sk = self._build_msgs(query, sid, files)
        self._merge_request_context(sk)
        runner = AgentRunner(self.provider)
        agent_cfg = self.config.get("agent", {})
        cost_cb = self._make_cost_callback(sk)
        role_hook = RolePermissionHook()
        compliance = ComplianceHook(self.tools, self.project_root, self.config)
        r = await runner.run(AgentRunSpec(
            initial_messages=msgs, tools=self.lazy_tools, model=self.model,
            max_iterations=self.max_iterations, max_tool_result_chars=self.max_tool_result_chars,
            hook=CompositeHook([role_hook, compliance]),
            tool_timeout_s=agent_cfg.get("tool_timeout", 120),
            tool_max_retries=agent_cfg.get("tool_max_retries", 2),
            tool_retry_backoff=agent_cfg.get("tool_retry_backoff", 2),
            session_key=sk,
            cost_callback=cost_cb,
        ))
        reply = r.final_content or ""
        # 提取思考内容和工具调用用于精确估算
        _reasoning = None
        _tc_json = None
        for m in reversed(r.messages or []):
            if m.get("role") == "assistant":
                _reasoning = m.get("reasoning_content") or None
                if m.get("tool_calls"):
                    import json as _j
                    _tc_json = _j.dumps(m["tool_calls"], ensure_ascii=False)
                break
        from core.chat_persist import persist_chat_turn
        self._prepare_run_result_usage(r)
        persist_chat_turn(self.session_manager, sk, query, r, thinking="")
        return reply

    async def chat_stream(self, query: str, sid: str = "", files: list[str] | None = None) -> AsyncGenerator[str, None]:
        sk_pre = sid or "cli:default"
        compact_note = await self._prepare_session_for_chat(sk_pre)
        msgs, sk = self._build_msgs(query, sid, files)
        self._merge_request_context(sk)
        q: asyncio.Queue[str] = asyncio.Queue()
        if compact_note:
            await q.put(json.dumps({"phase": "system_notice", "message": compact_note}, ensure_ascii=False))
        done = asyncio.Event()
        sse_hook = SSEHook(q)
        role_hook = RolePermissionHook()
        compliance_hook = ComplianceHook(self.tools, self.project_root, self.config, sse_hook=sse_hook)
        hook = CompositeHook([sse_hook, role_hook, compliance_hook])

        cost_cb = self._make_cost_callback(sk)
        async def run():
            agent_cfg = self.config.get("agent", {})
            cancel_ev = asyncio.Event()
            self._cancel_events[sk] = cancel_ev
            if len(self._cancel_events) > 100:
                self._cancel_events.clear()
            reply = ""
            run_result = None
            try:
                run_result = await AgentRunner(self.provider).run(AgentRunSpec(
                    initial_messages=msgs, tools=self.lazy_tools, model=self.model,
                    max_iterations=self.max_iterations, max_tool_result_chars=self.max_tool_result_chars,
                    hook=hook,
                    tool_timeout_s=agent_cfg.get("tool_timeout", 120),
                    tool_max_retries=agent_cfg.get("tool_max_retries", 2),
                    tool_retry_backoff=agent_cfg.get("tool_retry_backoff", 2),
                    session_key=sk,
                    cancel_event=cancel_ev,
                    cost_callback=cost_cb,
                ))
                reply = run_result.final_content or ""
                if reply:
                    for i in range(0, len(reply), 2):
                        await q.put(json.dumps({"phase": "answer", "token": reply[i:i+2]}, ensure_ascii=False))
                        await asyncio.sleep(0)
            except Exception as e:
                await q.put(json.dumps({"phase": "error", "message": str(e)[:200]}, ensure_ascii=False))
            finally:
                self._cancel_events.pop(sk, None)
                if run_result is not None:
                    from core.chat_persist import persist_chat_turn
                    thinking = (
                        sse_hook.thinking_content.strip()
                        if hasattr(sse_hook, "thinking_content")
                        else ""
                    )
                    self._prepare_run_result_usage(run_result, thinking=thinking)
                    persist_chat_turn(
                        self.session_manager, sk, query, run_result, thinking=thinking
                    )
                done.set()

        asyncio.create_task(run())
        while True:
            try:
                item = await asyncio.wait_for(q.get(), timeout=0.5)
                yield item
                continue
            except asyncio.TimeoutError:
                pass
            if done.is_set():
                # 清空剩余事件
                while not q.empty():
                    yield await q.get()
                yield json.dumps({"phase": "done"}, ensure_ascii=False)
                return

    async def reset_session(self, sid: str):
        s = self.session_manager.get_or_create(sid or "cli:default")
        s.clear(); self.session_manager.save(s)


adapter: KejiAdapter | None = None


async def get_adapter() -> KejiAdapter:
    global adapter
    if adapter is None:
        adapter = KejiAdapter()
    return adapter