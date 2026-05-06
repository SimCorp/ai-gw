# AI Gateway — developer shortcuts
#
# All test targets require the full gateway stack to be running first:
#   docker compose -f infra/docker-compose.yml up --wait
#
# Or bring everything up together (gateway + test runner) in one shot:
#   docker compose -f infra/docker-compose.yml -f infra/docker-compose.test.yml --profile test up --wait

COMPOSE      := docker compose -f infra/docker-compose.yml
COMPOSE_TEST := $(COMPOSE) -f infra/docker-compose.test.yml --profile test

# ── Gateway lifecycle ─────────────────────────────────────────────────────────

.PHONY: up
up:
	$(COMPOSE) up --build --wait

.PHONY: down
down:
	$(COMPOSE) down

.PHONY: logs
logs:
	$(COMPOSE) logs -f

# ── Test suite ────────────────────────────────────────────────────────────────

## Run the full test suite
.PHONY: test
test:
	$(COMPOSE_TEST) run --rm test-runner

## Run smoke tests only  (marker: -m smoke)
.PHONY: test-smoke
test-smoke:
	$(COMPOSE_TEST) run --rm test-runner -v --tb=short -m smoke

## Run proxy tests only  (marker: -m proxy)
.PHONY: test-proxy
test-proxy:
	$(COMPOSE_TEST) run --rm test-runner -v --tb=short -m proxy

# ── Claude agent ──────────────────────────────────────────────────────────────

## Launch an interactive Claude agent that routes through the SimCorp AI Gateway.
## Requires: ANTHROPIC_API_KEY=<gateway sk- key> make claude-agent
.PHONY: claude-agent
claude-agent:
	$(COMPOSE_TEST) run --rm -it claude-agent

# ── Claude sandbox (SSH) ──────────────────────────────────────────────────────

## Start the Claude sandbox container with SSH on port 2222.
## Connect with: ssh claude@localhost -p 2222  (password: gateway)
## Optionally set ANTHROPIC_API_KEY=<gateway sk- key> before running.
.PHONY: sandbox
sandbox:
	$(COMPOSE) --profile sandbox up --build -d claude-sandbox
	@echo ""
	@echo "Sandbox started. Connect with:"
	@echo "  ssh claude@localhost -p 2222"
	@echo "  Password: gateway"
	@echo ""
	@echo "Logs: make sandbox-logs"

.PHONY: sandbox-logs
sandbox-logs:
	$(COMPOSE) --profile sandbox logs -f claude-sandbox

.PHONY: sandbox-stop
sandbox-stop:
	$(COMPOSE) --profile sandbox stop claude-sandbox
