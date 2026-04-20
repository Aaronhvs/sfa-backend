# Fase 2 — Enriquecimiento FBref + Understat

## TL;DR

Enriquecer los datos ingresados por API-Football (Fase 1) con datos de FBref (PSxG real, stats de progresión/defensa) y Understat (xG por disparo como fallback). Esto convierte M4 de fijo 0.32 a real (1.16–1.76) y rellena campos de `PlayerStats` que API-Football no provee. Sigue la misma arquitectura hexagonal de Fase 1 con providers + use cases de enriquecimiento + Celery tasks.

---

## Decisiones

| Decisión | Valor |
|----------|-------|
| HTTP client | `httpx` (ya agregado en Fase 1), modo async |
| Rate limiting FBref | 4s entre requests (FBref bloquea scraping agresivo) |
| Rate limiting Understat | 2s entre requests |
| Name matching | Fuzzy Jaccard ≥ 0.75, extraído del legacy `understat_merge_v2.py` |
| PSxG source primario | FBref (tabla Shooting, PSxG por temporada) |
| PSxG fallback | Understat xG por disparo como proxy |
| Parsing | `beautifulsoup4` + `lxml` para FBref, regex JSON para Understat |
| Ejecución | Siempre **después** de API-Football, nunca en paralelo |
| PSxG granularidad | MVP usa PSxG agregado (`psxg_total / goals`) — shot log individual por jugador se difiere a Fase 2.1 |
| Transaccionalidad | Enriquecimiento es idempotente — se puede re-ejecutar sin duplicar |
| Champions en Understat | No existe — solo se enriquece con FBref |

---

## Prerequisitos de Fase 1

Estos elementos son **bloqueantes** para Fase 2:

1. `IngestionRepositoryPort` implementado y funcional
2. `player_events` y `player_stats` populados por API-Football
3. Players en BD con `external_id` y `name`
4. Fixtures en BD con `external_id`
5. `SFAScoringService` operativo con `score_event()`

---

## Archivos a crear

| # | Archivo | Descripción |
|---|---------|-------------|
| 1 | `src/sfa/domain/enrichment_ports.py` | DTOs de enriquecimiento + ports para FBref/Understat/Enrichment repository |
| 2 | `src/sfa/domain/name_matching.py` | Servicio de fuzzy matching de nombres de jugadores (extraído del legacy) |
| 3 | `src/sfa/infrastructure/providers/fbref_scraper.py` | Scraper FBref: stats por liga + PSxG agregado |
| 4 | `src/sfa/infrastructure/providers/understat_scraper.py` | Scraper Understat: xG por disparo, stats por liga |
| 5 | `src/sfa/infrastructure/repositories/enrichment_repository.py` | Repositorio de lectura/actualización para enriquecimiento |
| 6 | `src/sfa/application/use_cases/enrich_with_fbref.py` | Use case: enriquecer stats + PSxG desde FBref |
| 7 | `src/sfa/application/use_cases/enrich_with_understat.py` | Use case: enriquecer PSxG fallback desde Understat |
| 8 | `src/sfa/application/use_cases/recalculate_scores.py` | Use case: recalcular SFA scores cuando PSxG cambia |
| 9 | `src/sfa/tasks/enrichment_tasks.py` | Celery tasks para enriquecimiento periódico |

## Archivos a modificar

| # | Archivo | Cambio |
|---|---------|--------|
| 1 | `src/sfa/infrastructure/models/players/models.py` | Agregar `fbref_id` (String, unique) y `understat_id` (Integer, unique) |
| 2 | `src/sfa/infrastructure/repositories/__init__.py` | Export `EnrichmentRepository` |
| 3 | `src/sfa/infrastructure/providers/__init__.py` | Export scrapers FBref y Understat |
| 4 | `src/sfa/celery_app.py` | Agregar schedule de enrichment al `beat_schedule` |
| 5 | `src/sfa/api/v1/admin.py` | Agregar endpoints para disparar enriquecimiento manual |
| 6 | `requirements/base.txt` | Agregar `beautifulsoup4>=4.12.0`, `lxml>=5.0.0` |

---

## Fase A — Domain layer

### Paso 1: DTOs y ports de enriquecimiento

**Archivo nuevo:** `src/sfa/domain/enrichment_ports.py`

#### DTOs raw (datos crudos scrapeados)

```python
@dataclass(frozen=True)
class FBrefPlayerStatsDTO:
    player_name: str
    team_name: str
    position: str           # "FW", "MF", "DF", "GK"
    minutes: int
    goals: int
    assists: int
    xg: float
    xa: float
    progressive_passes: int
    progressive_carries: int
    psxg_total: float | None    # PSxG total de la temporada (tabla Shooting)


@dataclass(frozen=True)
class UnderstatPlayerDTO:
    player_name: str
    team_name: str
    understat_id: str
    goals: int
    assists: int
    npg: int                # non-penalty goals
    npxg: float             # non-penalty xG
    xa: float
    shots: int
    key_passes: int
    xg_per_shot: float      # proxy de PSxG por disparo
    minutes: int
    games: int
```

#### Port: FBrefProviderPort

```python
@runtime_checkable
class FBrefProviderPort(Protocol):
    async def fetch_league_player_stats(
        self, league: str,
    ) -> list[FBrefPlayerStatsDTO]: ...
    # Incluye stats estándar (xG, xA, PrgP, PrgC) + PSxG de tabla Shooting
```

#### Port: UnderstatProviderPort

```python
@runtime_checkable
class UnderstatProviderPort(Protocol):
    async def fetch_league_players(
        self, league: str, season: int,
    ) -> list[UnderstatPlayerDTO]: ...
    # Incluye xG, xA, shots, key_passes, xg_per_shot derivado
```

#### Port: EnrichmentRepositoryPort

```python
@runtime_checkable
class EnrichmentRepositoryPort(Protocol):
    async def get_players_by_competition(
        self, competition_id: int, season: str,
    ) -> list[PlayerEnrichDTO]: ...
    # Retorna jugadores con su nombre y stats acumuladas para matching

    async def get_player_events_without_psxg(
        self, player_id: int, competition_id: int, season: str,
    ) -> list[PlayerEventRow]: ...
    # Eventos tipo goal/goal_penalty donde psxg IS NULL

    async def update_player_external_ids(
        self, player_id: int,
        fbref_id: str | None,
        understat_id: int | None,
    ) -> None: ...

    async def update_player_stats_from_fbref(
        self, player_id: int, season: str, stats: dict,
    ) -> None: ...
    # Actualiza progressive_passes, progressive_carries, pressures_success,
    # recoveries_opp_half, clearances_goal_line, xg, xa
    # Solo sobreescribe si el campo actual es 0

    async def update_event_psxg(
        self, event_id: int, psxg: float,
    ) -> None: ...

    async def update_event_scores(
        self, event_id: int, m4: float, pts: float,
    ) -> None: ...

    async def update_season_score(
        self, player_id: int, competition_id: int,
        season: str, total_pts: float,
        matches_played: int, breakdown: dict,
    ) -> None: ...
```

---

### Paso 2: Name matching service

**Archivo nuevo:** `src/sfa/domain/name_matching.py`

Extraer y adaptar la lógica probada del legacy `_archive/understat_merge_v2.py`. Sin dependencias de infraestructura (puro domain).

```python
import unicodedata
import re


def normalize(name: str) -> str:
    """NFD decomposition + strip diacritics + lowercase + remove punctuation."""
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.lower()
    name = re.sub(r"[.\-'`]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def get_tokens(name: str) -> set[str]:
    """Split en tokens, ignorar tokens de ≤ 2 caracteres (iniciales)."""
    return {t for t in normalize(name).split() if len(t) > 2}


def match_score(source_name: str, db_name: str) -> float:
    """
    Score estricto:
    - Jaccard sobre tokens
    - Bonus +0.3 si el token más largo (apellido principal) coincide exactamente
    - Penalización ×0.4 si el apellido principal NO está en el otro nombre
    """
    tu = get_tokens(source_name)
    td = get_tokens(db_name)

    if not tu or not td:
        return 0.0

    common = tu & td
    if not common:
        return 0.0

    score = len(common) / len(tu | td)

    longest_u = max(tu, key=len) if tu else ""
    longest_d = max(td, key=len) if td else ""
    if longest_u and longest_d and longest_u == longest_d:
        score = min(1.0, score + 0.3)
    elif longest_u and longest_u not in td:
        score *= 0.4

    return score


def find_best_match(
    source_name: str, db_index: dict[str, object],
) -> tuple[object | None, float]:
    """
    Retorna (objeto, score) o (None, 0.0) si:
    - No hay match con score >= 0.75
    - Hay 2+ candidatos con diferencia < 0.1 entre sí (ambigüedad)
    """
    candidates = [
        (obj, match_score(source_name, db_name), db_name)
        for db_name, obj in db_index.items()
        if match_score(source_name, db_name) >= 0.75
    ]

    if not candidates:
        return None, 0.0

    candidates.sort(key=lambda x: x[1], reverse=True)

    if len(candidates) >= 2 and (candidates[0][1] - candidates[1][1]) < 0.1:
        return None, 0.0  # Ambiguo — descartar

    return candidates[0][0], candidates[0][1]
```

---

## Fase B — Infrastructure: Scrapers

### Paso 3: FBref Scraper

**Archivo nuevo:** `src/sfa/infrastructure/providers/fbref_scraper.py`

Implementa `FBrefProviderPort`.

#### URLs por liga

```python
LEAGUE_STATS_URLS: dict[str, str] = {
    "La Liga":          "https://fbref.com/en/comps/12/stats/La-Liga-Stats",
    "Premier League":   "https://fbref.com/en/comps/9/stats/Premier-League-Stats",
    "Bundesliga":       "https://fbref.com/en/comps/20/stats/Bundesliga-Stats",
    "Serie A":          "https://fbref.com/en/comps/11/stats/Serie-A-Stats",
    "Ligue 1":          "https://fbref.com/en/comps/13/stats/Ligue-1-Stats",
    "Champions League": "https://fbref.com/en/comps/8/stats/Champions-League-Stats",
}

LEAGUE_SHOOTING_URLS: dict[str, str] = {
    "La Liga":          "https://fbref.com/en/comps/12/shooting/La-Liga-Stats",
    "Premier League":   "https://fbref.com/en/comps/9/shooting/Premier-League-Stats",
    "Bundesliga":       "https://fbref.com/en/comps/20/shooting/Bundesliga-Stats",
    "Serie A":          "https://fbref.com/en/comps/11/shooting/Serie-A-Stats",
    "Ligue 1":          "https://fbref.com/en/comps/13/shooting/Ligue-1-Stats",
    "Champions League": "https://fbref.com/en/comps/8/shooting/Champions-League-Stats",
}
```

#### Responsabilidades

1. **HTTP async con httpx** — User-Agent que simula browser real (igual que legacy)
2. **Rate limiting**: `asyncio.sleep(4.0)` entre cada request
3. **Parsing stats_standard**: BeautifulSoup → `soup.find("table", {"id": "stats_standard"})` → `pd.read_html()` → aplanar MultiIndex → renombrar columnas clave
4. **Parsing stats_shooting**: buscar tabla `id="stats_shooting"` → extraer columnas `Player`, `Gls` (goals), `PSxG` (post-shot xG total)
5. **Merge interno**: cruzar stats_standard + stats_shooting por nombre de jugador para obtener PSxG junto con las demás stats
6. **Calcular proxy PSxG**: `psxg_avg_per_goal = psxg_total / goals_total` si goals_total > 0, else None

#### Columnas a extraer de stats_standard

| Columna FBref | Campo DTO |
|---------------|-----------|
| `Player` | `player_name` |
| `Squad` | `team_name` |
| `Pos` | `position` |
| `Min` | `minutes` |
| `Gls` | `goals` |
| `Ast` | `assists` |
| `xG` | `xg` |
| `xAG` / `xA` | `xa` |
| `PrgP` | `progressive_passes` |
| `PrgC` | `progressive_carries` |

#### Columnas a extraer de stats_shooting

| Columna FBref | Uso |
|---------------|-----|
| `Player` | matching |
| `Gls` | goals_total (denominador para psxg_avg) |
| `PSxG` | psxg_total |

#### Estructura del provider

```python
class FBrefScraper(FBrefProviderPort):
    _HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",
        "Accept": "text/html,application/xhtml+xml,...",
        "Accept-Language": "es-ES,es;q=0.8,en-US;q=0.5",
    }
    _RATE_LIMIT_SECONDS = 4.0

    async def _get_html(self, url: str) -> str:
        """GET con httpx async + rate limiting + retry x3."""
        ...

    async def _parse_stats_table(
        self, html: str, table_id: str,
    ) -> pd.DataFrame:
        """Parsea tabla FBref por id, aplana MultiIndex, limpia headers repetidos."""
        ...

    async def fetch_league_player_stats(
        self, league: str,
    ) -> list[FBrefPlayerStatsDTO]:
        """
        1. Fetch stats_standard → DataFrame
        2. Fetch stats_shooting → DataFrame
        3. Merge por nombre (left join)
        4. Construir list[FBrefPlayerStatsDTO]
        """
        ...
```

---

### Paso 4: Understat Scraper

**Archivo nuevo:** `src/sfa/infrastructure/providers/understat_scraper.py`

Implementa `UnderstatProviderPort`.

#### Mapeo de ligas

```python
LEAGUE_MAP: dict[str, str] = {
    "La Liga":        "La_liga",
    "Premier League": "EPL",
    "Bundesliga":     "Bundesliga",
    "Serie A":        "Serie_A",
    "Ligue 1":        "Ligue_1",
    # Champions League: NO disponible en Understat
}
```

#### Parsing de JSON embebido

```python
def _extract_json_var(html: str, var_name: str) -> list:
    """Extrae variable JSON embebida en el HTML de Understat."""
    pattern = rf"var\s+{var_name}\s*=\s*JSON\.parse\('(.+?)'\)"
    match = re.search(pattern, html)
    if not match:
        return []
    raw = match.group(1).encode("utf-8").decode("unicode_escape")
    return json.loads(raw)
```

#### Responsabilidades

1. **fetch_league_players**: GET `/league/{league}/{season}` → extraer `playersData` → parsear → calcular `xg_per_shot = xG / shots` (con `shots.replace(0, 1)` para evitar división por cero)
2. **Rate limiting**: `asyncio.sleep(2.0)` entre requests
3. **Retry x3** con backoff: 15s, 30s (replicar lógica del legacy)
4. **Campos a extraer**:

| Campo Understat | Campo DTO |
|-----------------|-----------|
| `player_name` | `player_name` |
| `team_title` | `team_name` |
| `id` | `understat_id` |
| `goals` | `goals` |
| `assists` | `assists` |
| `npg` | `npg` |
| `npxG` | `npxg` |
| `xA` | `xa` |
| `shots` | `shots` |
| `key_passes` | `key_passes` |
| `time` | `minutes` |
| `games` | `games` |
| derivado | `xg_per_shot` |

---

## Fase C — Infrastructure: Enrichment Repository

### Paso 5: Enrichment Repository

**Archivo nuevo:** `src/sfa/infrastructure/repositories/enrichment_repository.py`

Implementa `EnrichmentRepositoryPort`.

#### Queries principales

```python
class EnrichmentRepository(EnrichmentRepositoryPort):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_players_by_competition(
        self, competition_id: int, season: str,
    ) -> list[PlayerEnrichDTO]:
        """
        SELECT p.id, p.name, p.external_id, p.fbref_id, p.understat_id
        FROM players p
        JOIN teams t ON t.id = p.team_id
        JOIN sfa_season_scores s ON s.player_id = p.id
        WHERE t.competition_id = :competition_id
          AND s.competition_id = :competition_id
          AND s.season = :season
        """

    async def get_player_events_without_psxg(
        self, player_id: int, competition_id: int, season: str,
    ) -> list[PlayerEventRow]:
        """
        SELECT pe.id, pe.event_type, pe.minute, pe.m1, pe.m2, pe.m3, pe.mvisit
        FROM player_events pe
        JOIN fixtures f ON f.id = pe.fixture_id
        WHERE pe.player_id = :player_id
          AND f.competition_id = :competition_id
          AND f.season = :season
          AND pe.psxg IS NULL
          AND pe.event_type IN ('goal', 'goal_penalty')
        """

    async def update_player_stats_from_fbref(
        self, player_id: int, season: str, stats: dict,
    ) -> None:
        """
        UPDATE player_stats
        SET
          progressive_passes  = CASE WHEN progressive_passes  = 0 THEN :val ELSE progressive_passes  END,
          progressive_carries = CASE WHEN progressive_carries = 0 THEN :val ELSE progressive_carries END,
          xg                  = CASE WHEN xg = 0 THEN :val ELSE xg END,
          xa                  = CASE WHEN xa = 0 THEN :val ELSE xa END,
          ...
        WHERE player_id = :player_id AND season = :season
        """
        # Solo sobreescribe campos que actualmente son 0 (no borrar datos previos)

    async def update_event_psxg(self, event_id: int, psxg: float) -> None:
        """UPDATE player_events SET psxg = :psxg WHERE id = :event_id"""

    async def update_event_scores(
        self, event_id: int, m4: float, pts: float,
    ) -> None:
        """UPDATE player_events SET m4 = :m4, pts = :pts WHERE id = :event_id"""

    async def update_season_score(
        self, player_id: int, competition_id: int,
        season: str, total_pts: float,
        matches_played: int, breakdown: dict,
    ) -> None:
        """
        UPDATE sfa_season_scores
        SET total_pts = :total_pts, matches_played = :matches_played,
            breakdown = :breakdown, last_updated = now()
        WHERE player_id = :player_id
          AND competition_id = :competition_id
          AND season = :season
        """
```

---

## Fase D — Application: Use Cases

### Paso 6: EnrichWithFBrefUseCase

**Archivo nuevo:** `src/sfa/application/use_cases/enrich_with_fbref.py`

#### Dataclasses

```python
@dataclass(frozen=True)
class EnrichmentResult:
    competition: str
    players_matched: int
    players_skipped: int
    events_enriched: int    # events con PSxG actualizado
    stats_enriched: int     # player_stats con campos FBref actualizados
    status: str             # "completed" | "failed"
    error: str | None
```

#### Constructor

```python
class EnrichWithFBrefUseCase:
    def __init__(
        self,
        fbref: FBrefProviderPort,
        repo: EnrichmentRepositoryPort,
        scoring: SFAScoringService,
    ) -> None:
        self._fbref = fbref
        self._repo = repo
        self._scoring = scoring
```

#### Flujo execute(competition_name: str, competition_id: int, season: str)

**6.1 — Obtener stats de FBref**
```
1. await fbref.fetch_league_player_stats(competition_name)
   → list[FBrefPlayerStatsDTO] con xG, xA, PrgP, PrgC, PSxG total, goals total
```

**6.2 — Construir DB index**
```
2. await repo.get_players_by_competition(competition_id, season)
   → db_index: {player.name: PlayerEnrichDTO}
```

**6.3 — Match y enriquecimiento**
```
3. Por cada FBrefPlayerStatsDTO:
   a. find_best_match(dto.player_name, db_index) → (player, score)
   b. Si score < 0.75 → players_skipped += 1, log warning, continue
   c. Si ambiguo → players_skipped += 1, log warning, continue
   d. players_matched += 1

   e. Guardar fbref_id si el jugador no lo tiene aún
      → await repo.update_player_external_ids(player.id, fbref_id=dto.player_name, ...)

   f. Enriquecer player_stats:
      stats_to_update = {
          "xg": dto.xg,
          "xa": dto.xa,
          "progressive_passes": dto.progressive_passes,
          "progressive_carries": dto.progressive_carries,
      }
      await repo.update_player_stats_from_fbref(player.id, season, stats_to_update)
      stats_enriched += 1

   g. Enriquecer PSxG en events:
      - Si dto.psxg_total is None o dto.goals == 0 → skip
      - psxg_proxy = dto.psxg_total / dto.goals
      - events = await repo.get_player_events_without_psxg(player.id, competition_id, season)
      - Por cada event:
          await repo.update_event_psxg(event.id, psxg_proxy)
          events_enriched += 1
```

**6.4 — Resultado**
```
4. return EnrichmentResult(
       competition=competition_name,
       players_matched=players_matched,
       players_skipped=players_skipped,
       events_enriched=events_enriched,
       stats_enriched=stats_enriched,
       status="completed",
       error=None,
   )
```

---

### Paso 7: EnrichWithUnderstatUseCase

**Archivo nuevo:** `src/sfa/application/use_cases/enrich_with_understat.py`

#### Constructor

```python
class EnrichWithUnderstatUseCase:
    def __init__(
        self,
        understat: UnderstatProviderPort,
        repo: EnrichmentRepositoryPort,
    ) -> None:
        self._understat = understat
        self._repo = repo
```

#### Flujo execute(competition_name: str, competition_id: int, season: str, season_int: int)

**7.1 — Validar**
```
1. Si competition_name == "Champions League" → return early
   (Champions no existe en Understat)
```

**7.2 — Obtener datos de Understat**
```
2. await understat.fetch_league_players(competition_name, season_int)
   → list[UnderstatPlayerDTO]
3. Filtrar: solo jugadores con minutes >= 90
```

**7.3 — Construir DB index**
```
4. await repo.get_players_by_competition(competition_id, season)
   → db_index
```

**7.4 — Match y enriquecimiento PSxG fallback**
```
5. Por cada UnderstatPlayerDTO:
   a. find_best_match(dto.player_name, db_index) → (player, score)
   b. Si no match → skip

   c. Guardar understat_id:
      await repo.update_player_external_ids(player.id, understat_id=int(dto.understat_id))

   d. Solo enriquecer PSxG donde FBref NO lo cubrió (psxg IS NULL):
      events = await repo.get_player_events_without_psxg(player.id, competition_id, season)
      Si events vacía → FBref ya cubrió → skip
      Por cada event:
          await repo.update_event_psxg(event.id, dto.xg_per_shot)
          events_enriched += 1
```

---

### Paso 8: RecalculateScoresUseCase

**Archivo nuevo:** `src/sfa/application/use_cases/recalculate_scores.py`

#### Propósito

Cuando el PSxG de eventos cambia (de NULL/0.32 a un valor real), recalcular M4, pts del evento, y total del season_score.

#### Constructor

```python
class RecalculateScoresUseCase:
    def __init__(
        self,
        repo: EnrichmentRepositoryPort,
        scoring: SFAScoringService,
    ) -> None:
        self._repo = repo
        self._scoring = scoring
```

#### Flujo execute(competition_id: int, season: str)

```
1. Obtener todos los player_events donde psxg IS NOT NULL
   (estos son los que recibieron enriquecimiento)

2. Por cada evento:
   a. Recalcular M4 real:
      m4 = M4ShotDifficulty(psxg=event.psxg).value

   b. Recalcular CombinedMultiplier con M1/M2/M3 existentes + nuevo M4 + Mvisit existente:
      combined = max(0.3, min(4.0, event.m1 * event.m2 * event.m3 * m4 * event.mvisit))

   c. Recalcular base_pts desde el event_type y position del jugador:
      group = position_to_group(player.position)
      base_pts = BASE_POINTS_TABLE[group][action_type]
      new_pts = base_pts * combined

   d. Si new_pts != event.pts → actualizar:
      await repo.update_event_scores(event.id, m4=m4, pts=new_pts)
      events_updated += 1

3. Por cada jugador afectado:
   a. Obtener TODOS sus eventos de la competition/season (con psxg y sin psxg)
   b. Sumar pts de todos los eventos → new_total_pts
   c. Reconstruir breakdown JSONB por categoría de evento
   d. await repo.update_season_score(player_id, competition_id, season, new_total_pts, ...)
   scores_updated += 1

4. return RecalculationResult(events_updated, scores_updated)
```

---

## Fase E — Celery Tasks + Schedule

### Paso 9: Enrichment Tasks

**Archivo nuevo:** `src/sfa/tasks/enrichment_tasks.py`

```python
import asyncio
from sfa.celery_app import celery_app


@celery_app.task(bind=True, max_retries=2, default_retry_delay=600)
def enrich_fbref_task(self, competition_name: str, competition_id: int, season: str):
    """Enriquecimiento FBref para una liga. Luego recalcula scores."""
    try:
        asyncio.run(_run_enrich_fbref(competition_name, competition_id, season))
        asyncio.run(_run_recalculate(competition_id, season))
    except Exception as exc:
        self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=600)
def enrich_understat_task(
    self, competition_name: str, competition_id: int,
    season: str, season_int: int,
):
    """Enriquecimiento Understat para una liga (fallback PSxG). Luego recalcula."""
    try:
        asyncio.run(_run_enrich_understat(competition_name, competition_id, season, season_int))
        asyncio.run(_run_recalculate(competition_id, season))
    except Exception as exc:
        self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=1)
def enrich_all_task(self, season: str, season_int: int):
    """Enriquecimiento completo secuencial: por cada liga → FBref → Understat → Recalculate."""
    try:
        asyncio.run(_run_enrich_all(season, season_int))
    except Exception as exc:
        self.retry(exc=exc)
```

Los helpers `_run_enrich_fbref`, `_run_enrich_understat`, `_run_enrich_all` crean las dependencias
async igual que en Fase 1 (`AsyncSessionLocal` + providers + repos + use cases).

### Paso 10: Celery Beat schedule

**Archivo:** `src/sfa/celery_app.py`

Agregar al `beat_schedule` existente:

```python
"enrich-all-every-12h": {
    "task": "sfa.tasks.enrichment_tasks.enrich_all_task",
    "schedule": crontab(hour="2,14"),    # 2am y 2pm UTC
    "args": ("2024-25", 2024),
},
```

> El enriquecimiento corre en las horas 2 y 14 UTC, desfasado del ingestion principal
> (que corre a las 0, 8, 16 UTC) para no solapar requests.

Y agregar al `autodiscover_tasks`:

```python
celery_app.autodiscover_tasks(["sfa.tasks"])    # ya detecta ingestion_tasks + enrichment_tasks
```

### Paso 11: Endpoints admin

**Archivo:** `src/sfa/api/v1/admin.py`

Agregar al router existente:

```python
@router.post("/enrich-fbref/{competition_id}")
async def trigger_enrich_fbref(
    competition_id: int,
    competition_name: str = Query(...),
    season: str = Query(default="2024-25"),
):
    """Dispara enriquecimiento FBref + recálculo para una liga."""
    task = enrich_fbref_task.delay(competition_name, competition_id, season)
    return {"task_id": task.id, "competition_id": competition_id}


@router.post("/enrich-understat/{competition_id}")
async def trigger_enrich_understat(
    competition_id: int,
    competition_name: str = Query(...),
    season: str = Query(default="2024-25"),
    season_int: int = Query(default=2024),
):
    """Dispara enriquecimiento Understat + recálculo para una liga."""
    task = enrich_understat_task.delay(competition_name, competition_id, season, season_int)
    return {"task_id": task.id, "competition_id": competition_id}


@router.post("/enrich-all")
async def trigger_enrich_all(
    season: str = Query(default="2024-25"),
    season_int: int = Query(default=2024),
):
    """Dispara enriquecimiento completo de todas las ligas."""
    task = enrich_all_task.delay(season, season_int)
    return {"task_id": task.id, "season": season}


@router.post("/recalculate/{competition_id}")
async def trigger_recalculate(
    competition_id: int,
    season: str = Query(default="2024-25"),
):
    """Recalcula scores de una liga (útil si cambiaron parámetros del motor)."""
    task = recalculate_task.delay(competition_id, season)
    return {"task_id": task.id, "competition_id": competition_id}
```

---

## Fase F — Modelo y dependencias

### Paso 12: Player model — external IDs adicionales

**Archivo:** `src/sfa/infrastructure/models/players/models.py`

Agregar campos:

```python
fbref_id: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True)
understat_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
```

Documentar para migración manual:

```sql
ALTER TABLE players ADD COLUMN fbref_id VARCHAR(50) UNIQUE;
ALTER TABLE players ADD COLUMN understat_id INTEGER UNIQUE;
```

### Paso 13: Dependencias

**Archivo:** `requirements/base.txt`

Agregar:

```
beautifulsoup4>=4.12.0
lxml>=5.0.0
```

---

## Verificación

| # | Qué verificar | Cómo |
|---|---------------|------|
| 1 | Tests de Fase 1 siguen pasando | `pytest` |
| 2 | `name_matching` produce match correcto | Test unitario: `find_best_match("Vinícius Jr", {"Vinícius Júnior": player})` → score ≥ 0.75 |
| 3 | `name_matching` descarta ambiguos | Test unitario: dos jugadores con apellido similar → `(None, 0.0)` |
| 4 | FBref scraper parsea tabla de stats | Test unitario: HTML fixture estático → DTOs con xG, PrgP correctos |
| 5 | FBref scraper parsea tabla shooting | Test unitario: HTML fixture → PSxG total extraído correctamente |
| 6 | Understat scraper extrae JSON embebido | Test unitario: HTML fixture → DTOs con xG, xg_per_shot calculado |
| 7 | Enriquecimiento popula PSxG | Test integración: events con psxg=NULL → ejecutar enrich → psxg != NULL |
| 8 | Recálculo cambia pts cuando PSxG cambia | Test unitario: psxg=None → M4=1.0, psxg=0.05 → M4=1.76, pts mayor |
| 9 | Recálculo actualiza season_score | Test integración: verificar total_pts cambia después del recálculo |
| 10 | Idempotencia: 2 ejecuciones = mismo resultado | Test integración: ejecutar enrich 2 veces → mismos valores en BD |
| 11 | Rate limiting FBref | Test manual: logs muestran ≥4s entre requests |
| 12 | Pipeline completo | Manual: `POST /admin/enrich-fbref/140` → PSxG en BD → pts recalculados |
| 13 | Beat schedule activo | `docker compose logs celery_beat` → `enrich-all-every-12h` aparece en schedule |

---

## Excluido de esta fase (Fase 2.1+)

- PSxG por disparo individual (FBref shot log por jugador — requiere N requests extra)
- Detección automática de EXT/LAT desde FBref position data
- Fotos de jugadores (Wikipedia) — Fase 3
- Backfill histórico de temporadas anteriores — Fase 3
- Scraping con Playwright/Selenium (plan B si FBref bloquea httpx)
- Enrichment de Champions League con Understat (no disponible en esa fuente)
