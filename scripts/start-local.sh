#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
cd "$repo_root"

for command_name in docker docker-compose curl uv node npm python3; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'Error: %s is required but was not found in PATH.\n' "$command_name" >&2
    exit 1
  fi
done

if ! docker info >/dev/null 2>&1; then
  printf 'Error: Docker is not running. Start Docker Desktop and retry.\n' >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  printf 'Created .env from .env.example for local development.\n'
fi

if [[ -n "$(docker-compose ps -q api web)" ]]; then
  printf 'Stopping any previous API/web containers; they will run locally instead.\n'
  docker-compose stop api web
fi

printf 'Starting the PostgreSQL container only...\n'
docker-compose up -d postgres

postgres_ready=0
for ((attempt = 1; attempt <= 40; attempt++)); do
  if docker-compose exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; then
    postgres_ready=1
    break
  fi
  sleep 1
done

if [[ "$postgres_ready" -ne 1 ]]; then
  printf 'PostgreSQL did not become ready. Recent logs follow:\n' >&2
  docker-compose logs --tail=80 postgres >&2
  exit 1
fi

mkdir -p .local
chmod 700 .local
umask 077
compose_config="$(docker-compose config --format json)"
postgres_port="$(printf '%s' "$compose_config" | python3 -c 'import json, sys; config = json.load(sys.stdin); print(next(port["published"] for port in config["services"]["postgres"]["ports"] if int(port["target"]) == 5432))')"
if [[ -z "$(docker-compose ps -q postgres)" ]] &&
  ! python3 -c 'import socket, sys; sock = socket.socket(); sock.bind(("127.0.0.1", int(sys.argv[1]))); sock.close()' "$postgres_port"; then
  printf 'Error: 127.0.0.1:%s is already in use. Set LOCAL_POSTGRES_PORT to another free port in .env and retry.\n' "$postgres_port" >&2
  exit 1
fi
printf '%s' "$compose_config" | python3 "$script_dir/local-database-url.py" > .local/database-url
local_database_url="$(cat .local/database-url)"

printf 'Syncing local API dependencies...\n'
(cd backend && uv sync --frozen --extra dev)

if [[ ! -d web/node_modules || web/package-lock.json -nt web/node_modules/.package-lock.json ]]; then
  printf 'Installing local frontend dependencies...\n'
  (cd web && npm ci --registry=https://registry.npmjs.org)
fi

printf 'Applying database migrations...\n'
(cd backend && TOOLPLANNER_DATABASE_URL="$local_database_url" uv run --frozen alembic upgrade head)

start_local_process() {
  local name="$1"
  local pid_file=".local/${name}.pid"
  shift

  if [[ -f "$pid_file" ]]; then
    local old_pid old_command
    old_pid="$(cat "$pid_file")"
    if [[ "$old_pid" =~ ^[0-9]+$ ]] && kill -0 "$old_pid" 2>/dev/null; then
      old_command="$(ps -p "$old_pid" -o command= 2>/dev/null || true)"
      case "$name:$old_command" in
        api:*uvicorn\ toolplanner.main:app*) printf '%s is already running (pid %s).\n' "$name" "$old_pid"; return ;;
        web:*node_modules/.bin/vite*) printf '%s is already running (pid %s).\n' "$name" "$old_pid"; return ;;
      esac
      printf 'Error: recorded %s pid %s belongs to another process; inspect %s.\n' "$name" "$old_pid" "$pid_file" >&2
      exit 1
    fi
    rm -f "$pid_file"
  fi

  nohup "$@" > ".local/${name}.log" 2>&1 < /dev/null &
  printf '%s\n' "$!" > "$pid_file"
  printf 'Started local %s (pid %s).\n' "$name" "$(cat "$pid_file")"
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local log_file="$3"
  for ((attempt = 1; attempt <= 40; attempt++)); do
    if curl --max-time 2 --silent --fail "$url" >/dev/null; then
      return 0
    fi
    sleep 1
  done
  printf '%s did not become ready. Recent logs follow:\n' "$name" >&2
  tail -n 80 "$log_file" >&2
  return 1
}

if [[ ! -f .local/api.pid ]] && curl --max-time 1 --silent --fail http://127.0.0.1:8000/health/ready >/dev/null; then
  printf 'Error: port 8000 is already serving an untracked API process.\n' >&2
  exit 1
fi
start_local_process api env \
  TOOLPLANNER_DATABASE_URL="$local_database_url" \
  TOOLPLANNER_PUBLIC_BASE_URL=http://127.0.0.1:5173 \
  TOOLPLANNER_COOKIE_SECURE=false \
  TOOLPLANNER_CORS_ORIGINS='["http://localhost:5173"]' \
  bash -c 'cd "$1" && exec .venv/bin/uvicorn toolplanner.main:app --reload --host 127.0.0.1 --port 8000' _ "$repo_root/backend"
wait_for_url "Local API" "http://127.0.0.1:8000/health/ready" ".local/api.log"

if [[ ! -f .local/web.pid ]] && curl --max-time 1 --silent --fail http://127.0.0.1:5173/ >/dev/null; then
  printf 'Error: port 5173 is already serving an untracked frontend process.\n' >&2
  exit 1
fi
start_local_process web \
  bash -c 'cd "$1" && exec ./node_modules/.bin/vite --host 127.0.0.1' _ "$repo_root/web"
wait_for_url "Local frontend" "http://127.0.0.1:5173/" ".local/web.log"

printf '\nTool Planner is ready at http://127.0.0.1:5173\n'
printf 'PostgreSQL is running in Docker; API and frontend are running locally.\n'
printf 'If this is a fresh database, create the initial admins with:\n'
printf '  ./scripts/create-local-admins.sh\n'
printf 'Stop the local API, frontend, and PostgreSQL container with:\n'
printf '  ./scripts/stop-local.sh\n'
