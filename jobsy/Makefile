.PHONY: help dev down build test lint format migrate migrate-create logs clean

SHELL := /bin/bash

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Development ──────────────────────────────────────────────

dev: ## Start all services with docker-compose
	docker compose up --build -d
	@echo "Services starting..."
	@echo "  Gateway:       http://localhost:8000"
	@echo "  RabbitMQ Mgmt: http://localhost:15672"
	@echo "  MinIO Console: http://localhost:9001"
	@echo "  Elasticsearch: http://localhost:9200"

down: ## Stop all services
	docker compose down

down-clean: ## Stop all services and remove volumes
	docker compose down -v

build: ## Build all Docker images
	docker compose build

logs: ## Tail logs for all services
	docker compose logs -f

logs-%: ## Tail logs for a specific service (e.g., make logs-gateway)
	docker compose logs -f $*

restart-%: ## Restart a specific service (e.g., make restart-gateway)
	docker compose restart $*

# ── Testing ──────────────────────────────────────────────────

test: ## Run all unit tests
	pip install -r requirements-test.txt -q
	pytest -v --tb=short

test-cov: ## Run tests with coverage report
	pip install -r requirements-test.txt -q
	pytest --cov=. --cov-report=term-missing --cov-report=html -v

test-%: ## Run tests for a specific service (e.g., make test-reviews)
	pytest $*/tests/ -v --tb=short

# ── Code Quality ─────────────────────────────────────────────

lint: ## Run linter
	ruff check .

format: ## Auto-format code
	ruff format .
	ruff check --fix .

# ── Database ─────────────────────────────────────────────────

migrate: ## Run database migrations
	alembic upgrade head

migrate-create: ## Create a new migration (usage: make migrate-create msg="add users table")
	alembic revision --autogenerate -m "$(msg)"

migrate-down: ## Rollback last migration
	alembic downgrade -1

migrate-history: ## Show migration history
	alembic history --verbose

# ── Utilities ────────────────────────────────────────────────

shell-db: ## Open psql shell to the database
	docker compose exec postgres psql -U jobsy -d jobsy

shell-redis: ## Open redis-cli shell
	docker compose exec redis redis-cli

clean: ## Remove Python cache files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage coverage.xml

status: ## Show status of all services
	docker compose ps
