#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
cd "$repo_root"

if [[ ! -s .local/database-url ]]; then
  printf 'Error: run ./scripts/start-local.sh first.\n' >&2
  exit 1
fi

database_url="$(cat .local/database-url)"
cd backend
TOOLPLANNER_DATABASE_URL="$database_url" uv run --frozen python -m toolplanner.bootstrap_admin --count 2
