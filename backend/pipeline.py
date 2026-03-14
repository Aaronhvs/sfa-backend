"""
SFA — Pipeline principal
Orquesta: ingesta → normalización → cálculo SFA → guardado en DB
Se puede correr manualmente o desde el scheduler diario.
"""
import os
import logging
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

from backend.db.models import (
    SessionLocal, create_tables,
    Competition, Team, Player,
    StandingSnapshot, SFASeasonScore
)
from backend.ingest.fbref_ingest import run_full_ingestion
from backend.ingest.understat_ingest import fetch_league_players, merge_fbref_understat
from backend.engine.sfa_engine import (
    score_event, BASE_POINTS, COMPETITION_FACTORS
)

SEASON     = os.getenv("SEASON", "2024")
SEASON_STR = f"{SEASON}-{str(int(SEASON)+1)[2:]}"  # "2024-25"

# Mapa posición texto → código SFA
POSITION_MAP = {
    "FW":  "DEL",
    "MF":  "MC",
    "DF":  "DC",
    "GK":  "GK",
    "FW,MF": "EXT",
    "MF,FW": "EXT",
    "DF,MF": "LAT",
    "MF,DF": "LAT",
}

UNDERSTAT_LEAGUE_MAP = {
    "ESP-La Liga":              ("La_liga",    "La Liga"),
    "ENG-Premier League":       ("EPL",        "Premier League"),
    "EUR-Champions League":     (None,         "Champions League"),
    "GER-Bundesliga":           ("Bundesliga", "Bundesliga"),
    "ITA-Serie A":              ("Serie_A",    "Serie A"),
    "FRA-Ligue 1":              ("Ligue_1",    "Ligue 1"),
}


def estimate_sfa_season_pts(row: pd.Series, standings_df: pd.DataFrame, competition_name: str) -> float:
    """
    Calcula una estimación de puntos SFA de temporada para un jugador
    usando sus stats acumuladas + multiplicadores de contexto promedio.

    Nota: Esta es una ESTIMACIÓN basada en stats agregadas, no partido a partido.
    En v2 se calculará acción por acción con match logs completos.
    """
    total = 0.0

    # Posición aproximada en tabla (usamos mediana para contexto promedio)
    player_team = str(row.get("team", "")).strip()
    standings_map = {}
    if standings_df is not None and not standings_df.empty:
        for _, s in standings_df.iterrows():
            team_name = str(s.get("team", s.get("squad", ""))).strip()
            pos       = int(s.get("rank", s.get("Rk", 10)))
            standings_map[team_name.lower()] = pos

    player_team_pos = standings_map.get(player_team.lower(), 10)

    # Contexto promedio por competición
    comp_factor = COMPETITION_FACTORS.get(competition_name, 1.0)

    # ── Goles ──────────────────────────────────────────────────────────────
    goals = float(row.get("goals", 0))
    if goals > 0:
        # Multiplicadores promedio de temporada completa
        avg_m1 = 1.0
        avg_m3 = 1.15   # Promedio de minutos/marcador
        avg_m4 = 1.35   # Promedio de dificultad de disparo
        m_final = max(0.3, min(5.0, avg_m1 * comp_factor * avg_m3 * avg_m4))
        total += goals * 500 * m_final

    # ── Asistencias ────────────────────────────────────────────────────────
    assists = float(row.get("assists", 0))
    if assists > 0:
        m_final = max(0.3, min(5.0, 1.0 * comp_factor * 1.1))
        total += assists * 300 * m_final

    # ── xG sin gol ────────────────────────────────────────────────────────
    xg = float(row.get("xg", 0))
    xg_from_goals = goals * 0.35  # xG promedio por gol
    xg_no_goal = max(0, xg - xg_from_goals)
    if xg_no_goal > 0:
        total += xg_no_goal * 400 * max(0.3, min(5.0, comp_factor * 1.0))

    # ── xA sin asistencia ─────────────────────────────────────────────────
    xa = float(row.get("xa", 0))
    xa_no_assist = max(0, xa - assists * 0.3)
    if xa_no_assist > 0:
        total += xa_no_assist * 250 * max(0.3, min(5.0, comp_factor * 1.0))

    # ── Pases progresivos ─────────────────────────────────────────────────
    prog_passes = float(row.get("progressive_passes", 0))
    if prog_passes > 0:
        total += prog_passes * 18 * max(0.3, min(5.0, comp_factor * 1.05))

    # ── Conducciones progresivas ──────────────────────────────────────────
    prog_carries = float(row.get("progressive_carries", 0))
    if prog_carries > 0:
        total += prog_carries * 22 * max(0.3, min(5.0, comp_factor * 1.05))

    # ── Presiones exitosas ────────────────────────────────────────────────
    pressures = float(row.get("press_success", row.get("pressures", 0))) * 0.25
    if pressures > 0:
        total += pressures * 25 * max(0.3, min(5.0, comp_factor * 1.0))

    # ── Duelos ganados ────────────────────────────────────────────────────
    tackles   = float(row.get("tackles_won", 0))
    aerials   = float(row.get("aerials_won", 0))
    duels     = tackles + aerials
    if duels > 0:
        total += duels * 15 * max(0.3, min(5.0, comp_factor * 1.0))

    # ── Bloqueos ──────────────────────────────────────────────────────────
    blocks = float(row.get("blocks", 0))
    if blocks > 0:
        total += blocks * 30 * max(0.3, min(5.0, comp_factor * 1.0))

    return round(total, 2)


def upsert_player(db, row: pd.Series, team_obj, position: str) -> Player:
    """Crea o actualiza un jugador en la base de datos."""
    name    = str(row.get("player", "Unknown")).strip()
    fbref_id = str(row.get("player_id", f"auto_{name.replace(' ','_')}")).strip()

    player = db.query(Player).filter_by(fbref_id=fbref_id).first()
    if not player:
        player = Player(
            name=name,
            fbref_id=fbref_id,
            team_id=team_obj.id,
            position=position,
            nationality=str(row.get("nationality", "")).strip(),
        )
        db.add(player)
        db.flush()
    else:
        player.team_id   = team_obj.id
        player.position  = position

    return player


def upsert_team(db, team_name: str, competition_obj) -> Team:
    """Crea o actualiza un equipo en la base de datos."""
    team = db.query(Team).filter_by(
        name=team_name,
        competition_id=competition_obj.id
    ).first()
    if not team:
        team = Team(
            name=team_name,
            competition_id=competition_obj.id
        )
        db.add(team)
        db.flush()
    return team


def run_pipeline(leagues: list = None):
    """
    Pipeline completo: ingesta → cálculo SFA → guardado DB.
    """
    if leagues is None:
        raw = os.getenv("LEAGUES", "ESP-La Liga,ENG-Premier League")
        leagues = [l.strip() for l in raw.split(",")]

    log.info("=" * 55)
    log.info("🚀 SFA PIPELINE — INICIO")
    log.info(f"   Ligas: {leagues}")
    log.info(f"   Temporada: {SEASON_STR}")
    log.info("=" * 55)

    # 1. Crear tablas si no existen
    create_tables()

    db = SessionLocal()
    total_players_processed = 0

    try:
        for league_id in leagues:
            league_info = UNDERSTAT_LEAGUE_MAP.get(league_id, (None, league_id))
            understat_id   = league_info[0]
            competition_name = league_info[1]

            log.info(f"\n📋 Procesando: {competition_name}")

            # 2. Ingesta FBref
            log.info("  → Descargando de FBref...")
            fbref_data = run_full_ingestion([league_id])
            players_df = fbref_data.get("players", pd.DataFrame())
            standings_df = fbref_data.get("standings", pd.DataFrame())

            if players_df.empty:
                log.warning(f"  ⚠️  Sin datos FBref para {competition_name}")
                continue

            # 3. Ingesta Understat (si está disponible)
            if understat_id:
                log.info("  → Descargando de Understat...")
                understat_df = fetch_league_players(understat_id, int(SEASON))
                if not understat_df.empty:
                    players_df = merge_fbref_understat(players_df, understat_df)

            log.info(f"  ✅ {len(players_df)} jugadores para procesar")

            # 4. Crear/actualizar competición en DB
            comp = db.query(Competition).filter_by(name=competition_name).first()
            if not comp:
                comp_factor = COMPETITION_FACTORS.get(competition_name, 1.0)
                comp = Competition(
                    name=competition_name,
                    country=league_id.split("-")[0] if "-" in league_id else "EUR",
                    level=comp_factor
                )
                db.add(comp)
                db.flush()

            # 5. Guardar standings en DB
            if not standings_df.empty:
                log.info("  → Guardando tabla de posiciones...")
                for _, s_row in standings_df.iterrows():
                    team_name = str(s_row.get("team", s_row.get("squad", ""))).strip()
                    if not team_name:
                        continue
                    team = upsert_team(db, team_name, comp)
                    snap = StandingSnapshot(
                        competition_id=comp.id,
                        team_id=team.id,
                        season=SEASON_STR,
                        position=int(s_row.get("rank", s_row.get("Rk", 99))),
                    )
                    db.add(snap)

            # 6. Calcular y guardar SFA por jugador
            log.info("  → Calculando puntos SFA...")
            for _, row in players_df.iterrows():
                team_name = str(row.get("team", "Unknown")).strip()
                if not team_name or team_name == "0":
                    continue

                team = upsert_team(db, team_name, comp)

                # Mapear posición
                raw_pos  = str(row.get("pos", "MF")).split(",")[0].strip()
                position = POSITION_MAP.get(raw_pos, "MC")

                player = upsert_player(db, row, team, position)

                # Calcular puntos SFA estimados
                sfa_pts = estimate_sfa_season_pts(row, standings_df, competition_name)

                # Guardar o actualizar season score
                season_score = db.query(SFASeasonScore).filter_by(
                    player_id=player.id,
                    season=SEASON_STR
                ).first()

                if not season_score:
                    season_score = SFASeasonScore(
                        player_id=player.id,
                        season=SEASON_STR,
                        total_pts=sfa_pts,
                        matches_played=int(float(row.get("minutes_90s", 0)) * 90 // 90),
                    )
                    db.add(season_score)
                else:
                    season_score.total_pts     = sfa_pts
                    season_score.last_updated  = datetime.utcnow()

                total_players_processed += 1

            db.commit()
            log.info(f"  ✅ {competition_name} guardado en DB")

    except Exception as e:
        db.rollback()
        log.error(f"❌ Error en pipeline: {e}")
        raise
    finally:
        db.close()

    log.info("\n" + "=" * 55)
    log.info(f"✅ PIPELINE COMPLETADO — {total_players_processed} jugadores procesados")
    log.info("=" * 55)


if __name__ == "__main__":
    run_pipeline()
