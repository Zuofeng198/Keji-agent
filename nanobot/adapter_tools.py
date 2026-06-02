"""科吉业务工具 — 直接 import 函数调用，不走 CLI 子进程"""

from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
from typing import Any, Callable

from loguru import logger
from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.registry import ToolRegistry


# ── 工具函数缓存（按需导入，避免启动时全部加载）──

_FUNC_CACHE: dict[str, Callable] = {}
_MODULES = ["core.new_tools", "core.archive_tools", "core.ocr_tools",
            "core.email_tools", "core.filetools_organize", "core.tools",
            "core.db_tools"]


def _get_func(name: str) -> Callable | None:
    if name in _FUNC_CACHE:
        return _FUNC_CACHE[name]
    for mod_path in _MODULES:
        try:
            mod = importlib.import_module(mod_path)
            fn = getattr(mod, name, None)
            if fn is not None:
                _FUNC_CACHE[name] = fn
                return fn
        except Exception:
            continue
    return None


# ── 科吉工具类 ──

class KejiTool(Tool):
    """通用科吉工具包装：import 函数 -> asyncio.to_thread 执行"""

    def __init__(self, name: str, description: str, param_schema: dict, required: list[str] | None = None):
        self._name = name
        self._desc = description
        schema: dict = {"type": "object", "properties": param_schema}
        if required:
            schema["required"] = required
        self._schema = schema
        self._func: Callable | None = _get_func(name)

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._desc

    @property
    def parameters(self) -> dict[str, Any]:
        return self._schema

    async def execute(self, **kwargs: Any) -> str:
        logger.info("Tool: {} args={}", self._name, str(kwargs)[:200])
        try:
            if self._func is not None:
                result = await asyncio.to_thread(self._func, **kwargs)
                return str(result)[:4000]
            # 回退 CLI
            import subprocess, sys, json as _j, os as _os
            cli = str(Path(__file__).resolve().parent.parent / "cli.py")
            env = {**_os.environ, "PYTHONIOENCODING": "utf-8"}
            proc = subprocess.run(
                [sys.executable, cli, self._name, _j.dumps(kwargs, ensure_ascii=False)],
                capture_output=True, text=True, timeout=120,
                encoding="utf-8", errors="replace", env=env,
            )
            out = (proc.stdout or "").strip()
            for line in reversed(out.splitlines()):
                try:
                    obj = _j.loads(line)
                    if obj.get("ok"):
                        return str(obj["result"])[:4000]
                except _j.JSONDecodeError:
                    continue
            return (proc.stderr or "")[-300:] or "(无输出)"
        except asyncio.TimeoutError:
            return f"超时: {self._name}"
        except Exception as e:
            return f"错误: {type(e).__name__}: {str(e)[:200]}"


# ── 工具定义 ──

# (name, description, properties_dict, required_list_or_None)
TOOL_DEFS: list[tuple[str, str, dict, list[str] | None]] = [
    ("create_document", "创建Word文档，save_path必须含.docx扩展名",
     {"title": {"type": "string", "description": "文档标题"},
      "content": {"type": "string", "description": "正文内容"},
      "save_path": {"type": "string", "description": "保存路径，必须含.docx"},
      "count": {"type": "integer", "description": "份数，默认1"}},
     ["title", "save_path"]),
    ("create_table", "创建Excel表格",
     {"headers": {"type": "string", "description": "表头逗号分隔"},
      "rows": {"type": "string", "description": "行数据|分隔"},
      "save_path": {"type": "string", "description": "保存路径"}},
     ["headers", "save_path"]),
    ("create_presentation", "创建PPT",
     {"title": {"type": "string"}, "slides": {"type": "string", "description": "JSON数组"},
      "save_path": {"type": "string"}},
     ["title", "save_path"]),
    ("read_document", "读取PDF/Word/Excel/PPT文档内容",
     {"path": {"type": "string"}},
     ["path"]),
    ("delete_file", "删除文件（需确认）",
     {"path": {"type": "string"}, "confirm": {"type": "boolean", "description": "确认删除"}},
     ["path", "confirm"]),
    ("knowledge_stats", "知识库统计", {}, []),
    ("list_allowed_directories", "列出全局文件沙箱允许访问的目录", {}, []),

    # ── 基础工具 ──
    ("get_time", "获取当前日期时间", {}, []),
    ("calculator", "计算数学表达式", {"expr": {"type": "string", "description": "如 1+2*3"}}, ["expr"]),
    ("run_code", "执行Python代码完成任意任务", {"code": {"type": "string", "description": "Python代码"}}, ["code"]),

    # ── 数据处理 ──
    ("analyze_data", "分析CSV/Excel数据，计算统计指标", {"data_source": {"type": "string"}, "column": {"type": "string"}}, []),
    ("format_data", "格式化数据，支持排序/筛选/转置", {"data": {"type": "string"}, "operation": {"type": "string"}}, ["data"]),
    ("clean_data", "数据清洗", {"data_source": {"type": "string"}}, []),
    ("convert_data", "格式转换", {"data_source": {"type": "string"}, "target_format": {"type": "string"}}, []),
    ("etl_pipeline", "ETL数据处理", {"source": {"type": "string"}, "operations": {"type": "string"}}, []),

    # ── 知识库 ──
    ("query_knowledge", "知识库语义检索", {"query": {"type": "string"}}, ["query"]),
    ("index_knowledge", "索引文件到知识库", {"path": {"type": "string"}}, ["path"]),
    ("remove_from_knowledge", "从知识库删除文档", {"name": {"type": "string"}}, ["name"]),

    # ── OCR ──
    ("ocr_image", "图片文字识别", {"image_path": {"type": "string"}}, ["image_path"]),
    ("ocr_pdf", "PDF文字识别", {"pdf_path": {"type": "string"}}, ["pdf_path"]),
    ("ocr_batch", "批量OCR识别", {"directory": {"type": "string"}}, ["directory"]),

    # ── 压缩包 ──
    ("browse_archive", "浏览压缩包内容", {"path": {"type": "string", "description": "压缩包路径"}}, ["path"]),
    ("extract_archive", "解压压缩包", {"path": {"type": "string", "description": "压缩包路径"}, "output_dir": {"type": "string"}}, ["path"]),
    ("create_archive", "创建压缩包", {"sources": {"type": "string"}, "output_path": {"type": "string"}}, ["sources", "output_path"]),

    # ── 邮件 ──
    ("parse_email", "解析邮件文件", {"file_path": {"type": "string"}}, ["file_path"]),
    ("batch_parse_emails", "批量解析邮件", {"directory": {"type": "string"}}, ["directory"]),
    ("extract_email_attachments", "提取邮件附件", {"file_path": {"type": "string"}, "output_dir": {"type": "string"}}, ["file_path"]),

    # ── 文件整理 ──
    ("organize_files", "按类型自动分类整理文件", {"source_dir": {"type": "string"}, "mode": {"type": "string"}}, []),
    ("rename_files", "批量重命名文件。模式: prefix(加前缀)/suffix(加后缀)/replace(替换)/number(编号)", {"directory": {"type": "string"}, "pattern": {"type": "string", "description": "模式: prefix/suffix/replace/regex/number"}, "value": {"type": "string", "description": "模式参数"}}, ["directory"]),
    ("deduplicate_files", "文件去重", {"directory": {"type": "string"}}, ["directory"]),

    # ── 输出验证工具 ──
    ("verify_output", "验证输出文件数据的完整性：检查行数、空值、列名、合计一致性。支持指定 Sheet 和数值合计校验",
     {"path": {"type": "string", "description": "要验证的文件路径"},
      "expect_rows": {"type": "integer", "description": "期望的数据行数（0=不检查，排除表头行）"},
      "check_columns": {"type": "string", "description": "需要存在的列名，逗号分隔"},
      "sheet_name": {"type": "string", "description": "Excel Sheet 名（空=全部 sheet）"},
      "check_sum": {"type": "string", "description": "合计校验，格式 '列名=期望值' 或多个用分号隔开。如 '金额=1000' 或 '金额=-'（自动求和）"}},
     ["path"]),

    # ── 数据库工具 ──
    ("db_connect", "连接数据库（MySQL/PostgreSQL），返回连接ID",
     {"db_type": {"type": "string", "description": "mysql 或 postgresql"},
      "host": {"type": "string"}, "port": {"type": "integer"},
      "database": {"type": "string"}, "username": {"type": "string"},
      "password": {"type": "string"}},
     ["db_type", "host", "database", "username", "password"]),
    ("db_list_tables", "列出数据库中的所有表",
     {"connection_id": {"type": "string"}}, ["connection_id"]),
    ("db_describe_table", "查看表结构详情",
     {"connection_id": {"type": "string"}, "table_name": {"type": "string"}},
     ["connection_id", "table_name"]),
    ("db_execute_query", "执行 SQL 查询并返回结果",
     {"connection_id": {"type": "string"}, "sql": {"type": "string"},
      "limit": {"type": "integer", "description": "返回行数上限，默认100"}},
     ["connection_id", "sql"]),
    ("db_test_connection", "测试数据库连接",
     {"db_type": {"type": "string"}, "host": {"type": "string"},
      "port": {"type": "integer"}, "database": {"type": "string"},
      "username": {"type": "string"}, "password": {"type": "string"}},
     ["db_type", "host", "database", "username", "password"]),
    ("db_disconnect", "断开数据库连接",
     {"connection_id": {"type": "string"}}, ["connection_id"]),
]


def register_keji_tools(registry: ToolRegistry, project_root: Path):
    for item in TOOL_DEFS:
        name, desc, params, required = item[0], item[1], item[2], item[3] if len(item) > 3 else None
        try:
            registry.register(KejiTool(name, desc, params, required))
        except Exception as e:
            logger.warning("注册 {} 失败: {}", name, e)
    logger.info("科吉工具注册完成: {} 个", len(TOOL_DEFS))
