import os
from pathlib import Path

ROOT = Path(os.environ.get("FORGE_HOME", Path(__file__).resolve().parents[2]))
LIBRARY = ROOT / "library" / "agents"
TEAMS = ROOT / "teams"
TEMPLATES = ROOT / "templates"


def team_dir(team: str) -> Path:
    return TEAMS / team


def agent_dir(slug: str) -> Path:
    return LIBRARY / slug
