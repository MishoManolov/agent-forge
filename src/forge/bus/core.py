import hashlib
import json
import time

import redis

from .. import config

MAX_PER_MIN = 12  # per directed pair
MAX_REPEATS = 2  # identical body to same recipient


class LoopGuardError(Exception):
    pass


def connect(url: str | None = None) -> redis.Redis:
    return redis.Redis.from_url(url or config.redis_url(), decode_responses=True)


class Bus:
    def __init__(self, team: str, r: redis.Redis | None = None):
        self.team = team
        self.r = r or connect()

    def k(self, *parts: str) -> str:
        return ":".join(["forge", self.team, *parts])

    # -- roster ------------------------------------------------------------
    def register(self, agent: str, info: dict[str, str]) -> None:
        self.r.hset(self.k("roster"), agent, json.dumps(info))
        self._ensure_group(agent)

    def roster(self) -> dict[str, dict]:
        return {a: json.loads(v) for a, v in self.r.hgetall(self.k("roster")).items()}

    def _ensure_group(self, agent: str) -> None:
        try:
            self.r.xgroup_create(self.k("inbox", agent), agent, id="0", mkstream=True)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    # -- messaging -----------------------------------------------------------
    def _guard(self, sender: str, to: str, body: str) -> None:
        rk = self.k("rate", sender, to)
        n = self.r.incr(rk)
        if n == 1:
            self.r.expire(rk, 60)
        if n > MAX_PER_MIN:
            raise LoopGuardError(
                f"loop guard: {sender}->{to} sent {n} messages in 60s. Stop, wait, and summarise "
                "to the orchestrator or the user instead."
            )
        h = hashlib.sha1(body.strip().lower().encode()).hexdigest()
        hk = self.k("rep", sender, to, h)
        c = self.r.incr(hk)
        self.r.expire(hk, 600)
        if c > MAX_REPEATS:
            raise LoopGuardError(
                f"loop guard: identical message to {to} sent {c} times. Change approach or escalate."
            )

    def send(self, sender: str, to: str, body: str, subject: str = "", thread: str = "") -> str:
        if to != "user" and to not in self.roster():
            raise ValueError(f"unknown recipient '{to}'. Known: {sorted(self.roster())}")
        self._guard(sender, to, body)
        msg = {"from": sender, "to": to, "subject": subject, "body": body,
               "thread": thread, "ts": f"{time.time():.3f}"}
        mid = self.r.xadd(self.k("inbox", to), msg)
        self.audit("message", **msg, id=mid)
        return mid

    def broadcast(self, sender: str, body: str, subject: str = "") -> list[str]:
        return [self.send(sender, a, body, subject) for a in self.roster() if a != sender]

    def inbox(self, agent: str, count: int = 20) -> list[dict]:
        key = self.k("inbox", agent)
        self._ensure_group(agent)
        res = self.r.xreadgroup(agent, agent, {key: "0"}, count=count)  # un-acked first
        entries = res[0][1] if res else []
        if not entries:
            res = self.r.xreadgroup(agent, agent, {key: ">"}, count=count)
            entries = res[0][1] if res else []
        if entries:
            self.r.xack(key, agent, *[i for i, _ in entries])
        return [{"id": i, **f} for i, f in entries]

    def unread(self, agent: str) -> int:
        key = self.k("inbox", agent)
        try:
            for g in self.r.xinfo_groups(key):
                if g["name"] == agent:
                    return int(g.get("lag") or 0) + int(g.get("pending", 0))
        except redis.ResponseError:
            pass
        return 0

    # -- tasks ---------------------------------------------------------------
    def task_create(self, creator: str, title: str, assignee: str, detail: str = "") -> str:
        tid = f"T{self.r.incr(self.k('task_seq'))}"
        t = {"id": tid, "title": title, "assignee": assignee, "detail": detail,
             "status": "open", "creator": creator, "notes": []}
        self.r.hset(self.k("tasks"), tid, json.dumps(t))
        self.audit("task_create", **{k: v for k, v in t.items() if k != "notes"})
        return tid

    def task_update(self, who: str, tid: str, status: str = "", note: str = "") -> dict:
        raw = self.r.hget(self.k("tasks"), tid)
        if not raw:
            raise ValueError(f"no such task {tid}")
        t = json.loads(raw)
        if status:
            t["status"] = status
        if note:
            t["notes"].append(f"{who}: {note}")
        self.r.hset(self.k("tasks"), tid, json.dumps(t))
        self.audit("task_update", id=tid, by=who, status=status, note=note)
        return t

    def tasks(self) -> list[dict]:
        return [json.loads(v) for v in self.r.hvals(self.k("tasks"))]

    # -- audit ---------------------------------------------------------------
    def audit(self, kind: str, **fields) -> None:
        rec = {"kind": kind, "ts": f"{time.time():.3f}", **{k: str(v) for k, v in fields.items()}}
        self.r.xadd(self.k("log"), rec)

    def log(self, start: str = "-", count: int = 500) -> list[dict]:
        return [{"id": i, **f} for i, f in self.r.xrange(self.k("log"), start, "+", count=count)]
