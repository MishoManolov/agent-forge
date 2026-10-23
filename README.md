# agent-forge

Give it a list of roles in plain English and it builds a team of AI agents, each running in its own terminal, that work together on a target you give them.

- **Any role, not just developers.** Each role is researched on the web first (duties, workflows, tools, pitfalls), reviewed by a critic agent, and only then turned into an agent with a scope, responsibilities, skills, tools and persona. You approve every agent.
- **A team has an orchestrator.** You talk to the orchestrator. It splits your target into tasks, delegates to the specialists, reviews their results and reports back to you.
- **Agents talk to each other over Redis**, using a small set of tools (`send`, `inbox`, `broadcast`, `task_*`). Every message and action is logged and can be replayed.
- **Agents persist.** They live in a library and are reused across teams and iterations. They run on [Hermes Agent](https://hermes-agent.nousresearch.com/) (Nous Research), which saves skills and memory as it works, so they get better with use.
- **Many teams at once.** Each team gets its own tmux session, Redis namespace, workspace folder and port range.

```
            you
             │  (type the target in the orchestrator window)
             ▼
   ┌──────────────────────── tmux session  forge-<team> ─────────────────────────┐
   │ orchestrator │ portfolio-manager │ quant-researcher │ …   one window each   │
   │   Hermes     │      Hermes       │      Hermes      │                       │
   └───────┬──────┴─────────┬─────────┴────────┬─────────┴───────────────────────┘
           │ forge MCP tools (send / inbox / tasks)                 ▲
           ▼                                                        │ "you have mail"
        Redis streams  ◄──────────────────────────────────  courier (one per agent)
        (inboxes, task board, audit log)                    types a nudge into an idle pane
```

## Requirements

| Needed | Why | How to get it |
|---|---|---|
| Linux or macOS (Windows: use WSL) | tmux + shell | |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | Python 3.12 and dependencies | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| git | | usually preinstalled |
| [Docker](https://docs.docker.com/get-docker/) with the compose plugin | runs Redis | or point `FORGE_REDIS_URL` at any Redis 6.2+ |
| tmux 3.x | one terminal per agent | `sudo apt install tmux` / `brew install tmux` |
| [Hermes Agent](https://hermes-agent.nousresearch.com/) | the agent runtime | `uv run forge doctor --install` (runs Hermes' official installer) |
| A model provider | agents need an LLM | an API key for OpenRouter, Anthropic or OpenAI, or a provider logged in through Hermes (`hermes auth`) |

`forge doctor` checks all of this and prints the fix for anything missing.

## Quick start

```bash
git clone https://github.com/MishoManolov/agent-forge.git
cd agent-forge
./scripts/setup.sh                 # uv sync, creates .env, starts Redis, runs `forge doctor`
```

1. Open `.env` and add one provider key and a matching `FORGE_DEFAULT_MODEL` (examples are in the file).
2. If `forge doctor` says Hermes is missing: `uv run forge doctor --install`, then open a new shell so `~/.local/bin` is on your PATH.
3. Re-run `uv run forge doctor` until the required rows (tmux, docker, hermes, redis) are OK.

Then create and run a team:

```bash
# Research the roles, critique them, and approve each agent (y / e = edit / r = regenerate / s = skip)
uv run forge team new fund \
  --goal "Decide whether a 12-1 momentum equity strategy is worth backtesting" \
  -a "portfolio manager for a small momentum equity strategy" \
  -a "quant researcher who backtests trading rules"

uv run forge up fund               # starts the tmux session
uv run forge attach fund           # opens it; the orchestrator is the first window
```

In the orchestrator window, type your target. It delegates through Redis, the other windows light up as they are nudged, and results land in `teams/fund/workspace/`.

Role research uses the web and takes a few minutes per agent. To try the system without waiting, reuse the two sample agents that ship in `library/agents/`: `-a momentum-portfolio-manager -a quant-researcher-backtester`.

tmux basics: switch windows with `Ctrl-b` then `n` / `p` / a number; detach with `Ctrl-b d`; the `c-<agent>` windows are the couriers and can be ignored.

## Commands

| Command | What it does |
|---|---|
| `forge doctor [--install]` | Check tmux, docker, Redis, Hermes, provider keys; install Hermes |
| `forge agent new "<description>" [--goal ...]` | Research one role and save it to the library |
| `forge agent ls` | List library agents |
| `forge team new <name> -a <description-or-slug> ...` | Create a team. A description is researched; an existing slug is reused |
| `forge up <name>` / `down <name>` / `attach <name>` | Start, stop, open a team |
| `forge ls` | List teams and whether they are running |
| `forge logs <name> [-f]` | The message / task / nudge log |
| `forge promote <team> <agent>` | Copy what an agent learned in this team (skills, memory) back into its base profile |

Run commands with `uv run forge ...`, or activate the venv (`source .venv/bin/activate`) to type `forge ...`.

## How it works

- **Library** (`library/agents/<slug>/`): `spec.yaml` (role, scope, responsibilities, skills, tools, out of scope) and `SOUL.md` (persona). Each agent also has a persistent Hermes profile `forge-<slug>`.
- **Team start**: for each agent, a per-team profile `forge-<team>-<slug>` is cloned from its base profile (so a team's learning is kept separate until you `promote` it). The launcher writes the persona plus the team protocol and roster, registers the forge MCP server, and starts `hermes` in a tmux window inside the team workspace.
- **Messaging**: the MCP server gives each agent `send`, `broadcast`, `inbox`, `team_roster`, `task_create`, `task_update`, `task_list`. Messages are Redis streams with one inbox per agent.
- **Wake-up**: an idle Hermes session does not notice new mail, so a small courier process per agent watches its inbox and types a one-line nudge into the pane when the pane has stopped changing.
- **Loop guard**: more than 12 messages per minute between the same pair, or the same message sent three times, is refused with an instruction to escalate.
- **Hermes' own subagent tool is disabled** in team profiles. Otherwise the orchestrator quietly delegates to private subagents instead of messaging teammates.

## Configuration (`.env`)

| Variable | Meaning |
|---|---|
| `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | Copied into every agent's Hermes profile |
| `FORGE_DEFAULT_MODEL` | `<provider>/<model>`, e.g. `openrouter/anthropic/claude-sonnet-4`. Per-agent override: set `model:` in the agent's `spec.yaml` |
| `FORGE_ARCHITECT_MODEL` | Optional stronger model for role research |
| `FORGE_REDIS_URL` | Default `redis://127.0.0.1:6390/0` |
| `FORGE_YOLO` | `1` (default): agents run without approval prompts. `0`: Hermes asks in each pane |

## Safety, read this

With `FORGE_YOLO=1`, agents run shell commands as **your user** without asking. A hook blocks an obvious list of destructive commands (`rm -rf /` or `~`, force-push, `mkfs`, `dd` to a device, and similar), but that list is not a sandbox. Agents are told to stay in `teams/<team>/workspace/`; that is an instruction, not a boundary. Use a throwaway machine or VM for anything untrusted, or set `FORGE_YOLO=0`. Provider keys are written to each profile's `.env` (mode 600) under `~/.hermes/profiles/`.

## Known limitations

- Tested on Linux with Hermes 2026.9.24, tmux 3.4 and a 3-agent team (orchestrator plus two researched roles). macOS is untested.
- Role research output varies with the model. The pipeline retries and tolerates messy JSON, but a weak model can still produce a thin role; review each one when prompted.
- The nudge waits for a pane to stop changing. A pane stuck on a Hermes prompt or a provider rate limit will not be nudged until it settles.
- Not yet tested: two teams running at the same time, `forge promote` on a live team, providers other than GitHub Copilot.
- No web dashboard; observe with the tmux windows and `forge logs -f`.

## Development

```bash
uv run pytest        # unit tests; the Redis integration test is skipped if Redis is not running
uv run ruff check .
```

Layout: `src/forge/` — `bus/` (Redis messaging, loop guard, audit), `mcp_server/` (agent tools), `courier/` (nudges), `architect/` (role research + critic), `team/` (launcher, ports), `library/` (agent store), `guards/` (command filter and Hermes hook); `templates/protocol.md.j2` is the team protocol every agent is given.

## License

MIT
