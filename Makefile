API_DIR := apps/api
WEB_DIR := apps/web
SCHEMAS_DIR := packages/schemas
LLM_ROUTER_DIR := packages/llm_router
SANDBOX_DIR := apps/sandbox
ORCHESTRATOR_DIR := apps/orchestrator

.PHONY: dev test test-unit test-integration check lint typecheck e2e a11y migrate coverage-gate eval llm-router-gate tenant-scope-gate github-app-gate

$(API_DIR)/.venv/.stamp: $(API_DIR)/pyproject.toml $(SCHEMAS_DIR)/pyproject.toml
	cd $(API_DIR) && python3 -m venv .venv
	cd $(API_DIR) && .venv/bin/pip install --upgrade pip
	cd $(API_DIR) && .venv/bin/pip install -e "../../$(SCHEMAS_DIR)"
	cd $(API_DIR) && .venv/bin/pip install -e ".[dev]"
	touch $@

$(SCHEMAS_DIR)/.venv/.stamp: $(SCHEMAS_DIR)/pyproject.toml
	cd $(SCHEMAS_DIR) && python3 -m venv .venv
	cd $(SCHEMAS_DIR) && .venv/bin/pip install --upgrade pip
	cd $(SCHEMAS_DIR) && .venv/bin/pip install -e ".[dev]"
	touch $@

$(LLM_ROUTER_DIR)/.venv/.stamp: $(LLM_ROUTER_DIR)/pyproject.toml
	cd $(LLM_ROUTER_DIR) && python3 -m venv .venv
	cd $(LLM_ROUTER_DIR) && .venv/bin/pip install --upgrade pip
	cd $(LLM_ROUTER_DIR) && .venv/bin/pip install -e ".[dev]"
	touch $@

$(SANDBOX_DIR)/.venv/.stamp: $(SANDBOX_DIR)/pyproject.toml
	cd $(SANDBOX_DIR) && python3 -m venv .venv
	cd $(SANDBOX_DIR) && .venv/bin/pip install --upgrade pip
	cd $(SANDBOX_DIR) && .venv/bin/pip install -e ".[dev]"
	touch $@

$(ORCHESTRATOR_DIR)/.venv/.stamp: $(ORCHESTRATOR_DIR)/pyproject.toml $(SCHEMAS_DIR)/pyproject.toml $(LLM_ROUTER_DIR)/pyproject.toml
	cd $(ORCHESTRATOR_DIR) && python3 -m venv .venv
	cd $(ORCHESTRATOR_DIR) && .venv/bin/pip install --upgrade pip
	cd $(ORCHESTRATOR_DIR) && .venv/bin/pip install -e "../../$(SCHEMAS_DIR)"
	cd $(ORCHESTRATOR_DIR) && .venv/bin/pip install -e "../../$(LLM_ROUTER_DIR)"
	cd $(ORCHESTRATOR_DIR) && .venv/bin/pip install -e ".[dev]"
	touch $@

$(WEB_DIR)/node_modules/.stamp: $(WEB_DIR)/package.json
	cd $(WEB_DIR) && npm install
	touch $@

dev: ## Run the full stack via docker compose
	docker compose up --build

test: test-unit test-integration ## Unit tests (pytest + vitest)

# "Unit" = everything outside tests/integration (no Docker needed). T-203 adds
# orchestrator's first real root-level unit tests (test_git_ops.py, test_github_client.py
# — previously test_claude_runner.py/test_config.py existed but were never actually
# wired into any Makefile target, a pre-existing gap this fixes rather than repeats;
# tests/evals is excluded here too, same reason as tests/integration — real external
# calls, not a fast no-Docker unit suite).
test-unit: $(API_DIR)/.venv/.stamp $(SCHEMAS_DIR)/.venv/.stamp $(LLM_ROUTER_DIR)/.venv/.stamp $(SANDBOX_DIR)/.venv/.stamp $(ORCHESTRATOR_DIR)/.venv/.stamp $(WEB_DIR)/node_modules/.stamp ## Fast tests only, no Docker required
	cd $(API_DIR) && .venv/bin/pytest tests --ignore=tests/integration
	cd $(SCHEMAS_DIR) && .venv/bin/pytest
	cd $(LLM_ROUTER_DIR) && .venv/bin/pytest
	cd $(SANDBOX_DIR) && .venv/bin/pytest tests --ignore=tests/integration
	cd $(ORCHESTRATOR_DIR) && .venv/bin/pytest tests --ignore=tests/integration --ignore=tests/evals
	cd $(WEB_DIR) && npm test

test-integration: $(API_DIR)/.venv/.stamp $(SANDBOX_DIR)/.venv/.stamp $(ORCHESTRATOR_DIR)/.venv/.stamp ## Docker-backed integration suites
	cd $(API_DIR) && .venv/bin/pytest tests/integration
	cd $(SANDBOX_DIR) && .venv/bin/pytest tests/integration
	cd $(ORCHESTRATOR_DIR) && .venv/bin/pytest tests/integration

coverage-gate: $(API_DIR)/.venv/.stamp $(SCHEMAS_DIR)/.venv/.stamp $(LLM_ROUTER_DIR)/.venv/.stamp $(SANDBOX_DIR)/.venv/.stamp $(ORCHESTRATOR_DIR)/.venv/.stamp ## Changed-lines coverage floor (80%) vs origin/main
	cd $(SCHEMAS_DIR) && .venv/bin/pytest --cov=schemas --cov-report=xml:coverage.xml
	cd $(LLM_ROUTER_DIR) && .venv/bin/pytest --cov=llm_router --cov-report=xml:coverage.xml
	cd $(API_DIR) && .venv/bin/pytest --cov=api --cov-report=xml:coverage.xml tests
	cd $(SANDBOX_DIR) && .venv/bin/pytest --cov=sandbox --cov-report=xml:coverage.xml tests
	cd $(ORCHESTRATOR_DIR) && .venv/bin/pytest --cov=orchestrator --cov-report=xml:coverage.xml tests
	pip install --quiet diff-cover
	diff-cover $(SCHEMAS_DIR)/coverage.xml $(LLM_ROUTER_DIR)/coverage.xml $(API_DIR)/coverage.xml $(SANDBOX_DIR)/coverage.xml $(ORCHESTRATOR_DIR)/coverage.xml \
		--compare-branch=origin/main --fail-under=80

lint: $(API_DIR)/.venv/.stamp $(SCHEMAS_DIR)/.venv/.stamp $(LLM_ROUTER_DIR)/.venv/.stamp $(SANDBOX_DIR)/.venv/.stamp $(ORCHESTRATOR_DIR)/.venv/.stamp $(WEB_DIR)/node_modules/.stamp
	cd $(API_DIR) && .venv/bin/ruff check .
	cd $(SCHEMAS_DIR) && .venv/bin/ruff check .
	cd $(LLM_ROUTER_DIR) && .venv/bin/ruff check .
	cd $(SANDBOX_DIR) && .venv/bin/ruff check .
	cd $(ORCHESTRATOR_DIR) && .venv/bin/ruff check .
	cd $(WEB_DIR) && npm run lint

typecheck: $(API_DIR)/.venv/.stamp $(SCHEMAS_DIR)/.venv/.stamp $(LLM_ROUTER_DIR)/.venv/.stamp $(SANDBOX_DIR)/.venv/.stamp $(ORCHESTRATOR_DIR)/.venv/.stamp $(WEB_DIR)/node_modules/.stamp
	cd $(API_DIR) && .venv/bin/mypy src
	cd $(SCHEMAS_DIR) && .venv/bin/mypy src
	cd $(LLM_ROUTER_DIR) && .venv/bin/mypy src
	cd $(SANDBOX_DIR) && .venv/bin/mypy src
	cd $(ORCHESTRATOR_DIR) && .venv/bin/mypy src
	cd $(WEB_DIR) && npm run typecheck

llm-router-gate: ## Fail if anything outside packages/llm_router imports a provider SDK directly
	python3 scripts/check_llm_router_gate.py

tenant-scope-gate: ## Fail if any repository-layer function queries the DB without an org_id reference (T-201)
	python3 scripts/check_tenant_scope_gate.py

github-app-gate: ## Fail if api.github.com is referenced outside github_app_client.py (T-203)
	python3 scripts/check_github_app_gate.py

check: lint typecheck test llm-router-gate tenant-scope-gate github-app-gate ## Full QA gate: lint + typecheck + unit + integration + router gate + tenant-scope gate + github-app gate

e2e: $(WEB_DIR)/node_modules/.stamp ## Playwright end-to-end suite
	cd $(WEB_DIR) && npx playwright install --with-deps chromium
	cd $(WEB_DIR) && npm run e2e

a11y: $(WEB_DIR)/node_modules/.stamp ## Lighthouse accessibility audit of the board page (requires `npm run dev` running)
	cd $(WEB_DIR) && npm run a11y

migrate: $(API_DIR)/.venv/.stamp ## Apply alembic migrations
	cd $(API_DIR) && .venv/bin/alembic upgrade head

eval: $(ORCHESTRATOR_DIR)/.venv/.stamp ## Golden-set eval harness (SPEC-101); pass ARGS="--only-changed" etc.
	cd $(ORCHESTRATOR_DIR) && .venv/bin/python -m orchestrator.evals.runner run --set all $(ARGS)
