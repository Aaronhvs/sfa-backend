# SFA API — Reference

Base URL: `http://localhost:8000`  
Interactive docs: `/docs` (Swagger UI) · `/redoc` (ReDoc)

---

## Ranking

### `GET /api/v1/ranking`

Returns a ranked list of players ordered by SFA points for a given season.

**Query parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `season` | string | latest available | Season in `YYYY-YY` format, e.g. `2024-25` |
| `position` | string | — | Filter by position: `DEL`, `EXT`, `MC`, `DC`, `LAT`, `GK` |
| `competition_id` | integer | — | Filter by competition ID |
| `limit` | integer | `50` | Number of results (1–200) |

**Response `200`**

```json
{
  "season": "2024-25",
  "total": 48,
  "ranking": [
    {
      "rank": 1,
      "id": 12,
      "name": "Vinícius Jr.",
      "team": "Real Madrid",
      "position": "EXT",
      "competition": "La Liga",
      "sfa_pts": 18420.00,
      "matches": 28,
      "photo_url": "https://example.com/photo.png"
    }
  ]
}
```

**Status codes:** `200 OK` · `422 Unprocessable Entity` (invalid query params)

---

## Players

### `GET /api/v1/players/{player_id}`

Returns full season detail for a player, including global rank and breakdown by event type.

**Path parameters**

| Name | Type | Description |
|------|------|-------------|
| `player_id` | integer | Player ID |

**Query parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `season` | string | latest available for the player | Season in `YYYY-YY` format |

**Response `200`**

```json
{
  "id": 12,
  "name": "Vinícius Jr.",
  "team": "Real Madrid",
  "position": "EXT",
  "competition": "La Liga",
  "sfa_pts": 18420.00,
  "matches": 28,
  "photo_url": "https://example.com/photo.png",
  "global_rank": 1,
  "season": "2024-25",
  "breakdown": {
    "goal": { "count": 18, "pts": 12000.00 },
    "assist": { "count": 6, "pts": 4200.00 }
  },
  "competitions": ["La Liga", "Champions League"]
}
```

**Status codes:** `200 OK` · `404 Not Found` · `422 Unprocessable Entity`

---

### `GET /api/v1/players/{player_id}/events`

Returns all scored events for a player, ordered by date descending then minute ascending.

**Path parameters**

| Name | Type | Description |
|------|------|-------------|
| `player_id` | integer | Player ID |

**Query parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `season` | string | — | Filter by season |
| `competition_id` | integer | — | Filter by competition |

**Response `200`**

```json
[
  {
    "id": 301,
    "competition": "La Liga",
    "stage": "regular",
    "fixture_id": 88,
    "home_team": "Real Madrid",
    "away_team": "Barcelona",
    "played_at": "2025-03-15T20:00:00Z",
    "minute": 87,
    "event_type": "goal",
    "score_before": "0-0",
    "score_diff": 0,
    "m1": 1.05,
    "m2": 1.00,
    "m3": 2.50,
    "m4": 1.54,
    "mvisit": 1.30,
    "pts": 6000.00
  }
]
```

**Status codes:** `200 OK` · `422 Unprocessable Entity`

---

### `GET /api/v1/players/{player_id}/fixtures`

Returns a per-fixture summary of SFA points aggregated from all events in that match.

**Path parameters**

| Name | Type | Description |
|------|------|-------------|
| `player_id` | integer | Player ID |

**Query parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `season` | string | — | Filter by season |
| `competition_id` | integer | — | Filter by competition |

**Response `200`**

```json
[
  {
    "fixture_id": 88,
    "competition": "La Liga",
    "stage": "regular",
    "home_team": "Real Madrid",
    "away_team": "Barcelona",
    "played_at": "2025-03-15T20:00:00Z",
    "sfa_pts": 6000.00,
    "events_count": 1
  }
]
```

**Status codes:** `200 OK` · `422 Unprocessable Entity`

---

## Competitions

### `GET /api/v1/competitions`

Returns all competitions sorted by name.

**Response `200`**

```json
[
  { "id": 1, "name": "La Liga", "country": "ESP", "factor": 1.00 },
  { "id": 2, "name": "Champions League", "country": "EUR", "factor": 1.50 }
]
```

**Status codes:** `200 OK`

---

### `GET /api/v1/competitions/{competition_id}/standings`

Returns the standings table for a competition at a specific matchday.

**Path parameters**

| Name | Type | Description |
|------|------|-------------|
| `competition_id` | integer | Competition ID |

**Query parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `season` | string | latest available | Season in `YYYY-YY` format |
| `matchday` | integer | latest available | Matchday number |

**Response `200`**

```json
{
  "competition": "La Liga",
  "season": "2024-25",
  "matchday": 29,
  "standings": [
    { "position": 1, "team": "Real Madrid", "points": 72 },
    { "position": 2, "team": "Barcelona", "points": 68 }
  ]
}
```

**Status codes:** `200 OK` · `404 Not Found` (competition not found, or no standings for the given season/matchday) · `422 Unprocessable Entity`

---

## Compare

### `GET /api/v1/compare`

Returns full player detail for two players side by side.

**Query parameters**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `player_a` | integer | yes | ID of the first player |
| `player_b` | integer | yes | ID of the second player |
| `season` | string | no | Season in `YYYY-YY` format |

**Response `200`**

```json
{
  "season": "2024-25",
  "player_a": { "...same shape as GET /players/{id}..." },
  "player_b": { "...same shape as GET /players/{id}..." }
}
```

**Status codes:** `200 OK` · `404 Not Found` (if either player is not found) · `422 Unprocessable Entity`

---

## Status

### `GET /api/v1/status`

Returns system-level counters and the current active season.

**Response `200`**

```json
{
  "status": "ok",
  "season": "2024-25",
  "players": 520,
  "scores": 1040,
  "competitions": 3,
  "events": 8900,
  "api_version": "1.0.0"
}
```

**Status codes:** `200 OK`

---

## Health

### `GET /api/v1/health`

Verifies that the database and Redis connections are reachable.

**Response `200`**

```json
{
  "status": "ok",
  "database": "connected",
  "redis": "connected",
  "version": "1.0.0",
  "env": "development"
}
```

**Status codes:** `200 OK` (always — check `database`/`redis` fields for actual connectivity)
