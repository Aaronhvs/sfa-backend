# Fase 1 — Ingesta API-Football

## TL;DR

Implementar el pipeline de ingesta de datos desde API-Football v3 siguiendo la arquitectura hexagonal existente. Se crean: DTOs de ingesta, port de proveedor de datos, adapter HTTP para API-Football, repositorio de escritura, use case orquestador, y Celery tasks con Beat. M4 fijo 0.32 hasta tener PSxG real de FBref.

---

## Decisiones

| Decisión | Valor |
|----------|-------|
| API key | Vive en `.env`, se lee desde `BaseConfig` como `API_FOOTBALL_KEY` |
| Player / Team | Agregar `external_id` (API-Football ID) a ambos modelos |
| Celery Beat | Incluido con schedule periódico (cada 6-8 hrs) |
| Ligas | Las mismas 6: La Liga, PL, Bundesliga, Serie A, Ligue 1, Champions League |
| Posiciones | Detectar EXT/LAT desde el día 1 con diccionario de jugadores conocidos |
| Filtro minutos | ≥20 min por partido, ≥90 min acumulados en temporada |
| M4 (PSxG) | Fijo 0.32 (como legacy), hasta tener datos reales de FBref |
| Celery + async | `asyncio.run()` dentro del task para reusar repos async |
| HTTP client | `httpx` (async nativo, reemplaza `requests`) |

---

## Archivos a crear

| # | Archivo | Descripción |
|---|---------|-------------|
| 1 | `src/sfa/domain/ingestion_ports.py` | DTOs raw + ports de ingesta (provider + repository) |
| 2 | `src/sfa/domain/position_mapping.py` | Mapeo de posiciones API-Football → enum Position |
| 3 | `src/sfa/infrastructure/providers/__init__.py` | Barrel export del provider |
| 4 | `src/sfa/infrastructure/providers/api_football.py` | Adapter HTTP para API-Football v3 |
| 5 | `src/sfa/infrastructure/repositories/ingestion_repository.py` | Repositorio de escritura (upserts idempotentes) |
| 6 | `src/sfa/application/use_cases/ingest_competition.py` | Use case: ingestar 1 liga completa |
| 7 | `src/sfa/application/use_cases/ingest_all.py` | Use case: wrapper para ingestar todas las ligas |
| 8 | `src/sfa/tasks/__init__.py` | Barrel del módulo de tasks |
| 9 | `src/sfa/tasks/ingestion_tasks.py` | Celery tasks (thin wrappers) |
| 10 | `src/sfa/api/v1/admin.py` | Endpoints admin para disparar ingesta manualmente |

## Archivos a modificar

| # | Archivo | Cambio |
|---|---------|--------|
| 1 | `src/sfa/core/config.py` | Agregar `API_FOOTBALL_KEY`, `API_FOOTBALL_BASE_URL` |
| 2 | `src/sfa/infrastructure/models/players/models.py` | Agregar `external_id` |
| 3 | `src/sfa/infrastructure/models/teams/models.py` | Agregar `external_id` |
| 4 | `src/sfa/celery_app.py` | `beat_schedule`, `autodiscover_tasks` |
| 5 | `src/sfa/infrastructure/repositories/__init__.py` | Export `IngestionRepository` |
| 6 | `src/sfa/main.py` | Registrar admin router |
| 7 | `docker-compose-development.yml` | Servicio `celery_beat` |
| 8 | `requirements/base.txt` | Agregar `httpx` |

---

## Fase A — Modelo y configuración

### Paso 1: Config de API-Football

**Archivo:** `src/sfa/core/config.py`

Agregar a `BaseConfig`:

```python
API_FOOTBALL_KEY: str = ""
API_FOOTBALL_BASE_URL: str = "https://v3.football.api-sports.io"
```

Agregar a `.env`:

```
API_FOOTBALL_KEY=tu_key_aqui
```

### Paso 2: Migración — external_id en Player y Team

**Archivo:** `src/sfa/infrastructure/models/players/models.py`

Agregar campo:

```python
external_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
```

**Archivo:** `src/sfa/infrastructure/models/teams/models.py`

Agregar campo:

```python
external_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
```

> Nota: crear migración Alembic si se usa, o documentar `ALTER TABLE` manual.

### Paso 3: Dependencia httpx

**Archivo:** `requirements/base.txt`

Agregar:

```
httpx>=0.27.0
```

---

## Fase B — Domain layer

### Paso 4: DTOs raw y ports de ingesta

**Archivo nuevo:** `src/sfa/domain/ingestion_ports.py`

#### DTOs raw (datos crudos del proveedor externo)

```python
@dataclass(frozen=True)
class StandingRawDTO:
    team_external_id: int
    team_name: str
    position: int
    points: int


@dataclass(frozen=True)
class FixtureRawDTO:
    external_id: int
    home_team_external_id: int
    away_team_external_id: int
    home_team_name: str
    away_team_name: str
    round_str: str          # "Regular Season - 15", "Quarter-finals", etc.
    league_name: str
    played_at: datetime
    home_goals: int
    away_goals: int


@dataclass(frozen=True)
class FixtureEventRawDTO:
    type: str               # "Goal", "Card", "subst"
    detail: str             # "Normal Goal", "Penalty", "Missed Penalty", etc.
    player_name: str
    assist_name: str | None
    team_external_id: int
    minute: int
    extra_minute: int       # tiempo extra (0 si no aplica)


@dataclass(frozen=True)
class PlayerStatsRawDTO:
    player_external_id: int
    player_name: str
    position: str           # "Attacker", "Midfielder", "Defender", "Goalkeeper"
    minutes: int
    goals: int
    assists: int
    shots_on: int
    passes_key: int
    dribbles_success: int
    duels_won: int
    tackles: int
    interceptions: int
    blocks: int
```

#### Port: FootballDataProviderPort

```python
@runtime_checkable
class FootballDataProviderPort(Protocol):
    async def fetch_standings(
        self, league_id: int, season: int,
    ) -> list[StandingRawDTO]: ...

    async def fetch_team_fixtures(
        self, team_id: int, league_id: int, season: int,
    ) -> list[FixtureRawDTO]: ...

    async def fetch_fixture_events(
        self, fixture_id: int,
    ) -> list[FixtureEventRawDTO]: ...

    async def fetch_fixture_players(
        self, fixture_id: int, team_id: int,
    ) -> list[PlayerStatsRawDTO]: ...
```

#### Port: IngestionRepositoryPort

```python
@runtime_checkable
class IngestionRepositoryPort(Protocol):
    async def upsert_competition(
        self, name: str, country: str, factor: float,
    ) -> int: ...

    async def upsert_team(
        self, external_id: int, name: str, competition_id: int,
    ) -> int: ...

    async def upsert_player(
        self, external_id: int, name: str, team_id: int, position: Position,
    ) -> int: ...

    async def upsert_fixture(
        self, external_id: int, competition_id: int,
        home_team_id: int, away_team_id: int,
        stage: str, season: str, played_at: datetime,
        matchday: int | None,
    ) -> int: ...

    async def upsert_standing_snapshot(
        self, competition_id: int, team_id: int,
        season: str, matchday: int, position: int, points: int,
    ) -> None: ...

    async def upsert_player_event(
        self, player_id: int, fixture_id: int,
        minute: int, event_type: EventType,
        score_before: str | None, score_diff: int | None,
        psxg: float | None,
        m1: float, m2: float, m3: float, m4: float,
        mvisit: float, pts: float,
    ) -> None: ...

    async def upsert_player_stats(
        self, player_id: int, fixture_id: int,
        season: str, stats: dict,
    ) -> None: ...

    async def upsert_season_score(
        self, player_id: int, competition_id: int,
        season: str, total_pts: float,
        matches_played: int, breakdown: dict,
    ) -> None: ...

    async def save_ingestion_log(
        self, competition_id: int, season: str,
        status: IngestionStatus, players_processed: int | None,
        error_msg: str | None,
    ) -> None: ...

    async def delete_player_events_for_fixture(
        self, player_id: int, fixture_id: int,
    ) -> None: ...
```

### Paso 5: Mapeo de posiciones refinado

**Archivo nuevo:** `src/sfa/domain/position_mapping.py`

```python
from sfa.infrastructure.models.enums import Position

# Mapeo base: API-Football position string → Position enum
BASE_POSITION_MAP: dict[str, Position] = {
    "Attacker":   Position.DEL,
    "Midfielder": Position.MC,
    "Defender":   Position.DC,
    "Goalkeeper":  Position.GK,
}

# Diccionario de jugadores conocidos con posición refinada.
# Permite detectar EXT/LAT que API-Football no distingue.
KNOWN_POSITIONS: dict[str, Position] = {
    # La Liga — Extremos
    "Raphinha":              Position.EXT,
    "Lamine Yamal":          Position.EXT,
    "Dani Olmo":             Position.EXT,
    "Vinícius Júnior":       Position.EXT,
    "Rodrygo":               Position.EXT,
    "Nico Williams":         Position.EXT,
    "Ferran Torres":         Position.EXT,
    "Ansu Fati":             Position.EXT,
    "Bernardo Silva":        Position.EXT,
    # La Liga — Laterales
    "Alejandro Balde":       Position.LAT,
    "Jules Koundé":          Position.LAT,
    "Dani Carvajal":         Position.LAT,
    "Lucas Vázquez":         Position.LAT,
    "Ferland Mendy":         Position.LAT,
    # Premier League — Extremos
    "Bukayo Saka":           Position.EXT,
    "Marcus Rashford":       Position.EXT,
    "Gabriel Martinelli":    Position.EXT,
    "Phil Foden":            Position.EXT,
    "Jack Grealish":         Position.EXT,
    "Jarrod Bowen":          Position.EXT,
    "Omar Marmoush":         Position.EXT,
    # Premier League — Laterales
    "Trent Alexander-Arnold": Position.LAT,
    "Reece James":           Position.LAT,
    "Kyle Walker":           Position.LAT,
    "Andrew Robertson":      Position.LAT,
    # Bundesliga — Extremos
    "Jamal Musiala":         Position.EXT,
    "Florian Wirtz":         Position.EXT,
    "Kingsley Coman":        Position.EXT,
    "Leroy Sané":            Position.EXT,
    # Bundesliga — Laterales
    "Alejandro Grimaldo":    Position.LAT,
    "Alphonso Davies":       Position.LAT,
    # Serie A / Ligue 1 — Extremos
    "Rafael Leão":           Position.EXT,
    "Ousmane Dembélé":       Position.EXT,
    # ... se amplía progresivamente
}


def map_position(player_name: str, api_football_position: str) -> Position:
    """Determina la posición SFA de un jugador.

    1. Si el jugador está en KNOWN_POSITIONS, retorna esa posición.
    2. Si no, usa el mapeo base de API-Football.
    3. Si la posición de API-Football no se reconoce, retorna MC por defecto.
    """
    if player_name in KNOWN_POSITIONS:
        return KNOWN_POSITIONS[player_name]
    return BASE_POSITION_MAP.get(api_football_position, Position.MC)
```

---

## Fase C — Infrastructure adapters

### Paso 6: API-Football HTTP client (provider)

**Archivos nuevos:**
- `src/sfa/infrastructure/providers/__init__.py`
- `src/sfa/infrastructure/providers/api_football.py`

Implementa `FootballDataProviderPort`.

#### Responsabilidades

1. **HTTP async con httpx** — Cada método hace una request a la API
2. **Rate limiter** — Tracking interno de requests usados. Si la respuesta incluye `rateLimit` en errors, espera 65s y reintenta
3. **Retry con backoff** — 3 intentos, timeout 20s, sleep 10s en timeout
4. **Parseo** — Convierte JSON de API-Football → DTOs raw definidos en paso 4
5. **Stage mapping** — Dict `ROUND_TO_STAGE` traducido del legacy:

```python
ROUND_TO_STAGE: dict[str, str] = {
    "group stage":      "group",
    "league stage":     "group",
    "round of 32":      "round_of_16",
    "last 16":          "round_of_16",
    "round of 16":      "round_of_16",
    "quarter-finals":   "quarter",
    "quarter finals":   "quarter",
    "semi-finals":      "semi",
    "semi finals":      "semi",
    "3rd place final":  "semi",
    "final":            "final",
}
```

6. **Score at minute helper** — Calcula el marcador justo antes de un evento (traducido del legacy `get_score_at_minute`)

#### Estructura del provider

```python
class APIFootballProvider(FootballDataProviderPort):
    def __init__(self, api_key: str, base_url: str) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._requests_used = 0
        self._client: httpx.AsyncClient | None = None

    async def _get(self, endpoint: str, params: dict | None = None) -> dict:
        """HTTP GET con rate limiting, retry y backoff."""
        ...

    async def fetch_standings(self, league_id, season) -> list[StandingRawDTO]:
        data = await self._get("standings", {"league": league_id, "season": season})
        # parsear response[0].league.standings[0] → list[StandingRawDTO]
        ...

    async def fetch_team_fixtures(self, team_id, league_id, season) -> list[FixtureRawDTO]:
        data = await self._get("fixtures", {
            "team": team_id, "league": league_id,
            "season": season, "status": "FT",
        })
        # parsear response → list[FixtureRawDTO]
        ...

    async def fetch_fixture_events(self, fixture_id) -> list[FixtureEventRawDTO]:
        data = await self._get("fixtures/events", {"fixture": fixture_id})
        # parsear response → list[FixtureEventRawDTO]
        ...

    async def fetch_fixture_players(self, fixture_id, team_id) -> list[PlayerStatsRawDTO]:
        data = await self._get("fixtures/players", {"fixture": fixture_id})
        # filtrar por team_id, parsear → list[PlayerStatsRawDTO]
        ...

    def get_stage(self, round_str: str, league_name: str) -> str:
        """Mapea round string de API-Football → stage SFA."""
        ...

    def get_score_at_minute(
        self, events: list[FixtureEventRawDTO], minute: int, home_team_id: int,
    ) -> tuple[int, int]:
        """Retorna (home_goals, away_goals) justo antes del minuto dado."""
        ...

    @property
    def requests_used(self) -> int:
        return self._requests_used
```

> **Nota de seguridad:** la API key se pasa por constructor desde config, nunca se hardcodea.

### Paso 7: Ingestion repository (escritura)

**Archivo nuevo:** `src/sfa/infrastructure/repositories/ingestion_repository.py`

Implementa `IngestionRepositoryPort`.

#### Estrategia de upserts

| Entidad | Conflict target | Estrategia |
|---------|----------------|------------|
| Competition | `name` (unique) | `ON CONFLICT DO UPDATE` country, factor |
| Team | `external_id` (unique) | `ON CONFLICT DO UPDATE` name |
| Player | `external_id` (unique) | `ON CONFLICT DO UPDATE` name, team_id, position |
| Fixture | `external_id` (unique) | `ON CONFLICT DO UPDATE` stage, matchday |
| StandingSnapshot | `uq_standing_snapshot` | `ON CONFLICT DO UPDATE` position, points |
| PlayerStats | `uq_player_stats` | `ON CONFLICT DO UPDATE` todos los campos de stats |
| SFASeasonScore | `uq_sfa_season_score` | `ON CONFLICT DO UPDATE` total_pts, matches_played, breakdown, last_updated |
| PlayerEvent | N/A | `DELETE WHERE fixture_id + player_id` → `INSERT` (idempotente) |
| IngestionLog | N/A | Siempre `INSERT` (es append-only) |

#### Implementación con SQLAlchemy

Usar `sqlalchemy.dialects.postgresql.insert` para los upserts:

```python
from sqlalchemy.dialects.postgresql import insert as pg_insert

class IngestionRepository(IngestionRepositoryPort):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_team(self, external_id, name, competition_id) -> int:
        stmt = pg_insert(Team).values(
            external_id=external_id,
            name=name,
            competition_id=competition_id,
        ).on_conflict_do_update(
            index_elements=["external_id"],
            set_={"name": name},
        ).returning(Team.id)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.scalar_one()

    # ... análogo para cada entidad
```

**Modificar:** `src/sfa/infrastructure/repositories/__init__.py` — Agregar `IngestionRepository` al barrel export.

---

## Fase D — Application layer

### Paso 8: Use case IngestCompetition

**Archivo nuevo:** `src/sfa/application/use_cases/ingest_competition.py`

#### Dataclasses auxiliares

```python
@dataclass(frozen=True)
class LeagueConfig:
    id: int            # API-Football league ID
    name: str          # "La Liga", "Premier League", etc.
    country: str       # "ESP", "ENG", etc.
    comp_factor: float # 1.0 para ligas domésticas, 1.5 para Champions
    top_n: int         # cuántos equipos del top ingestar


@dataclass(frozen=True)
class IngestionResult:
    competition: str
    players_processed: int
    fixtures_processed: int
    status: str        # "completed" | "failed"
    error: str | None
```

#### Constante de ligas (mismas que legacy)

```python
LEAGUES: list[LeagueConfig] = [
    LeagueConfig(id=140, name="La Liga",          country="ESP", comp_factor=1.0, top_n=6),
    LeagueConfig(id=39,  name="Premier League",   country="ENG", comp_factor=1.0, top_n=6),
    LeagueConfig(id=78,  name="Bundesliga",       country="GER", comp_factor=1.0, top_n=6),
    LeagueConfig(id=135, name="Serie A",          country="ITA", comp_factor=1.0, top_n=6),
    LeagueConfig(id=61,  name="Ligue 1",          country="FRA", comp_factor=1.0, top_n=6),
    LeagueConfig(id=2,   name="Champions League", country="EUR", comp_factor=1.5, top_n=24),
]
```

#### Constructor

```python
class IngestCompetitionUseCase:
    def __init__(
        self,
        provider: FootballDataProviderPort,
        repo: IngestionRepositoryPort,
        scoring: SFAScoringService,
    ) -> None:
        self._provider = provider
        self._repo = repo
        self._scoring = scoring
```

#### Método execute — Flujo completo

```python
async def execute(
    self, league: LeagueConfig, season: int,
) -> IngestionResult:
```

**Paso 8.1 — Standings**
```
1. Fetch standings via provider
2. Upsert competition → competition_id
3. Por cada equipo en standings:
   a. Upsert team (external_id, name, competition_id) → team_id
   b. Upsert standing_snapshot
4. Construir pos_cache: {team_external_id: position}
5. Construir team_id_map: {team_external_id: team_db_id}
```

**Paso 8.2 — Fixtures por equipo**
```
6. Tomar top_n equipos de standings
7. Por cada equipo:
   a. Fetch fixtures via provider
   b. Por cada fixture:
      i.   Determinar home/away, opponent, is_home
      ii.  Obtener posición del rival en pos_cache (default 10)
      iii. Determinar stage via provider.get_stage()
      iv.  Upsert fixture → fixture_id
```

**Paso 8.3 — Eventos y stats por fixture**
```
      v.   Fetch fixture events via provider
      vi.  Fetch fixture players via provider
      vii. Por cada jugador (≥20 min):
           - map_position() para determinar Position
           - Upsert player (external_id, name, team_id, position)
           - Upsert player_stats
```

**Paso 8.4 — Cálculo SFA por jugador en el fixture**
```
           Para goles del jugador (matching por nombre en events):
             - minute = elapsed + extra
             - score_before = get_score_at_minute(events, minute, home_team_id)
             - score_diff desde perspectiva del jugador
             - is_penalty = detail == "Penalty"
             - is_away = player team != home team
             - group = position_to_group(player.position)
             - action = ActionType.GOAL o ActionType.GOAL_PENALTY
             - stage_factor = obtener de CompetitionStage
             - SFAScore = scoring.score_event(
                   group, action, player_team_pos, rival_pos,
                   stage_factor, minute, score_diff,
                   is_penalty, psxg=0.32, is_away,
               )
             - Upsert player_event con M1/M2/M3/M4/Mvisit/pts

           Para asistencias del jugador (matching assist_name en events):
             - Mismo cálculo pero action = ActionType.ASSIST
             - psxg = None (M4 = 1.0 para asistencias)

           Para stats agregadas (xG, duels, tackles, etc.):
             - scoring.score_match_stats(group, stats_dict, player_pos, rival_pos, stage_factor)
             - Sumar pts de cada SFAScore al acumulador del jugador
```

**Paso 8.5 — Acumular y guardar season scores**
```
8. Por cada jugador con ≥90 min acumulados en la temporada:
   a. Sumar total_pts de todos sus fixtures
   b. Construir breakdown JSONB (categoría → {count, pts, pct})
   c. Upsert season_score (player_id, competition_id, season, total_pts, matches_played, breakdown)
```

**Paso 8.6 — Ingestion log**
```
9. Guardar IngestionLog con status completed/failed, players_processed, error_msg
10. Commit final
```

> **Importante:** El use case recibe una sesión de BD. Todo el trabajo se hace en una transacción. Si falla, se hace rollback y se guarda el log con status=failed.

### Paso 9: Use case IngestAll

**Archivo nuevo:** `src/sfa/application/use_cases/ingest_all.py`

```python
class IngestAllCompetitionsUseCase:
    def __init__(
        self,
        provider: FootballDataProviderPort,
        repo: IngestionRepositoryPort,
        scoring: SFAScoringService,
    ) -> None:
        self._ingest = IngestCompetitionUseCase(provider, repo, scoring)

    async def execute(self, season: int) -> list[IngestionResult]:
        results = []
        for league in LEAGUES:
            # Verificar rate limit antes de cada liga
            if self._ingest._provider.requests_used >= 7000:
                break
            result = await self._ingest.execute(league, season)
            results.append(result)
        return results
```

---

## Fase E — Celery tasks + Beat

### Paso 10: Tasks de ingesta

**Archivos nuevos:**
- `src/sfa/tasks/__init__.py`
- `src/sfa/tasks/ingestion_tasks.py`

```python
import asyncio
from sfa.celery_app import celery_app


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def ingest_competition_task(self, league_id: int, season: int):
    """Ingesta de una liga específica. Thin wrapper sync → async."""
    try:
        asyncio.run(_run_ingest_competition(league_id, season))
    except Exception as exc:
        self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=1)
def ingest_all_competitions_task(self, season: int):
    """Ingesta de todas las ligas configuradas."""
    try:
        asyncio.run(_run_ingest_all(season))
    except Exception as exc:
        self.retry(exc=exc)


async def _run_ingest_competition(league_id: int, season: int):
    """Crea las dependencias async y ejecuta el use case."""
    from sfa.core.config import get_settings
    from sfa.infrastructure.database import AsyncSessionLocal
    from sfa.infrastructure.providers.api_football import APIFootballProvider
    from sfa.infrastructure.repositories.ingestion_repository import IngestionRepository
    from sfa.domain.scoring.services import SFAScoringService
    from sfa.application.use_cases.ingest_competition import (
        IngestCompetitionUseCase, LEAGUES,
    )

    settings = get_settings()
    provider = APIFootballProvider(settings.API_FOOTBALL_KEY, settings.API_FOOTBALL_BASE_URL)
    scoring = SFAScoringService()

    league = next((l for l in LEAGUES if l.id == league_id), None)
    if league is None:
        raise ValueError(f"Liga no encontrada: {league_id}")

    async with AsyncSessionLocal() as session:
        repo = IngestionRepository(session)
        use_case = IngestCompetitionUseCase(provider, repo, scoring)
        result = await use_case.execute(league, season)
        await session.commit()

    return result


async def _run_ingest_all(season: int):
    """Crea las dependencias async y ejecuta IngestAll."""
    from sfa.core.config import get_settings
    from sfa.infrastructure.database import AsyncSessionLocal
    from sfa.infrastructure.providers.api_football import APIFootballProvider
    from sfa.infrastructure.repositories.ingestion_repository import IngestionRepository
    from sfa.domain.scoring.services import SFAScoringService
    from sfa.application.use_cases.ingest_all import IngestAllCompetitionsUseCase

    settings = get_settings()
    provider = APIFootballProvider(settings.API_FOOTBALL_KEY, settings.API_FOOTBALL_BASE_URL)
    scoring = SFAScoringService()

    async with AsyncSessionLocal() as session:
        repo = IngestionRepository(session)
        use_case = IngestAllCompetitionsUseCase(provider, repo, scoring)
        results = await use_case.execute(season)
        await session.commit()

    return results
```

### Paso 11: Configurar Celery Beat

**Archivo:** `src/sfa/celery_app.py`

Reemplazar contenido completo por:

```python
from celery import Celery
from celery.schedules import crontab

from sfa.core.config import get_settings

settings = get_settings()

celery_app = Celery("sfa", broker=settings.CELERY_BROKER_URL)

celery_app.autodiscover_tasks(["sfa.tasks"])

celery_app.conf.beat_schedule = {
    "ingest-all-competitions-every-8h": {
        "task": "sfa.tasks.ingestion_tasks.ingest_all_competitions_task",
        "schedule": crontab(hour="*/8"),
        "args": (2024,),   # season — actualizar cada temporada
    },
}

celery_app.conf.timezone = "UTC"
```

### Paso 12: Docker compose — Celery Beat

**Archivo:** `docker-compose-development.yml`

Agregar servicio después de `celery_worker`:

```yaml
  celery_beat:
    build:
      context: .
      dockerfile: enviroments/development/Dockerfile
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql+asyncpg://sfa:sfa@db:5432/sfa
      REDIS_URL: redis://redis:6379/0
      CELERY_BROKER_URL: redis://redis:6379/0
    depends_on:
      - db
      - redis
    command: celery -A sfa.celery_app beat --loglevel=info
    volumes:
      - .:/code
```

---

## Fase F — Endpoint admin

### Paso 13: Router admin

**Archivo nuevo:** `src/sfa/api/v1/admin.py`

```python
from fastapi import APIRouter, Query
from sfa.tasks.ingestion_tasks import (
    ingest_competition_task,
    ingest_all_competitions_task,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

CURRENT_SEASON = 2024  # centralizar


@router.post("/ingest/{league_id}")
async def trigger_ingest_competition(
    league_id: int,
    season: int = Query(default=CURRENT_SEASON),
):
    """Dispara la ingesta de una liga específica como task async de Celery."""
    task = ingest_competition_task.delay(league_id, season)
    return {"task_id": task.id, "league_id": league_id, "season": season}


@router.post("/ingest-all")
async def trigger_ingest_all(
    season: int = Query(default=CURRENT_SEASON),
):
    """Dispara la ingesta de todas las ligas como task async de Celery."""
    task = ingest_all_competitions_task.delay(season)
    return {"task_id": task.id, "season": season}


@router.get("/ingestion-logs")
async def get_ingestion_logs():
    """Consulta los últimos logs de ingesta."""
    # TODO: inyectar repo y consultar IngestionLog
    # Por ahora retorna placeholder
    return {"logs": []}
```

**Modificar:** `src/sfa/main.py` — Agregar:

```python
from sfa.api.v1.admin import router as admin_router
# ... en la sección de include_router:
app.include_router(admin_router)
```

---

## Verificación

| # | Qué verificar | Cómo |
|---|---------------|------|
| 1 | Tests existentes siguen pasando | `pytest` |
| 2 | `IngestCompetitionUseCase` con provider mock calcula M1/M2/M3 correctamente | Test unitario: crear mock provider que retorne fixtures/events fijos, verificar que los `player_events` guardados tienen multiplicadores esperados |
| 3 | `APIFootballProvider` parsea JSON de standings/fixtures/events | Test unitario: fixtures JSON estáticos → verificar DTOs resultantes |
| 4 | `IngestionRepository` upserts son idempotentes | Test unitario: ejecutar upsert_team 2 veces con mismos datos → misma row |
| 5 | `position_mapping` mapea EXT/LAT para jugadores conocidos | Test unitario: `map_position("Lamine Yamal", "Attacker")` → `Position.EXT` |
| 6 | Pipeline end-to-end | Integración manual: `docker compose up` → `POST /api/v1/admin/ingest/140` → verificar datos en BD |
| 7 | Celery worker procesa la task | `docker compose logs celery_worker` — verificar que la task se ejecuta |
| 8 | Celery Beat agenda la task periódica | `docker compose logs celery_beat` — verificar schedule |

---

## Excluido de esta fase (Fase 2+)

- FBref scraper (PSxG real para M4, pases progresivos, presiones, recuperaciones)
- Understat scraper (xG por disparo individual)
- Merge fuzzy Understat ↔ BD (matching por nombre)
- Fotos de jugadores (Wikipedia)
- Diccionario completo de posiciones EXT/LAT (se amplía progresivamente)
- Recálculo de scores existentes al obtener PSxG real
- Alembic migrations (documentar ALTER TABLE por ahora si no hay setup)
