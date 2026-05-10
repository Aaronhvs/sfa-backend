DEV_COMPOSE  = docker-compose-development.yml
PROD_COMPOSE = docker-compose-prod.yml
DC_DEV       = docker compose -f $(DEV_COMPOSE)
DC_PROD      = docker compose -f $(PROD_COMPOSE)

.PHONY: help dev dev-build down down-prod logs logs-worker logs-beat \
        test lint format check shell ps migrate

help:
	@echo "SFA Backend — comandos disponibles"
	@echo ""
	@echo "  Desarrollo"
	@echo "    make dev           Levantar stack de desarrollo"
	@echo "    make dev-build     Levantar stack reconstruyendo imágenes"
	@echo "    make down          Bajar stack de desarrollo"
	@echo "    make ps            Estado de los contenedores"
	@echo ""
	@echo "  Producción"
	@echo "    make prod          Levantar stack de producción"
	@echo "    make prod-build    Levantar stack de producción reconstruyendo imágenes"
	@echo "    make down-prod     Bajar stack de producción"
	@echo ""
	@echo "  Logs"
	@echo "    make logs          Logs de todos los servicios (dev)"
	@echo "    make logs-api      Logs del servicio API"
	@echo "    make logs-worker   Logs del Celery worker"
	@echo "    make logs-beat     Logs del Celery beat"
	@echo ""
	@echo "  Base de datos"
	@echo "    make migrate       Correr migraciones Alembic"
	@echo "    make shell-db      Entrar a psql dentro del contenedor DB"
	@echo ""
	@echo "  Desarrollo local"
	@echo "    make shell         Shell dentro del contenedor API"
	@echo "    make test          Correr pytest"
	@echo "    make lint          Verificar estilo con flake8"
	@echo "    make format        Ordenar imports con isort"
	@echo "    make check         lint + isort --check (sin modificar)"

# ── Desarrollo ────────────────────────────────────────────────────────────────

dev:
	$(DC_DEV) up -d

dev-build:
	$(DC_DEV) up --build

down:
	$(DC_DEV) down

ps:
	$(DC_DEV) ps

# ── Producción ────────────────────────────────────────────────────────────────

prod:
	$(DC_PROD) up -d

prod-build:
	$(DC_PROD) up -d --build

down-prod:
	$(DC_PROD) down

# ── Logs ─────────────────────────────────────────────────────────────────────

logs:
	$(DC_DEV) logs -f

logs-api:
	$(DC_DEV) logs -f api

logs-worker:
	$(DC_DEV) logs -f celery_worker

logs-beat:
	$(DC_DEV) logs -f celery_beat

# ── Base de datos ─────────────────────────────────────────────────────────────

migrate:
	$(DC_DEV) exec api alembic upgrade head

shell-db:
	$(DC_DEV) exec db psql -U sfa -d sfa

# ── Desarrollo local ──────────────────────────────────────────────────────────

shell:
	$(DC_DEV) exec api bash

test:
	pytest tests/ -v

lint:
	flake8 src/ tests/

format:
	isort src/ tests/

check:
	flake8 src/ tests/
	isort --check-only src/ tests/
