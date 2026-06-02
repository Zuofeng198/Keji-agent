"""自检引擎 — 系统健康检查与报告生成"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.tools.registry import ToolRegistry

# ── 检查项 ──────────────────────────────────────────

# 必须存在的关键工具（按前缀分组）
CRITICAL_TOOL_PREFIXES = {
    "mcp_quack_":                "DuckDB数据分析",
    "mcp_filesystem_":           "文件系统操作",
    "mcp_engineer-your-data_":  "数据处理引擎",
}

# MCP 服务器名称映射（前缀 → 配置名）
MCP_SERVER_NAMES = {
    "mcp_quack_":                "quack",
    "mcp_filesystem_":           "filesystem",
    "mcp_memdb_":                "memdb",
    "mcp_excel_":                "excel",
    "mcp_charts_":               "charts",
    "mcp_doc-tools_":            "doc-tools",
    "mcp_image-gen_":            "image-gen",
    "mcp_engineer-your-data_":  "engineer-your-data",
}


class CheckResult:
    """单项检查结果"""

    def __init__(self, name: str, label: str):
        self.name = name
        self.label = label
        self.passed: bool = False
        self.warning: bool = False
        self.detail: str = ""

    def ok(self, detail: str = "") -> CheckResult:
        self.passed = True
        self.detail = detail
        return self

    def warn(self, detail: str = "") -> CheckResult:
        self.passed = True
        self.warning = True
        self.detail = detail
        return self

    def fail(self, detail: str = "") -> CheckResult:
        self.passed = False
        self.detail = detail
        return self

    @property
    def icon(self) -> str:
        if self.warning:
            return "⚠️"
        return "✅" if self.passed else "❌"

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "label": self.label,
                "passed": self.passed, "warning": self.warning, "detail": self.detail}


class SelfCheckReport:
    """完整自检报告"""

    def __init__(self):
        self.timestamp: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.results: list[CheckResult] = []
        self.errors: list[str] = []

    def add(self, result: CheckResult) -> None:
        self.results.append(result)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def is_all_pass(self) -> bool:
        return self.failed_count == 0 and not self.errors

    def format_text(self) -> str:
        lines = [
            "━━━ 科吉系统自检报告 ━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"时间: {self.timestamp}",
        ]
        if self.errors:
            lines.append(f"运行异常: {len(self.errors)} 个")
        else:
            total = len(self.results)
            passed = self.passed_count
            icon = "✅" if self.is_all_pass else "⚠️"
            lines.append(f"结果: {icon} 通过 {passed}/{total}")
        lines.append("")
        for r in self.results:
            lines.append(f"{r.icon} {r.label:<12} {r.detail}")
        if self.errors:
            lines.append("")
            for e in self.errors:
                lines.append(f"  ⚠️  {e}")
        lines.append("")
        lines.append("━━━ 结束 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "passed": self.passed_count,
            "failed": self.failed_count,
            "is_all_pass": self.is_all_pass,
            "results": [r.to_dict() for r in self.results],
            "errors": self.errors,
        }


class SelfCheckRunner:
    """自检引擎 — 执行所有检查项并生成报告"""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        project_root: Path,
        config: dict[str, Any] | None = None,
    ):
        self.tools = tool_registry
        self.project_root = project_root
        self.config = config or {}

    def run(self) -> SelfCheckReport:
        report = SelfCheckReport()
        for method in [
            self._check_tools,
            self._check_mcp,
            self._check_database,
            self._check_vector_store,
            self._check_ollama,
            self._check_filesystem,
            self._check_config,
        ]:
            try:
                result = method()
                report.add(result)
            except Exception as e:
                name = method.__name__.removeprefix("_check_")
                report.add(CheckResult(name, name).fail(str(e)[:200]))
                logger.warning("SelfCheck {} failed: {}", name, e)
        self._save_report(report)
        return report

    # ── ① 工具可达性 ──────────────────────────────

    def _check_tools(self) -> CheckResult:
        r = CheckResult("tools", "工具可达性")
        all_names = self.tools.tool_names
        total = len(all_names)
        missing: list[str] = []
        # 检查关键前缀组
        for prefix, label in CRITICAL_TOOL_PREFIXES.items():
            found = any(n.startswith(prefix) for n in all_names)
            if not found:
                missing.append(label)
        # 检查 DIRECT_TOOLS
        for name in ("create_document", "create_table", "read_document",
                     "query_knowledge", "analyze_data", "web_search"):
            if not self.tools.has(name):
                missing.append(name)
        if missing:
            return r.fail(f"缺少 {len(missing)} 个关键工具: {', '.join(missing)}")
        return r.ok(f"✓ {total}/{total} 工具已注册")

    # ── ② MCP 服务器健康 ───────────────────────────

    def _check_mcp(self) -> CheckResult:
        r = CheckResult("mcp", "MCP服务器")
        all_names = self.tools.tool_names
        found_servers: set[str] = set()
        for prefix, srv in MCP_SERVER_NAMES.items():
            if any(n.startswith(prefix) for n in all_names):
                found_servers.add(srv)
        total_configured = len(MCP_SERVER_NAMES)
        if len(found_servers) < total_configured:
            missing = set(MCP_SERVER_NAMES.values()) - found_servers
            return r.fail(f"未连接 {len(missing)} 个: {', '.join(sorted(missing))}")
        return r.ok(f"✓ {len(found_servers)}/{total_configured} 服务器在线")

    # ── ③ 数据库 ──────────────────────────────────

    def _check_database(self) -> CheckResult:
        r = CheckResult("database", "数据库")
        try:
            from core.database.db import get_db
            db = get_db()
            convs = db.list_conversations(limit=1)
            return r.ok(f"✓ keji.db 正常（{len(convs)} 条对话）")
        except ImportError as e:
            return r.fail(f"模块导入失败: {e}")

    # ── ④ 向量存储 ────────────────────────────────

    def _check_vector_store(self) -> CheckResult:
        r = CheckResult("vector_store", "向量存储")
        try:
            from core.rag.vector_store import get_vector_store
            vs = get_vector_store()
            count = vs.count()
            return r.ok(f"✓ ChromaDB 正常（{count} 个文档块）")
        except ImportError as e:
            return r.fail(f"模块导入失败: {e}")
        except Exception as e:
            return r.fail(str(e)[:200])

    # ── ⑤ 嵌入模型服务 ─────────────────────────

    def _check_ollama(self) -> CheckResult:
        r = CheckResult("embedding", "嵌入模型")
        models_cfg = self.config.get("models", {})
        default_provider = models_cfg.get("default", "deepseek")
        # 嵌入模型通常用 Ollama 本地跑（nomic-embed-text）
        ollama_cfg = models_cfg.get("ollama", {})
        base_url = ollama_cfg.get("base_url", "http://localhost:11434")
        try:
            import requests
            resp = requests.get(f"{base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                model = self.config.get("knowledge", {}).get("embedding_model", "nomic-embed-text")
                return r.ok(f"✓ Ollama ({model}) @ {base_url}")
            return r.warn(f"Ollama {base_url} 无响应（仅影响本地嵌入，对话不受影响）")
        except Exception as e:
            # 非 Ollama 场景（纯API）可以接受
            if default_provider != "ollama":
                return r.ok(f"✓ 使用云端API（{default_provider}），无需本地Ollama")
            return r.warn(f"Ollama {base_url} 连接失败: {str(e)[:80]}")

    # ── ⑥ 文件系统 ────────────────────────────────

    def _check_filesystem(self) -> CheckResult:
        r = CheckResult("filesystem", "文件系统")
        data_dir = self.project_root / "data"
        issues: list[str] = []
        if not data_dir.exists():
            issues.append("data/ 目录不存在")
        elif not os.access(str(data_dir), os.R_OK):
            issues.append("data/ 不可读")
        elif not os.access(str(data_dir), os.W_OK):
            issues.append("data/ 不可写")
        if issues:
            return r.fail("; ".join(issues))
        return r.ok(f"✓ {data_dir.name}/ 读写正常")

    # ── ⑦ 配置完整性 ──────────────────────────────

    def _check_config(self) -> CheckResult:
        r = CheckResult("config", "配置完整性")
        warnings: list[str] = []
        if not self.config:
            return r.fail("配置为空")
        # 模型配置检查
        models = self.config.get("models", {})
        default_provider = models.get("default", "")
        if not default_provider:
            warnings.append("未设置默认模型( models.default )")
        elif default_provider not in models:
            warnings.append(f"默认模型 '{default_provider}' 的配置不存在")
        else:
            provider_cfg = models.get(default_provider, {})
            if not provider_cfg.get("model"):
                warnings.append(f"{default_provider} 未指定具体模型名")
        # MCP 服务器
        mcp_servers = self.config.get("mcp_servers", {})
        if not mcp_servers:
            warnings.append("未配置MCP服务器")
        # 工具配置
        if not self.config.get("tools"):
            warnings.append("未配置工具段")
        # Agent 行为配置
        agent_cfg = self.config.get("agent", {})
        if not agent_cfg.get("max_tool_rounds"):
            warnings.append("未配置 max_tool_rounds")
        if warnings:
            return r.fail("⚠️ " + "; ".join(warnings))
        return r.ok(f"✓ 默认模型={default_provider}({provider_cfg.get('model','')}), {len(mcp_servers)}个MCP")

    # ── 报告持久化 ────────────────────────────────

    def _save_report(self, report: SelfCheckReport) -> None:
        try:
            self_dir = self.project_root / "data" / "selfcheck"
            self_dir.mkdir(parents=True, exist_ok=True)
            # latest.json
            (self_dir / "latest.json").write_text(
                json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            # history/ 带时间戳
            hist_dir = self_dir / "history"
            hist_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            (hist_dir / f"{ts}.json").write_text(
                json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Save selfcheck report failed: {}", e)
