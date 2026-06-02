import ast
import datetime
import json
import os
import sys
import subprocess
import operator
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from typing import Callable, Optional

import requests

from core.logger import setup_logger

# CLI 调度器路径
_CLI_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "cli.py"))

logger = setup_logger("keji.tools")

# 工具注册表
_tool_registry: dict[str, dict] = {}

# 工具线程池
_executor = ThreadPoolExecutor(max_workers=8)

# 安全的数学表达式求值
_SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.Mod: operator.mod,
}

_SAFE_FUNCS = {
    "abs": abs, "round": round, "min": min, "max": max,
    "int": int, "float": float,
}


def register_tool(
    name: str,
    description: str,
    parameters: dict,
    category: str = "general",
    timeout: int = 30,
):
    """装饰器：注册工具到全局注册表

    用法:
        @register_tool("get_time", "获取当前时间", {}, category="utility", timeout=10)
        def get_time():
            ...
    """

    def decorator(func: Callable):
        _tool_registry[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "category": category,
            "timeout": timeout,
            "func": func,
        }
        logger.info("Tool registered: %s (category=%s, timeout=%ds)", name, category, timeout)
        return func

    return decorator


def get_tool(name: str) -> Optional[dict]:
    return _tool_registry.get(name)


def list_tools(enabled: Optional[list[str]] = None) -> list[dict]:
    tools = []
    for name, meta in _tool_registry.items():
        if enabled is None or name in enabled:
            tools.append({
                "name": meta["name"],
                "description": meta["description"],
                "parameters": meta["parameters"],
                "category": meta["category"],
            })
    return tools


def get_tools_prompt(enabled: Optional[list[str]] = None) -> str:
    tools = list_tools(enabled)
    if not tools:
        return "当前没有可用工具。"

    lines = ["可用工具列表（通过 function calling 调用）："]
    for t in tools:
        params_desc = json.dumps(t["parameters"], ensure_ascii=False)
        lines.append(
            f"- {t['name']}: {t['description']}\n  parameters: {params_desc}"
        )
    return "\n".join(lines)


def call_tool(tool_name: str, **kwargs) -> str:
    """通过 CLI 进程调用工具，带超时控制"""
    meta = get_tool(tool_name)
    if meta is None:
        return f"错误：工具「{tool_name}」不存在"

    timeout = meta.get("timeout", 30)
    args_json = json.dumps(kwargs, ensure_ascii=False)

    try:
        proc = subprocess.run(
            [sys.executable, _CLI_PATH, tool_name, args_json],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        return f"错误：工具「{tool_name}」执行超时（{timeout}秒）"
    except FileNotFoundError:
        return f"错误：找不到 CLI 调度器 {_CLI_PATH}"
    except OSError as e:
        return f"CLI 进程启动失败：{e}"

    # 从 stdout 中提取结果：优先找含 "ok" 键的 JSON 行，避免误匹配日志行
    output = None
    stdout_text = (proc.stdout or "").strip()
    if stdout_text:
        lines = stdout_text.splitlines()
        # 第一遍：从末尾向前找含 "ok" 键的行（真正的结果）
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if "ok" in obj:
                    output = obj
                    break
            except json.JSONDecodeError:
                continue
        # 第二遍：没找到含 "ok" 的，再找任意合法 JSON（兜底）
        if output is None:
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    output = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue

    if output is None:
        stderr_tail = proc.stderr.strip()[-200:] if proc.stderr else ""
        return f"CLI 输出解析失败（exit={proc.returncode}）: {stderr_tail}"

    if output.get("ok"):
        result = str(output["result"])
        logger.info("Tool call: %s -> %d chars (CLI)", tool_name, len(result))
        return result
    else:
        err = output.get("error", "未知错误")
        logger.error("Tool error: %s -> %s", tool_name, err)
        return f"工具执行出错：{err}"


def call_tools_parallel(calls: list[dict]) -> list[dict]:
    """并行执行多个工具调用，返回结果列表"""
    if len(calls) <= 1:
        # 单个工具直接调
        return [_exec_one(c) for c in calls]

    futures = {}
    for i, c in enumerate(calls):
        futures[_executor.submit(_exec_one, c)] = i

    results = [None] * len(calls)
    for future in futures:
        idx = futures[future]
        try:
            results[idx] = future.result(timeout=60)
        except FutTimeout:
            results[idx] = {"tool": calls[idx].get("name", "unknown"), "result": "执行超时"}
    return results


def _exec_one(call: dict) -> dict:
    name = call.get("name", "")
    args = call.get("arguments", {})

    # 如果模型把参数传成了数组，按工具参数名顺序映射到命名参数
    if isinstance(args, list):
        meta = get_tool(name)
        if meta:
            param_names = list(meta["parameters"].keys())
            mapped = {}
            for i, v in enumerate(args):
                if i < len(param_names):
                    mapped[param_names[i]] = v
                else:
                    mapped[f"arg{i}"] = v
            args = mapped
        else:
            args = {f"arg{i}": v for i, v in enumerate(args)}

    return {"tool": name, "args": args, "result": call_tool(name, **args)}


def truncate_result(result: str, max_chars: int = 2000) -> str:
    """截断过长结果，避免撑爆上下文"""
    if len(result) <= max_chars:
        return result
    return result[:max_chars] + f"\n... (结果过长，已截断前 {max_chars} 字符，完整内容 {len(result)} 字符)"


# ---- 内置工具 ----

@register_tool(
    name="get_time",
    description="获取当前日期和时间",
    parameters={},
    category="utility",
    timeout=5,
)
def get_time() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@register_tool(
    name="calculator",
    description="安全地计算数学表达式，支持 +-*/% ** 和 abs/round/min/max/int/float",
    parameters={"expr": {"type": "string", "description": "数学表达式，如 1+2*3"}},
    category="utility",
    timeout=5,
)
def calculator(expr: str) -> str:
    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BinOp):
            op = _SAFE_OPERATORS.get(type(node.op))
            if op is None:
                raise ValueError(f"不允许的运算符: {type(node.op).__name__}")
            return op(_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp):
            op = _SAFE_OPERATORS.get(type(node.op))
            if op is None:
                raise ValueError(f"不允许的一元运算符: {type(node.op).__name__}")
            return op(_eval(node.operand))
        if isinstance(node, ast.Call):
            if node.func.id not in _SAFE_FUNCS:
                raise ValueError(f"不允许的函数: {node.func.id}")
            args = [_eval(a) for a in node.args]
            return _SAFE_FUNCS[node.func.id](*args)
        raise ValueError(f"不支持的表达式类型: {type(node).__name__}")

    try:
        tree = ast.parse(expr.strip(), mode="eval")
        result = _eval(tree)
        return f"计算结果：{result}"
    except Exception as e:
        return f"计算错误：{str(e)}"


@register_tool(
    name="read_file",
    description="读取电脑上的文本文件内容（支持完整路径或相对于 knowledge 目录的路径）",
    parameters={
        "filename": {"type": "string", "description": "文件路径，如 C:\\Users\\xxx\\Desktop\\note.txt 或 info.txt"},
        "path": {"type": "string", "description": "文件路径（filename 的别名）"},
        "file_path": {"type": "string", "description": "文件路径（filename 的别名）"},
    },
    category="io",
    timeout=10,
)
def read_file(filename: str = "", path: str = "", file_path: str = "", filepath: str = "") -> str:
    if path and not filename:
        filename = path
    if file_path and not filename:
        filename = file_path
    if filepath and not filename:
        filename = filepath
    if not filename:
        return "错误：请提供文件路径"
    # 先尝试作为完整路径
    if os.path.isfile(filename):
        file_path = os.path.abspath(filename)
    else:
        # 回退到 knowledge 目录
        base_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "knowledge")
        )
        file_path = os.path.abspath(os.path.join(base_dir, filename))

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return f"文件「{os.path.basename(file_path)}」内容：\n{content}"
    except FileNotFoundError:
        return f"错误：文件「{filename}」不存在"
    except PermissionError:
        return f"错误：无权限读取文件「{filename}」"
    except Exception as e:
        return f"读取文件出错：{str(e)}"


@register_tool(
    name="web_search",
    description="搜索网页内容，获取实时信息",
    parameters={
        "query": {"type": "string", "description": "搜索关键词"},
        "max_results": {"type": "integer", "description": "最大结果数，默认3"},
    },
    category="web",
    timeout=20,
)
def web_search(query: str, max_results: int = 3) -> str:
    url = f"https://html.duckduckgo.com/html/?q={query}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KejiAgent/1.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        # 简单提取文字内容
        from html.parser import HTMLParser

        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.texts = []
                self.skip = False

            def handle_starttag(self, tag, _attrs):
                if tag in ("script", "style"):
                    self.skip = True

            def handle_endtag(self, tag):
                if tag in ("script", "style"):
                    self.skip = False

            def handle_data(self, data):
                if not self.skip:
                    t = data.strip()
                    if len(t) > 20:
                        self.texts.append(t)

        extractor = TextExtractor()
        extractor.feed(resp.text)
        results = extractor.texts[:max_results * 2]
        if not results:
            return f"搜索「{query}」未找到相关内容"
        return f"搜索「{query}」结果：\n" + "\n---\n".join(results)
    except Exception as e:
        return f"网页搜索出错：{str(e)}"


# 导入扩展工具（触发装饰器注册）
from core import new_tools  # noqa: F401

# 导入新工具模块 — 仅用于触发装饰器注册
from core import archive_tools  # noqa: F401
from core import ocr_tools  # noqa: F401
from core import email_tools  # noqa: F401
from core import filetools_organize  # noqa: F401
from core import db_tools  # noqa: F401
