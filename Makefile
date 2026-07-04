API_DIR := apps/api
WEB_DIR := apps/web

.PHONY: dev test check lint typecheck e2e migrate

$(API_DIR)/.venv/.stamp: $(API_DIR)/pyproject.toml
	cd $(API_DIR) && python3 -m venv .venv
	cd $(API_DIR) && .venv/bin/pip install --upgrade pip
	cd $(API_DIR) && .venv/bin/pip install -e ".[dev]"
	touch $@

$(WEB_DIR)/node_modules/.stamp: $(WEB_DIR)/package.json
	cd $(WEB_DIR) && npm install
	touch $@

dev: ## Run the full stack via docker compose
	docker compose up --build

test: $(API_DIR)/.venv/.stamp $(WEB_DIR)/node_modules/.stamp ## Unit tests (pytest + vitest)
	cd $(API_DIR) && .venv/bin/pytest
	cd $(WEB_DIR) && npm test

lint: $(API_DIR)/.venv/.stamp $(WEB_DIR)/node_modules/.stamp
	cd $(API_DIR) && .venv/bin/ruff check .
	cd $(WEB_DIR) && npm run lint

typecheck: $(API_DIR)/.venv/.stamp $(WEB_DIR)/node_modules/.stamp
	cd $(API_DIR) && .venv/bin/mypy src
	cd $(WEB_DIR) && npm run typecheck

check: lint typecheck test ## Full QA gate: lint + typecheck + unit + integration

e2e: $(WEB_DIR)/node_modules/.stamp ## Playwright end-to-end suite
	cd $(WEB_DIR) && npx playwright install --with-deps chromium
	cd $(WEB_DIR) && npm run e2e

migrate: $(API_DIR)/.venv/.stamp ## Apply alembic migrations
	cd $(API_DIR) && .venv/bin/alembic upgrade head
