import os

from .paths import ROOT


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    env.update({k: v for k, v in os.environ.items() if k.startswith(("FORGE_", "ANTHROPIC_", "OPENAI_", "OPENROUTER_"))})
    return env


def get(key: str, default: str = "") -> str:
    return _load_env().get(key) or default


def redis_url() -> str:
    return get("FORGE_REDIS_URL", "redis://127.0.0.1:6390/0")


def provider_env() -> dict[str, str]:
    """API keys to pass to every agent process."""
    e = _load_env()
    return {k: v for k, v in e.items() if k.endswith("_API_KEY") and v}
