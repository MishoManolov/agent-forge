import json
import re
import time

import typer
import yaml
from rich.console import Console
from rich.prompt import Prompt

from . import doctor as doc
from . import paths
from .architect.pipeline import design_agent
from .bus import Bus
from .library import store
from .library.models import AgentSpec, TeamSpec
from .team import launcher

app = typer.Typer(no_args_is_help=True, help="agent-forge: persistent multi-agent teams in tmux")
agent_app = typer.Typer(help="manage the agent library")
team_app = typer.Typer(help="manage teams")
app.add_typer(agent_app, name="agent")
app.add_typer(team_app, name="team")
con = Console()

ORCH = AgentSpec(
    slug="orchestrator", name="Orchestrator", role="Team lead and project orchestrator",
    scope="Owns the target: planning, delegation, review, and reporting to the user",
    responsibilities=["Decompose the user's target into tasks", "Assign tasks to the best teammate",
                      "Read each deliverable and judge it against the target; request rework with specifics",
                      "Report at milestones: the conclusion and key findings first, file paths second",
                      "Resolve blockers"],
    skills=["planning", "delegation", "review"], is_orchestrator=True,
    soul="You are calm, decisive and concise. You never do specialist work yourself when a teammate "
         "owns it. You keep a short running plan and update the task board as work moves.")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "agent"


@app.command()
def doctor(install: bool = typer.Option(False, help="install Hermes if missing")):
    """Check tmux, docker, redis, hermes, providers."""
    if install:
        doc.install_hermes()
    raise typer.Exit(0 if doc.report() else 1)


@agent_app.command("ls")
def agent_ls():
    for a in store.list_all():
        con.print(f"[bold]{a.slug}[/] — {a.role}")


@agent_app.command("new")
def agent_new(description: str, goal: str = "", yes: bool = typer.Option(False, "--yes")):
    """Research a role, critique it, then approve into the library."""
    _create(description, goal, [], yes)


def _create(desc: str, goal: str, others: list[str], yes: bool) -> AgentSpec:
    con.print(f"[cyan]Researching role:[/] {desc}")
    spec = design_agent(desc, goal, others)
    spec.slug = _slug(spec.slug or spec.name)
    con.print(yaml.safe_dump(spec.model_dump(exclude={"soul", "research_notes"}), sort_keys=False))
    if not yes:
        while True:
            c = Prompt.ask("approve? [y]es / [e]dit file / [r]egenerate / [s]kip", default="y")
            if c == "y":
                break
            if c == "s":
                raise typer.Exit(1)
            if c == "r":
                return _create(desc, goal, others, yes)
            if c == "e":
                store.save(spec)
                typer.edit(filename=str(paths.agent_dir(spec.slug) / "spec.yaml"))
                spec = store.load(spec.slug)
    store.save(spec)
    con.print(f"[green]saved[/] library/agents/{spec.slug}")
    return spec


@team_app.command("new")
def team_new(name: str, goal: str = typer.Option("", help="team context for role research"),
             agents: list[str] = typer.Option(..., "--agent", "-a",
                                              help="description of an agent, or an existing library slug"),
             yes: bool = typer.Option(False, "--yes")):
    """Create a team: existing library agents are reused, new descriptions are researched."""
    if not (paths.agent_dir("orchestrator") / "spec.yaml").exists():
        store.save(ORCH)
    slugs = ["orchestrator"]
    for d in agents:
        if (paths.agent_dir(d) / "spec.yaml").exists():
            slugs.append(d)
            con.print(f"reusing [bold]{d}[/]")
        else:
            slugs.append(_create(d, goal, slugs, yes).slug)
    t = TeamSpec(name=name, agents=slugs, orchestrator="orchestrator")
    d = paths.team_dir(name)
    d.mkdir(parents=True, exist_ok=True)
    (d / "team.yaml").write_text(yaml.safe_dump(t.model_dump(), sort_keys=False))
    con.print(f"[green]team '{name}' ready[/]: {', '.join(slugs)}. Run: forge up {name}")


def _team(name: str) -> TeamSpec:
    return TeamSpec(**yaml.safe_load((paths.team_dir(name) / "team.yaml").read_text()))


@app.command()
def up(name: str):
    """Launch the team in tmux."""
    sess = launcher.up(_team(name))
    con.print(f"[green]up[/]. Attach: forge attach {name}  (tmux session {sess})")


@app.command()
def down(name: str):
    launcher.down(name)


@app.command()
def attach(name: str):
    import os
    os.execvp("tmux", ["tmux", "attach", "-t", launcher.session(name)])


@app.command()
def ls():
    for d in sorted(paths.TEAMS.iterdir()):
        if (d / "team.yaml").exists():
            t = _team(d.name)
            running = launcher._run(["tmux", "has-session", "-t", launcher.session(t.name)]).returncode == 0
            con.print(f"{'[green]●' if running else '○'}[/] {t.name}: {', '.join(t.agents)}")


@app.command()
def logs(name: str, follow: bool = typer.Option(False, "-f")):
    """Show the A2A message/action log."""
    bus, last = Bus(name), "-"
    while True:
        for e in bus.log(start=last if last == "-" else f"({last}"):
            last = e["id"]
            kind = e.pop("kind")
            e.pop("id")
            ts = float(e.pop("ts"))
            con.print(f"{time.strftime('%H:%M:%S', time.localtime(ts))} [bold]{kind}[/] "
                      + json.dumps(e, ensure_ascii=False)[:300])
        if not follow:
            break
        time.sleep(1)


@app.command()
def promote(team: str, agent: str):
    """Copy a team agent's learned skills/memory back into the library base profile."""
    import shutil
    src, dst = launcher.hermes_home(launcher.team_profile(team, agent)), launcher.hermes_home(launcher.base_profile(agent))
    for sub in ("skills", "memories"):
        if (src / sub).exists():
            shutil.copytree(src / sub, dst / sub, dirs_exist_ok=True)
    con.print(f"[green]promoted[/] {team}/{agent} -> base profile")
