import re
import sys

DENY = [
    r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f?\s+(/|~|\$HOME)(\s|$)",
    r"git\s+push\s+.*(--force|-f)\b",
    r"git\s+reset\s+--hard\s+origin",
    r"\bmkfs\b", r"\bdd\s+if=.*of=/dev/", r":\(\)\s*\{", r"\bchmod\s+-R\s+777\s+/",
]


def check(cmd: str) -> str | None:
    for p in DENY:
        if re.search(p, cmd):
            return f"blocked by forge guard: matches {p}"
    return None


if __name__ == "__main__":
    reason = check(" ".join(sys.argv[1:]))
    if reason:
        print(reason, file=sys.stderr)
        sys.exit(2)
