#!/usr/bin/env bash
# One-shot setup for agent-forge. Safe to re-run. Linux and macOS.
set -euo pipefail
cd "$(dirname "$0")/.."

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

command -v uv >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }
command -v git >/dev/null || { echo "git is required"; exit 1; }

say "1/4 Python environment"
uv sync

say "2/4 .env"
if [ ! -f .env ]; then cp .env.example .env && echo "created .env - add a provider key to it"; else echo ".env exists"; fi

say "3/4 Redis (docker compose)"
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
  docker compose up -d
else
  echo "docker is not running/installed. Start Docker, then run: docker compose up -d"
  echo "(or point FORGE_REDIS_URL in .env at any Redis >= 6.2)"
fi

say "4/4 Check everything"
uv run forge doctor || {
  echo
  echo "Fix the MISSING rows above. Missing Hermes? Run: uv run forge doctor --install"
  exit 1
}
