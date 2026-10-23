"""Hermes pre_tool_call shell hook: reads the tool call JSON on stdin, blocks destructive commands."""
import json
import sys

from .destructive import check


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        print("{}")
        return
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    reason = check(cmd) if payload.get("tool_name") == "terminal" else None
    print(json.dumps({"decision": "block", "reason": reason}) if reason else "{}")


if __name__ == "__main__":
    main()
