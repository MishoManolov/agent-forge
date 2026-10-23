"""Nudges an idle agent pane when new messages arrive. Text only; bodies stay in Redis."""
import subprocess
import time
from dataclasses import dataclass, field

from ..bus import Bus

NUDGE = "You have {n} new team message(s). Call the inbox tool now and act on them."
IDLE_SECS = 3.0
RENUDGE_SECS = 45.0


def _pane(target: str) -> str:
    r = subprocess.run(["tmux", "capture-pane", "-p", "-t", target], capture_output=True, text=True)
    return r.stdout


def _send(target: str, text: str) -> None:
    subprocess.run(["tmux", "send-keys", "-t", target, "-l", text], check=False)
    time.sleep(0.2)
    subprocess.run(["tmux", "send-keys", "-t", target, "Enter"], check=False)


@dataclass
class State:
    snap: str = ""
    stable_since: float = field(default_factory=time.time)
    last_nudge: float = 0.0


def step(bus: Bus, agent: str, target: str, st: State, now: float, pane=_pane, send=_send) -> bool:
    """One poll. Returns True if a nudge was sent. Never nudges a pane whose output is changing."""
    n = bus.unread(agent)
    snap = pane(target)
    if snap != st.snap:
        st.snap, st.stable_since = snap, now
    idle = now - st.stable_since >= IDLE_SECS
    if n and idle and now - st.last_nudge >= RENUDGE_SECS:
        send(target, NUDGE.format(n=n))
        bus.audit("nudge", agent=agent, unread=n)
        st.last_nudge = now
        return True
    return False


def run(team: str, agent: str, target: str, poll: float = 1.0) -> None:
    bus, st = Bus(team), State()
    while True:
        time.sleep(poll)
        try:
            step(bus, agent, target, st, time.time())
        except Exception:  # redis restarting, tmux window gone: keep polling
            continue
