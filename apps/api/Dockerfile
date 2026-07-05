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

RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
