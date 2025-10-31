.PHONY: help build up down logs shell clean backfill models migrate

# Variables
COMPOSE_FILE=docker-compose.yml
PYTHON_CMD=python3

help: ## Show this help message
	@echo "BTC Trading Platform - Makefile Commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

build: ## Build Docker images
	docker compose build

up: ## Start all services
	docker compose up -d

down: ## Stop all services
	docker compose down

logs: ## Show logs from all services
	docker compose logs -f

logs-ingestor: ## Show logs from ingestor service
	docker compose logs -f ingestor

logs-executor: ## Show logs from executor service
	docker compose logs -f executor

logs-trader: ## Show logs from trader service
	docker compose logs -f trader

logs-modelgen: ## Show logs from modelgen service
	docker compose logs -f modelgen

shell-ingestor: ## Open shell in ingestor container
	docker compose exec ingestor /bin/bash

shell-postgres: ## Open psql shell in postgres
	docker compose exec postgres psql -U postgres -d okx_bot

shell-redis: ## Open redis-cli
	docker compose exec redis redis-cli

clean: ## Remove all containers, volumes, and networks
	docker compose down -v
	docker system prune -f

migrate: ## Run database migrations
	docker compose exec postgres psql -U postgres -d okx_bot -f /docker-entrypoint-initdb.d/0001_init_market.sql
	docker compose exec postgres psql -U postgres -d okx_bot -f /docker-entrypoint-initdb.d/0002_init_registry.sql
	docker compose exec postgres psql -U postgres -d okx_bot -f /docker-entrypoint-initdb.d/0003_init_trading.sql

backfill: ## Trigger historical data backfill
	docker compose exec ingestor python -m services.ingestor.main

models: ## Generate new models
	docker compose exec modelgen python -m services.modelgen.main

status: ## Show status of all services
	docker compose ps

restart: ## Restart all services
	docker compose restart

restart-ingestor: ## Restart ingestor service
	docker compose restart ingestor

restart-executor: ## Restart executor service
	docker compose restart executor

restart-trader: ## Restart trader service
	docker compose restart trader

dev-setup: ## Setup development environment locally
	pip install -r requirements/base.txt
	cp .env.example .env

test: ## Run tests (placeholder)
	@echo "Tests not yet implemented"

lint: ## Run linters (placeholder)
	@echo "Linters not yet configured"

format: ## Format code with black (placeholder)
	@echo "Formatter not yet configured"

