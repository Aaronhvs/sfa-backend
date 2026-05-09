#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import sys

# Ensure src/ is in the path so `sfa` package can be imported directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="SFA — Stadistic Football Award CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  python src/run.py --download --league-id 140 --season 2024 --yes\n"
            "  python src/run.py --recalculate --competition-id 1 --season 2024\n"
            "  python src/run.py --add-competition --league-id 39 --season 2024\n"
        ),
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--download", action="store_true",
        help="Download raw player data + calculate SFA scores",
    )
    mode.add_argument(
        "--recalculate", action="store_true",
        help="Recalculate SFA scores from existing RAW data (no API calls)",
    )
    mode.add_argument(
        "--add-competition", action="store_true",
        help="Add a new competition: download all players + calculate",
    )

    parser.add_argument("--league-id", type=int, metavar="ID",
                        help="API-Football league ID (e.g. 140 = La Liga)")
    parser.add_argument("--season", type=int, default=2024, metavar="YEAR",
                        help="Season year (default: 2024)")
    parser.add_argument("--players", type=str, metavar="NAMES",
                        help="Comma-separated player name filters, e.g. 'Yamal,Vinicius'")
    parser.add_argument("--competition-id", type=int, metavar="ID",
                        help="DB competition ID (required for --recalculate)")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Skip all confirmation prompts")

    return parser


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _resolve_league(league_id: int | None, silent: bool = False):
    from sfa.domain.ingestion_ports import LEAGUES

    if league_id is None:
        if not silent:
            print("\nLigas disponibles:")
            for lg in LEAGUES:
                print(f"  {lg.id:>4}  {lg.name} ({lg.country})")
        try:
            league_id = int(input("\nLeague ID: ").strip())
        except (ValueError, EOFError):
            print("ERROR: league-id inválido.")
            sys.exit(1)

    league = next((lg for lg in LEAGUES if lg.id == league_id), None)
    if league is None:
        print(f"ERROR: No existe la liga con id={league_id}.")
        sys.exit(1)
    return league


# ---------------------------------------------------------------------------
# --download flow
# ---------------------------------------------------------------------------


async def _run_download(args: argparse.Namespace) -> None:
    from sqlalchemy import select

    from sfa.application.use_cases.calculate_sfa_from_raw import CalculateSFAFromRawUseCase
    from sfa.application.use_cases.download_player_data import DownloadPlayerDataUseCase
    from sfa.core.config import get_settings
    from sfa.domain.ingestion_ports import RequestEstimationService
    from sfa.domain.scoring.services import SFAScoringService
    from sfa.infrastructure.database import AsyncSessionLocal
    from sfa.infrastructure.models.competitions.models import Competition
    from sfa.infrastructure.providers.api_football import APIFootballProvider
    from sfa.infrastructure.repositories.ingestion_repository import IngestionRepository
    from sfa.infrastructure.repositories.raw_data_repository import RawDataRepository

    league = _resolve_league(args.league_id)

    # Player filter
    player_filter: list[str] | None = None
    if args.players:
        player_filter = [p.strip() for p in args.players.split(",") if p.strip()]
    elif not args.yes:
        raw = input("Filtro de jugadores (opcional, separados por coma): ").strip()
        if raw:
            player_filter = [p.strip() for p in raw.split(",") if p.strip()]

    season_str = str(args.season)

    # Estimate requests
    fixtures_per_league: dict[int, int] = {}
    async with AsyncSessionLocal() as session:
        row = await session.execute(
            select(Competition.id).where(Competition.name == league.name)
        )
        competition_id = row.scalar_one_or_none()
        if competition_id is not None:
            fixture_ids = await RawDataRepository(session).get_downloaded_fixture_ids(
                competition_id, season_str
            )
            fixtures_per_league[league.id] = len(fixture_ids)

    estimation = RequestEstimationService().estimate([league], 0, fixtures_per_league)
    print(
        f"\nEstimación: ~{estimation.net_new_requests} requests nuevos "
        f"de {estimation.daily_limit} diarios  "
        f"(fixtures pendientes: {estimation.fixtures_pending})."
    )
    if not estimation.is_feasible:
        print("ADVERTENCIA: supera el límite diario de la API.")

    if not args.yes:
        confirm = input("¿Continuar? [s/N]: ").strip().lower()
        if confirm not in ("s", "si", "sí", "y", "yes"):
            print("Cancelado.")
            return

    # Download
    settings = get_settings()
    provider = APIFootballProvider(settings.API_FOOTBALL_KEY, settings.API_FOOTBALL_BASE_URL)
    scoring = SFAScoringService()

    print(f"\nDescargando {league.name} season {args.season}...")
    async with AsyncSessionLocal() as session:
        download_uc = DownloadPlayerDataUseCase(provider, IngestionRepository(session))
        dl = await download_uc.execute(league, args.season, player_filter=player_filter)
        await session.commit()

    print(
        f"  fixtures descargados={dl.fixtures_downloaded}  "
        f"saltados={dl.fixtures_skipped}  "
        f"jugadores={dl.players_downloaded}  "
        f"requests={dl.requests_used}"
    )

    if dl.status == "failed":
        print(f"ERROR en descarga: {dl.error}")
        sys.exit(1)

    # Resolve competition_id and calculate
    async with AsyncSessionLocal() as session:
        row = await session.execute(
            select(Competition.id).where(Competition.name == league.name)
        )
        competition_id = row.scalar_one()

    print(f"\nCalculando SFA scores (competition_id={competition_id}, season={season_str})...")
    async with AsyncSessionLocal() as session:
        calc_uc = CalculateSFAFromRawUseCase(
            RawDataRepository(session), IngestionRepository(session), scoring
        )
        calc = await calc_uc.execute(competition_id, season_str)
        await session.commit()

    print(
        f"  jugadores calculados={calc.players_calculated}  "
        f"eventos={calc.events_created}  "
        f"scores actualizados={calc.scores_updated}"
    )

    if calc.status == "failed":
        print(f"ERROR en cálculo: {calc.error}")
        sys.exit(1)

    print("\nListo.")


# ---------------------------------------------------------------------------
# --recalculate flow
# ---------------------------------------------------------------------------


async def _run_recalculate(args: argparse.Namespace) -> None:
    from sfa.application.use_cases.calculate_sfa_from_raw import CalculateSFAFromRawUseCase
    from sfa.domain.scoring.services import SFAScoringService
    from sfa.infrastructure.database import AsyncSessionLocal
    from sfa.infrastructure.repositories.ingestion_repository import IngestionRepository
    from sfa.infrastructure.repositories.raw_data_repository import RawDataRepository

    competition_id = args.competition_id
    if competition_id is None:
        try:
            competition_id = int(input("competition-id: ").strip())
        except (ValueError, EOFError):
            print("ERROR: competition-id inválido.")
            sys.exit(1)

    season_str = str(args.season)
    scoring = SFAScoringService()

    print(f"\nRecalculando competition_id={competition_id} season={season_str}...")
    async with AsyncSessionLocal() as session:
        calc_uc = CalculateSFAFromRawUseCase(
            RawDataRepository(session), IngestionRepository(session), scoring
        )
        result = await calc_uc.execute(competition_id, season_str)
        await session.commit()

    print(
        f"Recalculados {result.players_calculated} jugadores, "
        f"{result.events_created} eventos, "
        f"{result.scores_updated} scores actualizados."
    )

    if result.status == "failed":
        print(f"ERROR: {result.error}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# --add-competition flow
# ---------------------------------------------------------------------------


async def _run_add_competition(args: argparse.Namespace) -> None:
    from sqlalchemy import select

    from sfa.application.use_cases.calculate_sfa_from_raw import CalculateSFAFromRawUseCase
    from sfa.application.use_cases.download_player_data import DownloadPlayerDataUseCase
    from sfa.core.config import get_settings
    from sfa.domain.scoring.services import SFAScoringService
    from sfa.infrastructure.database import AsyncSessionLocal
    from sfa.infrastructure.models.competitions.models import Competition
    from sfa.infrastructure.providers.api_football import APIFootballProvider
    from sfa.infrastructure.repositories.ingestion_repository import IngestionRepository
    from sfa.infrastructure.repositories.raw_data_repository import RawDataRepository

    league = _resolve_league(args.league_id)
    season_str = str(args.season)

    settings = get_settings()
    provider = APIFootballProvider(settings.API_FOOTBALL_KEY, settings.API_FOOTBALL_BASE_URL)
    scoring = SFAScoringService()

    print(f"\nAgregando {league.name} season {args.season} (todos los jugadores)...")
    async with AsyncSessionLocal() as session:
        download_uc = DownloadPlayerDataUseCase(provider, IngestionRepository(session))
        dl = await download_uc.execute(league, args.season)
        await session.commit()

    print(
        f"  fixtures descargados={dl.fixtures_downloaded}  "
        f"saltados={dl.fixtures_skipped}  "
        f"jugadores={dl.players_downloaded}  "
        f"requests={dl.requests_used}"
    )

    if dl.status == "failed":
        print(f"ERROR en descarga: {dl.error}")
        sys.exit(1)

    async with AsyncSessionLocal() as session:
        row = await session.execute(
            select(Competition.id).where(Competition.name == league.name)
        )
        competition_id = row.scalar_one()

    print(f"\nCalculando SFA scores (competition_id={competition_id}, season={season_str})...")
    async with AsyncSessionLocal() as session:
        calc_uc = CalculateSFAFromRawUseCase(
            RawDataRepository(session), IngestionRepository(session), scoring
        )
        calc = await calc_uc.execute(competition_id, season_str)
        await session.commit()

    print(
        f"  jugadores calculados={calc.players_calculated}  "
        f"eventos={calc.events_created}  "
        f"scores actualizados={calc.scores_updated}"
    )

    if calc.status == "failed":
        print(f"ERROR en cálculo: {calc.error}")
        sys.exit(1)

    print("\nListo.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.download:
        await _run_download(args)
    elif args.recalculate:
        await _run_recalculate(args)
    elif args.add_competition:
        await _run_add_competition(args)


if __name__ == "__main__":
    asyncio.run(main())
