from __future__ import annotations

import asyncio
import logging

import httpx
from bs4 import BeautifulSoup, Tag

from sfa.domain.enrichment_ports import FBrefPlayerStatsDTO, FBrefProviderPort

logger = logging.getLogger(__name__)

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


class FBrefScraper:
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3",
    }
    _RATE_LIMIT_SECONDS = 4.0

    async def _get_html(self, url: str) -> str:
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    headers=self._HEADERS,
                    follow_redirects=True,
                    timeout=30.0,
                ) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    return response.text
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                if attempt == 2:
                    raise
                wait = 15.0 * (attempt + 1)
                logger.warning(
                    "FBref request failed (attempt %d), retrying in %.0fs: %s",
                    attempt + 1, wait, exc,
                )
                await asyncio.sleep(wait)
        raise RuntimeError("Unreachable")  # pragma: no cover

    def _parse_standard_table(self, html: str) -> list[dict]:
        """Parse stats_standard table by data-stat attributes."""
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", {"id": "stats_standard"})
        if not isinstance(table, Tag):
            logger.warning("stats_standard table not found in FBref HTML")
            return []

        rows: list[dict] = []
        tbody = table.find("tbody")
        if not isinstance(tbody, Tag):
            return rows

        for tr in tbody.find_all("tr"):
            if "thead" in tr.get("class", []):
                continue
            name = _cell_text(tr, "player")
            if not name:
                continue
            rows.append({
                "player": name,
                "squad": _cell_text(tr, "squad"),
                "pos": _cell_text(tr, "pos"),
                "minutes": _to_int(_cell_text(tr, "minutes")),
                "goals": _to_int(_cell_text(tr, "goals")),
                "assists": _to_int(_cell_text(tr, "assists")),
                "xg": _to_float(_cell_text(tr, "xg")),
                # FBref uses "xg_assist" for xAG (expected assists)
                "xa": _to_float(
                    _cell_text(tr, "xg_assist") or _cell_text(tr, "xg_assist_net")
                ),
                "progressive_passes": _to_int(_cell_text(tr, "progressive_passes")),
                "progressive_carries": _to_int(_cell_text(tr, "progressive_carries")),
            })

        return rows

    def _parse_shooting_table(self, html: str) -> dict[str, dict]:
        """Parse stats_shooting table. Returns {player_name: {goals, psxg}}."""
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", {"id": "stats_shooting"})
        if not isinstance(table, Tag):
            logger.warning("stats_shooting table not found in FBref HTML")
            return {}

        result: dict[str, dict] = {}
        tbody = table.find("tbody")
        if not isinstance(tbody, Tag):
            return result

        for tr in tbody.find_all("tr"):
            if "thead" in tr.get("class", []):
                continue
            name = _cell_text(tr, "player")
            if not name:
                continue
            psxg_raw = _cell_text(tr, "psxg")
            result[name] = {
                "goals": _to_int(_cell_text(tr, "goals")),
                "psxg": _to_float(psxg_raw) if psxg_raw else None,
            }

        return result

    async def fetch_league_player_stats(
        self, league: str,
    ) -> list[FBrefPlayerStatsDTO]:
        stats_url = LEAGUE_STATS_URLS.get(league)
        if not stats_url:
            logger.warning("No FBref URL configured for league: %s", league)
            return []

        stats_html = await self._get_html(stats_url)
        await asyncio.sleep(self._RATE_LIMIT_SECONDS)

        shooting_by_player: dict[str, dict] = {}
        shooting_url = LEAGUE_SHOOTING_URLS.get(league)
        if shooting_url:
            shooting_html = await self._get_html(shooting_url)
            await asyncio.sleep(self._RATE_LIMIT_SECONDS)
            shooting_by_player = self._parse_shooting_table(shooting_html)

        standard_rows = self._parse_standard_table(stats_html)

        result: list[FBrefPlayerStatsDTO] = []
        for row in standard_rows:
            name = row["player"]
            shooting = shooting_by_player.get(name, {})
            raw_psxg = shooting.get("psxg")
            psxg_total: float | None = raw_psxg if raw_psxg and raw_psxg > 0 else None

            result.append(FBrefPlayerStatsDTO(
                player_name=name,
                team_name=row["squad"],
                position=row["pos"],
                minutes=row["minutes"],
                goals=row["goals"],
                assists=row["assists"],
                xg=row["xg"],
                xa=row["xa"],
                progressive_passes=row["progressive_passes"],
                progressive_carries=row["progressive_carries"],
                psxg_total=psxg_total,
            ))

        logger.info("FBref: %d players scraped for %s", len(result), league)
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cell_text(tr: Tag, data_stat: str) -> str:
    cell = tr.find(["td", "th"], {"data-stat": data_stat})
    return cell.get_text(strip=True) if isinstance(cell, Tag) else ""


def _to_int(value: str) -> int:
    try:
        return int(value.replace(",", ""))
    except (ValueError, AttributeError):
        return 0


def _to_float(value: str) -> float:
    try:
        return float(value.replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0
