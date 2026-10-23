import json

from forge.architect.pipeline import design_agent, extract_json

SPEC = {"slug": "pm", "name": "PM", "role": "Portfolio manager", "scope": "allocation",
        "responsibilities": ["rebalance"], "soul": "You are rigorous."}


def test_extract_json_from_noise():
    assert extract_json('blah {"a": {"b": 1}} trailing')["a"]["b"] == 1


def test_critic_revises():
    calls = []

    def llm(profile, prompt):
        calls.append(profile)
        if profile == "forge-architect":
            return "```json\n" + json.dumps(SPEC) + "\n```"
        if calls.count("forge-critic") == 1:
            return json.dumps({"ok": False, "issues": ["vague"], "revised": {**SPEC, "scope": "better"}})
        return json.dumps({"ok": True, "issues": [], "revised": None})

    spec = design_agent("portfolio manager", llm=llm)
    assert spec.scope == "better"
    assert calls == ["forge-architect", "forge-critic", "forge-critic"]


def test_spec_coerces_messy_model_output():
    messy = {**SPEC, "research_notes": {"Duties": ["a", "b"]}, "skills": "one", "tools": [{"n": 1}],
             "responsibilities": {"x": "y"}}
    from forge.library.models import AgentSpec
    s = AgentSpec(**messy)
    assert "Duties" in s.research_notes and s.skills == ["one"]
    assert s.responsibilities == ["x: y"] and "n" in s.tools[0]


def test_retry_on_missing_json(tmp_path, monkeypatch):
    from forge import paths
    monkeypatch.setattr(paths, "TEAMS", tmp_path)
    replies = iter(["I need more info.", json.dumps(SPEC), json.dumps({"ok": True})])
    spec = design_agent("pm", llm=lambda p, q: next(replies))
    assert spec.slug == "pm"
    assert len(list((tmp_path / ".debug").iterdir())) == 1


def test_extract_skips_decoy_objects():
    txt = 'notes {"Momentum": "x"} then ' + json.dumps(SPEC)
    assert extract_json(txt, ("name", "role"))["slug"] == "pm"
