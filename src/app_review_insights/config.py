"""环境配置：从 .env 与环境变量读取（标准库实现，不引入第三方依赖）。"""

from __future__ import annotations

import os
import pathlib


def load_dotenv(path: str | pathlib.Path = ".env") -> None:
    p = pathlib.Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default


def llm_settings() -> dict:
    return {
        "provider": env_str("LLM_PROVIDER", "deepseek"),
        "base_url": env_str("LLM_BASE_URL", "https://api.deepseek.com"),
        "api_key": env_str("LLM_API_KEY"),
        "model": env_str("LLM_MODEL", "deepseek-v4-flash"),
        "temperature": env_float("LLM_TEMPERATURE", 0.3),
        "timeout": env_int("LLM_TIMEOUT", 60),
        "max_retries": env_int("LLM_MAX_RETRIES", 2),
    }


def llm_available() -> bool:
    return bool(env_str("LLM_API_KEY"))
