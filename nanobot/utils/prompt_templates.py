"""Jinja2-based template rendering for agent prompts."""

from pathlib import Path

try:
    from importlib.resources import files as _pkg_files
except ImportError:
    from importlib_resources import files as _pkg_files  # type: ignore

from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from loguru import logger


_TEMPLATE_DIR: Path | None = None


def _get_template_dir() -> Path:
    global _TEMPLATE_DIR
    if _TEMPLATE_DIR is not None:
        return _TEMPLATE_DIR
    try:
        pkg = _pkg_files("nanobot")
        candidate = pkg / "templates"
        if candidate.is_dir():
            _TEMPLATE_DIR = Path(str(candidate))
            return _TEMPLATE_DIR
    except (ModuleNotFoundError, TypeError, Exception):
        pass
    # Fall back to filesystem path relative to this file
    fallback = Path(__file__).resolve().parent.parent / "templates"
    if fallback.is_dir():
        _TEMPLATE_DIR = fallback
        return fallback
    raise FileNotFoundError("Could not locate nanobot/templates directory")


def render_template(
    name: str,
    *,
    strip: bool = False,
    **kwargs,
) -> str:
    """Render a Jinja2 template from the nanobot/templates package."""
    template_dir = _get_template_dir()
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=False,
    )
    try:
        template = env.get_template(name)
    except TemplateNotFound:
        logger.warning("Template not found: {} (in {})", name, template_dir)
        return ""
    result = template.render(**kwargs)
    if strip:
        result = result.strip()
    return result
