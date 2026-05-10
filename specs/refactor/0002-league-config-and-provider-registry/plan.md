# Plan: Refactor 0002 — League Config and Provider Registry

## Contexto del rediseño

El plan original proponía crear tres tablas nuevas (`league_configs`, `providers`,
`league_provider_mappings`). Ese diseño choca con la tabla `competitions` que ya existe y
que tiene exactamente los mismos campos conceptuales (`name`, `country`, `competition_factor`).

**Solución:** extender `competitions` con dos columnas:
- `top_n INTEGER NOT NULL DEFAULT 6` — el n que `LeagueConfig.top_n` ya tenía en memoria
- `providers JSONB NOT NULL DEFAULT '{}'` — dict `{"api-football": 140}` que mapea proveedor → external_id

No se crea ninguna tabla nueva. `LeagueConfigRepository` consulta directamente `competitions`.

---

## Archivos a crear

- [ ] `src/sfa/infrastructure/repositories/league_config_repository.py` — implementación de `LeagueConfigRepositoryPort`
- [ ] `scripts/seed_league_configs.py` — script async standalone: aplica DDL y puebla datos iniciales
- [ ] `tests/use_cases/test_ingest_all_competitions.py` — tests de `IngestAllCompetitionsUseCase` con nueva firma

## Archivos a modificar

- [ ] `src/sfa/domain/ingestion_ports.py` — añadir `LeagueConfigDTO` y `LeagueConfigRepositoryPort`
- [ ] `src/sfa/infrastructure/models/competitions/models.py` — añadir `top_n` y `providers` a `Competition`
- [ ] `src/sfa/application/use_cases/ingest_competition.py` — eliminar `LeagueConfig`, `LEAGUES`; adaptar `execute()` para `LeagueConfigDTO`
- [ ] `src/sfa/application/use_cases/ingest_all.py` — añadir `league_config_repo`; eliminar import de `LEAGUES`
- [ ] `src/sfa/infrastructure/repositories/__init__.py` — añadir `LeagueConfigRepository` al `__all__`
- [ ] `src/sfa/core/dependencies.py` — añadir factory `get_league_config_repository`
- [ ] `src/sfa/tasks/ingestion_tasks.py` — late-import de `LeagueConfigRepository`; resolver liga desde BD
- [ ] `src/sfa/tasks/enrichment_tasks.py` — eliminar import de `LEAGUES`; consultar desde BD

---

## Checklist de implementación

### 1. Domain — nuevos DTOs y Port

- [ ] En `src/sfa/domain/ingestion_ports.py`, añadir `LeagueConfigDTO` como frozen dataclass con campos:
  `competition_id: int`, `external_id: int`, `name: str`, `country: str`, `comp_factor: float`,
  `top_n: int`. El campo `competition_id` es la PK de `competitions` (ya resuelta); `external_id` es
  el valor extraído de `providers[provider_name]`.
  Criterio: el dataclass existe, es frozen, no importa nada de `infrastructure/`.

- [ ] En el mismo archivo, añadir `LeagueConfigRepositoryPort` como `@runtime_checkable Protocol` con dos métodos:
  `get_all_active_leagues(self, provider_name: str) -> list[LeagueConfigDTO]` y
  `get_league_by_external_id(self, provider_name: str, external_id: int) -> LeagueConfigDTO | None`.
  Criterio: el Protocol está decorado con `@runtime_checkable`, ambos métodos son `async`.

### 2. Infrastructure — extender modelo Competition

- [ ] En `src/sfa/infrastructure/models/competitions/models.py`, añadir a `Competition`:
  - `top_n: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("6"))` con
    `CheckConstraint("top_n > 0", name="ck_competition_top_n_positive")` en `__table_args__`.
  - `providers: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))`.
  Criterio: `Competition.__table__.columns` contiene `top_n` y `providers`; importa `JSONB` desde
  `sqlalchemy.dialects.postgresql` y `text` desde `sqlalchemy`.
  Nota: `Base.metadata.create_all` no aplica columnas a tablas existentes. El DDL real lo aplica
  el seed script (ver paso 8).

### 3. Infrastructure — repositorio

- [ ] Crear `src/sfa/infrastructure/repositories/league_config_repository.py` con clase
  `LeagueConfigRepository(LeagueConfigRepositoryPort)`. Constructor recibe `session: AsyncSession`.
  Criterio: no importa nada de `application/`.

- [ ] Implementar `get_all_active_leagues(self, provider_name: str) -> list[LeagueConfigDTO]`:
  `SELECT * FROM competitions WHERE providers ? :provider_name` (operador JSONB has-key).
  En SQLAlchemy: `Competition.providers.has_key(provider_name)`.
  Para cada fila: `external_id = int(row.providers[provider_name])`.
  Retornar lista de `LeagueConfigDTO` frozen.
  Criterio: retorna DTOs, nunca modelos ORM.

- [ ] Implementar `get_league_by_external_id(self, provider_name: str, external_id: int) -> LeagueConfigDTO | None`:
  `SELECT * FROM competitions WHERE providers->>:provider_name = :external_id::text`.
  En SQLAlchemy: `Competition.providers[provider_name].as_string() == str(external_id)`.
  Retorna `None` si no hay coincidencia.
  Criterio: retorna `LeagueConfigDTO | None`.

- [ ] Añadir `LeagueConfigRepository` al `__all__` de `src/sfa/infrastructure/repositories/__init__.py`.
  Criterio: `from sfa.infrastructure.repositories import LeagueConfigRepository` funciona.

### 4. Application — refactor use cases

- [ ] En `src/sfa/application/use_cases/ingest_competition.py`:
  - Eliminar la clase `LeagueConfig` y la constante `LEAGUES`.
  - Importar `LeagueConfigDTO` desde `sfa.domain.ingestion_ports`.
  - Cambiar firma a `execute(self, league: LeagueConfigDTO, season: int)`.
  - Reemplazar `competition_id = await self._repo.upsert_competition(...)` por
    `competition_id = league.competition_id` (la competition ya existe, fue sembrada).
  - Reemplazar toda referencia a `league.id` por `league.external_id` (en `fetch_standings`,
    `fetch_team_fixtures`).
  Criterio: el archivo no contiene `LEAGUES` ni la clase `LeagueConfig`; sin errores de importación.

- [ ] En `src/sfa/application/use_cases/ingest_all.py`:
  - Añadir `league_config_repo: LeagueConfigRepositoryPort` como cuarto parámetro en `__init__`.
  - Cambiar `execute(self, season: int, provider_name: str = "api-football") -> list[IngestionResult]`.
  - Reemplazar el loop sobre `LEAGUES` por `await self._league_config_repo.get_all_active_leagues(provider_name)`.
  Criterio: el archivo no contiene referencias a `LEAGUES`; la guard de `requests_used >= 7000` se mantiene.

### 5. Tasks — ingestion

- [ ] En `_run_ingest_competition` en `src/sfa/tasks/ingestion_tasks.py`:
  - Eliminar import de `LEAGUES`.
  - Añadir late-imports de `LeagueConfigRepository`.
  - Dentro del `async with AsyncSessionLocal()`, instanciar `league_config_repo` y llamar
    `await league_config_repo.get_league_by_external_id("api-football", league_id)`.
  - Si retorna `None`, lanzar `ValueError(f"League not found: {league_id}")`.
  Criterio: el helper no importa `LEAGUES`; `ValueError` con mismo mensaje que antes.

- [ ] En `_run_ingest_all`:
  - Añadir late-import de `LeagueConfigRepository`.
  - Instanciar `league_config_repo` y pasarlo como cuarto argumento a `IngestAllCompetitionsUseCase`.
  Criterio: `_run_ingest_all` no importa `LEAGUES`.

### 6. Tasks — enrichment (bug fix incluido)

- [ ] En `_run_enrich_all` en `src/sfa/tasks/enrichment_tasks.py`:
  - Eliminar `from sfa.application.use_cases.ingest_competition import LEAGUES`.
  - Añadir late-imports de `LeagueConfigRepository` y `AsyncSessionLocal`.
  - Abrir sesión, instanciar `league_config_repo`, llamar
    `await league_config_repo.get_all_active_leagues("api-football")`.
  - Iterar usando `league.name` como `competition_name` y `league.competition_id` como `competition_id`.
  - Si `league.competition_id` es 0 o inválido, logear warning con prefijo `[_run_enrich_all]` y `continue`.
  Criterio: el helper no importa `LEAGUES`; usa `league.competition_id` (PK de `competitions`, no external_id);
  el bug donde `league.id` era pasado como `competition_id` queda eliminado.

### 7. DI — wiring

- [ ] En `src/sfa/core/dependencies.py`:
  - Importar `LeagueConfigRepository` desde `sfa.infrastructure.repositories`.
  - Añadir factory:
    ```python
    async def get_league_config_repository(
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> LeagueConfigRepository:
        return LeagueConfigRepository(db)
    ```
  Criterio: la factory sigue el patrón estándar del archivo.

### 8. Seed de datos iniciales (incluye DDL)

- [ ] Crear `scripts/seed_league_configs.py` como script async standalone. El script debe:
  1. Aplicar DDL con `ALTER TABLE IF EXISTS ... ADD COLUMN IF NOT EXISTS` para `top_n` y `providers`
     (permite ejecutar contra BD existente sin recrear la tabla).
  2. Upsert de las 6 competitions con `ON CONFLICT (name) DO UPDATE SET top_n=..., providers=...`.
  Datos:
  | name             | country | comp_factor | top_n | providers                |
  |------------------|---------|-------------|-------|--------------------------|
  | La Liga          | ESP     | 1.0         | 6     | `{"api-football": 140}`  |
  | Premier League   | ENG     | 1.0         | 6     | `{"api-football": 39}`   |
  | Bundesliga       | GER     | 1.0         | 6     | `{"api-football": 78}`   |
  | Serie A          | ITA     | 1.0         | 6     | `{"api-football": 135}`  |
  | Ligue 1          | FRA     | 1.0         | 6     | `{"api-football": 61}`   |
  | Champions League | EUR     | 1.5         | 24    | `{"api-football": 2}`    |
  Criterio: ejecutar el script dos veces no produce errores ni duplicados.

### 9. Tests

- [ ] Antes de escribir tests nuevos, correr `pytest tests/` y documentar en un comentario al inicio
  del archivo qué fallos preexistían. Criterio: el comentario existe.

- [ ] Crear `tests/use_cases/test_ingest_all_competitions.py` con
  `FakeLeagueConfigRepository(LeagueConfigRepositoryPort)` que implemente los dos métodos del Protocol.
  Criterio: `isinstance(FakeLeagueConfigRepository(...), LeagueConfigRepositoryPort)` es `True`.

- [ ] Test `test_execute_iterates_all_active_leagues`: use case con fake repo que devuelve 2 ligas,
  fake provider, fake ingestion repo. Verificar que `execute()` procesa ambas ligas y retorna 2 resultados.
  Criterio: pasa con `@pytest.mark.anyio`.

- [ ] Test `test_execute_respects_requests_limit`: fake provider con `requests_used = 7000`.
  Verificar que el use case hace break antes de procesar todas las ligas.
  Criterio: pasa con `@pytest.mark.anyio`.

- [ ] Test `test_get_league_by_external_id_returns_none_for_unknown`: verificar que cuando el repo
  retorna `None`, el ramal de `ValueError` en la task se activa correctamente.
  Criterio: cubre el ramal `league is None`.

- [ ] Verificar `pytest tests/` pasa sin regresiones.
  Criterio: ningún test que pasaba antes falla ahora.

### 10. Calidad

- [ ] `flake8 src/ tests/` sin errores introducidos por este refactor.
- [ ] `isort --check-only src/ tests/` sin errores (exit code 0).

---

## Verificación

1. Arrancar BD con `make dev` y ejecutar `python scripts/seed_league_configs.py`.
   Verificar en `competitions` que las 6 filas tienen `top_n` y `providers` poblados.
2. Ejecutar el script una segunda vez. Verificar idempotencia (sin errores, conteos iguales).
3. Lanzar `ingest_competition_task(league_id=140, season=2024)`. Verificar en logs que la liga
   se resuelve desde BD via `get_league_by_external_id`.
4. Lanzar `ingest_all_competitions_task(season=2024)`. Verificar que itera las 6 ligas
   consultando BD via `get_all_active_leagues`.
5. Lanzar `enrich_all_task(season="2024", season_int=2024)`. Verificar en logs que usa
   `league.competition_id` (PK de `competitions`, no external_id).
6. Ejecutar `pytest tests/` y verificar sin regresiones.
7. Ejecutar `make check` sin errores.

---

## Agent Routing Brief

**DDD Designer needed:** no

Este refactor no introduce nuevas entidades de dominio, aggregates ni value objects con
invariantes de negocio. `LeagueConfigDTO` es un DTO de lectura (frozen dataclass) que proyecta
filas de `competitions`. `LeagueConfigRepositoryPort` es un port de salida estándar. No hay
lógica de negocio nueva ni conceptos del dominio del fútbol que modelar.