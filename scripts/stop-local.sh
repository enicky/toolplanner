#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
cd "$repo_root"

stop_local_process() {
  local name="$1"
  local expected="$2"
  local pid_file=".local/${name}.pid"
  [[ -f "$pid_file" ]] || return 0

  local pid process
  pid="$(cat "$pid_file")"
  if [[ ! "$pid" =~ ^[0-9]+$ ]] || ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$pid_file"
    return 0
  fi
  process="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  if [[ "$process" != *"$expected"* ]]; then
    printf 'Refusing to stop pid %s: it is not the recorded Tool Planner %s process.\n' "$pid" "$name" >&2
    return 1
  fi

  kill "$pid"
  for ((attempt = 1; attempt <= 10; attempt++)); do
    if ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$pid_file"
      printf 'Stopped local %s.\n' "$name"
      return 0
    fi
    sleep 1
  done
  printf '%s process %s did not stop; inspect .local/%s.log.\n' "$name" "$pid" "$name" >&2
  return 1
}

stop_local_process web "node_modules/.bin/vite"
stop_local_process api "uvicorn toolplanner.main:app"

if [[ -n "$(docker-compose ps -q postgres)" ]]; then
  docker-compose stop postgres
fi

printf 'Stopped local Tool Planner. PostgreSQL data remains in its Docker volume.\n'
