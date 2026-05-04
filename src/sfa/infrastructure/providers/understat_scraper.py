from __future__ import annotations

import asyncio
import json
import logging
import re

import httpx

from sfa.domain.enrichment_ports import UnderstatPlayerDTO, UnderstatProviderPort

logger = logging.getLogger(__name__)

LEAGUE_MAP: dict[str, str] = {
    "La Liga":        "La_liga",
    "Premier League": "EPL",
    "Bundesliga":     "Bundesliga",
    "Serie A":        "Serie_A",
    "Ligue 1":        "Ligue_1",
    # Champions League: NOT available on Understat
}

_BASE_URL = "https://understat.com"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3",
}
_RATE_LIMIT_SECONDS = 2.0


class UnderstatScraper:
    async def _get_html(self, url: str) -> str:
        backoffs = [15.0, 30.0]
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    headers=_HEADERS,
                    follow_redirects=True,
                    timeout=30.0,
                ) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    return response.text
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                if attempt == 2:
                    raise
                wait = backoffs[attempt]
                logger.warning(
                    "Understat request failed (attempt %d), retrying in %.0fs: %s",
                    attempt + 1, wait, exc,
                )
                await asyncio.sleep(wait)
        raise RuntimeError("Unreachable")  # pragma: no cover

    async def fetch_league_players(
        self, league: str, season: int,
    ) -> list[UnderstatPlayerDTO]:
        league_slug = LEAGUE_MAP.get(league)
        if not league_slug:
            logger.warning(
                "League %s not available on Understat (no slug configured)", league
            )
            return []

        url = f"{_BASE_URL}/league/{league_slug}/{season}"
        html = await self._get_html(url)
        await asyncio.sleep(_RATE_LIMIT_SECONDS)

        raw_players = _extract_json_var(html, "playersData")
        if not raw_players:
            logger.warning("No playersData found in Understat HTML for %s/%s", league, season)
            return []

        result: list[UnderstatPlayerDTO] = []
        for p in raw_players:
            try:
                shots = int(p.get("shots", 0)) or 1  # avoid division by zero
                xg_val = float(p.get("xG", 0.0))
                xg_per_shot = round(xg_val / shots, 4)

                result.append(UnderstatPlayerDTO(
                    player_name=p.get("player_name", ""),
                    team_name=p.get("team_title", ""),
                    understat_id=str(p.get("id", "")),
                    goals=int(p.get("goals", 0)),
                    assists=int(p.get("assists", 0)),
                    npg=int(p.get("npg", 0)),
                    npxg=float(p.get("npxG", 0.0)),
                    xa=float(p.get("xA", 0.0)),
                    shots=int(p.get("shots", 0)),
                    key_passes=int(p.get("key_passes", 0)),
                    xg_per_shot=xg_per_shot,
                    minutes=int(p.get("time", 0)),
                    games=int(p.get("games", 0)),
                ))
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("Failed to parse Understat player entry: %s — %s", p, exc)

        logger.info("Understat: %d players scraped for %s/%s", len(result), league, season)
        return result


def _extract_json_var(html: str, var_name: str) -> list:
    """Extract a JSON variable embedded in Understat HTML via JSON.parse('...')."""
    pattern = rf"var\s+{var_name}\s*=\s*JSON\.parse\('(.+?)'\)"
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        return []
    raw = match.group(1)
    try:
        # Understat encodes the JSON payload with unicode_escape sequences.
        # Decoding via unicode_escape then re-encoding to latin-1 and back to
        # utf-8 correctly handles non-ASCII player names (accented characters).
        decoded = raw.encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8")
        return json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error("Failed to parse Understat JSON for var %s", var_name)
            return []
