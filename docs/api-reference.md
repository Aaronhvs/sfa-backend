# API Reference — SFA Backend

Referencia rapida de todos los endpoints. Base URL: `http://localhost:8000/api/v1`

Para documentacion detallada (por que existe cada endpoint, flujo interno, errores)
ver [`guia-tecnica.md`](./guia-tecnica.md).

Para ejecutar los ejemplos sin escribir curl, usar los archivos `.http` en `http/`
con VS Code REST Client (`humao.rest-client`) o JetBrains HTTP Client.

---

## Health y Status

### GET /health
Verifica conexion a PostgreSQL y Redis.

```
GET /api/v1/health
```

Respuesta: `{"status":"ok","database":"connected","redis":"connected","version":"0.1.0","env":"development"}`

Archivo: [`http/status.http`](../http/status.http)

---

### GET /status
Resumen de datos en el sistema: jugadores, scores, competiciones, eventos.

```
GET /api/v1/status
```

Respuesta: `{"status":"ok","season":"2024","players":342,"scores":510,"competitions":6,"events":1850,"api_version":"0.1.0"}`

Archivo: [`http/status.http`](../http/status.http)

---

## Ranking

### GET /ranking

| Param | Tipo | Default | Descripcion |
|---|---|---|---|
| `season` | string | ultima disponible | Ej: `"2024"` |
| `position` | string | todas | `DEL` `EXT` `MC` `DC` `LAT` `GK` |
| `competition_id` | int | todas | ID interno de competicion |
| `limit` | int | 50 | Max 200 |

```
GET /api/v1/ranking
GET /api/v1/ranking?season=2024&position=DEL&limit=10
GET /api/v1/ranking?competition_id=1
```

Respuesta: `{"season":"2024","total":342,"ranking":[{"rank":1,"id":47,"name":"...","sfa_pts":12450.75,...}]}`

Archivo: [`http/ranking.http`](../http/ranking.http)

---

## Players

### GET /players/{player_id}

Perfil completo: score, partidos, rank global, breakdown por tipo de accion.

| Param | Tipo | Default | Descripcion |
|---|---|---|---|
| `player_id` | path int | — | ID interno del jugador |
| `season` | string | ultima | Ej: `"2024"` |

```
GET /api/v1/players/47
GET /api/v1/players/47?season=2024
```

Errores: `404` si el jugador no existe.

Archivo: [`http/players.http`](../http/players.http)

---

### GET /players/{player_id}/events

Cada evento individual (gol, asistencia) con todos los multiplicadores M1-M4 y Mvisit.

| Param | Tipo | Default | Descripcion |
|---|---|---|---|
| `player_id` | path int | — | ID del jugador |
| `season` | string | null | Filtrar por temporada |
| `competition_id` | int | null | Filtrar por competicion |

```
GET /api/v1/players/47/events
GET /api/v1/players/47/events?season=2024&competition_id=1
```

Archivo: [`http/players.http`](../http/players.http)

---

### GET /players/{player_id}/fixtures

Partidos del jugador con SFA pts acumulados por partido.

| Param | Tipo | Default | Descripcion |
|---|---|---|---|
| `player_id` | path int | — | ID del jugador |
| `season` | string | null | Filtrar por temporada |
| `competition_id` | int | null | Filtrar por competicion |

```
GET /api/v1/players/47/fixtures
GET /api/v1/players/47/fixtures?season=2024
```

Archivo: [`http/players.http`](../http/players.http)

---

## Compare

### GET /compare

Comparacion head-to-head entre dos jugadores. Devuelve dos `PlayerDetail` completos.

| Param | Tipo | Requerido | Descripcion |
|---|---|---|---|
| `player_a` | int | si | ID del primer jugador |
| `player_b` | int | si | ID del segundo jugador |
| `season` | string | no | Temporada |

```
GET /api/v1/compare?player_a=47&player_b=9
GET /api/v1/compare?player_a=47&player_b=9&season=2024
```

Errores: `404` si cualquiera de los dos IDs no existe.

Archivo: [`http/compare.http`](../http/compare.http)

---

## Competitions

### GET /competitions

Lista todas las competiciones con datos en la DB.

```
GET /api/v1/competitions
```

Respuesta: `[{"id":1,"name":"La Liga","country":"ESP","comp_factor":1.0}, ...]`

Archivo: [`http/competitions.http`](../http/competitions.http)

---

### GET /competitions/{competition_id}/standings

Clasificacion de una liga en un momento dado.

| Param | Tipo | Default | Descripcion |
|---|---|---|---|
| `competition_id` | path int | — | ID interno de la competicion |
| `season` | string | null | Temporada |
| `matchday` | int | null (ultimo) | Numero de jornada |

```
GET /api/v1/competitions/1/standings
GET /api/v1/competitions/1/standings?season=2024&matchday=20
```

Errores: `404` si la competicion no existe o no tiene standings.

Archivo: [`http/competitions.http`](../http/competitions.http)

---

## Admin

Requieren que Celery worker este corriendo. Devuelven un `task_id` inmediatamente;
la operacion real corre en background.

### IDs de ligas (API-Football)

| ID | Liga |
|---|---|
| 140 | La Liga |
| 39 | Premier League |
| 78 | Bundesliga |
| 135 | Serie A |
| 61 | Ligue 1 |
| 2 | Champions League |

---

### POST /admin/ingest/{league_id}

Ingesta completa de una liga: standings, fixtures, eventos, stats, SFA scores.

```
POST /api/v1/admin/ingest/140?season=2024
```

Respuesta: `{"task_id":"abc123","league_id":140,"season":2024}`

---

### POST /admin/ingest-all

Ingesta de todas las ligas configuradas.

```
POST /api/v1/admin/ingest-all?season=2024
```

---

### POST /admin/enrich-fbref/{competition_id}

Enriquecimiento con estadisticas avanzadas de FBref. Requiere `competition_name`.
El `competition_id` es el ID interno (de tu DB) — consultarlo con `GET /competitions`.

```
POST /api/v1/admin/enrich-fbref/1?competition_name=La%20Liga&season=2024
```

---

### POST /admin/enrich-understat/{competition_id}

Enriquecimiento con PSxG real de Understat. Champions League se salta automaticamente.

```
POST /api/v1/admin/enrich-understat/1?competition_name=La%20Liga&season=2024&season_int=2024
```

---

### POST /admin/enrich-all

FBref + Understat + Recalculo para todas las ligas en secuencia.

```
POST /api/v1/admin/enrich-all?season=2024&season_int=2024
```

---

### POST /admin/recalculate/{competition_id}

Recalcula SFA scores con los parametros actuales sin llamar a APIs externas.
Util despues de modificar `BASE_POINTS_TABLE` o multiplicadores.

```
POST /api/v1/admin/recalculate/1?season=2024
```

---

### GET /admin/ingestion-logs

Estado de las ultimas ingestas. Pendiente de implementacion completa.

```
GET /api/v1/admin/ingestion-logs
```

Archivo para todos los endpoints admin: [`http/admin.http`](../http/admin.http)
