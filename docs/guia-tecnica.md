# Guia Tecnica — SFA Backend

> Documento de referencia para entender, ejecutar y extender el sistema.
> Cubre: arranque local, endpoints, tareas Celery, flujo completo de datos,
> estado actual del sistema y comparacion con el codigo legacy.

---

## Tabla de contenidos

1. [Como levantar la app](#1-como-levantar-la-app)
2. [Flujo completo de datos](#2-flujo-completo-de-datos)
3. [Endpoints de Admin — Ingesta y Enriquecimiento](#3-endpoints-de-admin--ingesta-y-enriquecimiento)
4. [Endpoints de Consulta](#4-endpoints-de-consulta)
5. [Tareas Celery](#5-tareas-celery)
6. [Estado actual del sistema](#6-estado-actual-del-sistema)
7. [Legacy vs Estado actual](#7-legacy-vs-estado-actual)

---

## 1. Como levantar la app

### Archivos .http

Todos los ejemplos de esta guia se muestran como `curl`. Existe ademas un archivo `.http`
por recurso en `http/` — compatibles con VS Code REST Client y JetBrains HTTP Client:

| Archivo | Endpoints cubiertos |
|---|---|
| `http/ranking.http` | `GET /ranking` con todos los filtros |
| `http/players.http` | `GET /players/{id}`, `/events`, `/fixtures` |
| `http/competitions.http` | `GET /competitions`, standings |
| `http/compare.http` | `GET /compare` |
| `http/status.http` | `GET /status`, `GET /health` |
| `http/admin.http` | Todos los `POST /admin/*` (ingest, enrich, recalculate) |

Para usarlos en VS Code: instalar la extension **REST Client** (`humao.rest-client`),
abrir el archivo `.http` y hacer click en `Send Request` sobre cualquier bloque.

---

### Con Docker (recomendado)

**Pre-requisitos:** Docker Desktop instalado y corriendo.

```bash
# 1. Copiar variables de entorno
cp .env.example .env

# 2. Editar .env — obligatorio completar estos dos campos:
#    SECRET_KEY=cualquier-string-largo
#    API_FOOTBALL_KEY=tu-key-de-api-sports.io

# 3. Levantar todos los servicios
docker compose -f docker-compose-development.yml up --build

# 4. En otra terminal, aplicar migraciones de base de datos
docker compose -f docker-compose-development.yml exec api alembic upgrade head
```

Servicios que se levantan:

| Servicio | Puerto | Descripcion |
|---|---|---|
| `api` | 8000 | FastAPI — API REST principal |
| `db` | 5432 | PostgreSQL 16 |
| `redis` | 6379 | Redis 7 (broker de Celery) |
| `celery_worker` | — | Ejecuta tareas en background |
| `celery_beat` | — | Scheduler que dispara tareas periodicas |

Verificar que todo funciona:

```bash
curl http://localhost:8000/api/v1/health
# {"status":"ok","database":"connected","redis":"connected","version":"0.1.0","env":"development"}
```

### Sin Docker (desarrollo local)

```bash
# 1. Crear entorno virtual e instalar dependencias
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 2. Tener PostgreSQL y Redis corriendo localmente (o via Docker individual)
# Los defaults en .env apuntan a localhost

# 3. Migraciones
alembic upgrade head

# 4. Levantar API
uvicorn sfa.main:app --reload --host 0.0.0.0 --port 8000

# 5. Levantar worker Celery (en otra terminal)
celery -A sfa.celery_app worker --loglevel=info

# 6. Levantar scheduler Celery Beat (en otra terminal)
celery -A sfa.celery_app beat --loglevel=info
```

---

## 2. Flujo completo de datos

### Vision general

```
API-Football (fuente)
    |
    v
POST /api/v1/admin/ingest/{league_id}
    |
    v
Celery Worker
    |
    v
IngestCompetitionUseCase
    |-- APIFootballProvider (fetch standings, fixtures, events, players)
    |-- IngestionRepository  (upsert en PostgreSQL)
    |-- SFAScoringService    (calcula SFA pts por evento)
    |
    v
Base de datos: competitions, teams, players, fixtures,
               player_stats, player_events, sfa_season_scores
    |
    v
POST /api/v1/admin/enrich-fbref/{competition_id}
    |
    v
EnrichWithFBrefUseCase
    |-- FBrefScraper (xG, xA, pases progresivos, conducciones...)
    |-- EnrichmentRepository (actualiza player_stats)
    |
    v
POST /api/v1/admin/enrich-understat/{competition_id}
    |
    v
EnrichWithUnderstatUseCase
    |-- UnderstatScraper (PSxG partido a partido)
    |-- EnrichmentRepository (actualiza player_events con PSxG real)
    |
    v
RecalculateScoresUseCase
    |-- Recalcula M4 con PSxG real (antes era 0.32 por defecto)
    |-- Actualiza sfa_season_scores
    |
    v
GET /api/v1/ranking, /api/v1/players, etc.
```

### Capas de arquitectura

Cada request sigue exactamente este camino — sin atajos:

```
HTTP Request
    |
    v
Router (api/v1/*.py)
    Valida parametros via Pydantic, llama al use case
    |
    v
Use Case (application/use_cases/*.py)
    Orquesta la logica de negocio usando Protocols del dominio
    NO importa SQLAlchemy ni ningun detalle de infraestructura
    |
    v
Domain (domain/)
    Protocols (interfaces), DTOs frozen, logica de scoring pura
    |
    v
Repository / Provider (infrastructure/)
    Unica capa que toca la DB o APIs externas
    Siempre retorna DTOs del dominio, nunca ORM models
    |
    v
PostgreSQL / Redis / API-Football / FBref / Understat
```

### Como leer el codigo de un use case

Ejemplo: `GetRankingUseCase` en `application/use_cases/get_ranking.py`

```python
class GetRankingUseCase:
    def __init__(self, score_repo: SFAScoreRepositoryProtocol) -> None:
        # Recibe el repositorio por inyeccion de dependencias
        # No sabe si es PostgreSQL, SQLite o un Fake de tests
        self._score_repo = score_repo

    async def execute(self, season, position, competition_id, limit) -> RankingResult:
        # 1. Si no viene season, busca la mas reciente en DB
        if season is None:
            season = await self._score_repo.latest_season()
        # 2. Delega la query al repositorio
        ranking = await self._score_repo.get_ranking(season, position, competition_id, limit)
        # 3. Retorna un DTO frozen (no un ORM model)
        return RankingResult(season=season, total=total, ranking=ranking)
```

El wiring (conectar el use case con el repositorio real) ocurre en `core/dependencies.py`:

```python
async def get_ranking_use_case(
    score_repo: Annotated[SFAScoreRepository, Depends(get_sfa_score_repository)],
) -> GetRankingUseCase:
    return GetRankingUseCase(score_repo)
```

---

## 3. Endpoints de Admin — Ingesta y Enriquecimiento

Estos son los endpoints que traen datos del exterior. Son el punto de entrada
de todo el sistema. Sin correrlos, la base de datos esta vacia.

> Todos los ejemplos disponibles en [`http/admin.http`](../http/admin.http) —
> abrirlo con VS Code REST Client para ejecutar sin escribir curl.

---

### POST /api/v1/admin/ingest/{league_id}

**Por que existe:** Trae datos completos de una liga desde API-Football: clasificacion,
partidos, eventos partido a partido (goles, asistencias) y estadisticas de jugadores.
Calcula los SFA pts de cada evento en tiempo real durante la ingesta.

**Para que:** Poblar la DB con jugadores, fixtures y scores. Es el paso 1 obligatorio
antes de poder usar cualquier endpoint de consulta.

**Parametros:**

| Parametro | Tipo | Default | Descripcion |
|---|---|---|---|
| `league_id` | path | — | ID de la liga en API-Football (ver tabla abajo) |
| `season` | query | 2024 | Temporada a ingestar |

**IDs de ligas disponibles:**

| ID | Liga |
|---|---|
| 140 | La Liga |
| 39 | Premier League |
| 78 | Bundesliga |
| 135 | Serie A |
| 61 | Ligue 1 |
| 2 | Champions League |

**Ejemplo:**

```bash
# Ingestar La Liga temporada 2024
curl -X POST "http://localhost:8000/api/v1/admin/ingest/140?season=2024"
```

**Respuesta:**

```json
{
  "task_id": "abc123-...",
  "league_id": 140,
  "season": 2024
}
```

El `task_id` es el ID de la tarea Celery. La ingesta corre en background.
Para ver el resultado, revisar los logs del `celery_worker`.

**Que hace internamente (fases):**

1. Descarga la clasificacion actual de la liga (standings)
2. Para cada equipo del top N (6 equipos en ligas, 24 en Champions):
   - Descarga todos sus partidos de la temporada
   - Por cada partido: descarga eventos (goles, asistencias) y stats de jugadores
3. Por cada jugador con 20+ minutos en el partido:
   - Calcula M1 (dificultad rival) segun posicion en tabla
   - Calcula M3 (minuto/marcador) para cada gol o asistencia
   - Guarda el evento con todos los multiplicadores y el score final
4. Al terminar: guarda el score acumulado de temporada por jugador
5. Registra un log de ingestion (completado/fallido)

**Estado anterior en legacy:** En el legacy (`_archive/backend/pipeline.py`) no existia
este endpoint. El pipeline corria como script Python directamente (`python pipeline.py`)
o se disparaba desde un scheduler interno de APScheduler embebido en el proceso FastAPI.
No habia cola de tareas, no habia retries automaticos y si fallaba en una liga, toda
la ejecucion se detenia.

**Que aporta al proyecto:** Es la puerta de entrada de datos reales. Sin este paso
el sistema no tiene nada que mostrar. Despues de correrlo por primera vez, el ranking
y los perfiles de jugadores ya estan disponibles.

---

### POST /api/v1/admin/ingest-all

**Por que existe:** Misma logica que el anterior pero para todas las ligas configuradas
en una sola llamada. Util para la primera carga o para sincronizaciones manuales.

**Parametros:**

| Parametro | Tipo | Default | Descripcion |
|---|---|---|---|
| `season` | query | 2024 | Temporada a ingestar |

**Ejemplo:**

```bash
curl -X POST "http://localhost:8000/api/v1/admin/ingest-all?season=2024"
```

**Respuesta:**

```json
{"task_id": "def456-...", "season": 2024}
```

**Advertencia:** Consume muchas requests de API-Football. Con el plan gratuito
(100 req/dia) no podras completar todas las ligas en un dia.

---

### POST /api/v1/admin/enrich-fbref/{competition_id}

**Por que existe:** API-Football no tiene estadisticas avanzadas (xG, xA, pases
progresivos, conducciones progresivas, presiones). FBref si las tiene. Este endpoint
scrapea FBref y enriquece los datos ya ingresados.

**Para que:** Mejorar la precision del scoring. Sin enriquecimiento, acciones como
xG_no_goal, progressive_passes o pressures_success quedan en 0. El ranking basico
funciona, pero el score es menos preciso.

**Parametros:**

| Parametro | Tipo | Default | Descripcion |
|---|---|---|---|
| `competition_id` | path | — | ID interno de la competicion (de la DB, no de API-Football) |
| `competition_name` | query | obligatorio | Nombre exacto ("La Liga", "Premier League"...) |
| `season` | query | "2024" | Temporada como string |

**Ejemplo:**

```bash
curl -X POST "http://localhost:8000/api/v1/admin/enrich-fbref/1?competition_name=La+Liga&season=2024"
```

**Nota:** El `competition_id` es el ID de tu tabla `competitions` en PostgreSQL,
no el ID de API-Football. Consultalo con `GET /api/v1/competitions`.

**Despues de este endpoint:** Recalcula automaticamente los SFA scores con los
nuevos datos.

**Estado anterior en legacy:** El scraper de FBref existia (`_archive/backend/ingest/fbref_ingest.py`)
pero se ejecutaba en el mismo proceso sincrono del pipeline. Si FBref bloqueaba la IP
o cambiaba su HTML, el pipeline completo fallaba sin retries.

---

### POST /api/v1/admin/enrich-understat/{competition_id}

**Por que existe:** Understat tiene el PSxG (Post-Shot Expected Goals) partido a
partido por jugador. PSxG es el dato que alimenta M4 (dificultad del disparo). Sin el,
M4 usa el valor por defecto de 0.32, lo que hace que todos los goles tengan el mismo
peso en M4. Con PSxG real, un gol desde angulo imposible vale mas que un tap-in.

**Para que:** Afinar M4. Impacta directamente en el score de cada gol. Champions League
no tiene datos en Understat, se salta automaticamente.

**Parametros:**

| Parametro | Tipo | Default | Descripcion |
|---|---|---|---|
| `competition_id` | path | — | ID interno de la competicion |
| `competition_name` | query | obligatorio | Nombre de la liga |
| `season` | query | "2024" | Temporada como string |
| `season_int` | query | 2024 | Temporada como entero (para Understat) |

**Ejemplo:**

```bash
curl -X POST "http://localhost:8000/api/v1/admin/enrich-understat/1?competition_name=La+Liga&season=2024&season_int=2024"
```

**Despues de este endpoint:** Recalcula automaticamente los scores con PSxG real.

---

### POST /api/v1/admin/enrich-all

**Por que existe:** Atajo que corre FBref + Understat + Recalculo para todas las
ligas en secuencia. Es el equivalente del "refresh completo" de datos de enrichment.

**Ejemplo:**

```bash
curl -X POST "http://localhost:8000/api/v1/admin/enrich-all?season=2024&season_int=2024"
```

---

### POST /api/v1/admin/recalculate/{competition_id}

**Por que existe:** Si cambias los parametros del scoring (por ejemplo, modificas
BASE_POINTS_TABLE en `domain/scoring/services.py`) necesitas recalcular todos los
scores historicos sin volver a llamar a las APIs externas.

**Ejemplo:**

```bash
curl -X POST "http://localhost:8000/api/v1/admin/recalculate/1?season=2024"
```

**Resultado esperado:** Todos los `sfa_season_scores` de esa liga/temporada se
recalculan con los nuevos parametros. El ranking refleja los cambios inmediatamente.

---

### Orden recomendado para la primera carga

```
1. POST /admin/ingest/140          # La Liga
2. POST /admin/ingest/39           # Premier League
   ... (una liga por dia con plan gratuito)

3. GET /competitions               # Anotar el competition_id de cada liga

4. POST /admin/enrich-fbref/1?competition_name=La+Liga&season=2024
5. POST /admin/enrich-understat/1?competition_name=La+Liga&season=2024&season_int=2024

6. GET /ranking                    # Ya tiene datos con scoring completo
```

---

## 4. Endpoints de Consulta

Estos endpoints solo leen de la DB. No llaman a ninguna API externa.
Requieren que ya se haya ejecutado al menos una ingesta.

> Archivos `.http` disponibles: [`http/ranking.http`](../http/ranking.http) ·
> [`http/players.http`](../http/players.http) ·
> [`http/competitions.http`](../http/competitions.http) ·
> [`http/compare.http`](../http/compare.http) ·
> [`http/status.http`](../http/status.http)

---

### GET /api/v1/health

**Para que:** Verificar que la infraestructura esta levantada correctamente.
Comprueba conexion a PostgreSQL y a Redis.

**Parametros:** Ninguno.

**Ejemplo:**

```bash
curl http://localhost:8000/api/v1/health
```

**Respuesta exitosa:**

```json
{
  "status": "ok",
  "database": "connected",
  "redis": "connected",
  "version": "0.1.0",
  "env": "development"
}
```

**Errores posibles:**

| Valor | Causa |
|---|---|
| `"database": "error"` | PostgreSQL no disponible o credenciales incorrectas |
| `"redis": "error"` | Redis no disponible |

---

### GET /api/v1/status

**Para que:** Ver el estado de los datos del sistema — cuantos jugadores, partidos,
scores y eventos hay en la DB, y cual es la temporada mas reciente.

**Parametros:** Ninguno.

**Ejemplo:**

```bash
curl http://localhost:8000/api/v1/status
```

**Respuesta:**

```json
{
  "status": "ok",
  "season": "2024",
  "players": 342,
  "scores": 510,
  "competitions": 6,
  "events": 1850,
  "api_version": "0.1.0"
}
```

Si `players` es 0, aun no se ha corrido ninguna ingesta.

---

### GET /api/v1/ranking

**Para que:** El endpoint principal del sistema. Devuelve el ranking de jugadores
ordenado por SFA pts de mayor a menor.

**Parametros:**

| Parametro | Tipo | Default | Descripcion |
|---|---|---|---|
| `season` | query | temporada mas reciente | Ej: "2024" |
| `position` | query | null (todas) | DEL, EXT, MC, DC, LAT, GK |
| `competition_id` | query | null (todas) | ID interno de la competicion |
| `limit` | query | 50 | Cantidad de resultados (max 200) |

**Ejemplos:**

```bash
# Top 50 global
curl "http://localhost:8000/api/v1/ranking"

# Solo mediocampistas de La Liga
curl "http://localhost:8000/api/v1/ranking?position=MC&competition_id=1"

# Top 10
curl "http://localhost:8000/api/v1/ranking?limit=10"
```

**Respuesta:**

```json
{
  "season": "2024",
  "total": 342,
  "ranking": [
    {
      "rank": 1,
      "id": 47,
      "name": "Erling Haaland",
      "team": "Manchester City",
      "position": "DEL",
      "competition": "Premier League",
      "sfa_pts": 12450.75,
      "matches": 28,
      "photo_url": "https://..."
    }
  ]
}
```

**Diferencia con legacy:** En el legacy, el ranking se calculaba en el endpoint mismo
con N queries N+1 (una query por jugador para sumar sus scores). En el sistema actual,
hay una sola query optimizada que hace JOIN de scores + players + teams.

---

### GET /api/v1/players/{player_id}

**Para que:** Perfil completo de un jugador: score total, partidos, ranking global,
desglose de puntos por tipo de accion y lista de competiciones en las que participo.

**Parametros:**

| Parametro | Tipo | Default | Descripcion |
|---|---|---|---|
| `player_id` | path | — | ID interno del jugador (de la DB) |
| `season` | query | temporada mas reciente | Ej: "2024" |

**Ejemplo:**

```bash
curl "http://localhost:8000/api/v1/players/47"
```

**Respuesta:**

```json
{
  "id": 47,
  "name": "Erling Haaland",
  "team": "Manchester City",
  "position": "DEL",
  "competition": "Premier League",
  "sfa_pts": 12450.75,
  "matches": 28,
  "photo_url": "https://...",
  "global_rank": 1,
  "season": "2024",
  "breakdown": {
    "goal": {"count": 22, "pts": 9800.50},
    "assist": {"count": 5, "pts": 1850.25},
    "stats": {"count": 0, "pts": 800.00}
  },
  "competitions": ["Premier League"]
}
```

**Errores posibles:**

```json
// 404 si el player_id no existe
{"detail": "Player not found"}
```

---

### GET /api/v1/players/{player_id}/events

**Para que:** Ver cada evento individual que genero puntos para el jugador.
Muestra el detalle completo del calculo SFA: el minuto, el marcador antes del evento,
y cada multiplicador (M1, M2, M3, M4, Mvisit) con su valor.

**Parametros:**

| Parametro | Tipo | Default | Descripcion |
|---|---|---|---|
| `player_id` | path | — | ID del jugador |
| `season` | query | null (todas) | Filtrar por temporada |
| `competition_id` | query | null (todas) | Filtrar por competicion |

**Ejemplo:**

```bash
curl "http://localhost:8000/api/v1/players/47/events"
```

**Respuesta:**

```json
[
  {
    "id": 1234,
    "competition": "Premier League",
    "stage": "Regular Season",
    "fixture_id": 891,
    "home_team": "Manchester City",
    "away_team": "Arsenal",
    "played_at": "2024-10-05T15:00:00",
    "minute": 87,
    "event_type": "goal",
    "score_before": "1:1",
    "score_diff": 0,
    "m1": 1.15,
    "m2": 1.0,
    "m3": 2.5,
    "m4": 1.56,
    "mvisit": 1.0,
    "pts": 2808.00
  }
]
```

**Como leer este response:** Este gol vale 2808 pts porque:
- Base: 500 pts (DEL, gol)
- M1 = 1.15 (rival bien posicionado)
- M2 = 1.0 (liga regular)
- M3 = 2.5 (minuto 87, empate — maximo multiplicador)
- M4 = 1.56 (PSxG bajo, disparo dificil)
- Mvisit = 1.0 (partido de local)
- Total = 500 × CLAMP(1.15 × 1.0 × 2.5 × 1.56 × 1.0) = 500 × 4.0 = 2000... (techo aplicado a 4.0)

---

### GET /api/v1/players/{player_id}/fixtures

**Para que:** Ver todos los partidos del jugador con el total de puntos SFA por partido.
Util para identificar que partidos fueron sus mejores actuaciones.

**Parametros:**

| Parametro | Tipo | Default | Descripcion |
|---|---|---|---|
| `player_id` | path | — | ID del jugador |
| `season` | query | null | Filtrar por temporada |
| `competition_id` | query | null | Filtrar por competicion |

**Ejemplo:**

```bash
curl "http://localhost:8000/api/v1/players/47/fixtures"
```

**Respuesta:**

```json
[
  {
    "fixture_id": 891,
    "competition": "Premier League",
    "stage": "Regular Season",
    "home_team": "Manchester City",
    "away_team": "Arsenal",
    "played_at": "2024-10-05T15:00:00",
    "sfa_pts": 2808.00,
    "events_count": 1
  }
]
```

---

### GET /api/v1/compare

**Para que:** Comparar dos jugadores cara a cara con sus estadisticas SFA completas.
Cada jugador se devuelve como un `PlayerDetail` completo, incluyendo breakdown.

**Parametros:**

| Parametro | Tipo | Default | Descripcion |
|---|---|---|---|
| `player_a` | query | obligatorio | ID del primer jugador |
| `player_b` | query | obligatorio | ID del segundo jugador |
| `season` | query | null | Temporada |

**Ejemplo:**

```bash
curl "http://localhost:8000/api/v1/compare?player_a=47&player_b=9"
```

**Respuesta:**

```json
{
  "season": "2024",
  "player_a": { /* PlayerDetail completo */ },
  "player_b": { /* PlayerDetail completo */ }
}
```

**Errores posibles:**

```json
// 404 si alguno de los dos player_id no existe
{"detail": "Player not found"}
```

---

### GET /api/v1/competitions

**Para que:** Listar todas las competiciones que tienen datos en la DB.
Util para obtener los `competition_id` que se necesitan en otros endpoints.

**Parametros:** Ninguno.

**Ejemplo:**

```bash
curl "http://localhost:8000/api/v1/competitions"
```

**Respuesta:**

```json
[
  {"id": 1, "name": "La Liga", "country": "ESP", "comp_factor": 1.0},
  {"id": 2, "name": "Premier League", "country": "ENG", "comp_factor": 1.0},
  {"id": 3, "name": "Champions League", "country": "EUR", "comp_factor": 1.5}
]
```

---

### GET /api/v1/competitions/{competition_id}/standings

**Para que:** Ver la clasificacion de la liga en un momento dado (matchday).
Los datos vienen del ultimo snapshot ingresado.

**Parametros:**

| Parametro | Tipo | Default | Descripcion |
|---|---|---|---|
| `competition_id` | path | — | ID interno de la competicion |
| `season` | query | null | Temporada |
| `matchday` | query | null (ultimo) | Numero de jornada |

**Ejemplo:**

```bash
curl "http://localhost:8000/api/v1/competitions/1/standings"
```

**Respuesta:**

```json
{
  "competition": "La Liga",
  "season": "2024",
  "matchday": 28,
  "standings": [
    {"position": 1, "team": "Real Madrid", "points": 67},
    {"position": 2, "team": "FC Barcelona", "points": 63}
  ]
}
```

**Errores posibles:**

```json
// 404 si competition_id no existe o no tiene standings
{"detail": "No standings found for competition 99"}
```

---

## 5. Tareas Celery

Las tareas Celery son los workers que ejecutan operaciones pesadas en background.
No bloquean la API. Se disparan desde los endpoints de admin.

### Configuracion del Beat Schedule

Definido en `src/sfa/celery_app.py`:

| Tarea | Horario | Argumentos |
|---|---|---|
| `ingest_all_competitions_task` | Cada 8h (00:00, 08:00, 16:00 UTC) | season=2024 |
| `enrich_all_task` | A las 02:00 y 14:00 UTC | season="2024", season_int=2024 |

El offset entre ingesta y enrichment es intencional: la ingesta corre primero (0h, 8h, 16h),
y el enrichment 2 horas despues (2h, 14h) cuando ya hay datos frescos disponibles.

### ingest_competition_task

```python
ingest_competition_task(league_id: int, season: int)
```

- Retries: 3 intentos, espera 5 minutos entre retries
- Crea su propia sesion de DB: `async with AsyncSessionLocal()`
- Instancia `APIFootballProvider`, `IngestionRepository`, `SFAScoringService`
- Llama a `IngestCompetitionUseCase.execute(league, season)`
- Hace `session.commit()` al final

### ingest_all_competitions_task

```python
ingest_all_competitions_task(season: int)
```

- Retries: 1 intento
- Llama a `IngestAllCompetitionsUseCase` que itera sobre la lista `LEAGUES`
- Un solo commit al final

### enrich_fbref_task

```python
enrich_fbref_task(competition_name: str, competition_id: int, season: str)
```

- Retries: 2 intentos, espera 10 minutos (FBref puede bloquear temporalmente)
- Corre `EnrichWithFBrefUseCase` + `RecalculateScoresUseCase` en secuencia
- Dos commits: uno por enrichment, uno por recalculo

### enrich_understat_task

```python
enrich_understat_task(competition_name: str, competition_id: int, season: str, season_int: int)
```

- Retries: 2 intentos, espera 10 minutos
- Corre `EnrichWithUnderstatUseCase` + `RecalculateScoresUseCase`
- Champions League se salta internamente (Understat no tiene datos de UCL)

### enrich_all_task

```python
enrich_all_task(season: str, season_int: int)
```

- Retries: 1 intento
- Para cada liga en LEAGUES: FBref → Understat → Recalculo (en secuencia)

### recalculate_task

```python
recalculate_task(competition_id: int, season: str)
```

- Retries: 2 intentos, espera 5 minutos
- Solo recalcula scores existentes con los parametros actuales
- No llama a ninguna API externa

### Como ver el estado de una tarea

```bash
# En los logs del worker:
docker compose -f docker-compose-development.yml logs celery_worker -f

# Buscar por task_id en los logs
docker compose -f docker-compose-development.yml logs celery_worker | grep "abc123"
```

---

## 6. Estado actual del sistema

### Que tiene el sistema hoy

| Funcionalidad | Estado |
|---|---|
| Ingesta de API-Football (fixtures, eventos, stats) | Implementado |
| Calculo de SFA pts evento por evento | Implementado |
| Multiplicadores M1, M2, M3, M4, Mvisit | Implementado |
| Enrichment FBref (stats avanzadas) | Implementado |
| Enrichment Understat (PSxG real) | Implementado |
| Recalculo de scores post-enrichment | Implementado |
| Ranking global con filtros | Implementado |
| Perfil de jugador con breakdown | Implementado |
| Eventos por jugador con detalle de multiplicadores | Implementado |
| Fixtures por jugador | Implementado |
| Comparacion head-to-head | Implementado |
| Clasificaciones por liga | Implementado |
| Celery Beat con schedule automatico | Implementado |
| Health check y status | Implementado |
| Logs de ingestion en DB | Implementado (modelo existe, endpoint pendiente) |

### Que le falta al sistema

| Funcionalidad | Prioridad | Notas |
|---|---|---|
| `GET /admin/ingestion-logs` | Media | El endpoint esta declarado pero retorna `[]` vacio. El repositorio y modelo existen |
| Scoring para porteros (GK) | Alta | Los GK se saltan en la ingesta. Faltan metricas como paradas, PSxG evitado |
| Estadisticas avanzadas de FBref en el score | Media | xG_no_goal, progressive_passes, pressures_success tienen base_pts definidos pero no se calculan en la ingesta (solo se usan en enrichment) |
| Autenticacion en endpoints de admin | Alta | Cualquiera con acceso a la API puede disparar ingestas |
| Tests de use cases de ingestion/enrichment | Alta | Solo existen tests parciales |
| Fotos de jugadores | Baja | El campo `photo_url` existe en el modelo pero no se popula en la ingesta actual |
| Soporte multi-temporada en el ranking | Media | El filtro existe pero la UI necesita validacion |
| Endpoint de logs de ingestion | Media | Ver arriba |

---

## 7. Legacy vs Estado actual

### Vision general del cambio

| Aspecto | Legacy (`_archive/`) | Sistema actual |
|---|---|---|
| Arquitectura | Monolitica (todo junto) | Hexagonal (capas separadas) |
| ORM | SQLAlchemy sincrono (Session) | SQLAlchemy 2.0 async (AsyncSession) |
| Cola de tareas | APScheduler embebido en FastAPI | Celery 5 + Redis (proceso separado) |
| Ingesta | Script Python o pipeline.py directo | Use cases invocados via Celery |
| Calculo SFA | Estimacion por stats agregadas de temporada | Evento por evento, accion por accion |
| Repositorio | Queries SQL raw o ORM directo en endpoints | Repository Pattern con Protocols |
| Tests | Sin tests formales | pytest + anyio + Fakes |
| Configuracion | Variables `.env` cargadas con `load_dotenv()` | Pydantic Settings con validacion |

---

### Mapa de archivos legacy → actual

| Archivo legacy | Equivalente actual | Que cambio |
|---|---|---|
| `_archive/backend/api/main.py` | `src/sfa/main.py` + `api/v1/*.py` | Endpoints separados por router. Schemas Pydantic. Sin logica de negocio en el router |
| `_archive/backend/engine/sfa_engine.py` | `domain/scoring/services.py` + `domain/scoring/value_objects.py` | Las funciones sueltas pasaron a ser Value Objects inmutables. La formula paso de estimacion a calculo real evento por evento |
| `_archive/backend/pipeline.py` | `application/use_cases/ingest_competition.py` + `tasks/ingestion_tasks.py` | El pipeline sincrono se partio en un use case (logica) y una tarea Celery (transporte). Los commits son explicitos |
| `_archive/backend/db/models.py` | `infrastructure/models/*/models.py` + `infrastructure/database.py` | Los modelos se separaron por entidad. Se agrego Base, engine async, y SessionLocal async |
| `_archive/backend/ingest/fbref_ingest.py` | `infrastructure/providers/fbref_scraper.py` + `application/use_cases/enrich_with_fbref.py` | El scraper es ahora un adaptador de puerto. La logica de guardar datos esta en el use case, no en el scraper |
| `_archive/backend/ingest/understat_ingest.py` | `infrastructure/providers/understat_scraper.py` + `application/use_cases/enrich_with_understat.py` | Mismo patron que FBref |
| `_archive/api_football_ingest_v5.py` | `infrastructure/providers/api_football.py` | El provider es ahora una clase que implementa `FootballDataProviderPort`. Tests posibles via Fakes |

---

### Decision clave: calculo real vs estimacion

El cambio mas importante en el dominio de scoring:

**Legacy — estimacion de temporada completa:**

```python
# pipeline.py — se calculaba UNA VEZ con stats acumuladas
def estimate_sfa_season_pts(row, standings_df, competition_name):
    goals = float(row.get("goals", 0))
    avg_m3 = 1.15   # Promedio estatico de toda la temporada
    avg_m4 = 1.35   # PSxG promedio estatico
    total += goals * 500 * (avg_m1 * comp_factor * avg_m3 * avg_m4)
```

Problema: todos los goles de un jugador tenian el mismo multiplicador, aunque uno fuera en el minuto 89 perdiendo y otro en el minuto 15 ganando 3-0.

**Sistema actual — calculo por evento:**

```python
# ingest_competition.py — se calcula por cada gol/asistencia individual
for goal_evt in player_goals:
    minute = goal_evt.minute          # Minuto real del gol
    score_diff = ...                  # Marcador real en ese momento
    m3 = M3MinuteScore(minute, score_diff, is_penalty)  # Minuto/marcador real
    m4 = M4ShotDifficulty(psxg)       # PSxG real (o default 0.32 sin enrichment)
    sfa = SFAScore(base_pts, CombinedMultiplier(m1, m2, m3, m4, mvisit))
```

Resultado: un gol en el minuto 89 empatado vale 2.5× mas que en el minuto 15 ganando.
El scoring refleja el contexto real del partido.

---

### Decision clave: separacion de capas

**Legacy — logica mezclada en el endpoint:**

```python
# api/main.py — el endpoint hacia queries ORM, calculaba el ranking, retornaba todo
@app.get("/api/ranking")
def get_ranking(season, position, db: Session = Depends(get_db)):
    # Query N+1: una query por jugador para sumar sus scores
    rows = db.execute(text("SELECT DISTINCT player_id FROM sfa_season_scores..."))
    players_data = []
    for pid in player_ids:
        player = db.query(Player).filter_by(id=pid).first()  # N queries
        totals = get_player_totals(db, pid, season)           # N queries mas
        players_data.append((player, totals))
    players_data.sort(...)
```

**Sistema actual — cada capa hace solo lo suyo:**

```python
# ranking.py (router) — solo valida y delega
async def get_ranking(use_case, season, position, competition_id, limit):
    result = await use_case.execute(season, position, competition_id, limit)
    return RankingResponseSchema(...)

# get_ranking.py (use case) — solo orquesta
async def execute(self, season, position, competition_id, limit):
    ranking = await self._score_repo.get_ranking(season, position, competition_id, limit)
    return RankingResult(...)

# sfa_score_repository.py (repository) — solo hace la query
async def get_ranking(self, season, position, competition_id, limit):
    # Una sola query con JOIN optimizado
    stmt = select(SFASeasonScore, Player, Team, Competition).join(...)
    rows = await self._session.execute(stmt)
    return [RankedPlayerDTO(...) for row in rows]
```

Beneficio: el use case puede testearse con un `FakeSFAScoreRepository` sin tocar la DB.
El repositorio puede optimizarse sin cambiar el use case ni el router.