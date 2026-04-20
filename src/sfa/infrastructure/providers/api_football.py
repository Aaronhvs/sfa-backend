from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import httpx

from sfa.domain.ingestion_ports import (
    FixtureEventRawDTO,
    FixtureRawDTO,
    PlayerStatsRawDTO,
    StandingRawDTO,
)

logger = logging.getLogger(__name__)

ROUND_TO_STAGE: dict[str, str] = {
    "group stage":     "group",
    "league stage":    "group",
    "round of 32":     "round_of_16",
    "last 16":         "round_of_16",
    "round of 16":     "round_of_16",
    "quarter-finals":  "quarter",
    "quarter finals":  "quarter",
    "semi-finals":     "semi",
    "semi finals":     "semi",
    "3rd place final": "semi",
    "final":           "final",
}


class APIFootballProvider:
    """HTTP adapter for API-Football v3."""

    def __init__(self, api_key: str, base_url: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._requests_used = 0
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={"x-apisports-key": self._api_key},
                timeout=20.0,
            )
        return self._client

    async def _get(self, endpoint: str, params: dict | None = None) -> dict:
        """HTTP GET with rate limiting, retry, and backoff."""
        client = self._get_client()
        last_exc: Exception | None = None

        for attempt in range(3):
            try:
                response = await client.get(endpoint, params=params)
                response.raise_for_status()
                data: dict = response.json()
                self._requests_used += 1

                errors = data.get("errors")
                if errors:
                    err_str = str(errors)
                    if "rateLimit" in err_str:
                        logger.warning("Rate limit hit, waiting 65s before retry")
                        await asyncio.sleep(65)
                        continue
                    logger.warning("API errors for %s: %s", endpoint, errors)

                return data

            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning("Timeout on %s (attempt %d/3)", endpoint, attempt + 1)
                if attempt < 2:
                    await asyncio.sleep(10)
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                logger.error("HTTP error on %s: %s", endpoint, exc)
                if attempt < 2:
                    await asyncio.sleep(10)

        raise RuntimeError(
            f"Failed to GET /{endpoint} after 3 attempts"
        ) from last_exc

    async def fetch_standings(self, league_id: int, season: int) -> list[StandingRawDTO]:
        data = await self._get("standings", {"league": league_id, "season": season})
        try:
            standings_raw = data["response"][0]["league"]["standings"][0]
        except (IndexError, KeyError, TypeError):
            logger.warning("No standings data for league %d season %d", league_id, season)
            return []

        result: list[StandingRawDTO] = []
        for entry in standings_raw:
            result.append(
                StandingRawDTO(
                    team_external_id=entry["team"]["id"],
                    team_name=entry["team"]["name"],
                    position=entry["rank"],
                    points=entry["points"],
                    played=entry["all"]["played"],
                )
            )
        return result

    async def fetch_team_fixtures(
        self, team_id: int, league_id: int, season: int,
    ) -> list[FixtureRawDTO]:
        data = await self._get(
            "fixtures",
            {"team": team_id, "league": league_id, "season": season, "status": "FT"},
        )
        result: list[FixtureRawDTO] = []
        for f in data.get("response", []):
            try:
                played_at = datetime.fromisoformat(f["fixture"]["date"])
                result.append(
                    FixtureRawDTO(
                        external_id=f["fixture"]["id"],
                        home_team_external_id=f["teams"]["home"]["id"],
                        away_team_external_id=f["teams"]["away"]["id"],
                        home_team_name=f["teams"]["home"]["name"],
                        away_team_name=f["teams"]["away"]["name"],
                        round_str=f["league"]["round"],
                        league_name=f["league"]["name"],
                        played_at=played_at,
                        home_goals=f["goals"]["home"] or 0,
                        away_goals=f["goals"]["away"] or 0,
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Skipping malformed fixture: %s", exc)
        return result

    async def fetch_fixture_events(self, fixture_id: int) -> list[FixtureEventRawDTO]:
        data = await self._get("fixtures/events", {"fixture": fixture_id})
        result: list[FixtureEventRawDTO] = []
        for e in data.get("response", []):
            try:
                result.append(
                    FixtureEventRawDTO(
                        type=e.get("type") or "",
                        detail=e.get("detail") or "",
                        player_name=e["player"].get("name") or "",
                        assist_name=e["assist"].get("name"),
                        team_external_id=e["team"]["id"],
                        minute=e["time"]["elapsed"] or 0,
                        extra_minute=e["time"]["extra"] or 0,
                    )
                )
            except (KeyError, TypeError) as exc:
                logger.warning("Skipping malformed event: %s", exc)
        return result

    async def fetch_fixture_players(
        self, fixture_id: int, team_id: int,
    ) -> list[PlayerStatsRawDTO]:
        data = await self._get("fixtures/players", {"fixture": fixture_id})
        result: list[PlayerStatsRawDTO] = []

        for team_data in data.get("response", []):
            if team_data["team"]["id"] != team_id:
                continue
            for p in team_data.get("players", []):
                try:
                    stats = p["statistics"][0] if p.get("statistics") else {}
                    games = stats.get("games") or {}
                    goals = stats.get("goals") or {}
                    shots = stats.get("shots") or {}
                    passes = stats.get("passes") or {}
                    dribbles = stats.get("dribbles") or {}
                    duels = stats.get("duels") or {}
                    tackles = stats.get("tackles") or {}

                    result.append(
                        PlayerStatsRawDTO(
                            player_external_id=p["player"]["id"],
                            player_name=p["player"]["name"],
                            position=games.get("position") or "Midfielder",
                            minutes=games.get("minutes") or 0,
                            goals=goals.get("total") or 0,
                            assists=goals.get("assists") or 0,
                            shots_on=shots.get("on") or 0,
                            passes_key=passes.get("key") or 0,
                            dribbles_success=dribbles.get("success") or 0,
                            duels_won=duels.get("won") or 0,
                            tackles=tackles.get("total") or 0,
                            interceptions=tackles.get("interceptions") or 0,
                            blocks=tackles.get("blocks") or 0,
                        )
                    )
                except (KeyError, TypeError, IndexError) as exc:
                    logger.warning("Skipping malformed player stats: %s", exc)
        return result

    def get_stage(self, round_str: str, league_name: str) -> str:
        """Map API-Football round string → SFA stage."""
        key = round_str.lower().strip()
        for pattern, stage in ROUND_TO_STAGE.items():
            if pattern in key:
                return stage
        return "regular"

    def get_score_at_minute(
        self,
        events: list[FixtureEventRawDTO],
        minute: int,
        home_team_id: int,
    ) -> tuple[int, int]:
        """Return (home_goals, away_goals) scored strictly before the given minute."""
        home_goals = 0
        away_goals = 0
        for e in events:
            event_minute = e.minute + e.extra_minute
            if event_minute >= minute:
                continue
            if e.type != "Goal" or e.detail == "Missed Penalty":
                continue
            if e.detail == "Own Goal":
                if e.team_external_id == home_team_id:
                    away_goals += 1
                else:
                    home_goals += 1
            else:
                if e.team_external_id == home_team_id:
                    home_goals += 1
                else:
                    away_goals += 1
        return home_goals, away_goals

    @property
    def requests_used(self) -> int:
        return self._requests_used
