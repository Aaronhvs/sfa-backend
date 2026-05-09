# Plan: Separar capa RAW de datos de la capa de cálculo SFA

## Archivos a crear

- [ ] `src/sfa/domain/raw_data_ports.py` — `RawPlayerStatsDTO` + `RawDataRepositoryPort` Protocol
- [ ] `src/sfa/infrastructure/repositories/raw_data_repository.py` — Implementación de `RawDataRepositoryPort` con JOIN desnormalizado
- [ ] `src/sfa/application/use_cases/download_player_data.py` — `DownloadPlayerDataUseCase` (solo descarga, sin cálculo SFA)
- [ ] `src/sfa/application/use_cases/calculate_sfa_from_raw.py` — `CalculateSFAFromRawUseCase` (solo cálculo desde RAW)
- [ ] `tests/use_cases/test_download_player_data.py` — Tests unitarios con Fakes
- [ ] `tests/use_cases/test_calculate_sfa_from_raw.py` — Tests unitarios con Fakes
- [ ] `src/run.py` — CLI interactivo con `argparse` + `input()`
- [ ] `http/download_and_calculate.http` — Casos HTTP para los nuevos endpoints admin

## Archivos a modificar

- [ ] `src/sfa/infrastructure/models/player_stats/models.py` — Agregar `photo_url` y `downloaded_at`
- [ ] `src/sfa/domain/ingestion_ports.py` — Mover `LeagueConfig`/`LEAGUES` desde use case; agregar `DownloadResult`, `CalculationResult`, `RequestEstimationResult`, `RequestEstimationService`, `DownloadPlayerDataUseCaseProtocol`, `CalculateSFAFromRawUseCaseProtocol`; agregar `fixture_players_already_downloaded` a `IngestionRepositoryPort`
- [ ] `src/sfa/infrastructure/providers/api_football.py` — Extraer `photo_url` de `p['player']['photo']` en `fetch_fixture_players`
- [ ] `src/sfa/infrastructure/repositories/ingestion_repository.py` — Persistir `photo_url` en `upsert_player_stats`; implementar `fixture_players_already_downloaded`
- [ ] `src/sfa/infrastructure/repositories/__init__.py` — Exportar `RawDataRepository`
- [ ] `src/sfa/application/use_cases/ingest_competition.py` — Agregar docstring deprecated; importar `LeagueConfig`/`LEAGUES` desde `domain/ingestion_ports.py`
- [ ] `src/sfa/application/use_cases/ingest_all.py` — Agregar docstring deprecated; importar `LEAGUES` desde `domain/ingestion_ports.py`
- [ ] `src/sfa/tasks/ingestion_tasks.py` — Actualizar tasks para usar `DownloadPlayerDataUseCase` + `CalculateSFAFromRawUseCase` en secuencia; agregar `recalculate_sfa_task`
- [ ] `src/sfa/api/v1/admin.py` — Agregar endpoint `POST /api/v1/admin/recalculate`
- [ ] `src/sfa/core/dependencies.py` — Agregar factories para `RawDataRepository`, `DownloadPlayerDataUseCase`, `CalculateSFAFromRawUseCase`

---

## Checklist de implementación

### Fase 1 — Expansión del modelo RAW

- [ ] **1.1** Agregar `photo_url: Mapped[str | None]` (Text, nullable) y `downloaded_at: Mapped[datetime]` (DateTime timezone=True, not null, server_default=func.now()) al modelo `PlayerStats` en `src/sfa/infrastructure/models/player_stats/models.py`.
  _Listo cuando:_ el modelo es importable sin errores; ambas columnas tienen los tipos y constraints correctos.

- [ ] **1.2** Añadir comentario de migración SQL en el mismo archivo con los `ALTER TABLE` exactos:
  `ALTER TABLE player_stats ADD COLUMN photo_url TEXT;`
  `ALTER TABLE player_stats ADD COLUMN downloaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW();`
  _Listo cuando:_ el comentario existe en el modelo y los SQL son correctos y ejecutables contra la DB.

- [ ] **1.3** Agregar campo `photo_url: str | None` al DTO `PlayerStatsRawDTO` en `src/sfa/domain/ingestion_ports.py`.
  _Listo cuando:_ `PlayerStatsRawDTO` tiene el campo; el dataclass es `frozen=True` y pasa `isinstance` check contra `PlayerStatsRawDTO`.

- [ ] **1.4** Actualizar `APIFootballProvider.fetch_fixture_players` en `src/sfa/infrastructure/providers/api_football.py` para extraer `p['player']['photo']` y asignarlo a `photo_url` en el `PlayerStatsRawDTO` construido. Manejar `None` si el campo no está presente.
  _Listo cuando:_ con JSON de fixture que incluye `photo`, el DTO tiene `photo_url` populado; con JSON sin `photo`, el DTO tiene `photo_url = None`.

- [ ] **1.5** Actualizar `IngestionRepository.upsert_player_stats` en `src/sfa/infrastructure/repositories/ingestion_repository.py` para recibir y persistir `photo_url` en el `INSERT` y en el `ON CONFLICT DO UPDATE`.
  _Listo cuando:_ el método incluye `photo_url` en el dict de valores del `pg_insert`; ejecutar dos veces con misma clave actualiza `photo_url` correctamente.

---

### Fase 2 — Domain: nuevos ports y DTOs

- [ ] **2.1** Mover `LeagueConfig` dataclass y `LEAGUES` list desde `src/sfa/application/use_cases/ingest_competition.py` a `src/sfa/domain/ingestion_ports.py`. Actualizar los imports en `ingest_competition.py`, `ingest_all.py` e `ingestion_tasks.py`.
  _Listo cuando:_ `from sfa.domain.ingestion_ports import LeagueConfig, LEAGUES` funciona; los tres archivos existentes importan desde ahí; no hay errores de importación circular.

- [ ] **2.2** Agregar `DownloadResult`, `CalculationResult` y `RequestEstimationResult` como `@dataclass(frozen=True)` en `src/sfa/domain/ingestion_ports.py` con todos los campos listados en `decisions.md`.
  _Listo cuando:_ los tres DTOs están definidos; cada uno tiene exactamente los campos de la decisión correspondiente; son importables desde `sfa.domain.ingestion_ports`.

- [ ] **2.3** Agregar el método `fixture_players_already_downloaded(fixture_id: int) -> bool` al `IngestionRepositoryPort` Protocol en `src/sfa/domain/ingestion_ports.py`. Implementar el método en `IngestionRepository` haciendo `SELECT COUNT(*) > 0 FROM player_stats WHERE fixture_id = :fixture_id`.
  _Listo cuando:_ el Protocol tiene el método; `IngestionRepository` implementa el método; una llamada con `fixture_id` de un fixture con datos retorna `True`; con un `fixture_id` inexistente retorna `False`.

- [ ] **2.4** Crear `src/sfa/domain/raw_data_ports.py` con `RawPlayerStatsDTO` frozen dataclass y `RawDataRepositoryPort` `@runtime_checkable` Protocol.
  `RawPlayerStatsDTO` debe tener los campos: `player_id`, `fixture_id`, `competition_id`, `season`, `player_name`, `position` (type `Position`), `goals`, `assists`, `shots_on`, `passes_key`, `dribbles_success`, `duels_won`, `tackles`, `interceptions`, `blocks`, `minutes`, `is_away`, `rival_position`, `player_team_position`, `stage_factor`, `home_team_external_id`, `fixture_events` (type `list[FixtureEventRawDTO]`).
  `RawDataRepositoryPort` debe tener los cuatro métodos definidos en `decisions.md` con sus signaturas exactas.
  _Listo cuando:_ el archivo existe; tiene `from __future__ import annotations`; el Protocol es `@runtime_checkable`; no hay dependencias circulares.

- [ ] **2.5** Agregar `DownloadPlayerDataUseCaseProtocol` y `CalculateSFAFromRawUseCaseProtocol` como `@runtime_checkable` Protocol en `src/sfa/domain/ingestion_ports.py`.
  _Listo cuando:_ ambos Protocols están definidos con sus métodos `execute`; son importables desde `sfa.domain.ingestion_ports`.

- [ ] **2.6** Agregar `RequestEstimationService` en `src/sfa/domain/ingestion_ports.py` como clase pura (sin I/O, sin acceso a DB ni API).
  El método `estimate(leagues: list[LeagueConfig], already_downloaded_count: int, fixtures_per_league: dict[int, int]) -> RequestEstimationResult` calcula:
  `net_new = sum(2 * max(0, expected_fixtures - downloaded) + 2 for league in leagues)` donde `expected_fixtures` viene de `fixtures_per_league[league.id]` con default 38 para ligas y 10 para UCL.
  _Listo cuando:_ el método es puro; con 0 fixtures descargados calcula correctamente; con todos descargados retorna `net_new_requests = 0` y `is_feasible = True`.

---

### Fase 3 — Infrastructure: RawDataRepository

- [ ] **3.1** Crear `src/sfa/infrastructure/repositories/raw_data_repository.py` con `RawDataRepository` implementando `RawDataRepositoryPort`. El constructor recibe `session: AsyncSession`.
  _Listo cuando:_ la clase existe; `isinstance(RawDataRepository(session), RawDataRepositoryPort)` es `True`; el archivo tiene los imports necesarios sin importar modelos de dominio desde infrastructure.

- [ ] **3.2** Implementar `get_raw_stats_for_calculation(competition_id, season, player_ids=None) -> list[RawPlayerStatsDTO]`.
  La query hace JOIN: `player_stats` → `fixtures` (ON `player_stats.fixture_id = fixtures.id`) → `players` (ON `player_stats.player_id = players.id`) → `standing_snapshot` (ON `players.team_id = team_id AND season`) → `competition_stages` (ON `fixtures.competition_id AND fixtures.stage`).
  Para cada row, determina `is_away = (players.team_id == fixtures.away_team_id)` y obtiene `rival_position` del `standing_snapshot` del equipo contrario.
  Retorna `RawPlayerStatsDTO` con todos los campos. Nunca retorna ORM models.
  _Listo cuando:_ para un fixture home, `is_away=False` y `rival_position` es la posición del equipo visitante; para un fixture away, `is_away=True`.

- [ ] **3.3** Implementar `get_fixture_events_raw(fixture_id) -> list[FixtureEventRawDTO]` en `RawDataRepository`.
  _Nota:_ los eventos en texto crudo (FixtureEventRawDTO) no se almacenan actualmente en la BD. Este método debe leer de `player_events` (que tiene `event_type`, `minute`, etc.) y reconstruir el contexto necesario para `_process_event`. Documentar en el método qué campos están disponibles y cuáles se deben deducir.
  _Listo cuando:_ el método retorna datos suficientes para que `CalculateSFAFromRawUseCase` pueda identificar goles y asistencias por jugador en el fixture.

- [ ] **3.4** Implementar `get_downloaded_fixture_ids(competition_id, season) -> set[int]` en `RawDataRepository`.
  _Listo cuando:_ retorna el conjunto de `fixture_id` únicos presentes en `player_stats` filtrado por `competition_id` y `season`. Usado por CLI para estimar requests pendientes.

- [ ] **3.5** Implementar `get_players_in_competition(competition_id, season) -> list[PlayerEnrichDTO]` en `RawDataRepository`. Retorna los jugadores que tienen al menos una fila en `player_stats` para esa `competition_id` y `season`.
  _Listo cuando:_ retorna `PlayerEnrichDTO` (ya definido en `enrichment_ports.py`) sin importar ese módulo dos veces — verificar que no hay duplicación de DTO.

- [ ] **3.6** Exportar `RawDataRepository` desde `src/sfa/infrastructure/repositories/__init__.py`.
  _Listo cuando:_ `from sfa.infrastructure.repositories import RawDataRepository` funciona sin error.

---

### Fase 4 — Application: DownloadPlayerDataUseCase

- [ ] **4.1** Crear `src/sfa/application/use_cases/download_player_data.py` con `DownloadPlayerDataUseCase`. Constructor: `__init__(self, provider: FootballDataProviderPort, repo: IngestionRepositoryPort)` — sin `scoring`. Método: `execute(self, league: LeagueConfig, season: int, player_filter: list[str] | None = None) -> DownloadResult`.
  _Listo cuando:_ la clase existe e importa correctamente desde `domain/`; no importa nada de `infrastructure/` ni de `domain/scoring/`.

- [ ] **4.2** Implementar Fase 1 (standings) en `DownloadPlayerDataUseCase.execute()`: `fetch_standings`, `upsert_competition`, `upsert_team` por cada equipo, `upsert_standing_snapshot`.
  _Listo cuando:_ ejecutado dos veces con los mismos datos no crea duplicados (idempotente); `competition_id` se retorna correctamente del upsert.

- [ ] **4.3** Implementar Fase 2 (fixtures) en `DownloadPlayerDataUseCase.execute()`: iterar top_n equipos, `fetch_team_fixtures`, `upsert_fixture`. Antes de `fetch_fixture_events` y `fetch_fixture_players`, verificar `repo.fixture_players_already_downloaded(fixture.external_id)`. Si retorna `True`, incrementar `fixtures_skipped` y continuar sin hacer requests a la API.
  _Listo cuando:_ con un fixture ya en BD, `fixtures_skipped` incrementa y `requests_used` no incrementa para ese fixture.

- [ ] **4.4** Implementar Fase 3 (players+stats) en `DownloadPlayerDataUseCase.execute()`: `fetch_fixture_events` (para tener la lista de eventos), `fetch_fixture_players`, `upsert_player` con `photo_url`, `upsert_player_stats`. No crear `player_events` ni `sfa_season_scores`.
  _Listo cuando:_ `player_stats` se persiste con `photo_url` y `downloaded_at`; `PlayerEvent` y `SFASeasonScore` no son tocados; `players_downloaded` en el resultado es correcto.

- [ ] **4.5** Implementar `player_filter` en `DownloadPlayerDataUseCase`: si `player_filter` no es `None`, solo procesar jugadores cuyo nombre contenga alguno de los strings del filtro (case-insensitive, `any(f.lower() in ps.player_name.lower() for f in player_filter)`).
  _Listo cuando:_ con `player_filter=["Yamal"]` solo se upsertea `player_stats` para jugadores con "Yamal" en el nombre; con `player_filter=None` se procesan todos.

- [ ] **4.6** Escribir `tests/use_cases/test_download_player_data.py` con `FakeFootballDataProvider` (implementa `FootballDataProviderPort` completo) y `FakeIngestionRepository` (implementa `IngestionRepositoryPort` completo). Mínimo 3 tests con `@pytest.mark.anyio`:
  1. `test_download_normal_returns_correct_result` — fixture no descargado previamente → `fixtures_downloaded=1`, `fixtures_skipped=0`.
  2. `test_already_downloaded_fixture_is_skipped` — fixture ya descargado → `fixtures_skipped=1`, sin requests a la API para ese fixture.
  3. `test_player_filter_excludes_non_matching_players` — `player_filter=["Yamal"]` → solo ese jugador en `FakeIngestionRepository.player_stats`.
  _Listo cuando:_ `pytest tests/use_cases/test_download_player_data.py` pasa sin errores.

---

### Fase 5 — Application: CalculateSFAFromRawUseCase

- [ ] **5.1** Crear `src/sfa/application/use_cases/calculate_sfa_from_raw.py` con `CalculateSFAFromRawUseCase`. Constructor: `__init__(self, raw_repo: RawDataRepositoryPort, ingestion_repo: IngestionRepositoryPort, scoring: SFAScoringService)`. Método: `execute(self, competition_id: int, season: str, player_ids: list[int] | None = None) -> CalculationResult`.
  _Listo cuando:_ la clase existe; importa solo de `domain/`; no importa nada de `infrastructure/`.

- [ ] **5.2** Implementar el loop principal de `CalculateSFAFromRawUseCase.execute()`: llamar a `raw_repo.get_raw_stats_for_calculation(competition_id, season, player_ids)`, iterar sobre cada `RawPlayerStatsDTO`, reconstruir goles y asistencias a partir de `dto.fixture_events` (filtrando por nombre del jugador con `_name_matches`), calcular M1–M4+Mvisit para cada evento, hacer `delete_player_events_for_fixture` + `upsert_player_event`, acumular `breakdown`.
  La lógica de `_process_event` de `IngestCompetitionUseCase` se migra aquí como método privado `_process_event`.
  _Listo cuando:_ para un gol en minuto 85 con score_diff=-1 (perdiendo), `M3=2.5`; el `PlayerEvent` resultante tiene los valores de multiplicadores correctos.

- [ ] **5.3** Implementar `score_match_stats` en `CalculateSFAFromRawUseCase`: para cada `RawPlayerStatsDTO`, pasar `{ActionType.DUELS_WON: dto.duels_won, ActionType.TACKLES_INTERCEPTIONS: dto.tackles + dto.interceptions, ActionType.BLOCKS: dto.blocks, ActionType.DRIBBLES_WON: dto.dribbles_success}` a `scoring.score_match_stats`. Sumar los pts al acumulador del jugador.
  _Listo cuando:_ un jugador con 5 duelos ganados genera pts de match stats en el acumulador.

- [ ] **5.4** Implementar upsert final de `SFASeasonScore` al terminar el loop: por cada `player_id` con `total_minutes >= 90`, construir `breakdown` con `{count, pts, pct}` por categoría y llamar a `ingestion_repo.upsert_season_score`. Incrementar `scores_updated`.
  _Listo cuando:_ un jugador con 95 min genera `SFASeasonScore`; un jugador con 85 min no lo genera; el `breakdown` tiene el `pct` calculado correctamente.

- [ ] **5.5** Escribir `tests/use_cases/test_calculate_sfa_from_raw.py` con `FakeRawDataRepository` (implementa `RawDataRepositoryPort` completo) y `FakeIngestionRepository`. Mínimo 3 tests con `@pytest.mark.anyio`:
  1. `test_goal_minute_85_losing_generates_m3_2_5` — gol en minuto 85, perdiendo 0-1 → M3=2.5 en el `PlayerEvent` insertado.
  2. `test_player_under_90_min_no_season_score` — jugador con 85 min → `scores_updated=0`.
  3. `test_player_ids_filter_limits_calculation` — con `player_ids=[42]` solo se calculan eventos para ese jugador.
  _Listo cuando:_ `pytest tests/use_cases/test_calculate_sfa_from_raw.py` pasa sin errores.

---

### Fase 6 — Actualizar Celery tasks y endpoints admin

- [ ] **6.1** Actualizar `_run_ingest_competition` en `src/sfa/tasks/ingestion_tasks.py` para ejecutar en secuencia: (1) `DownloadPlayerDataUseCase.execute(league, season)` con `session.commit()`, (2) `CalculateSFAFromRawUseCase.execute(competition_id, season)` con `session.commit()`. `SFAScoringService` solo se pasa al segundo use case.
  _Listo cuando:_ la task ejecuta ambos use cases en orden; si el primero falla, el segundo no se ejecuta; el log de error se guarda correctamente.

- [ ] **6.2** Actualizar `_run_ingest_all` en `src/sfa/tasks/ingestion_tasks.py` análogamente: iterar sobre `LEAGUES` (importadas desde `domain/ingestion_ports.py`), por cada liga ejecutar Download + Calculate en secuencia. Mantener el guard `requests_used >= 7000` antes de cada liga.
  _Listo cuando:_ la task itera las ligas; el guard de rate limit funciona; `LEAGUES` se importa desde `domain/ingestion_ports.py`.

- [ ] **6.3** Agregar `recalculate_sfa_task(self, competition_id: int, season: str)` en `src/sfa/tasks/ingestion_tasks.py` como `@celery_app.task(bind=True, max_retries=3)`. El helper `_run_recalculate` instancia `CalculateSFAFromRawUseCase` sin crear ningún `APIFootballProvider`.
  _Listo cuando:_ la task existe; ejecutarla no hace ningún request HTTP; retorna `CalculationResult`.

- [ ] **6.4** Agregar endpoint `POST /api/v1/admin/recalculate` en `src/sfa/api/v1/admin.py` que dispara `recalculate_sfa_task.delay(competition_id, season)`. Acepta `competition_id: int` y `season: str` como query params. Retorna `{"task_id": ..., "competition_id": ..., "season": ...}`.
  _Listo cuando:_ el endpoint existe; `POST /api/v1/admin/recalculate?competition_id=1&season=2024` retorna 200 con `task_id`.

- [ ] **6.5** Agregar en `src/sfa/core/dependencies.py`:
  - `get_raw_data_repository(db) -> RawDataRepository`
  - `get_download_player_data_use_case(provider, repo) -> DownloadPlayerDataUseCase`
  - `get_calculate_sfa_from_raw_use_case(raw_repo, ingestion_repo, scoring) -> CalculateSFAFromRawUseCase`
  Seguir el patrón estándar con `Annotated[..., Depends(...)]`.
  _Listo cuando:_ los tres factories están en `dependencies.py`; no hay wiring fuera de ese archivo.

---

### Fase 7 — CLI run.py

- [ ] **7.1** Crear `src/run.py` con `argparse`: tres subcomandos mutuamente excluyentes `--download`, `--recalculate`, `--add-competition`. `--download` acepta flags opcionales: `--players` (lista de nombres separados por coma), `--league-id` (int), `--season` (int, default 2024), `--yes` (bool, skip confirmación).
  _Listo cuando:_ `python src/run.py --help` muestra los tres subcomandos; `python src/run.py --download --help` muestra los flags.

- [ ] **7.2** Implementar flujo `--download` en `src/run.py`:
  1. Listar jugadores existentes en BD via `RawDataRepository.get_players_in_competition` (o todos los players si no hay filtro de competición).
  2. Listar competiciones disponibles (LEAGUES desde `domain/ingestion_ports.py`).
  3. Si `--players` no pasado por flag, pedir con `input()`.
  4. Si `--league-id` no pasado por flag, pedir con `input()`.
  5. Calcular estimación via `RequestEstimationService.estimate()`.
  6. Mostrar: `"Estimación: ~N requests nuevos de 100 diarios. ¿Continuar? [s/N]"`.
  7. Si no `--yes`, pedir confirmación con `input()`.
  8. Ejecutar `DownloadPlayerDataUseCase.execute()` con `AsyncSessionLocal`.
  9. Ejecutar `CalculateSFAFromRawUseCase.execute()` inmediatamente después.
  10. Imprimir resumen: fixtures descargados, saltados, jugadores, requests usados.
  _Listo cuando:_ el flujo interactivo funciona end-to-end en local contra la DB real.

- [ ] **7.3** Implementar estimación de requests en el flujo `--download` de `run.py` usando `RawDataRepository.get_downloaded_fixture_ids` para obtener el count de fixtures ya descargados y `RequestEstimationService.estimate` para el cálculo.
  _Listo cuando:_ la estimación es precisa: para una liga con 0 fixtures descargados muestra el máximo; para una liga completamente descargada muestra 0 requests nuevos.

- [ ] **7.4** Implementar flujo `--recalculate` en `src/run.py`: acepta `--competition-id` (int) y `--season` (str) como flags. Ejecuta `CalculateSFAFromRawUseCase.execute()` sin ninguna llamada a API. Imprime: `"Recalculados N jugadores, M eventos, K scores actualizados"`.
  _Listo cuando:_ `python src/run.py --recalculate --competition-id 1 --season 2024` ejecuta el recálculo e imprime el resumen. No hace ningún request HTTP.

- [ ] **7.5** Implementar flujo `--add-competition` en `src/run.py`: acepta `--league-id` (int) y `--season` (int). Ejecuta `DownloadPlayerDataUseCase.execute()` para esa liga. Los jugadores nuevos encontrados se agregan a la BD; los ya existentes se actualizan (idempotente).
  _Listo cuando:_ `python src/run.py --add-competition --league-id 140 --season 2024` descarga La Liga; segunda ejecución salta fixtures ya descargados.

---

### Fase 8 — Deprecación y limpieza

- [ ] **8.1** Agregar docstring de deprecación a `IngestCompetitionUseCase` y `IngestAllCompetitionsUseCase`:
  `"""DEPRECATED: use DownloadPlayerDataUseCase + CalculateSFAFromRawUseCase instead. Will be removed in next refactor."""`
  _Listo cuando:_ ambas clases tienen el docstring; ningún test falla.

- [ ] **8.2** Crear `http/download_and_calculate.http` con mínimo 4 casos HTTP:
  `POST /api/v1/admin/ingest/140` (trigger download La Liga),
  `POST /api/v1/admin/recalculate?competition_id=1&season=2024` (trigger recalculate),
  `POST /api/v1/admin/ingest-all?season=2024` (trigger all),
  `GET /api/v1/status` (verificar estado post-ingestion).
  Con comentarios explicando el flujo RAW → CALCULADO.
  _Listo cuando:_ el archivo existe con los 4 casos y comentarios.

- [ ] **8.3** Ejecutar `pytest tests/` completo y documentar resultado. Los tests existentes de `IngestCompetitionUseCase` deben seguir pasando. Los tests nuevos de los use cases nuevos deben pasar.
  _Listo cuando:_ `pytest tests/` pasa; si hay fallos pre-existentes, están documentados.

- [ ] **8.4** Verificar `flake8 src/ tests/` sin errores (max-line-length 120).
  _Listo cuando:_ `flake8 src/ tests/` retorna exit code 0.

- [ ] **8.5** Verificar `isort --check-only src/ tests/` sin errores.
  _Listo cuando:_ `isort --check-only src/ tests/` retorna exit code 0.

---

## Agent Routing Brief

**DDD Designer needed:** no

Este refactor no introduce nuevas entidades de dominio, nuevos value objects con invariantes,
ni nuevos aggregates con reglas de consistencia.

Los nuevos tipos de datos son:
- `RawPlayerStatsDTO` — read model desnormalizado, contenedor de datos sin comportamiento.
- `DownloadResult`, `CalculationResult`, `RequestEstimationResult` — result DTOs de
  operaciones, frozen dataclasses sin invariantes de negocio.
- `LeagueConfig` — ya existía en el codebase, solo se mueve de ubicación.

`RequestEstimationService` es lógica de negocio pura (aritmética sobre constantes del
dominio de la API), no requiere modelado de dominio.

La invariante central — "los datos RAW son inmutables; los cálculos SFA siempre se generan
desde RAW; nunca mezclar descarga con cálculo" — se impone mediante separación de use cases
y ports, no mediante entidades de dominio con comportamiento.

**Orden obligatorio de implementación:**

Seguir las fases en orden estricto. No saltarse fases.

1. **Fase 1** primero: el modelo necesita las columnas nuevas antes de que el repositorio
   pueda escribir `photo_url`.
2. **Fase 2** antes de Fase 3 y 4: los ports de dominio deben existir para que
   infrastructure y application puedan compilar.
3. **Fase 3** antes de Fases 4 y 5: el repositorio debe existir para que los use cases
   puedan ser testeados con Fakes realistas.
4. **Fases 4 y 5** pueden desarrollarse en paralelo una vez Fase 2 y 3 están completas.
5. **Fase 6** solo cuando Fases 4 y 5 están completas y testeadas.
6. **Fase 7** (CLI) al final, cuando todos los use cases están operativos.
7. **Fase 8** siempre al final.

## Verificación end-to-end

1. Aplicar migración SQL: `ALTER TABLE player_stats ADD COLUMN photo_url TEXT; ALTER TABLE player_stats ADD COLUMN downloaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW();`
2. `python src/run.py --download --league-id 140 --season 2024 --yes` — debe descargar La Liga, mostrar estimación de requests, y calcular SFA automáticamente al terminar.
3. Segunda ejecución: `python src/run.py --download --league-id 140 --season 2024 --yes` — debe mostrar `fixtures_skipped = N` (todos los ya descargados) y `requests_used = 2` (solo standings + fixtures list).
4. `python src/run.py --recalculate --competition-id 1 --season 2024` — debe recalcular todos los jugadores sin hacer ningún request HTTP. Verificar en la BD que `sfa_season_scores.total_pts` cambia si se modificó la fórmula.
5. `pytest tests/` — todos los tests nuevos y existentes deben pasar.
6. `POST /api/v1/admin/recalculate?competition_id=1&season=2024` — debe retornar `task_id`; el worker de Celery debe ejecutar el cálculo sin tocar la API.
