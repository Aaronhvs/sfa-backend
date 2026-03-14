"""
ingest_team.py — Reingestar un equipo específico sin tocar el resto de la DB.

Uso:
    python ingest_team.py --team "Bayern München" --league "Champions League"
    python ingest_team.py --team "Barcelona" --league "La Liga"
    python ingest_team.py --team "Real Madrid" --league "La Liga" --league "Champions League"

Ligas disponibles:
    La Liga | Premier League | Bundesliga | Serie A | Ligue 1 | Champions League
"""
import argparse, sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from api_football_ingest_v5 import (
    fetch_standings, fetch_team_fixtures, fetch_fixture_events,
    fetch_fixture_players, parse_fixture_player_stats, calc_match_sfa,
    get_stage, SEASON, SEASON_STR, LEAGUES,
)
from backend.db.models import (
    SessionLocal, create_tables, Competition, Team, Player,
    StandingSnapshot, SFASeasonScore, PlayerStats, PlayerEvent
)
from sqlalchemy import text
from datetime import datetime, timezone

POSITION_MAP = {"Attacker": "DEL", "Midfielder": "MC", "Defender": "DC", "Goalkeeper": "GK"}


def find_league_info(league_name):
    for l in LEAGUES:
        if l["name"].lower() == league_name.lower():
            return l
    return None


def ingest_team(team_name_query: str, league_names: list[str]):
    create_tables()
    db = SessionLocal()

    for league_name in league_names:
        league_info = find_league_info(league_name)
        if not league_info:
            print(f"❌ Liga no encontrada: {league_name}")
            print(f"   Disponibles: {[l['name'] for l in LEAGUES]}")
            continue

        league_id = league_info["id"]
        print(f"\n{'─'*60}")
        print(f"📋 {league_name} — buscando '{team_name_query}'")

        standings = fetch_standings(league_id)
        time.sleep(1)
        if not standings:
            print(f"  ⚠️  Sin standings para {league_name}")
            continue

        # Buscar el equipo (matching parcial)
        team_data = next(
            (s for s in standings if team_name_query.lower() in s["team_name"].lower()),
            None
        )
        if not team_data:
            print(f"  ❌ Equipo '{team_name_query}' no encontrado en {league_name}")
            print(f"     Equipos disponibles: {[s['team_name'] for s in standings]}")
            continue

        team_id   = team_data["team_id"]
        team_name = team_data["team_name"]
        team_pos  = team_data["position"]
        pos_cache = {s["team_id"]: s["position"] for s in standings}

        print(f"  ✅ Encontrado: {team_name} (pos #{team_pos})")

        # Asegurar Competition en DB
        comp = db.query(Competition).filter_by(name=league_name).first()
        if not comp:
            comp = Competition(name=league_name, country=league_info["country"],
                               level=league_info["comp_factor"])
            db.add(comp); db.flush()

        # Asegurar Team en DB
        team_obj = db.query(Team).filter_by(name=team_name, competition_id=comp.id).first()
        if not team_obj:
            team_obj = Team(name=team_name, competition_id=comp.id)
            db.add(team_obj); db.flush()
        db.commit()

        # Fixtures
        fixtures = fetch_team_fixtures(team_id, league_id)
        time.sleep(1)
        if not fixtures:
            print(f"  ⚠️  Sin fixtures")
            continue

        print(f"  📅 {len(fixtures)} partidos encontrados")
        player_accumulator = {}

        for i, fixture_data in enumerate(fixtures):
            fix_id        = fixture_data["fixture"]["id"]
            home_id       = fixture_data["teams"]["home"]["id"]
            away_id       = fixture_data["teams"]["away"]["id"]
            home_name     = fixture_data["teams"]["home"]["name"]
            away_name     = fixture_data["teams"]["away"]["name"]
            is_home       = (home_id == team_id)
            opponent_id   = away_id if is_home else home_id
            opponent_name = away_name if is_home else home_name
            opponent_pos  = pos_cache.get(opponent_id, 10)
            stage         = get_stage(fixture_data)

            events      = fetch_fixture_events(fix_id)
            time.sleep(0.5)
            fix_players = fetch_fixture_players(fix_id)
            time.sleep(0.5)

            player_stats_map = parse_fixture_player_stats(fix_players, team_id)
            if not player_stats_map:
                continue

            print(f"    [{i+1}/{len(fixtures)}] {home_name} vs {away_name}", end="\r")

            for api_player_id, pstats in player_stats_map.items():
                if (pstats.get("minutes") or 0) < 20:
                    continue

                bd, match_pts, match_events = calc_match_sfa(
                    player_stats    = pstats,
                    events          = events,
                    home_team_id    = home_id,
                    player_team_id  = team_id,
                    opponent_pos    = opponent_pos,
                    player_team_pos = team_pos,
                    league_name     = league_name,
                    stage           = stage,
                )

                if api_player_id not in player_accumulator:
                    player_accumulator[api_player_id] = {
                        "name": pstats["name"], "position": pstats["position"],
                        "total_pts": 0.0, "appearances": 0, "minutes": 0,
                        "breakdown": {}, "pending_events": [],
                        "goals_normal": 0, "goals_penalty": 0, "assists": 0,
                        "shots_on": 0, "passes_key": 0, "dribbles_success": 0,
                        "duels_won": 0, "tackles": 0, "interceptions": 0, "blocks": 0,
                    }

                acc = player_accumulator[api_player_id]
                acc["total_pts"]   += match_pts
                acc["appearances"] += 1
                acc["minutes"]     += pstats.get("minutes", 0) or 0

                for ev in match_events:
                    acc["pending_events"].append({
                        **ev,
                        "fixture_id":   fix_id,
                        "home_team":    home_name,
                        "away_team":    away_name,
                        "opponent":     opponent_name,
                        "opponent_pos": opponent_pos,
                    })

                for stat in ["goals_normal","goals_penalty","assists","shots_on",
                             "passes_key","dribbles_success","duels_won","tackles",
                             "interceptions","blocks"]:
                    acc[stat] += pstats.get(stat.replace("goals_normal","goals"), 0) or 0

                for cat, val in bd.items():
                    if cat not in acc["breakdown"]:
                        acc["breakdown"][cat] = {"count": 0, "pts": 0,
                                                  "icon": val.get("icon",""),
                                                  "color": val.get("color","#fff")}
                        if "unit" in val:
                            acc["breakdown"][cat]["unit"] = val["unit"]
                    acc["breakdown"][cat]["count"] += val.get("count", 0)
                    acc["breakdown"][cat]["pts"]   += val.get("pts", 0)

        # Guardar en DB
        print(f"\n  💾 Guardando {len(player_accumulator)} jugadores...")
        saved = 0
        now = datetime.now(timezone.utc)

        for api_player_id, acc in player_accumulator.items():
            if acc["appearances"] == 0:
                continue

            position = POSITION_MAP.get(acc["position"], "MC")

            player = db.query(Player).filter(Player.name == acc["name"]).first()
            if not player:
                player = Player(name=acc["name"], team_id=team_obj.id, position=position)
                db.add(player); db.flush()
            elif player.position == "MC" and position != "MC":
                player.position = position

            season_key = f"{SEASON_STR}::{league_name}"
            score = db.query(SFASeasonScore).filter_by(
                player_id=player.id, season=season_key
            ).first()
            if not score:
                score = SFASeasonScore(player_id=player.id, season=season_key)
                db.add(score)
            score.total_pts      = round(acc["total_pts"], 0)
            score.matches_played = acc["appearances"]
            score.breakdown_json = json.dumps(acc["breakdown"], ensure_ascii=False)
            score.last_updated   = now

            # PlayerStats
            ps = db.query(PlayerStats).filter_by(
                player_id=player.id, season=SEASON_STR, competition=league_name
            ).first()
            if not ps:
                ps = PlayerStats(player_id=player.id, season=SEASON_STR,
                                 competition=league_name)
                db.add(ps)
            ps.goals_normal = acc["goals_normal"]; ps.assists = acc["assists"]
            ps.shots_on = acc["shots_on"]; ps.passes_key = acc["passes_key"]
            ps.dribbles_success = acc["dribbles_success"]; ps.duels_won = acc["duels_won"]
            ps.tackles = acc["tackles"]; ps.interceptions = acc["interceptions"]
            ps.blocks = acc["blocks"]; ps.minutes = acc["minutes"]
            ps.appearances = acc["appearances"]; ps.last_updated = now

            # PlayerEvents — borrar y reinsertar
            db.query(PlayerEvent).filter_by(
                player_id=player.id, season=SEASON_STR, competition=league_name
            ).delete()
            for ev in acc.get("pending_events", []):
                db.add(PlayerEvent(
                    player_id=player.id, season=SEASON_STR, competition=league_name,
                    stage=ev.get("stage", "regular"), fixture_id=ev["fixture_id"],
                    home_team=ev["home_team"], away_team=ev["away_team"],
                    opponent=ev["opponent"], opponent_pos=ev.get("opponent_pos"),
                    minute=ev["minute"], event_type=ev["event_type"],
                    score_before=ev.get("score_before"), score_diff=ev.get("score_diff"),
                    m1=ev.get("m1"), m2=ev.get("m2"), m3=ev.get("m3"),
                    pts=ev["pts"], last_updated=now,
                ))

            saved += 1

        db.commit()
        print(f"  ✅ {saved} jugadores guardados en {league_name}")

    db.close()
    print(f"\n✅ Listo")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--team",   required=True, help="Nombre del equipo (parcial)")
    parser.add_argument("--league", required=True, action="append",
                        help="Liga (puede repetirse para múltiples ligas)")
    args = parser.parse_args()
    ingest_team(args.team, args.league)
