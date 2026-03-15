# Plan: Infrastructure Bootstrap for SFA Backend

## Objective

Bootstrap the project infrastructure from scratch — **without touching `_archive/`**.
Deliverable: runnable FastAPI app with `/api/v1/health`, PostgreSQL + Redis, hexagonal architecture,
two environment configs, Docker Compose, GitHub Actions CI, and linters.

---

## Steps

### Step 1 — Trim `requirements.txt` (analysis only)

Read `/requirements.txt` and identify which packages to keep for the new skeleton:

| Keep | Drop |
|------|------|
| `fastapi` | `soccerdata` |
| `uvicorn` | `pandas` |
| `sqlalchemy` | `beautifulsoup4` |
| `python-dotenv` | `apscheduler` |
| `asyncpg` | everything else not listed |
| `redis` | |
| `celery` | |
| `pydantic-settings` | |

> **Do NOT delete the root `requirements.txt`** — kept for reference.

---

### Step 2 — Create project skeleton

Create the following directory/file layout:

```
sfa-backend/
├── src/
│   └── sfa/
│       ├── __init__.py
│       ├── main.py
│       ├── celery_app.py
│       ├── api/
│       │   ├── __init__.py
│       │   └── v1/
│       │       ├── __init__.py
│       │       └── health.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   └── dependencies.py
│       ├── infrastructure/
│       │   ├── __init__.py
│       │   ├── database.py
│       │   └── redis_client.py
│       └── domain/
│           └── __init__.py
├── tests/
│   ├── __init__.py
│   └── test_health.py
├── requirements/
│   ├── base.txt
│   ├── local.txt
│   ├── production.txt
│   └── test.txt
├── django/
│   ├── development/
│   │   ├── Dockerfile
│   │   └── start
│   └── production/
│       ├── Dockerfile
│       └── start
├── .github/
│   └── workflows/
│       └── ci.yml
├── docker-compose-development.yml
├── docker-compose-prod.yml
├── .env.example
├── .flake8
├── pyproject.toml
└── pytest.ini
```

---

### Step 3 — Settings / config (`src/sfa/core/config.py`)

Using `pydantic-settings`. Three config classes, selected by `APP_ENV` env var:

| Class | `APP_ENV` | `DEBUG` | `.env` file | Notes |
|-------|-----------|---------|-------------|-------|
| `DevelopmentConfig` | `development` | `True` | yes | default |
| `ProductionConfig` | `production` | `False` | no | all vars from real env |
| `TestConfig` | `test` | `True` | no | overrides `DATABASE_URL` to `sfa_test`, sets `CELERY_TASK_ALWAYS_EAGER=True` |

**Required fields (all envs):**

- `DATABASE_URL` — default `postgresql+asyncpg://sfa:sfa@localhost:5432/sfa`
- `REDIS_URL` — default `redis://localhost:6379/0`
- `CELERY_BROKER_URL` — default same as `REDIS_URL`
- `APP_ENV` — default `development`
- `APP_VERSION` — default `0.1.0`
- `DEBUG` — default `False`
- `SECRET_KEY` — **required, no default**; raise `ValueError` at startup if missing

`get_settings()` factory reads `APP_ENV` and returns the appropriate config instance.

---

### Step 4 — Application code

#### `src/sfa/main.py`
- FastAPI app factory, title `"SFA API"`, version from config
- Include health router at prefix `/api/v1`
- Startup event: attempt `SELECT 1` (DB) and `ping()` (Redis); log result; **do not crash on failure**

#### `src/sfa/api/v1/health.py`
- `GET /api/v1/health` — always returns HTTP 200
- Response body:
  ```json
  {
    "status": "ok",
    "database": "connected" | "error",
    "redis": "connected" | "error",
    "version": "0.1.0",
    "env": "development"
  }
  ```
- Endpoint attempts real `SELECT 1` and `ping()` on each request

#### `src/sfa/infrastructure/database.py`
- Async SQLAlchemy engine (`asyncpg`)
- `AsyncSessionLocal` factory
- `Base` declarative base
- `get_db()` async generator dependency (yields session)

#### `src/sfa/infrastructure/redis_client.py`
- `redis.asyncio` client
- `get_redis()` async dependency

#### `src/sfa/core/dependencies.py`
- Re-exports `get_db` and `get_redis` for use in route handlers

#### `src/sfa/celery_app.py`
- Minimal Celery stub using `settings.CELERY_BROKER_URL`

---

### Step 5 — Docker

#### Entry-point scripts (executable shell scripts)

**`django/development/start`**
```sh
#!/bin/sh
set -o errexit
set -o nounset
uvicorn sfa.main:app --host 0.0.0.0 --port 8000 --reload
```

**`django/production/start`**
```sh
#!/bin/sh
set -o errexit
set -o nounset
gunicorn sfa.main:app \
  --bind 0.0.0.0:8000 \
  --workers 3 \
  --worker-class uvicorn.workers.UvicornWorker \
  --access-logfile - \
  --log-level=info
```

#### Dockerfiles

**`django/development/Dockerfile`** — `python:3.12-slim`, installs `local.txt` + `test.txt`

**`django/production/Dockerfile`** — `python:3.12-slim`, installs `production.txt` only

#### Docker Compose

**`docker-compose-development.yml`** — services: `api`, `db` (postgres:16-alpine), `redis` (redis:7-alpine), `celery_worker`

**`docker-compose-prod.yml`** — same services, uses production Dockerfile, no source-code volume mounts

---

### Step 6 — Requirements files

| File | Contents |
|------|----------|
| `requirements/base.txt` | `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `asyncpg`, `redis`, `celery`, `python-dotenv`, `pydantic-settings` |
| `requirements/local.txt` | `-r base.txt` |
| `requirements/production.txt` | `-r base.txt` + `gunicorn` |
| `requirements/test.txt` | `-r base.txt` + `pytest`, `pytest-asyncio`, `pytest-cov`, `pytest-mock`, `httpx`, `flake8`, `isort`, `coverage` |

---

### Step 7 — CI (GitHub Actions)

**`.github/workflows/ci.yml`** — single `ci` job on `ubuntu-latest`:

1. Spin up `postgres:16` and `redis:7` as job services
2. Checkout code
3. Setup Python 3.12
4. Install `local.txt` + `test.txt`
5. Run `flake8 src/ tests/`
6. Run `isort --check-only --diff src/ tests/`
7. Run `coverage run -m pytest tests/` → report with `--fail-under=80`
8. Upload `coverage.xml` as artifact
9. Run `pytest tests/`

Env vars injected in CI: `APP_ENV=test`, `SECRET_KEY`, `DATABASE_URL` (sfa_test), `REDIS_URL`, `CELERY_BROKER_URL`

---

### Step 8 — Linter configuration

**`.flake8`**
- `max-line-length = 120`
- `exclude = migrations,__pycache__,.git,_archive,.venv`
- `select = E302,E501,F401,F821`
- `ignore = E203,W503`

**`pyproject.toml`** (isort only)
- `profile = "black"`, `line_length = 120`, `skip = ["migrations", "_archive", ".venv"]`

**`pytest.ini`**
- `asyncio_mode = auto`
- `testpaths = tests`

---

### Step 9 — `.env.example`

Template with all required variables and safe defaults for local development.

---

## Tests

`tests/test_health.py`:
- `httpx.AsyncClient` + `pytest-asyncio`
- Mock DB (`get_db`) and Redis (`get_redis`) — **no real infrastructure needed**
- Assertions: HTTP 200, response contains `status`, `database`, `redis`, `version`, `env`

---

## Done When

- [ ] `docker compose -f docker-compose-development.yml up` starts api, db, redis, celery_worker without errors
- [ ] `curl localhost:8000/api/v1/health` returns HTTP 200 with valid JSON
- [ ] `pytest tests/ --cov=sfa --cov-fail-under=80` passes
- [ ] `flake8 src/ tests/` exits with 0 errors
- [ ] `isort --check-only src/ tests/` exits with 0 errors
- [ ] `django/development/start` and `django/production/start` are executable shell scripts
- [ ] `django/production/start` uses gunicorn with `uvicorn.workers.UvicornWorker`
- [ ] Both `docker-compose-development.yml` and `docker-compose-prod.yml` exist and are valid YAML
- [ ] `.github/workflows/ci.yml` is present and syntactically valid YAML
- [ ] `_archive/` is untouched
