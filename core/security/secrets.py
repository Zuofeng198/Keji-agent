"""配置加载与 ${ENV_VAR} 密钥解析。"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

_ENV_PATTERN = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")

# 日志中脱敏的键名（小写匹配）
_SECRET_KEYS = frozenset({
    "api_key", "app_secret", "secret", "password", "token",
    "verification_token", "encrypt_key", "work_secret",
})


def resolve_env_ref(value: str) -> str:
    """将 '${VAR}' 解析为环境变量；非引用格式原样返回。"""
    if not isinstance(value, str):
        return value
    m = _ENV_PATTERN.match(value.strip())
    if not m:
        return value
    var = m.group(1)
    resolved = os.environ.get(var, "")
    if not resolved:
        logger.warning("环境变量 {} 未设置（配置项引用了 ${{{}}}）", var, var)
    return resolved


def resolve_secrets(obj: Any) -> Any:
    """递归解析配置中的 ${ENV} 引用。"""
    if isinstance(obj, dict):
        return {k: resolve_secrets(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_secrets(v) for v in obj]
    if isinstance(obj, str):
        return resolve_env_ref(obj)
    return obj


def mask_secrets(obj: Any) -> Any:
    """用于审计/日志的参数脱敏。"""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if str(k).lower() in _SECRET_KEYS:
                out[k] = "***"
            else:
                out[k] = mask_secrets(v)
        return out
    if isinstance(obj, list):
        return [mask_secrets(v) for v in obj]
    return obj


def load_dotenv_file(project_root: Path | None = None) -> None:
    """从项目根目录 .env 加载环境变量（不覆盖已存在的变量）。"""
    root = project_root or Path(__file__).resolve().parent.parent.parent
    env_file = root / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_app_config(config_path: Path | None = None) -> dict:
    """加载 config.yaml 并解析环境变量引用。"""
    root = Path(__file__).resolve().parent.parent.parent
    load_dotenv_file(root)
    if config_path is None:
        config_path = root / "config.yaml"
    if not config_path.is_file():
        logger.warning("配置文件不存在: {}", config_path)
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return resolve_secrets(raw)
