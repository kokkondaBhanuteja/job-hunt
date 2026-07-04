# Shortcuts for the dockerized stack (db + api + worker + frontend) and host-only CLI.
# Run `make` (or `make help`) to list targets.

.DEFAULT_GOAL := help
.PHONY: help up down restart build logs ps db host-cli notify-test test clean

help:  ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up:  ## Build + start the whole stack (detached)
	docker compose up --build -d
	@echo "UI  -> http://localhost:8080  (Settings: paste API_TOKEN, leave API base blank)"
	@echo "API -> http://localhost:8000"

down:  ## Stop the stack (keeps the Postgres volume)
	docker compose down

restart:  ## Restart the app containers (api + worker + frontend)
	docker compose restart api worker frontend

build:  ## Rebuild images without starting
	docker compose build

logs:  ## Follow logs from all services (Ctrl-C to stop)
	docker compose logs -f

ps:  ## Show container status
	docker compose ps

db:  ## Start only Postgres (for host-native `uv run hunt ...` dev)
	docker compose up -d db

host-cli:  ## Run a host CLI command (browser features), e.g. make host-cli CMD="apply-fill 12"
	cd backend && uv run hunt $(CMD)

notify-test:  ## Send a test notification via the configured channel (host)
	cd backend && uv run hunt notify-test

test:  ## Run backend pytest + frontend vitest
	cd backend && uv run pytest -q
	cd frontend && npx vitest run

clean:  ## Stop the stack AND delete the Postgres volume (DESTROYS local data)
	docker compose down -v
