"""SelfCheckTool — 系统自检工具"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from nanobot.agent.tools.base import Tool
from nanobot.selfcheck.runner import SelfCheckRunner

if TYPE_CHECKING:
    from nanobot.agent.tools.registry import ToolRegistry


class SelfCheckTool(Tool):
    """运行系统全面自检：工具可达性、MCP服务器、数据库、向量存储、Ollama、文件系统、配置"""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        project_root: Path,
        config: dict[str, Any] | None = None,
    ):
        self._registry = tool_registry
        self._project_root = project_root
        self._config = config or {}

    @property
    def name(self) -> str:
        return "selfcheck_run"

    @property
    def description(self) -> str:
        return (
            "运行系统全面自检，检查所有关键组件是否正常。\n"
            "检查项：工具可达性、MCP服务器、数据库(keji.db)、"
            "向量存储(ChromaDB)、Ollama服务、文件系统(data/)、配置完整性。\n"
            "当用户要求自检、或你发现工具有异常时，调用此工具。\n"
            "结果会同时保存到 data/selfcheck/latest.json。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["full", "tools", "mcp", "database"],
                    "description": "检查范围：full（全部）、tools（仅工具）、mcp（仅MCP）、database（仅数据库）",
                },
            },
        }

    async def execute(self, scope: str = "full", **kwargs: Any) -> str:
        runner = SelfCheckRunner(self._registry, self._project_root, self._config)
        report = runner.run()
        return report.format_text()
