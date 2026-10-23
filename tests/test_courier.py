import fakeredis

from forge.bus import Bus
from forge.courier.courier import IDLE_SECS, RENUDGE_SECS, State, step


def setup():
    b = Bus("t", fakeredis.FakeRedis(decode_responses=True))
    b.register("w", {})
    b.register("o", {})
    sent = []
    return b, State(snap="x", stable_since=0.0), sent


def test_no_nudge_without_messages():
    b, st, sent = setup()
    assert not step(b, "w", "t:w", st, 100.0, pane=lambda t: "x", send=lambda t, s: sent.append(s))
    assert not sent


def test_nudges_idle_pane_once_then_waits():
    b, st, sent = setup()
    b.send("o", "w", "hi")
    kw = {"pane": lambda t: "x", "send": lambda t, s: sent.append(s)}
    assert step(b, "w", "t:w", st, 100.0, **kw)
    assert not step(b, "w", "t:w", st, 101.0, **kw)  # inside re-nudge window
    assert step(b, "w", "t:w", st, 100.0 + RENUDGE_SECS + 1, **kw)
    assert len(sent) == 2 and "1 new" in sent[0]


def test_busy_pane_is_not_nudged():
    b, st, sent = setup()
    b.send("o", "w", "hi")
    frames = iter(["a", "b", "c"])
    for t in (100.0, 101.0, 102.0):
        step(b, "w", "t:w", st, t, pane=lambda _: next(frames), send=lambda t_, s: sent.append(s))
    assert not sent  # output kept changing for < IDLE_SECS each time
    assert IDLE_SECS > 1
