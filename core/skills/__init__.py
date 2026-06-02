"""技能系统：兼容 Anthropic SKILL.md 格式的技能加载与管理"""

from core.skills.models import Skill
from core.skills.registry import SkillRegistry

_registry: SkillRegistry | None = None


def get_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
        _registry.scan()
    return _registry


def reload_skills():
    global _registry
    _registry = SkillRegistry()
    _registry.scan()
    return _registry
