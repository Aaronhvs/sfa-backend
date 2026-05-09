# Separar capa RAW de datos de la capa de cálculo SFA

## Contexto de negocio

El pipeline de ingestion actual mezcla descarga de datos con cálculo SFA en un único flujo
(`IngestCompetitionUseCase`, 5 fases en una transacción). Esto genera tres problemas críticos:

1. **Cambiar la fórmula SFA obliga a redescargar todo desde la API.** El cálculo y la
   persistencia de datos brutos están acoplados en el mismo use case.
2. **No se puede agregar una competición nueva sin redescargar lo ya descargado.** No hay
   detección de fixtures ya procesados.
3. **El plan free de API-Football es 100 req/día.** Cada request es crítico; redescargar
   datos ya existentes es un desperdicio que puede dejar el sistema sin cuota diaria.

El refactor establece una invariante de arquitectura dura: los datos RAW descargados de la
API son inmutables desde el punto de vista del cálculo SFA. El cálculo siempre se regenera
desde RAW, nunca desde la API.

## Restricciones

- API-Football plan free: 100 requests/día. No hay margen para requests desperdiciados.
- El modelo `PlayerStats` ya existe y tiene datos en producción. La migración debe ser
  no-destructiva (solo `ADD COLUMN`).
- Los endpoints HTTP existentes (`/api/v1/admin/ingest/...`) no deben romperse durante
  la transición. `IngestCompetitionUseCase` se preserva como deprecated.
- La arquitectura hexagonal es innegociable: use cases solo importan de `domain/`,
  repositories solo retornan DTOs frozen, wiring solo en `core/dependencies.py`.
- No se agregan nuevas dependencias de Python (no Click, no Typer). Solo stdlib.

## Decisiones tomadas

| ID | Decisión elegida | Alternativa descartada | Razón |
|----|-----------------|------------------------|-------|
| D-01 | Separar en dos use cases: `DownloadPlayerDataUseCase` (solo API) y `CalculateSFAFromRawUseCase` (solo lectura de RAW) | Agregar flags de modo al `IngestCompetitionUseCase` existente | Dos responsabilidades distintas requieren dos use cases distintos. Los flags de modo crean lógica condicional compleja. |
| D-02 | Expandir `PlayerStats` con `photo_url` y `downloaded_at` en lugar de crear tabla nueva | Crear tabla `raw_player_snapshots` separada | `PlayerStats` ya es la tabla RAW de facto (datos de API-Football por fixture). Evitar duplicación de schema. |
| D-03 | `photo_url` extraída del endpoint `fixtures/players` via `p['player']['photo']` | Endpoint separado `players/{id}` | El campo está disponible en la misma respuesta ya consultada. Cero requests adicionales. |
| D-04 | Idempotencia via `fixture_players_already_downloaded(fixture_id) -> bool` en `IngestionRepositoryPort` | Hash de contenido o timestamps de modificación | Verificar existencia de filas en `player_stats` por `fixture_id` es simple, correcto y no requiere lógica extra. |
| D-05 | `RequestEstimationService` como clase pura en `domain/ingestion_ports.py` | Lógica de estimación inline en `run.py` | La estimación de requests es lógica de negocio (reglas del dominio de la API), debe vivir en domain y ser testeable de forma aislada. |
| D-06 | CLI `src/run.py` con `argparse` + `input()`, invocando use cases directamente | Celery task nueva o endpoint HTTP para el flujo interactivo | El CLI es un input adapter más, coherente con la arquitectura hexagonal. No requiere servidor activo. |
| D-07 | `DownloadPlayerDataUseCase` con `player_filter: list[str] | None` | Filtro solo a nivel de competición (top_n equipos) | Permite selección granular de jugadores específicos, que es el flujo interactivo pedido. |
| D-08 | `CalculateSFAFromRawUseCase` lee de `RawDataRepositoryPort` (nuevo port de lectura) | Reusar `IngestionRepositoryPort` para lectura | Separación de responsabilidades: `IngestionRepositoryPort` es para escritura de datos de API, `RawDataRepositoryPort` es para lectura de datos para el cálculo. |
| D-09 | `RawPlayerStatsDTO` como read model con JOIN desnormalizado | Múltiples queries separadas en el use case | El use case no debe orquestar queries de infraestructura. El repositorio materializa el JOIN y entrega un DTO completo. |
| D-10 | `LeagueConfig` y `LEAGUES` se mueven a `domain/ingestion_ports.py` | Mantenerlos en `application/use_cases/ingest_competition.py` | Son configuración de dominio (qué ligas existen), no lógica de aplicación. Múltiples use cases los necesitan sin crear importaciones cruzadas entre use cases. |
| D-11 | Protocols de los nuevos use cases en `domain/ingestion_ports.py` | Archivo `domain/application_ports.py` nuevo | Mantener coherencia con el patrón existente: todos los ports de ingestion en un solo archivo. |
| D-12 | `IngestCompetitionUseCase` se preserva con docstring deprecated | Eliminarlo inmediatamente | Migración gradual sin romper Celery tasks ni endpoints existentes durante la transición. |
| D-13 | `argparse` (stdlib) + `input()` para el CLI | Click o Typer | Cero dependencias nuevas. El flujo interactivo no justifica una librería completa de CLI. |

## Domain Model

### No se requiere @DDD-Designer

Los nuevos DTOs (`RawPlayerStatsDTO`, `DownloadResult`, `CalculationResult`,
`RequestEstimationResult`) son contenedores de datos sin invariantes de negocio complejas.
No hay nuevos aggregates, no hay nuevas reglas de consistencia de dominio.

La invariante central —"los datos RAW son inmutables; los cálculos SFA siempre se generan
desde RAW"— se impone mediante separación de use cases y ports, no mediante entidades de
dominio con comportamiento.

`RequestEstimationService` es lógica de negocio pura (cálculo aritmético sobre constantes
del dominio), sin modelado de dominio complejo.

### Modelo SQLAlchemy modificado

**`infrastructure/models/player_stats/models.py` — `PlayerStats`**

Columnas nuevas:
- `photo_url: Mapped[str | None]` — Text, nullable. URL de foto devuelta por API-Football.
- `downloaded_at: Mapped[datetime]` — DateTime(timezone=True), not null, server_default=func.now().

La tabla `player_stats` se convierte en la **tabla RAW canónica**. Es inmutable desde el
punto de vista de `CalculateSFAFromRawUseCase`: ese use case solo la lee.

Migración requerida:
```sql
ALTER TABLE player_stats ADD COLUMN photo_url TEXT;
ALTER TABLE player_stats ADD COLUMN downloaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
```

### Nuevos DTOs de dominio

**`domain/raw_data_ports.py`**

`RawPlayerStatsDTO` (frozen dataclass) — read model desnormalizado para el cálculo SFA:
- `player_id: int`
- `fixture_id: int`
- `competition_id: int`
- `season: str`
- `player_name: str`
- `position: Position`
- `goals: int`
- `assists: int`
- `shots_on: int`
- `passes_key: int`
- `dribbles_success: int`
- `duels_won: int`
- `tackles: int`
- `interceptions: int`
- `blocks: int`
- `minutes: int`
- `is_away: bool`
- `rival_position: int`
- `player_team_position: int`
- `stage_factor: float`
- `home_team_external_id: int`
- `fixture_events: list[FixtureEventRawDTO]`

**`domain/ingestion_ports.py`** (nuevos en el archivo existente)

`DownloadResult` (frozen dataclass):
- `competition: str`
- `fixtures_downloaded: int`
- `fixtures_skipped: int`
- `players_downloaded: int`
- `requests_used: int`
- `status: str`
- `error: str | None`

`CalculationResult` (frozen dataclass):
- `competition_id: int`
- `season: str`
- `players_calculated: int`
- `events_created: int`
- `scores_updated: int`
- `status: str`
- `error: str | None`

`RequestEstimationResult` (frozen dataclass):
- `total_estimated_requests: int`
- `fixtures_already_downloaded: int`
- `fixtures_pending: int`
- `net_new_requests: int`
- `daily_limit: int`
- `is_feasible: bool`

`LeagueConfig` (frozen dataclass) — movida desde `application/use_cases/ingest_competition.py`:
- `id: int`
- `name: str`
- `country: str`
- `comp_factor: float`
- `top_n: int`

### Nuevos Ports

**`domain/raw_data_ports.py` — `RawDataRepositoryPort`** (`@runtime_checkable Protocol`)

Métodos:
- `get_raw_stats_for_calculation(competition_id, season, player_ids=None) -> list[RawPlayerStatsDTO]`
  — JOIN entre `player_stats`, `fixtures`, `standing_snapshot`, `competition_stages`.
- `get_fixture_events_raw(fixture_id) -> list[FixtureEventRawDTO]`
  — Lee eventos del fixture desde `player_events` (para reconstruir contexto de score).
- `get_players_in_competition(competition_id, season) -> list[PlayerEnrichDTO]`
  — Lista jugadores con datos RAW en una competición/temporada. Usado por el CLI.
- `get_downloaded_fixture_ids(competition_id, season) -> set[int]`
  — Set de fixture_ids que ya tienen filas en `player_stats`. Usado para estimación de requests.

**`domain/ingestion_ports.py` — nuevos Protocols** (en el archivo existente)

`DownloadPlayerDataUseCaseProtocol` (`@runtime_checkable Protocol`):
- `execute(league, season, player_filter=None) -> DownloadResult`

`CalculateSFAFromRawUseCaseProtocol` (`@runtime_checkable Protocol`):
- `execute(competition_id, season, player_ids=None) -> CalculationResult`

**`domain/ingestion_ports.py` — método nuevo en `IngestionRepositoryPort`**

- `fixture_players_already_downloaded(fixture_id: int) -> bool`
  — `SELECT COUNT(*) > 0 FROM player_stats WHERE fixture_id = :fixture_id`.

## Integraciones externas

**API-Football v3**
- Autenticación: header `x-apisports-key` (ya implementado en `APIFootballProvider`).
- Rate limit: 100 req/día (plan free). La idempotencia de descarga y la estimación previa
  son las salvaguardas principales.
- Campo nuevo a extraer: `p['player']['photo']` del endpoint `fixtures/players`.
  Es un string URL (puede ser `None` si el jugador no tiene foto).
- No se agregan nuevos endpoints de API-Football en este refactor.
