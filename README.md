# SFA — Stadistic Football Award

Sistema de puntuación de jugadores de fútbol que combina estadísticas avanzadas con contexto real del partido. Calcula un score (SFA pts) por cada acción significativa usando multiplicadores de contexto.

## Documentacion

| Documento | Descripcion |
|---|---|
| **Este archivo** | Setup rapido, formula de scoring, referencia de variables de entorno |
| [`docs/guia-tecnica.md`](docs/guia-tecnica.md) | Guia completa: como levantar la app, que hace cada endpoint (por que / para que / resultado esperado), tareas Celery, flujo API→UseCase→Domain→Infrastructure, estado actual del sistema y comparacion detallada con el codigo legacy |
| [`docs/api-reference.md`](docs/api-reference.md) | Referencia rapida de todos los endpoints con parametros, ejemplos curl y link al archivo `.http` correspondiente |

---

## Stack

| Componente | Tecnología |
|---|---|
| API | FastAPI (Python 3.12) |
| ORM / DB | SQLAlchemy 2.0 async + asyncpg + PostgreSQL 16 |
| Cola de tareas | Celery 5 + Redis 7 |
| Fuente de datos principal | API-Football v3 |
| Enriquecimiento | FBref scraper + Understat scraper |
| Infraestructura local | Docker Compose |

---

## Arquitectura

El proyecto sigue arquitectura hexagonal estricta. Toda operación pasa por:

```
Router (Input Adapter) → Use Case → Repository (Output Adapter)
```

```
src/sfa/
├── api/v1/            # Routers FastAPI + Pydantic schemas
│   └── schemas/
├── application/
│   └── use_cases/     # Un archivo por use case
├── core/
│   ├── config.py      # Settings (pydantic-settings + @lru_cache)
│   └── dependencies.py  # Unico lugar de wiring (DI)
├── domain/
│   ├── ports.py            # Read-side Protocols + DTOs frozen
│   ├── ingestion_ports.py
│   ├── enrichment_ports.py
│   └── scoring/            # Subdomain de scoring
│       ├── value_objects.py  # M1-M4, Mvisit, SFAScore, ActionType
│       ├── entities.py
│       └── services.py       # SFAScoringService + BASE_POINTS_TABLE
├── infrastructure/
│   ├── database.py
│   ├── redis_client.py
│   ├── models/        # SQLAlchemy models
│   ├── providers/     # Adaptadores de APIs externas
│   └── repositories/  # Implementaciones de Protocols del domain
└── tasks/             # Celery tasks (sync -> async wrappers)
```

---

## Formula de scoring (SFA pts)

```
SFA pts = base_pts × CLAMP(M1 × M2 × M3 × M4 × Mvisit, 0.3, 4.0)
```

| Multiplicador | Descripcion | Rango |
|---|---|---|
| **M1** Dificultad rival | `1.0 + (posicion_equipo - posicion_rival) / 20` | [0.5, 2.0] |
| **M2** Fase competicion | Factor por etapa del torneo (liguero, octavos, final...) | > 0 |
| **M3** Minuto / marcador | Bonus segun minuto y diferencia de goles en el momento | [0.6, 2.5] |
| **M4** Dificultad disparo | `1.0 + (1.0 - PSxG) × 0.8` | [1.0, 1.8] |
| **Mvisit** Factor visitante | ×1.3 para goles/asistencias como visitante | 1.0 o 1.3 |

### Puntos base por posicion

| Accion | DEL/EXT (FW) | MC (MF) | DC/LAT (DF) |
|---|---|---|---|
| Gol | 500 | 800 | 1500 |
| Gol penalti | 300 | 500 | 500 |
| Asistencia | 500 | 600 | 1000 |
| Asistencia corner | 250 | 0 | 0 |
| Regates ganados | 50 | 300 | 0 |
| Duelos ganados | 100 | 100 | 400 |
| Tackles + int. | 250 | 200 | 400 |
| Bloqueos | 250 | 150 | 300 |

---

## Competiciones configuradas

| ID | Liga | Pais | Factor comp. | Top N equipos |
|---|---|---|---|---|
| 140 | La Liga | ESP | 1.0 | 6 |
| 39 | Premier League | ENG | 1.0 | 6 |
| 78 | Bundesliga | GER | 1.0 | 6 |
| 135 | Serie A | ITA | 1.0 | 6 |
| 61 | Ligue 1 | FRA | 1.0 | 6 |
| 2 | Champions League | EUR | 1.5 | 24 |

---

## Setup local

### 1. Pre-requisitos

- Docker + Docker Compose
- API key de [API-Football](https://www.api-sports.io/) (plan gratuito: 100 req/dia)

### 2. Variables de entorno

```bash
cp .env.example .env
```

Editar `.env` y completar:

```env
SECRET_KEY=tu-secret-key
API_FOOTBALL_KEY=tu-api-key-aqui
```

El resto de valores ya apuntan a los servicios Docker correctamente:

```env
DATABASE_URL=postgresql+asyncpg://sfa:sfa@db:5432/sfa
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
```

### 3. Levantar servicios

```bash
docker compose -f docker-compose-development.yml up --build
```

Esto levanta:
- `api` — FastAPI en `http://localhost:8000`
- `db` — PostgreSQL 16 en puerto 5432
- `redis` — Redis 7 en puerto 6379
- `celery_worker` — Worker que ejecuta las tareas
- `celery_beat` — Scheduler que dispara tareas periodicamente

### 4. Aplicar migraciones

```bash
docker compose -f docker-compose-development.yml exec api alembic upgrade head
```

---

## Documentacion interactiva

Una vez levantado el sistema:

| URL | Descripcion |
|---|---|
| `http://localhost:8000/docs` | Swagger UI |
| `http://localhost:8000/redoc` | ReDoc |
| `http://localhost:8000/api/v1/health` | Health check |

---

## Ingesta de datos

La ingesta se dispara via HTTP (admin endpoints) o corre automaticamente via Celery Beat.

### Pipeline completo

```
API-Football → Ingestion → FBref scraper → Understat scraper → Recalculate scores
   (Phase 1)               (Phase 2a)        (Phase 2b)          (Phase 3)
```

### Disparar manualmente via API

**Ingestar una liga especifica:**
```http
POST http://localhost:8000/api/v1/admin/ingest/140?season=2024
```

**Ingestar todas las ligas configuradas:**
```http
POST http://localhost:8000/api/v1/admin/ingest-all?season=2024
```

**Enriquecer con FBref (estadisticas avanzadas):**
```http
POST http://localhost:8000/api/v1/admin/enrich-fbref/140?competition_name=La+Liga&season=2024
```

**Enriquecer con Understat (PSxG para porteros):**
```http
POST http://localhost:8000/api/v1/admin/enrich-understat/140?competition_name=La+Liga&season=2024&season_int=2024
```

**Enriquecer todas las ligas (FBref + Understat + Recalculo):**
```http
POST http://localhost:8000/api/v1/admin/enrich-all?season=2024&season_int=2024
```

**Recalcular scores (despues de cambiar parametros):**
```http
POST http://localhost:8000/api/v1/admin/recalculate/140?season=2024
```

Cada endpoint devuelve un `task_id` de Celery para trackear el estado de la tarea.

### Schedule automatico (Celery Beat)

| Tarea | Schedule | Descripcion |
|---|---|---|
| `ingest_all_competitions_task` | Cada 8h (0, 8, 16 UTC) | Ingesta completa de todas las ligas |
| `enrich_all_task` | 2am y 2pm UTC | Enriquecimiento FBref + Understat + Recalculo |

### IDs de ligas de referencia

```
La Liga          → 140
Premier League   → 39
Bundesliga       → 78
Serie A          → 135
Ligue 1          → 61
Champions League → 2
```

---

## Endpoints de consulta

| Metodo | Ruta | Descripcion |
|---|---|---|
| GET | `/api/v1/ranking` | Ranking global de jugadores |
| GET | `/api/v1/players/{id}` | Detalle de un jugador |
| GET | `/api/v1/players/{id}/fixtures` | Partidos de un jugador |
| GET | `/api/v1/players/{id}/events` | Eventos SFA de un jugador |
| GET | `/api/v1/competitions` | Lista de competiciones |
| GET | `/api/v1/competitions/{id}/standings` | Clasificacion de una competicion |
| GET | `/api/v1/compare` | Comparacion head-to-head entre dos jugadores |
| GET | `/api/v1/status` | Estado del sistema + ultima ingesta |
| GET | `/api/v1/health` | Health check (DB + Redis) |

Ver ejemplos completos en `http/` (archivos `.http`).

---

## Tests

```bash
# Correr todos los tests
pytest tests/

# Con coverage
pytest tests/ --cov=src/sfa --cov-report=term-missing

# Linting
flake8 src/ tests/
isort --check src/ tests/
```

Cobertura minima requerida: **80%**.

---

## Estructura de specs

Las decisiones de arquitectura y planes de implementacion viven en `specs/`:

```
specs/
├── feature/NNNN-slug/
│   ├── decisions.md
│   └── plan.md
└── refactor/NNNN-slug/
    ├── decisions.md
    └── plan.md
```

---

## Variables de entorno — referencia completa

| Variable | Default | Descripcion |
|---|---|---|
| `APP_ENV` | `development` | Entorno de la app |
| `APP_VERSION` | `0.1.0` | Version de la API |
| `DEBUG` | `False` | Modo debug |
| `SECRET_KEY` | — | Clave secreta (obligatoria) |
| `DATABASE_URL` | `postgresql+asyncpg://sfa:sfa@localhost:5432/sfa` | Conexion a PostgreSQL |
| `REDIS_URL` | `redis://localhost:6379/0` | Conexion a Redis |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Broker de Celery |
| `API_FOOTBALL_KEY` | — | API key de api-sports.io |
| `API_FOOTBALL_BASE_URL` | `https://v3.football.api-sports.io` | Base URL de la API |