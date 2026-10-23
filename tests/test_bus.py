import fakeredis
import pytest

from forge.bus import Bus, LoopGuardError


@pytest.fixture
def bus():
    b = Bus("t", fakeredis.FakeRedis(decode_responses=True))
    for a in ("orch", "w1"):
        b.register(a, {"role": a})
    return b


def test_send_and_inbox(bus):
    bus.send("orch", "w1", "do X", subject="s")
    assert bus.unread("w1") == 1
    msgs = bus.inbox("w1")
    assert [m["body"] for m in msgs] == ["do X"]
    assert bus.inbox("w1") == []
    assert bus.unread("w1") == 0


def test_unknown_recipient(bus):
    with pytest.raises(ValueError):
        bus.send("orch", "nobody", "x")


def test_user_recipient_allowed(bus):
    bus.send("orch", "user", "question?")


def test_repeat_guard(bus):
    bus.send("orch", "w1", "same")
    bus.send("orch", "w1", "same")
    with pytest.raises(LoopGuardError):
        bus.send("orch", "w1", "same")


def test_rate_guard(bus):
    with pytest.raises(LoopGuardError):
        for i in range(30):
            bus.send("orch", "w1", f"m{i}")


def test_tasks_and_audit(bus):
    tid = bus.task_create("orch", "t", "w1")
    t = bus.task_update("w1", tid, status="done", note="ok")
    assert t["status"] == "done" and t["notes"] == ["w1: ok"]
    assert any(e["kind"] == "task_update" for e in bus.log())
