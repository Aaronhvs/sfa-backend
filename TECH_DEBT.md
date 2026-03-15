# Technical Debt

## [TD-001] Hardcoded credentials in Docker Compose and missing SECRET_KEY in .env

**Priority:** High
**Area:** Security / Configuration

### Problem

Currently the compose files hardcode database and Redis credentials directly in
the `environment:` block, and `SECRET_KEY` is never injected into the production
container. This works as a temporary fix but is not acceptable for any real
deployment.

Three things need to happen together:

1. **`.env` / secret store** — Add all real credentials to `.env` (or a secrets
   manager in production). At minimum:
   ```env
   SECRET_KEY=<strong-random-value>
   POSTGRES_USER=<value>
   POSTGRES_PASSWORD=<value>
   POSTGRES_DB=<value>
   DATABASE_URL=postgresql+asyncpg://<user>:<password>@db:5432/<db>
   REDIS_URL=redis://redis:6379/0
   CELERY_BROKER_URL=redis://redis:6379/0
   ```

2. **Docker Compose** — Remove the hardcoded `environment:` values from `api`
   and `celery_worker` in both compose files. Replace them with `env_file: .env`
   only, so the single source of truth is the `.env` file:
   ```yaml
   env_file:
     - .env
   # Remove the hardcoded environment: block entirely
   ```
   Also pass `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` to the `db`
   service from the same `.env` instead of hardcoding them.

3. **Code** — Ensure `src/sfa/core/config.py` reads every credential from the
   environment and never has a fallback to a real password. Default values like
   `postgresql+asyncpg://sfa:sfa@...` are acceptable only for local dev; the
   `ProductionConfig` class should have no defaults for sensitive fields and
   should raise `ValueError` on startup if they are missing (same pattern already
   used for `SECRET_KEY`).

### Acceptance criteria

- `docker compose -f docker-compose-development.yml up` starts with no credentials
  in the compose YAML itself
- `SECRET_KEY` is required and non-empty in all environments
- `.env` is in `.gitignore` and `.env.example` is the only committed reference
- `ProductionConfig` raises `ValueError` at startup if `DATABASE_URL`,
  `REDIS_URL`, or `SECRET_KEY` are missing
