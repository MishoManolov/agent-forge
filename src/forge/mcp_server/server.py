"""Per-agent MCP server. Identity comes from FORGE_TEAM / FORGE_AGENT env vars."""
import os

from mcp.server.fastmcp import FastMCP

from ..bus import Bus, LoopGuardError

TEAM = os.environ.get("FORGE_TEAM", "dev")
ME = os.environ.get("FORGE_AGENT", "anon")
mcp = FastMCP(f"forge-{ME}")
_bus: Bus | None = None


def bus() -> Bus:
    global _bus
    if _bus is None:
        _bus = Bus(TEAM)
    return _bus


@mcp.tool()
def send(to: str, body: str, subject: str = "", thread: str = "") -> str:
    """Send a message to a teammate (or 'user' to ask the human). Keep it self-contained."""
    try:
        return f"sent {bus().send(ME, to, body, subject, thread)}"
    except (LoopGuardError, ValueError) as e:
        return f"NOT SENT: {e}"


@mcp.tool()
def broadcast(body: str, subject: str = "") -> str:
    """Send a message to every teammate."""
    try:
        return f"sent to {len(bus().broadcast(ME, body, subject))} agents"
    except LoopGuardError as e:
        return f"NOT SENT: {e}"


@mcp.tool()
def inbox(count: int = 20) -> list[dict]:
    """Read (and clear) your unread messages. Call this whenever you are nudged."""
    return bus().inbox(ME, count)


@mcp.tool()
def team_roster() -> dict:
    """Who is on the team, their roles and scope."""
    return bus().roster()


@mcp.tool()
def task_create(title: str, assignee: str, detail: str = "") -> str:
    """Create a task on the shared board and assign it. Also message the assignee."""
    return bus().task_create(ME, title, assignee, detail)


@mcp.tool()
def task_update(task_id: str, status: str = "", note: str = "") -> dict:
    """Update a task. status: open | in_progress | blocked | review | done."""
    return bus().task_update(ME, task_id, status, note)


@mcp.tool()
def task_list() -> list[dict]:
    """The shared task board."""
    return bus().tasks()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
