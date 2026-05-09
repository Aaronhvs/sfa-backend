# SFA — Stadistic Football Award Backend

## Project Overview

Sistema de puntuación de jugadores de fútbol que combina estadísticas avanzadas con contexto
real del partido. Calcula un score (SFA pts) por cada acción significativa usando multiplicadores
de contexto (dificultad del rival, fase de la competición, minuto del partido, dificultad del
disparo, factor visitante).

**Stack:** Python 3.12 · FastAPI · SQLAlchemy 2.0 async (asyncpg) · PostgreSQL 16 · Celery 5 + Redis 7 · Docker Compose

**Fuentes de datos:** API-Football v3 (ingestion) · FBref scraper · Understat scraper (enrichment)

**Directorio fuente:** `src/sfa/` · **Tests:** `tests/` · **Specs:** `specs/`

---

## Architecture Decision Framework

Todo en SFA sigue arquitectura hexagonal. Toda operación pasa obligatoriamente por:

```
Router (Input Adapter) → Use Case → Repository (Output Adapter)
```

No existe CRUD puro en SFA. No hay atajos.

**Capas y sus responsabilidades:**

| Capa | Ruta | Puede importar |
|---|---|---|
| `api/v1/` | Routers + Pydantic schemas | `application/`, `core/` |
| `application/` | Use Cases | `domain/` únicamente |
| `domain/` | Protocols, DTOs, scoring | Nada de infra |
| `infrastructure/` | Repositorios, providers, models | `domain/`, `core/` |
| `core/` | Config + DI (dependencies.py) | Todo |
| `tasks/` | Celery tasks | `application/`, `infrastructure/`, `core/` |

---

## HARD ROUTING RULE — DESIGN PHASE

Si la solicitud implica diseñar, planificar, crear spec, montar un flujo, agregar un
endpoint o feature, "quiero un plan", "necesito un spec", "nueva funcionalidad":

1. Invocar EXCLUSIVAMENTE `@Architecture-Engineer`
2. NO generar código, explicaciones ni planes como texto suelto en el chat
3. NO leer archivos ni usar herramientas previas

El agente es el único responsable de tomar decisiones de arquitectura y ejecutar
`/sfa-spec` al final de su proceso.

---

## Spec Workflow

**Chat 1 — Diseño:**

```
Usuario pide feature
      ↓
@Architecture-Engineer analiza codebase
      ↓
¿Requiere nuevas entidades de dominio? → Sí: invoca @DDD-Designer
      ↓
Consolida decisiones e invoca /sfa-spec
      ↓
Produce: specs/NNNN-slug/decisions.md + plan.md
```

**Chat 2 — Implementación:**

- Leer `plan.md` completo antes de escribir una línea de código
- Procesar TODOS los ítems del checklist en orden — ninguno puede omitirse silenciosamente
- Ítems etiquetados `[DDD]` → consultar sección "Agent Routing Brief" al final del plan

| Etiqueta | Agente a invocar |
|---|---|
| `[DDD]` | `@DDD-Designer` |

**Formato de specs:**

```
specs/
├── feature/NNNN-slug/
│   ├── decisions.md   ← contexto, restricciones, decisiones, domain model
│   └── plan.md        ← checklist de implementación + Agent Routing Brief
└── refactor/NNNN-slug/
    ├── decisions.md
    └── plan.md
```

**Numeración:** listar todas las carpetas en `specs/feature/` y `specs/refactor/`,
tomar el número más alto, sumar 1. El spec es el contrato entre Chat 1 y Chat 2.
La implementación NO puede comenzar sin un spec válido.

---

## Layers Reference

```
src/sfa/
├── api/v1/                    # HTTP: routers FastAPI + Pydantic schemas
│   ├── schemas/               # Un archivo por recurso
│   └── *.py                   # Un router por recurso
├── application/
│   └── use_cases/             # Un archivo por use case
├── core/
│   ├── config.py              # Settings (pydantic-settings + @lru_cache)
│   └── dependencies.py        # ÚNICO lugar de wiring (DI factories)
├── domain/
│   ├── ports.py               # Read-side Protocols + DTOs frozen
│   ├── ingestion_ports.py     # Ports + DTOs de ingestion
│   ├── enrichment_ports.py    # Ports + DTOs de enrichment
│   ├── name_matching.py
│   ├── position_mapping.py
│   └── scoring/               # Subdomain de scoring
│       ├── value_objects.py   # M1-M4, Mvisit, SFAScore, ActionType
│       ├── entities.py        # Player, ScoredEvent, PlayerSeasonScore
│       └── services.py        # SFAScoringService + BASE_POINTS_TABLE
├── infrastructure/
│   ├── database.py            # Engine + AsyncSessionLocal + Base
│   ├── redis_client.py
│   ├── models/                # SQLAlchemy models (un subdir por entidad)
│   │   ├── enums.py           # Position, EventType, IngestionStatus
│   │   └── <entity>/models.py
│   ├── providers/             # Adaptadores de APIs externas
│   └── repositories/         # Implementaciones de Protocols del domain
└── tasks/                     # Celery tasks (sync → async wrappers)
```

---

## Anti-patterns

- No poner lógica de negocio en routers ni schemas
- No importar SQLAlchemy models en use cases ni domain
- No usar `MagicMock` en tests — usar Fakes que implementen el Protocol completo
- No crear `services.py` sueltos — cada operación es un use case específico
- No poner wiring (DI) fuera de `core/dependencies.py`
- No retornar ORM models desde repositories — siempre DTOs de dominio (frozen dataclasses)
- No acceder a `_archive/` — es código legacy, no referenciarlo ni copiarlo

---

## Naming Conventions

| Elemento | Convención | Ejemplo |
|---|---|---|
| Use case clase | `VerbNounUseCase` | `GetRankingUseCase` |
| Use case protocol | `VerbNounUseCaseProtocol` | `GetRankingUseCaseProtocol` |
| Use case result | `VerbNounResult` | `RankingResult` |
| Repository | `EntityRepository` | `PlayerRepository` |
| Repository protocol | `EntityRepositoryProtocol` | `PlayerRepositoryProtocol` |
| Provider port | `EntityProviderPort` | `FootballDataProviderPort` |
| DTO dominio | `EntityDTO` / `EntityRawDTO` | `PlayerScoreDTO`, `FixtureRawDTO` |
| Pydantic schema | `EntitySchema` / `EntityResponseSchema` | `RankingResponseSchema` |
| Celery task | `verb_noun_task` | `ingest_all_competitions_task` |
| Módulo | `snake_case` | `sfa_score_repository.py` |

---

## Shared Conventions

### Wiring (Dependency Injection)

El wiring ocurre exclusivamente en `core/dependencies.py`. Nunca en el router, nunca en
`__init__` de ninguna clase.

```python
# core/dependencies.py — patrón estándar
async def get_ranking_use_case(
    score_repo: Annotated[SFAScoreRepository, Depends(get_sfa_score_repository)],
) -> GetRankingUseCase:
    return GetRankingUseCase(score_repo)
```

### Error Handling

Domain exceptions burbujean hasta el router. Solo el router las captura y traduce a HTTP.
La capa `application/` no atrapa errores de dominio.

```python
# Solo en routers — único punto de traducción de errores
@router.get("/players/{player_id}")
async def get_player(player_id: int, use_case: ...):
    try:
        return await use_case.execute(player_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

### Logging

Prefijo obligatorio `[ClassName]` o `[function_name]` en todos los logs.

```python
logger = logging.getLogger(__name__)

logger.info("[GetRankingUseCase] No season found, returning empty ranking")
logger.error("[ingest_competition_task] Failed for league_id=%s: %s", league_id, exc)
```

### Async

Todo acceso a DB es async (`asyncpg` + SQLAlchemy async). Usar `async with AsyncSessionLocal()`
en Celery tasks. Nunca llamar a `session.commit()` desde use cases — solo desde tasks o routers.

### Settings

Acceder a settings vía `get_settings()` (singleton `@lru_cache`). Nunca instanciar `Settings()`
directamente.

### Language

- Código en inglés (variables, clases, funciones, comentarios nuevos)
- Git commits en inglés, conventional commits
- Claude Code responde en español

### Branch Naming

`SFA-{descripcion-del-ticket}` — e.g. `SFA-add-tactics-module`, `SFA-fix-scoring-m4`

### HTTP Files

Todo endpoint nuevo tiene un archivo `.http` en `http/` con todos los casos (happy path +
error cases + filtros). Naming: `recurso.http` en snake_case.

---

## Testing Rules — Innegociables

1. Correr `pytest tests/` antes de escribir tests nuevos y documentar qué fallos ya existían
2. Todo use case nuevo requiere tests — no se implementa sin coverage de la funcionalidad nueva
3. Fakes implementan el Protocol completo (`@runtime_checkable`), nunca `MagicMock`
4. Marker `@pytest.mark.anyio` en todos los tests async
5. Tests de use cases viven en `tests/use_cases/test_verb_noun.py`
6. Tests de use cases usan siempre Fakes — nunca DB real

**Estructura mínima de un test de use case:**

```python
class FakeEntityRepository(EntityRepositoryProtocol):
    # Implementa TODOS los métodos del Protocol

class TestVerbNounUseCase:
    @pytest.mark.anyio
    async def test_<escenario>_<resultado_esperado>(self):
        ...
```

**CI:** flake8 + isort --check + pytest coverage ≥80%

---

## Code Style

- `flake8`: max-line-length 120, `exclude = migrations,__pycache__,.git,_archive,.venv`
  Rules: `select = E302,E501,F401,F821`, `ignore = E203,W503`
- `isort`: profile "black", line_length 120, `skip = ["migrations", "_archive", ".venv"]`
- `from __future__ import annotations` en todos los archivos de `domain/` y `application/`

---

## Skills disponibles

| Skill | Cuándo usarlo |
|---|---|
| `/sfa-spec` | Crear un spec nuevo (invocado por Architecture-Engineer) |
| `/sfa-use-case` | Crear un use case nuevo |
| `/sfa-router` | Crear un router + schemas nuevos |
| `/sfa-repository` | Crear un repository nuevo |
| `/sfa-celery-task` | Crear una Celery task |
| `/sfa-test` | Crear tests para un use case |
| `/sfa-scoring` | Modificar el dominio de scoring |
