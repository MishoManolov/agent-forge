"""Role Architect -> Critic loop. `llm` runs a Hermes profile headlessly and returns text."""
import json
import re
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from ..library.models import AgentSpec

SPEC_KEYS = ("name", "role", "scope", "responsibilities")
LLM = Callable[[str, str], str]  # (profile, prompt) -> text

ARCHITECT_PROMPT = """You are the Role Architect. Research this role on the web: real duties, workflows,
tools and data sources, vocabulary, standards, common pitfalls, and what makes someone excellent.
Then design an AI agent for it.

Role description from the user: {desc}
Team goal context (may be empty): {goal}
Teammates already planned: {others}

Reply with ONLY a JSON object with keys: slug (kebab-case), name, role, scope, responsibilities
(list), skills (list of concrete skills/procedures), tools (list of tools/data sources it should use),
out_of_scope (list), soul (persona and working style, 150-400 words, written in second person),
research_notes (key findings with source URLs)."""

CRITIC_PROMPT = """You are the Critic. Review this agent spec for the role "{desc}".
Check: is the scope specific and non-overlapping with teammates ({others}); are responsibilities
concrete and verifiable; are skills/tools realistic for a terminal agent with web access; is the
persona accurate to how real professionals work; any hallucinated claims.
Spec:
{spec}

Reply with ONLY JSON: {{"ok": bool, "issues": [str], "revised": <full corrected spec JSON or null>}}"""


def ensure_profile(profile: str) -> None:
    from ..team.launcher import merge_env
    home = Path.home() / ".hermes" / "profiles" / profile
    if not home.exists():
        r = subprocess.run(["hermes", "profile", "create", profile, "--clone", "--no-alias"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"cannot create profile {profile}: {r.stderr or r.stdout}")
    merge_env(home)


def hermes_llm(profile: str, prompt: str) -> str:
    ensure_profile(profile)
    from .. import config
    from ..team.launcher import model_flags
    flags = model_flags(config.get("FORGE_ARCHITECT_MODEL") or config.get("FORGE_DEFAULT_MODEL")) \
        if (config.get("FORGE_ARCHITECT_MODEL") or config.get("FORGE_DEFAULT_MODEL")) else []
    r = subprocess.run(["hermes", "-p", profile, *flags, "-z", prompt], capture_output=True,
                       text=True, timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"hermes failed: {r.stderr[-500:]}")
    return r.stdout


def extract_json(text: str, required: tuple[str, ...] = ()) -> dict:
    """First JSON object in text that has all `required` keys (outermost objects win)."""
    dec = json.JSONDecoder()
    pos = 0
    for m in re.finditer(r"\{", text):
        if m.start() < pos:
            continue  # inside an object we already decoded
        try:
            obj, n = dec.raw_decode(text[m.start():])
        except json.JSONDecodeError:
            continue
        pos = m.start() + n
        if isinstance(obj, dict) and all(k in obj for k in required):
            return obj
    raise ValueError("no matching JSON object in model output")


def ask_json(llm: LLM, profile: str, prompt: str, required: tuple[str, ...] = (),
             tries: int = 3) -> dict:
    """Ask for JSON; on a miss, retry with a stricter reminder. Raw replies go to teams/.debug."""
    from .. import paths
    nudge = ""
    for i in range(tries):
        out = llm(profile, prompt + nudge)
        try:
            return extract_json(out, required)
        except ValueError:
            dbg = paths.TEAMS / ".debug"
            dbg.mkdir(parents=True, exist_ok=True)
            (dbg / f"{profile}-{int(time.time())}-{i}.txt").write_text(out)
            nudge = ("\n\nIMPORTANT: your previous reply contained no JSON object. Reply with ONLY "
                     "the JSON object, no prose, no questions, no tool use.")
    raise ValueError(f"{profile}: no JSON after {tries} tries (raw output in teams/.debug)")


def design_agent(desc: str, goal: str = "", others: list[str] | None = None, llm: LLM = hermes_llm,
                 rounds: int = 2) -> AgentSpec:
    others_s = "; ".join(others or []) or "none"
    spec = ask_json(llm, "forge-architect", ARCHITECT_PROMPT.format(desc=desc, goal=goal, others=others_s), SPEC_KEYS)
    for _ in range(rounds):
        verdict = ask_json(llm, "forge-critic", CRITIC_PROMPT.format(
            desc=desc, others=others_s, spec=json.dumps(spec, indent=1)), ("ok",))
        rev = verdict.get("revised")
        if verdict.get("ok") or not isinstance(rev, dict) or not all(k in rev for k in SPEC_KEYS):
            break
        spec = rev
    return AgentSpec(**spec)
