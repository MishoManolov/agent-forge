import platform
import shutil
import subprocess

from rich.console import Console
from rich.table import Table

from . import config

HERMES_INSTALL = "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"


def _ok(cmd: list[str]) -> bool:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=10).returncode == 0
    except Exception:
        return False


def checks() -> list[tuple[str, bool, str]]:
    out = []
    tmux_fix = "brew install tmux" if platform.system() == "Darwin" else "sudo apt install -y tmux (or build/extract tmux into ~/.local/bin)"
    out.append(("tmux", shutil.which("tmux") is not None, tmux_fix))
    out.append(("docker", _ok(["docker", "info"]), "install/start docker"))
    out.append(("hermes", shutil.which("hermes") is not None, HERMES_INSTALL))
    try:
        from .bus import connect
        redis_ok = bool(connect().ping())
    except Exception:
        redis_ok = False
    out.append(("redis", redis_ok, "docker compose up -d   (in ~/agent-forge)"))
    keys = config.provider_env()
    for name, var in (("anthropic key", "ANTHROPIC_API_KEY"), ("openai key", "OPENAI_API_KEY"),
                      ("openrouter key", "OPENROUTER_API_KEY")):
        out.append((name, var in keys, f"set {var} in .env (optional)"))
    out.append(("claude CLI login", shutil.which("claude") is not None, "host login; Hermes reuse unverified"))
    out.append(("codex CLI login", shutil.which("codex") is not None, "host login; Hermes reuse unverified"))
    return out


def report() -> bool:
    t = Table("check", "status", "fix")
    required = {"tmux", "docker", "hermes", "redis"}
    ok = True
    for name, good, fix in checks():
        if name in required and not good:
            ok = False
        t.add_row(name, "[green]ok" if good else ("[red]MISSING" if name in required else "[yellow]no"),
                  "" if good else fix)
    Console().print(t)
    return ok


def install_hermes() -> int:
    return subprocess.call(HERMES_INSTALL, shell=True)
