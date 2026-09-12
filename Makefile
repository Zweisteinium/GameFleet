# GameFleet - one Makefile for native development and Docker deployment.
# Run `make` or `make help` for the list of targets.

DOCKER_REPO ?= h3xachad
# Image tag defaults to the project version in backend/pyproject.toml (kept in sync with frontend/package.json).
VERSION ?= $(shell sed -n 's/^version = "\(.*\)"/\1/p' backend/pyproject.toml)
BACKEND_IMAGE  = $(DOCKER_REPO)/gamefleet-backend
FRONTEND_IMAGE = $(DOCKER_REPO)/gamefleet-frontend
COMPOSE = DOCKER_REPO=$(DOCKER_REPO) VERSION=$(VERSION) docker compose

.DEFAULT_GOAL := help
.PHONY: help install backend frontend db check swagger hash up down restart logs ps shell build release clean

##@ Native development

install: ## Install backend (uv) and frontend (pnpm) dependencies
	cd backend && uv sync
	cd frontend && pnpm install

backend: ## Run the API with auto-reload on http://localhost:8000
	cd backend && uv run uvicorn gamefleet_backend.main:app --reload --host 127.0.0.1 --port 8000

frontend: ## Run the SvelteKit dev server on http://localhost:3000
	cd frontend && pnpm dev

db: ## Start a local PostgreSQL 16 container for development (matches backend/.env defaults)
	docker run -d --name gamefleet-postgres --restart unless-stopped \
		-e POSTGRES_USER=gamefleet_user -e POSTGRES_PASSWORD=gamefleet_pass -e POSTGRES_DB=gamefleet_db \
		-p 5432:5432 -v gamefleet-postgres:/var/lib/postgresql/data postgres:16

check: ## Type-check and lint the frontend, import-check the backend
	cd frontend && pnpm check && pnpm exec eslint .
	cd backend && uv run python -c "import gamefleet_backend.main"

swagger: ## Regenerate frontend/src/lib/api from the running backend's OpenAPI schema
	cd frontend && pnpm swagger

hash: ## Print an scrypt hash for a GAMEFLEET_USERS password (prompts for it)
	cd backend && uv run python -m gamefleet_backend.auth hash

##@ Docker (docker-compose.yml, configured through .env)

up: ## Build and start backend + frontend in the background
	$(COMPOSE) up -d --build

down: ## Stop and remove the containers
	$(COMPOSE) down

restart: ## Restart the containers
	$(COMPOSE) restart

logs: ## Follow logs of all services (make logs S=backend for one)
	$(COMPOSE) logs -f $(S)

ps: ## Show container status
	$(COMPOSE) ps

shell: ## Open a shell in the backend container
	$(COMPOSE) exec backend /bin/bash

build: ## Build both images from scratch, tagged $(VERSION)
	$(COMPOSE) build --no-cache

release: build ## Build, tag as latest and push both images to $(DOCKER_REPO)
	docker tag $(BACKEND_IMAGE):$(VERSION) $(BACKEND_IMAGE):latest
	docker tag $(FRONTEND_IMAGE):$(VERSION) $(FRONTEND_IMAGE):latest
	docker push $(BACKEND_IMAGE):$(VERSION)
	docker push $(BACKEND_IMAGE):latest
	docker push $(FRONTEND_IMAGE):$(VERSION)
	docker push $(FRONTEND_IMAGE):latest

clean: ## Stop containers and remove volumes (deletes the cached game artwork)
	$(COMPOSE) down -v

help: ## Show this help
	@echo "GameFleet $(VERSION)   (make [target] [DOCKER_REPO=user] [VERSION=tag])"
	@awk 'BEGIN {FS = ":.*##"} /^##@/ { printf "\n%s\n", substr($$0, 5) } /^[a-zA-Z_-]+:.*##/ { printf "  %-12s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
