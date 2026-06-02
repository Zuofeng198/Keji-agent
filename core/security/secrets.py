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


_PROVIDER_ENV_VARS: dict[str, str] = {
    "deepseek": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def provider_env_var(provider: str) -> str:
    return _PROVIDER_ENV_VARS.get(provider, f"{provider.upper()}_API_KEY")


def is_env_ref(value: str) -> bool:
    return bool(_ENV_PATTERN.match(str(value or "").strip()))


def upsert_dotenv_var(project_root: Path, key: str, value: str) -> None:
    """写入或更新项目根 .env 中的变量（不覆盖其他行）。"""
    env_file = project_root / ".env"
    lines: list[str] = []
    if env_file.is_file():
        lines = env_file.read_text(encoding="utf-8").splitlines()
    found = False
    out: list[str] = []
    prefix = f"{key}="
    for line in lines:
        if line.strip().startswith("#") or "=" not in line:
            out.append(line)
            continue
        k, _, _ = line.partition("=")
        if k.strip() == key:
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        if out and out[-1].strip():
            out.append("")
        out.append(f"{key}={value}")
    env_file.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.environ[key] = value
    logger.info("已更新 .env 中的 {}", key)


def persist_provider_api_key(config: dict, provider: str, api_key: str, project_root: Path | None = None) -> None:
    """将模型 API Key 写入 .env，并在 config 中改为 ${ENV} 引用。"""
    key = (api_key or "").strip()
    if not key or is_env_ref(key) or key in ("***", "••••"):
        return
    root = project_root or Path(__file__).resolve().parent.parent.parent
    var = provider_env_var(provider)
    upsert_dotenv_var(root, var, key)
    models = config.setdefault("models", {})
    prov = models.setdefault(provider, {})
    prov["api_key"] = f"${{{var}}}"


def mask_api_key_for_settings(raw: str) -> tuple[str, bool]:
    """返回 (展示值, 是否已配置)。不向浏览器回传明文密钥。"""
    if not raw:
        return "", False
    if is_env_ref(raw):
        return "", True
    return "", True


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
