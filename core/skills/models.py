from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Skill:
    """一个可复用的技能包，兼容 Anthropic SKILL.md 格式。"""
    name: str
    description: str
    version: str = "1.0.0"
    path: Path | None = None
    instructions: str = ""  # SKILL.md body（不含 YAML frontmatter）
    raw_frontmatter: dict = field(default_factory=dict)
