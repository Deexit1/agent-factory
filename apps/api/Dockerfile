FROM python:3.12-slim

WORKDIR /app

# Build context is the repo root (see docker-compose.yml) so this can reach
# packages/schemas — apps/api has depended on it since T-006/T-007's webhook +
# failure-distiller code, same as the local Makefile venv already does.
COPY packages/schemas /packages/schemas
RUN pip install --no-cache-dir -e /packages/schemas

COPY apps/api/pyproject.toml ./
COPY apps/api/src ./src

RUN pip install --no-cache-dir -e .

# capability_registry.py / eval_floors.py locate the repo root by walking up for this
# file (present at the real repo root on the host too) — never hardcode a `.parents[N]`
# depth here, since COPY flattens the `apps/api/` prefix relative to a host checkout.
COPY capability_registry.yaml ./

RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
