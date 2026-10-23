"""Builds per-team Hermes profiles and the tmux session. Shell calls go through `run`."""
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

from .. import config, paths
from ..bus import Bus
from ..library import store
from ..library.models import AgentSpec, TeamSpec
from . import ports

Run = Callable[..., subprocess.CompletedProcess]


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def hermes_home(profile: str) -> Path:
    return Path.home() / ".hermes" / "profiles" / profile


def base_profile(slug: str) -> str:
    return f"forge-{slug}"


def team_profile(team: str, slug: str) -> str:
    return f"forge-{team}-{slug}"


def session(team: str) -> str:
    return f"forge-{team}"


def render_soul(spec: AgentSpec, team: str, roster: list[AgentSpec], workspace: Path,
                port_lo: int, port_hi: int) -> str:
    env = Environment(loader=FileSystemLoader(paths.TEMPLATES), keep_trailing_newline=True)
    proto = env.get_template("protocol.md.j2").render(
        agent=spec, team=team, roster=[a for a in roster if a.slug != spec.slug],
        workspace=workspace, port_lo=port_lo, port_hi=port_hi)
    head = (f"# {spec.name}\n\nRole: {spec.role}\nScope: {spec.scope}\n\n## Responsibilities\n"
            + "".join(f"- {x}\n" for x in spec.responsibilities)
            + ("\n## Out of scope\n" + "".join(f"- {x}\n" for x in spec.out_of_scope)
               if spec.out_of_scope else "")
            + ("\n## Skills\n" + "".join(f"- {x}\n" for x in spec.skills) if spec.skills else "")
            + ("\n## Tools\n" + "".join(f"- {x}\n" for x in spec.tools) if spec.tools else "")
            + f"\n{spec.soul}\n")
    return head + proto


def ensure_base_profile(spec: AgentSpec, run: Run = _run) -> Path:
    """Persistent per-agent profile; survives across teams and iterations."""
    p = base_profile(spec.slug)
    home = hermes_home(p)
    if not home.exists():
        r = run(["hermes", "profile", "create", p, "--clone", "--no-alias"])
        if r.returncode != 0:
            raise RuntimeError(f"hermes profile create failed: {r.stderr or r.stdout}")
    return home


def build_team_profile(spec: AgentSpec, team: str, roster: list[AgentSpec], workspace: Path,
                       port_range: tuple[int, int], run: Run = _run) -> str:
    ensure_base_profile(spec, run)
    p = team_profile(team, spec.slug)
    if not hermes_home(p).exists():
        r = run(["hermes", "profile", "create", p, "--clone-from", base_profile(spec.slug),
                 "--clone-all", "--no-alias"])
        if r.returncode != 0:
            raise RuntimeError(f"hermes profile create failed: {r.stderr or r.stdout}")
    home = hermes_home(p)
    (home / "SOUL.md").write_text(render_soul(spec, team, roster, workspace, *port_range))
    # library skills authored by the architect
    for sk in (paths.agent_dir(spec.slug) / "skills").glob("*"):
        dst = home / "skills" / sk.name
        if sk.is_dir():
            shutil.copytree(sk, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(sk, dst)
    _write_config(home, spec, team)
    # Hermes' own subagents bypass the bus; the forge MCP tools must be the only way to delegate.
    run(["hermes", "-p", p, "tools", "disable", *DISABLED_TOOLSETS])
    merge_env(home)
    return p


DISABLED_TOOLSETS = ["delegation", "cronjob", "computer_use"]
PROVIDER_PREFIXES = {"openrouter", "openai-codex", "copilot", "nous", "gemini", "anthropic-direct"}


def model_flags(model: str) -> list[str]:
    """CLI flags selecting provider/model for a 'provider/model' spec string."""
    b = model_block(model, None)
    return (["--provider", b["provider"]] if "provider" in b else []) + ["-m", b["default"]]


def model_block(model: str, current: object) -> dict:
    """'openrouter/vendor/name' -> provider openrouter; otherwise keep provider auto-detect."""
    block = dict(current) if isinstance(current, dict) else {}
    head, _, rest = model.partition("/")
    if head in PROVIDER_PREFIXES and rest:
        block.update(default=rest, provider=head.removesuffix("-direct"))
    else:
        block.update(default=model)
    return block


def first_turn(spec: AgentSpec, team: str) -> str:
    if spec.is_orchestrator:
        return (f"You are the orchestrator of team {team}. Call team_roster, then greet the user "
                "briefly and ask for the target. Do nothing else until you have it.")
    return (f"You are {spec.name} on team {team}. Call team_roster once, then stop and wait; "
            "the orchestrator will message you. Act when nudged to read your inbox.")


def merge_env(home: Path) -> None:
    """Put forge's provider API keys into a Hermes profile .env (set keys replace; comments are ignored)."""
    keys = config.provider_env()
    if not keys:
        return
    envf = home / ".env"
    lines = envf.read_text().splitlines() if envf.exists() else []
    done: set[str] = set()
    for i, line in enumerate(lines):
        k = line.split("=", 1)[0].strip()
        if not line.lstrip().startswith("#") and "=" in line and k in keys:
            lines[i], _ = f"{k}={keys[k]}", done.add(k)
    lines += [f"{k}={v}" for k, v in keys.items() if k not in done]
    envf.write_text("\n".join(lines) + "\n")
    envf.chmod(0o600)


def _write_config(home: Path, spec: AgentSpec, team: str) -> None:
    f = home / "config.yaml"
    cfg = yaml.safe_load(f.read_text()) if f.exists() and f.read_text().strip() else {}
    cfg = cfg or {}
    model = spec.model or config.get("FORGE_DEFAULT_MODEL")
    if model:
        cfg["model"] = model_block(model, cfg.get("model"))
    cfg["hooks_auto_accept"] = True
    cfg.setdefault("sessions", {})["auto_prune"] = False  # avoid a blocking first-run prompt in panes
    cfg["hooks"] = {"pre_tool_call": [{
        "matcher": "terminal", "timeout": 10, "fail_closed": True,
        "command": f"{sys.executable} -m forge.guards.hook"}]}
    cfg.setdefault("mcp_servers", {})["forge"] = {
        "command": sys.executable,
        "args": ["-m", "forge.mcp_server.server"],
        "env": {"FORGE_TEAM": team, "FORGE_AGENT": spec.slug,
                "FORGE_REDIS_URL": config.redis_url(), "FORGE_HOME": str(paths.ROOT),
                "PYTHONPATH": str(paths.ROOT / "src")},
        "tools": {"prompts": False, "resources": False},
    }
    f.write_text(yaml.safe_dump(cfg, sort_keys=False))


def init_workspace(team: str) -> Path:
    ws = paths.team_dir(team) / "workspace"
    for d in ("docs", "reports", "src"):
        (ws / d).mkdir(parents=True, exist_ok=True)
    if not (ws / ".git").exists():
        _run(["git", "init", "-q", str(ws)])
    return ws


def up(team: TeamSpec, run: Run = _run, bus: Bus | None = None) -> str:
    roster = [store.load(s) for s in team.agents]
    bus = bus or Bus(team.name)
    port_range = ports.allocate(bus.r, team.name)
    ws = init_workspace(team.name)
    sess = session(team.name)
    if run(["tmux", "has-session", "-t", sess]).returncode == 0:
        raise RuntimeError(f"team '{team.name}' is already running (tmux session {sess})")
    ordered = sorted(roster, key=lambda a: a.slug != team.orchestrator)
    for spec in ordered:
        bus.register(spec.slug, {"role": spec.role, "scope": spec.scope})
    for i, spec in enumerate(ordered):
        prof = build_team_profile(spec, team.name, roster, ws, port_range, run)
        env = f"FORGE_TEAM={team.name} FORGE_AGENT={spec.slug}"
        yolo = " --yolo" if config.get("FORGE_YOLO", "1") == "1" else ""
        cmd = (f"{env} PYTHONPATH={paths.ROOT / 'src'} hermes -p {prof}{yolo} "
               f"chat -q {shlex.quote(first_turn(spec, team.name))}")
        if i == 0:
            run(["tmux", "new-session", "-d", "-s", sess, "-n", spec.slug, "-c", str(ws), cmd])
        else:
            run(["tmux", "new-window", "-t", sess, "-n", spec.slug, "-c", str(ws), cmd])
        courier = (f"{sys.executable} -m forge.courier {team.name} {spec.slug} {sess}:{spec.slug}")
        run(["tmux", "new-window", "-d", "-t", sess, "-n", f"c-{spec.slug}", "-c", str(paths.ROOT),
             f"while true; do PYTHONPATH={paths.ROOT / 'src'} {courier}; sleep 2; done"])
    run(["tmux", "select-window", "-t", f"{sess}:{team.orchestrator}"])
    bus.audit("team_up", team=team.name, agents=",".join(team.agents))
    return sess


def down(team: str, run: Run = _run) -> None:
    run(["tmux", "kill-session", "-t", session(team)])
