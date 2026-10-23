import json

from pydantic import BaseModel, Field, field_validator

LIST_FIELDS = ("responsibilities", "skills", "tools", "out_of_scope")
TEXT_FIELDS = ("name", "role", "scope", "soul", "research_notes", "slug")


def _text(v: object) -> str:
    if v is None:
        return ""
    return v if isinstance(v, str) else json.dumps(v, indent=1, ensure_ascii=False)


class AgentSpec(BaseModel):
    slug: str
    name: str
    role: str
    scope: str
    responsibilities: list[str]
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    model: str | None = None  # provider/model override
    soul: str = ""  # full persona text (SOUL.md body)
    research_notes: str = ""
    is_orchestrator: bool = False

    @field_validator(*TEXT_FIELDS, mode="before")
    @classmethod
    def _coerce_text(cls, v: object) -> str:
        return _text(v)

    @field_validator(*LIST_FIELDS, mode="before")
    @classmethod
    def _coerce_list(cls, v: object) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, dict):
            return [f"{k}: {_text(x)}" for k, x in v.items()]
        return [_text(x) for x in v]


class TeamSpec(BaseModel):
    name: str
    agents: list[str]  # library slugs; orchestrator included
    orchestrator: str
    port_base: int = 0
