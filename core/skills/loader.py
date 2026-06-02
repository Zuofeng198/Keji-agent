"""SKILL.md 解析器：兼容 Anthropic 格式的 YAML frontmatter + Markdown body 解析。"""

import re
from pathlib import Path
from typing import Any

import yaml

from core.skills.models import Skill


def parse_skill(skill_dir: Path) -> Skill | None:
    """解析一个技能目录，读取 SKILL.md 并提取 frontmatter + body。

    Anthropic SKILL.md 格式：
    ```
    ---
    name: skill-name
    description: 技能描述
    version: 1.0.0
    ---

    ## Instructions
    ...
    ```
    """
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        return None

    raw = skill_file.read_text(encoding="utf-8").strip()

    # 解析 YAML frontmatter（--- ... --- 之间的内容）
    frontmatter: dict[str, Any] = {}
    body = raw

    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        try:
            frontmatter = yaml.safe_load(fm_text) or {}
        except yaml.YAMLError:
            frontmatter = {}
        body = raw[fm_match.end():].strip()

    name = frontmatter.get("name", skill_dir.name)
    description = frontmatter.get("description", "")
    version = str(frontmatter.get("version", "1.0.0"))

    if not name:
        return None

    return Skill(
        name=name,
        description=description,
        version=version,
        path=skill_dir,
        instructions=body,
        raw_frontmatter=frontmatter,
    )
