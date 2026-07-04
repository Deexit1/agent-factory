#!/usr/bin/env bash
# Starts a real postgres + migrated API for Playwright's mock-free e2e tests (SPEC-002).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

if [ ! -f .env ]; then
  cp .env.example .env
fi

docker compose up -d postgres
until docker compose ps postgres | grep -q "healthy"; do sleep 1; done

set -a
source .env
set +a

cd apps/api
export DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT}/${POSTGRES_DB}"
# SPEC-006: e2e is mock-free against a real API, so it needs real auth too. Dev-login
# stands in for the Google round-trip (see docs/06-tech-stack.md / .env.example).
export AUTH_DEV_MODE=true
export SESSION_JWT_SECRET="${SESSION_JWT_SECRET:-e2e-session-secret-at-least-32-bytes-long}"
export AGENT_FACTORY_SERVICE_TOKEN="${AGENT_FACTORY_SERVICE_TOKEN:-e2e-service-token-at-least-32-bytes}"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

# POSIX venvs put the interpreter in bin/, Windows venvs in Scripts/.
PYTHON=.venv/bin/python
if [ ! -x "$PYTHON" ]; then
  PYTHON=.venv/Scripts/python
fi

"$PYTHON" -m pip install --quiet --upgrade pip
"$PYTHON" -m pip install --quiet -e "../../packages/schemas"
"$PYTHON" -m pip install --quiet -e ".[dev]"
"$PYTHON" -m alembic upgrade head
exec "$PYTHON" -m uvicorn api.main:app --host 0.0.0.0 --port 8000
