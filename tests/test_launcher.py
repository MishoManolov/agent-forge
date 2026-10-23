import subprocess

import fakeredis
import yaml

from forge import paths
from forge.bus import Bus
from forge.library import store
from forge.library.models import AgentSpec, TeamSpec
from forge.team import launcher


def mk(slug, orch=False):
    return AgentSpec(slug=slug, name=slug.title(), role=f"{slug} role", scope="s",
                     responsibilities=["r"], is_orchestrator=orch, soul="soul")


def test_up_builds_profiles_and_tmux(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LIBRARY", tmp_path / "lib")
    monkeypatch.setattr(paths, "TEAMS", tmp_path / "teams")
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    monkeypatch.setattr(launcher.Path, "home", classmethod(lambda c: tmp_path / "home"))
    for s in ("orchestrator", "pm"):
        store.save(mk(s, s == "orchestrator"))
    cmds = []

    def run(cmd, **kw):
        cmds.append(cmd)
        if cmd[:3] == ["hermes", "profile", "create"]:
            launcher.hermes_home(cmd[3]).mkdir(parents=True)
        return subprocess.CompletedProcess(cmd, 1 if cmd[:2] == ["tmux", "has-session"] else 0, "", "")

    bus = Bus("t1", fakeredis.FakeRedis(decode_responses=True))
    launcher.up(TeamSpec(name="t1", agents=["orchestrator", "pm"], orchestrator="orchestrator"), run, bus)
    assert any(c[:2] == ["tmux", "new-session"] and "orchestrator" in c for c in cmds)
    assert sum(1 for c in cmds if c[:2] == ["tmux", "new-window"]) == 3  # pm + 2 couriers
    soul = (launcher.hermes_home("forge-t1-pm") / "SOUL.md").read_text()
    assert "orchestrator role" in soul and "Worker duties" in soul
    cfg = yaml.safe_load((launcher.hermes_home("forge-t1-pm") / "config.yaml").read_text())
    assert cfg["mcp_servers"]["forge"]["env"]["FORGE_AGENT"] == "pm"
    assert set(bus.roster()) == {"orchestrator", "pm"}
    assert any(c[:5] == ["hermes", "-p", "forge-t1-pm", "tools", "disable"] and "delegation" in c for c in cmds)


def test_model_block():
    assert launcher.model_block("openrouter/x/y", None) == {"default": "x/y", "provider": "openrouter"}
    assert launcher.model_block("anthropic/claude-sonnet-5-5", {"provider": "auto"}) == {
        "provider": "auto", "default": "anthropic/claude-sonnet-5-5"}


def test_merge_env_replaces_comment_templates(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher.config, "provider_env", lambda: {"OPENROUTER_API_KEY": "k1", "OPENAI_API_KEY": "k2"})
    (tmp_path / ".env").write_text("# OPENROUTER_API_KEY=\nOPENAI_API_KEY=old\nOTHER=1\n")
    launcher.merge_env(tmp_path)
    lines = (tmp_path / ".env").read_text().splitlines()
    assert "OPENAI_API_KEY=k2" in lines and "OPENROUTER_API_KEY=k1" in lines and "OTHER=1" in lines
    assert "OPENAI_API_KEY=old" not in lines
    assert oct((tmp_path / ".env").stat().st_mode)[-3:] == "600"
