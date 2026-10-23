import redis

BASE, SPAN = 9100, 20


def allocate(r: redis.Redis, team: str) -> tuple[int, int]:
    """Stable, non-overlapping port range per team (kept in Redis)."""
    cur = r.hget("forge:ports", team)
    if cur:
        lo = int(cur)
    else:
        lo = BASE + (int(r.incr("forge:port_seq")) - 1) * SPAN
        r.hset("forge:ports", team, lo)
    return lo, lo + SPAN - 1
