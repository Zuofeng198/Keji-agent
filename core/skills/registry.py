"""技能注册表：扫描 skills/ 目录，管理所有已注册的技能。"""

from pathlib import Path
from typing import Any

from loguru import logger

from core.skills.loader import parse_skill
from core.skills.models import Skill


class SkillRegistry:
    """扫描并缓存 skills/ 目录下的所有技能。"""

    def __init__(self, skills_dir: Path | str | None = None):
        if skills_dir is None:
            # 默认：项目根目录下的 skills/
            skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
        self._skills_dir = Path(skills_dir)
        self._skills: dict[str, Skill] = {}

    def scan(self) -> int:
        """扫描 skills/ 目录，注册所有 SKILL.md。"""
        self._skills.clear()
        if not self._skills_dir.is_dir():
            logger.warning("技能目录不存在: {}", self._skills_dir)
            return 0

        count = 0
        for entry in sorted(self._skills_dir.iterdir()):
            if not entry.is_dir():
                continue
            try:
                skill = parse_skill(entry)
                if skill is None:
                    continue
                if skill.name in self._skills:
                    logger.warning("技能名称重复，后者覆盖前者: {}", skill.name)
                self._skills[skill.name] = skill
                count += 1
            except Exception as e:
                logger.warning("解析技能失败 {}: {}", entry.name, e)

        logger.info("扫描到 {} 个技能: {}", count, list(self._skills.keys()))
        return count

    def list_skills(self) -> list[dict[str, Any]]:
        """返回所有技能的 name + description（不含完整 instructions）。"""
        return [
            {
                "name": s.name,
                "description": s.description,
                "version": s.version,
                "active": False,  # 前端标记用
            }
            for s in self._skills.values()
        ]

    def get_skill(self, name: str) -> Skill | None:
        """按名称获取完整技能（含 instructions）。"""
        return self._skills.get(name)

    def has_skill(self, name: str) -> bool:
        return name in self._skills

    @property
    def all_skills(self) -> dict[str, Skill]:
        return dict(self._skills)
