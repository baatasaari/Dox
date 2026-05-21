.PHONY: install dev stop clean migrate migrate-create test test-unit lint lint-fix seed help

help:
	@echo "Dox — available targets:"
	@echo "  install        Install all dependencies via Poetry"
	@echo "  dev            Start Docker services and run migrations"
	@echo "  stop           Stop Docker services"
	@echo "  clean          Stop Docker services and destroy volumes (destructive)"
	@echo "  migrate        Run Alembic migrations (upgrade head)"
	@echo "  migrate-create Create a new migration: make migrate-create name=<name>"
	@echo "  test           Run full test suite (requires Docker services running)"
	@echo "  test-unit      Run unit tests only (no Docker required)"
	@echo "  lint           Run ruff and mypy"
	@echo "  lint-fix       Run ruff with auto-fix"
	@echo "  seed           Load development fixtures"

install:
	poetry install

dev:
	docker-compose up -d
	@echo "Waiting for PostgreSQL to be ready..."
	@for i in $$(seq 1 30); do \
		docker-compose exec postgres pg_isready -U dox -d dox > /dev/null 2>&1 && break; \
		echo "  attempt $$i/30..."; \
		sleep 1; \
	done
	@docker-compose exec postgres pg_isready -U dox -d dox > /dev/null 2>&1 || (echo "ERROR: PostgreSQL did not become ready" && exit 1)
	@echo "PostgreSQL is ready."
	$(MAKE) migrate

stop:
	docker-compose down

clean:
	@read -p "This destroys all local data. Type YES to confirm: " confirm; \
	[ "$$confirm" = "YES" ] || (echo "Aborted." && exit 1)
	docker-compose down -v
	@echo "All volumes removed."

migrate:
	poetry run alembic upgrade head

migrate-create:
ifndef name
	$(error name is required: make migrate-create name=<migration_name>)
endif
	poetry run alembic revision --autogenerate -m "$(name)"

test:
	poetry run pytest

test-unit:
	poetry run pytest tests/unit/ --no-cov

lint:
	poetry run ruff check .
	poetry run mypy common/ services/

lint-fix:
	poetry run ruff check --fix .

seed:
	poetry run python -m scripts.seed_fixtures
