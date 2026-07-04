API_DIR := apps/api
WEB_DIR := apps/web
SCHEMAS_DIR := packages/schemas
SANDBOX_DIR := apps/sandbox
ORCHESTRATOR_DIR := apps/orchestrator

.PHONY: dev test check lint typecheck e2e a11y migrate

$(API_DIR)/.venv/.stamp: $(API_DIR)/pyproject.toml
	cd $(API_DIR) && python3 -m venv .venv
	cd $(API_DIR) && .venv/bin/pip install --upgrade pip
	cd $(API_DIR) && .venv/bin/pip install -e ".[dev]"
	touch $@

$(SCHEMAS_DIR)/.venv/.stamp: $(SCHEMAS_DIR)/pyproject.toml
	cd $(SCHEMAS_DIR) && python3 -m venv .venv
	cd $(SCHEMAS_DIR) && .venv/bin/pip install --upgrade pip
	cd $(SCHEMAS_DIR) && .venv/bin/pip install -e ".[dev]"
	touch $@

$(SANDBOX_DIR)/.venv/.stamp: $(SANDBOX_DIR)/pyproject.toml
	cd $(SANDBOX_DIR) && python3 -m venv .venv
	cd $(SANDBOX_DIR) && .venv/bin/pip install --upgrade pip
	cd $(SANDBOX_DIR) && .venv/bin/pip install -e ".[dev]"
	touch $@

$(ORCHESTRATOR_DIR)/.venv/.stamp: $(ORCHESTRATOR_DIR)/pyproject.toml $(SCHEMAS_DIR)/pyproject.toml
	cd $(ORCHESTRATOR_DIR) && python3 -m venv .venv
	cd $(ORCHESTRATOR_DIR) && .venv/bin/pip install --upgrade pip
	cd $(ORCHESTRATOR_DIR) && .venv/bin/pip install -e "../../$(SCHEMAS_DIR)"
	cd $(ORCHESTRATOR_DIR) && .venv/bin/pip install -e ".[dev]"
	touch $@

$(WEB_DIR)/node_modules/.stamp: $(WEB_DIR)/package.json
	cd $(WEB_DIR) && npm install
	touch $@

dev: ## Run the full stack via docker compose
	docker compose up --build

test: $(API_DIR)/.venv/.stamp $(SCHEMAS_DIR)/.venv/.stamp $(SANDBOX_DIR)/.venv/.stamp $(ORCHESTRATOR_DIR)/.venv/.stamp $(WEB_DIR)/node_modules/.stamp ## Unit tests (pytest + vitest)
	cd $(API_DIR) && .venv/bin/pytest
	cd $(SCHEMAS_DIR) && .venv/bin/pytest
	cd $(SANDBOX_DIR) && .venv/bin/pytest
	cd $(ORCHESTRATOR_DIR) && .venv/bin/pytest
	cd $(WEB_DIR) && npm test

lint: $(API_DIR)/.venv/.stamp $(SCHEMAS_DIR)/.venv/.stamp $(SANDBOX_DIR)/.venv/.stamp $(ORCHESTRATOR_DIR)/.venv/.stamp $(WEB_DIR)/node_modules/.stamp
	cd $(API_DIR) && .venv/bin/ruff check .
	cd $(SCHEMAS_DIR) && .venv/bin/ruff check .
	cd $(SANDBOX_DIR) && .venv/bin/ruff check .
	cd $(ORCHESTRATOR_DIR) && .venv/bin/ruff check .
	cd $(WEB_DIR) && npm run lint

typecheck: $(API_DIR)/.venv/.stamp $(SCHEMAS_DIR)/.venv/.stamp $(SANDBOX_DIR)/.venv/.stamp $(ORCHESTRATOR_DIR)/.venv/.stamp $(WEB_DIR)/node_modules/.stamp
	cd $(API_DIR) && .venv/bin/mypy src
	cd $(SCHEMAS_DIR) && .venv/bin/mypy src
	cd $(SANDBOX_DIR) && .venv/bin/mypy src
	cd $(ORCHESTRATOR_DIR) && .venv/bin/mypy src
	cd $(WEB_DIR) && npm run typecheck

check: lint typecheck test ## Full QA gate: lint + typecheck + unit + integration

e2e: $(WEB_DIR)/node_modules/.stamp ## Playwright end-to-end suite
	cd $(WEB_DIR) && npx playwright install --with-deps chromium
	cd $(WEB_DIR) && npm run e2e

a11y: $(WEB_DIR)/node_modules/.stamp ## Lighthouse accessibility audit of the board page (requires `npm run dev` running)
	cd $(WEB_DIR) && npm run a11y

migrate: $(API_DIR)/.venv/.stamp ## Apply alembic migrations
	cd $(API_DIR) && .venv/bin/alembic upgrade head
