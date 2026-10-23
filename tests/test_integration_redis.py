"""Needs the forge-redis container (docker compose up -d). Skipped otherwise."""
import uuid

import pytest

from forge.bus import Bus, connect

try:
    connect().ping()
    UP = True
except Exception:
    UP = False

pytestmark = pytest.mark.skipif(not UP, reason="redis not running")


def test_two_teams_isolated_and_mcp_tools(monkeypatch):
    a, b = f"ta{uuid.uuid4().hex[:6]}", f"tb{uuid.uuid4().hex[:6]}"
    ba, bb = Bus(a), Bus(b)
    for bus in (ba, bb):
        for ag in ("orchestrator", "pm"):
            bus.register(ag, {})
    ba.send("orchestrator", "pm", "only for team a")
    assert bb.unread("pm") == 0 and ba.unread("pm") == 1

    from forge.mcp_server import server
    monkeypatch.setattr(server, "TEAM", a)
    monkeypatch.setattr(server, "ME", "pm")
    monkeypatch.setattr(server, "_bus", None)
    msgs = server.inbox()
    assert msgs[0]["body"] == "only for team a"
    assert server.send("nobody", "x").startswith("NOT SENT")
    assert server.send("orchestrator", "done").startswith("sent")
    assert ba.unread("orchestrator") == 1
    for bus in (ba, bb):
        for key in bus.r.scan_iter(f"forge:{bus.team}:*"):
            bus.r.delete(key)
