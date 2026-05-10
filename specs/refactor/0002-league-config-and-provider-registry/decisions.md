# Refactor 0002: League Config and Provider Registry

## Contexto de negocio

Actualmente el sistema de ingesta de datos tiene dos problemas de mantenibilidad críticos:

1. **LEAGUES hardcodeada**: La lista `LEAGUES` vive en `application/use_cases/ingest_competition.py`
   como una constante Python. Para añadir o modificar una liga hay que hacer un deploy. Además,
   `IngestAllCompetitionsUseCase` y `enrichment_tasks.py` la importan directamente, creando
   acoplamiento entre la capa de aplicación y la configuración operacional.

2. **Provider instanciado en la task**: `APIFootballProvider` se construye directamente en
   `_run_ingest_competition` y `_run_ingest_all` con credenciales sacadas de `settings`. No hay
   registro de qué providers existen ni cómo mapean sus IDs internos a las ligas del sistema.

El objetivo es persistir las ligas y los providers en BD, con una tabla de mapping que relacione
`(liga, provider) → ID externo específico de ese provider`. Una liga como La Liga tiene `id=140`
en api-football y `id=2014` en football-data.org: ese mapeo debe ser un dato, no un hardcode.

## Restricciones

- El contrato de `FootballDataProviderPort` (los métodos `fetch_*`) NO cambia. `IngestCompetitionUseCase`
  recibe el provider por DI y opera con `league_id: int` — este flujo se mantiene igual.
- `LeagueConfig` como dataclass frozen en `ingest_competition.py` desaparece: se reemplaza por un DTO
  de dominio leído desde BD (`LeagueConfigDTO` en `domain/ingestion_ports.py`).
- `IngestCompetitionUseCase.execute()` sigue recibiendo un objeto con los mismos campos que tenía
  `LeagueConfig` (`id`, `name`, `country`, `comp_factor`, `top_n`). La diferencia es que ese objeto
  viene de BD, no de un hardcode. El campo `id: int` pasa a llamarse `external_id: int`.
- Las tasks de enrichment usan `competition_id` (int, PK de `competitions`) y `competition_name`.
  `_run_enrich_all` hoy itera sobre `LEAGUES` hardcodeada — eso se elimina.
- No se introducen nuevas entidades de dominio con invariantes de negocio. No es necesario invocar
  `@DDD-Designer`.
- UUID como PK en `league_configs` y `providers`. `league_provider_mappings` usa PK serial int.
- La migración de datos inicial debe insertar los 6 registros actuales de `LEAGUES` y el provider
  `api-football` con sus mappings. No se usa Alembic — el proyecto arranca con `create_all`.
- No se exponen endpoints nuevos en esta iteración.

## Decisiones tomadas

| Decisión | Alternativa descartada | Razón |
|---|---|---|
| `LeagueConfigDTO` con campo `competition_id: int \| None` resuelto por JOIN con `competitions` | Port separado `CompetitionResolverPort` | Sobrecomplica sin beneficio real; el JOIN es directo y el campo ya está en BD |
| UUID como PK en `league_configs` y `providers` | Serial int | Providers y ligas son entidades de configuración con identidad estable; UUID evita colisiones al seedear entre entornos |
| `LeagueProviderMappingModel` con PK serial int | UUID | La mapping es un registro de relación puro, no necesita identidad global |
| Seed en script standalone `scripts/seed_league_configs.py` | Seed en `start.sh` o fixture de tests | Más fácil de re-ejecutar, auditar y extender sin tocar la infraestructura de arranque |
| `get_all_active_leagues` resuelve `competition_id` con un segundo SELECT por liga | Un único JOIN complejo con LEFT OUTER | Más legible, el overhead es insignificante (6 ligas) |
| No se añaden endpoints CRUD para ligas/providers en este refactor | Incluir endpoints de gestión | El objetivo es eliminar el hardcode, no construir un panel de administración |

## Domain Model

No aplica. Este refactor no introduce nuevas entidades de dominio, aggregates ni value objects
con invariantes de negocio. `LeagueConfigDTO` es un DTO de lectura (frozen dataclass) sin reglas
de construcción propias.

## Decisiones arquitectónicas detalladas

### AD-01: Tres nuevos modelos SQLAlchemy en `infrastructure/models/league_config/`

**`LeagueConfigModel`** (tabla `league_configs`):
- PK: `UUID` generado en BD (`gen_random_uuid()`, `server_default`)
- `name VARCHAR(100) UNIQUE NOT NULL`
- `country VARCHAR(10) NOT NULL`
- `comp_factor NUMERIC(4,2) NOT NULL` — CHECK `comp_factor > 0`
- `top_n INTEGER NOT NULL` — CHECK `top_n > 0`

**`ProviderModel`** (tabla `providers`):
- PK: `UUID` generado en BD
- `name VARCHAR(50) UNIQUE NOT NULL` — slug como `"api-football"`, `"football-data"`

**`LeagueProviderMappingModel`** (tabla `league_provider_mappings`):
- PK: serial `INTEGER`
- `league_config_id UUID FK → league_configs.id ON DELETE CASCADE`
- `provider_id UUID FK → providers.id ON DELETE CASCADE`
- `external_id INTEGER NOT NULL` — ID de la liga en ese provider
- UNIQUE: `(league_config_id, provider_id)`
- UNIQUE: `(provider_id, external_id)`

### AD-02: DTO de dominio `LeagueConfigDTO` en `domain/ingestion_ports.py`

Frozen dataclass añadido al final del archivo existente:

```
LeagueConfigDTO:
  league_config_id: UUID       — PK de league_configs
  external_id: int             — ID en el provider activo
  name: str
  country: str
  comp_factor: float
  top_n: int
  competition_id: int | None   — PK de competitions (None si aún no ingestada)
```

Reemplaza a `LeagueConfig` en `ingest_competition.py`. Donde antes se usaba `league.id` ahora se
usa `league.external_id`.

### AD-03: Nuevo Port `LeagueConfigRepositoryPort` en `domain/ingestion_ports.py`

```
@runtime_checkable
class LeagueConfigRepositoryPort(Protocol):
    async def get_all_active_leagues(self, provider_name: str) -> list[LeagueConfigDTO]: ...
    async def get_league_by_external_id(
        self, provider_name: str, external_id: int
    ) -> LeagueConfigDTO | None: ...
```

### AD-04: `LeagueConfigRepository` en `infrastructure/repositories/`

Implementa `LeagueConfigRepositoryPort`. Los dos métodos hacen JOIN entre
`league_configs`, `providers` y `league_provider_mappings` filtrando por `providers.name`.
`get_all_active_leagues` hace adicionalmente un SELECT por `competitions.name` para resolver
`competition_id`. Retorna siempre DTOs frozen — nunca modelos ORM.

### AD-05: `IngestCompetitionUseCase` — eliminar `LeagueConfig` y `LEAGUES`

- Eliminar la clase `LeagueConfig` (dataclass) y la constante `LEAGUES`
- Importar `LeagueConfigDTO` desde `domain/ingestion_ports`
- `execute(self, league: LeagueConfigDTO, season: int)` — body idéntico, `league.id` → `league.external_id`

### AD-06: `IngestAllCompetitionsUseCase` — nueva dependencia de repo

- `__init__` recibe `league_config_repo: LeagueConfigRepositoryPort` como cuarto parámetro
- `execute(self, season: int, provider_name: str = "api-football")`
- Body consulta `await self._league_config_repo.get_all_active_leagues(provider_name)` e itera
- Elimina import de `LEAGUES`

### AD-07: Celery tasks de ingesta — resolver liga desde BD

`_run_ingest_competition(league_id, season)`:
- Late-import de `LeagueConfigRepository` dentro del helper async
- Construir `league_config_repo` dentro del `async with AsyncSessionLocal()`
- `league = await league_config_repo.get_league_by_external_id("api-football", league_id)`
- Si `league is None` → `ValueError` (mismo comportamiento actual)
- Eliminar import de `LEAGUES`

`_run_ingest_all(season)`:
- Late-import de `LeagueConfigRepository`
- Pasar `league_config_repo` a `IngestAllCompetitionsUseCase(..., league_config_repo)`

### AD-08: `_run_enrich_all` en enrichment_tasks — eliminar import de LEAGUES

- Late-import de `LeagueConfigRepository`
- Abrir sesión, construir `league_config_repo`, llamar `get_all_active_leagues("api-football")`
- Iterar sobre `LeagueConfigDTO`: `league.name` como `competition_name`, `league.competition_id` como `competition_id`
- Si `league.competition_id is None`: log warning y skip

### AD-09: Compatibilidad enrichment — `competition_id: int | None` en el DTO

Las tasks de enrichment reciben `competition_id: int` (PK de `competitions`). El DTO incluye
ese campo resuelto por el repository via JOIN con `competitions` por `name`. Si la liga está
configurada pero no ingestada aún, `competition_id` es `None` y la task hace skip con warning.

### AD-10: Seed idempotente en `scripts/seed_league_configs.py`

Script async standalone con `ON CONFLICT DO NOTHING` en cada INSERT. Datos iniciales:

| Liga             | country | comp_factor | top_n | api-football id |
|------------------|---------|-------------|-------|-----------------|
| La Liga          | ESP     | 1.0         | 6     | 140             |
| Premier League   | ENG     | 1.0         | 6     | 39              |
| Bundesliga       | GER     | 1.0         | 6     | 78              |
| Serie A          | ITA     | 1.0         | 6     | 135             |
| Ligue 1          | FRA     | 1.0         | 6     | 61              |
| Champions League | EUR     | 1.5         | 24    | 2               |

### AD-11: Wiring en `core/dependencies.py`

```python
async def get_league_config_repository(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LeagueConfigRepository:
    return LeagueConfigRepository(db)
```

Las tasks usan late imports — la factory sirve para futuro uso en routers si se añaden endpoints.

### AD-12: Sin endpoints nuevos

El refactor es puramente interno. No hay routers ni schemas nuevos. Un spec de feature futuro
podrá añadir endpoints CRUDE para gestión de ligas y providers.

## Integraciones externas

Ninguna nueva. `APIFootballProvider` sigue siendo el único provider implementado. El registro
de providers en BD es preparación para futuros adapters (football-data.org, etc.) sin cambios
en el core de ingesta.