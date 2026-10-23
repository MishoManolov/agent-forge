import shutil

import yaml

from .. import paths
from .models import AgentSpec


def save(spec: AgentSpec) -> None:
    d = paths.agent_dir(spec.slug)
    (d / "skills").mkdir(parents=True, exist_ok=True)
    (d / "memory").mkdir(exist_ok=True)
    (d / "spec.yaml").write_text(yaml.safe_dump(spec.model_dump(), sort_keys=False, allow_unicode=True))
    (d / "SOUL.md").write_text(spec.soul)


def load(slug: str) -> AgentSpec:
    f = paths.agent_dir(slug) / "spec.yaml"
    if not f.exists():
        raise FileNotFoundError(f"agent '{slug}' not in library")
    return AgentSpec(**yaml.safe_load(f.read_text()))


def list_all() -> list[AgentSpec]:
    return [load(p.name) for p in sorted(paths.LIBRARY.iterdir()) if (p / "spec.yaml").exists()]


def remove(slug: str) -> None:
    shutil.rmtree(paths.agent_dir(slug), ignore_errors=True)
