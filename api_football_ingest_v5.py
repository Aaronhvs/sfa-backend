"""
SFA — Ingesta desde API-Football v4
- Datos por partido: fixtures + events + players
- M1 real: posición del rival en tabla
- M2 real: competición × instancia (group/round_of_16/quarter/semi/final)
- M3 real: minuto × marcador al momento de la acción
- M4: psxg fijo 0.32 (sin datos por disparo en este plan)
- Top 6 por liga + Champions League completa
"""
import requests, time, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

from backend.db.models import create_tables, SessionLocal, Competition, Team, Player, StandingSnapshot, SFASeasonScore, PlayerStats, PlayerEvent
from backend.engine.sfa_engine import score_event, COMPETITION_FACTORS
from sqlalchemy import text
from datetime import datetime, timezone

API_KEY    = os.getenv("API_FOOTBALL_KEY", "0f896f6a0c76ae2c79b9361cf8f7e515")
API_BASE   = "https://v3.football.api-sports.io"
HEADERS    = {"x-apisports-key": API_KEY}
SEASON     = 2024
SEASON_STR = "2024-25"

LEAGUES = [
    {"id": 140, "name": "La Liga",          "country": "ESP", "comp_factor": 1.0, "top_n": 6},
    {"id": 39,  "name": "Premier League",   "country": "ENG", "comp_factor": 1.0, "top_n": 6},
    {"id": 78,  "name": "Bundesliga",       "country": "GER", "comp_factor": 1.0, "top_n": 6},
    {"id": 135, "name": "Serie A",          "country": "ITA", "comp_factor": 1.0, "top_n": 6},
    {"id": 61,  "name": "Ligue 1",          "country": "FRA", "comp_factor": 1.0, "top_n": 6},
    {"id": 2,   "name": "Champions League", "country": "EUR", "comp_factor": 1.5, "top_n": 24},
]

POSITION_MAP = {"Attacker": "DEL", "Midfielder": "MC", "Defender": "DC", "Goalkeeper": "GK"}

# Mapeo de rondas de Champions a instancias del motor SFA
ROUND_TO_STAGE = {
    # Formato viejo
    "group stage":          "group",
    "round of 32":          "round_of_16",
    "last 16":              "round_of_16",
    "3rd place final":      "semi",
    # Formato UCL 2024-25 (League Stage - N)
    "league stage":         "group",
    # Eliminatorias — orden importa: más específico primero
    "quarter-finals":       "quarter",
    "quarter finals":       "quarter",
    "semi-finals":          "semi",
    "semi finals":          "semi",
    "round of 16":          "round_of_16",
    # Final siempre al final para no matchear "semi-finals"
    "final":                "final",
}

requests_used = 0
requests_limit = 7000  # dejamos margen de 500


def api_get(endpoint, params=None, retries=3):
    global requests_used
    url  = f"{API_BASE}/{endpoint}"
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, params=params or {}, timeout=20)
            remaining = resp.headers.get("x-ratelimit-requests-remaining", "?")
            requests_used += 1
            if requests_used % 100 == 0:
                print(f"  📊 Requests usados: {requests_used} | Restantes hoy: {remaining}")
            resp.raise_for_status()
            data = resp.json()
            if data.get("errors"):
                err = str(data["errors"])
                if "rateLimit" in err:
                    print(f"  ⏳ Rate limit — esperando 65s...")
                    time.sleep(65)
                    continue
                print(f"  ⚠️  Error API: {err}")
                return {}
            return data
        except requests.exceptions.Timeout:
            print(f"  ⏳ Timeout (intento {attempt+1}/{retries}), reintentando...")
            time.sleep(10)
        except Exception as e:
            print(f"  ❌ Error: {e}")
            return {}
    return {}


# ── STANDINGS ─────────────────────────────────────────────────────────────────

def fetch_standings(league_id):
    data = api_get("standings", {"league": league_id, "season": SEASON})
    try:
        standings = data["response"][0]["league"]["standings"][0]
        return [
            {
                "team_id":   s["team"]["id"],
                "team_name": s["team"]["name"],
                "position":  s["rank"],
                "points":    s["points"],
            }
            for s in standings
        ]
    except (KeyError, IndexError):
        return []


# ── FIXTURES ──────────────────────────────────────────────────────────────────

def fetch_team_fixtures(team_id, league_id):
    """Retorna todos los partidos de un equipo en la liga/temporada."""
    data = api_get("fixtures", {
        "team":   team_id,
        "league": league_id,
        "season": SEASON,
        "status": "FT",  # solo partidos terminados
    })
    return data.get("response", [])


def fetch_fixture_events(fixture_id):
    """Eventos de un partido: goles, tarjetas, sustituciones."""
    data = api_get("fixtures/events", {"fixture": fixture_id})
    return data.get("response", [])


def fetch_fixture_players(fixture_id):
    """Stats de jugadores en un partido específico."""
    data = api_get("fixtures/players", {"fixture": fixture_id})
    return data.get("response", [])


# ── HELPERS ───────────────────────────────────────────────────────────────────

def get_stage(fixture_data):
    """Extrae la instancia del partido (group, round_of_16, semi, final)."""
    round_str   = fixture_data.get("league", {}).get("round", "").lower()
    league_name = fixture_data.get("league", {}).get("name", "")
    for key, stage in ROUND_TO_STAGE.items():
        if key in round_str:
            return stage
    if "champion" in league_name.lower():
        print(f"      [⚠️  stage no reconocido] round='{round_str}'")
    return "group" if "league stage" in round_str else "regular"


def build_score_timeline(events):
    """
    Construye un dict {minute: (home_goals, away_goals)} con el marcador
    acumulado en cada minuto donde hubo gol.
    """
    timeline = {}
    home_goals = 0
    away_goals = 0

    # Ordenar eventos por minuto
    goals = [e for e in events if e.get("type") == "Goal" and e.get("detail") != "Missed Penalty"]
    goals.sort(key=lambda e: (e.get("time", {}).get("elapsed") or 0))

    for g in goals:
        minute = g.get("time", {}).get("elapsed") or 0
        extra  = g.get("time", {}).get("extra") or 0
        real_minute = minute + extra

        team_name = g.get("team", {}).get("name", "")
        timeline[real_minute] = (home_goals, away_goals, team_name)

        # Actualizar marcador
        if g.get("team", {}).get("id") == g.get("fixture", {}).get("homeTeam", {}).get("id"):
            home_goals += 1
        else:
            away_goals += 1

    return timeline, home_goals, away_goals


def get_score_at_minute(events, minute, home_team_id):
    """
    Retorna (score_diff, home_goals, away_goals) al momento de la acción.
    score_diff: desde perspectiva del jugador (positivo = ganando)
    """
    home_g = 0
    away_g = 0
    goals = [
        e for e in events
        if e.get("type") == "Goal"
        and e.get("detail") != "Missed Penalty"
        and (e.get("time", {}).get("elapsed") or 0) < minute
    ]
    for g in goals:
        if g.get("team", {}).get("id") == home_team_id:
            home_g += 1
        else:
            away_g += 1
    return home_g, away_g


def parse_fixture_player_stats(fixture_players_data, team_id):
    """
    Extrae stats de jugadores de un partido.
    Retorna dict: {player_id: {goals, assists, shots_on, passes_key, ...}}
    """
    result = {}
    for team_data in fixture_players_data:
        if team_data.get("team", {}).get("id") != team_id:
            continue
        for p in team_data.get("players", []):
            pid   = p.get("player", {}).get("id")
            pname = p.get("player", {}).get("name", "")
            s     = p.get("statistics", [{}])[0]
            if not pid:
                continue
            result[pid] = {
                "name":             pname,
                "position":         s.get("games", {}).get("position", "Midfielder"),
                "minutes":          s.get("games", {}).get("minutes") or 0,
                "goals":            s.get("goals", {}).get("total") or 0,
                "assists":          s.get("goals", {}).get("assists") or 0,
                "shots_on":         s.get("shots", {}).get("on") or 0,
                "passes_key":       s.get("passes", {}).get("key") or 0,
                "dribbles_success": s.get("dribbles", {}).get("success") or 0,
                "duels_won":        s.get("duels", {}).get("won") or 0,
                "tackles":          s.get("tackles", {}).get("total") or 0,
                "interceptions":    s.get("tackles", {}).get("interceptions") or 0,
                "blocks":           s.get("tackles", {}).get("blocks") or 0,
            }
    return result


# ── CÁLCULO SFA POR PARTIDO ───────────────────────────────────────────────────

def calc_match_sfa(
    player_stats,       # dict con stats del jugador en este partido
    events,             # lista de eventos del partido
    home_team_id,       # ID del equipo local
    player_team_id,     # ID del equipo del jugador
    opponent_pos,       # posición del rival en tabla
    player_team_pos,    # posición del equipo del jugador
    league_name,        # nombre de la competición
    stage,              # instancia del partido
):
    """
    Calcula puntos SFA para un jugador en un partido específico.
    Usa M1, M2, M3 reales. M4 fijo (sin PSxG por partido).
    """
    breakdown = {}
    pending_events = []
    total = 0.0
    cf = COMPETITION_FACTORS.get(league_name, 1.0)

    # Encontrar goles del jugador en los eventos
    player_name = player_stats.get("name", "")
    player_goals_events = [
        e for e in events
        if e.get("type") == "Goal"
        and e.get("detail") != "Missed Penalty"
        and e.get("team", {}).get("id") == player_team_id
        and (
            (e.get("player", {}).get("name") or "").lower() in player_name.lower()
            or player_name.lower() in (e.get("player", {}).get("name") or "").lower()
        )
    ]

    player_assist_events = [
        e for e in events
        if e.get("type") == "Goal"
        and e.get("detail") != "Missed Penalty"
        and e.get("team", {}).get("id") == player_team_id
        and (
            (e.get("assist", {}).get("name") or "").lower() in player_name.lower()
            or player_name.lower() in (e.get("assist", {}).get("name") or "").lower()
        )
        and e.get("assist", {}).get("name")  # que haya asistente registrado
    ]

    # ── Goles con M3 real ────────────────────────────────────────────────────
    goals_normal = 0
    goals_penalty = 0

    for g_event in player_goals_events:
        minute = (g_event.get("time", {}).get("elapsed") or 0)
        extra  = (g_event.get("time", {}).get("extra") or 0)
        real_min = minute + extra
        is_pen = g_event.get("detail") == "Penalty"

        # Marcador ANTES de este gol
        home_g, away_g = get_score_at_minute(events, real_min, home_team_id)

        if player_team_id == home_team_id:
            score_diff = home_g - away_g
        else:
            score_diff = away_g - home_g

        if is_pen:
            r = score_event("goal_penalty", player_team_pos, opponent_pos,
                           league_name, stage, real_min, score_diff,
                           is_penalty=True, psxg=0.75)
            goals_penalty += 1
            key = "Goles (penal)"
            if key not in breakdown:
                breakdown[key] = {"count": 0, "pts": 0, "icon": "🥅", "color": "#f0c040"}
            breakdown[key]["count"] += 1
            breakdown[key]["pts"]   += round(r["total_pts"])
            event_type = "goal_penalty"
        else:
            r = score_event("goal", player_team_pos, opponent_pos,
                           league_name, stage, real_min, score_diff,
                           psxg=0.32)
            goals_normal += 1
            key = "Goles (jugada)"
            if key not in breakdown:
                breakdown[key] = {"count": 0, "pts": 0, "icon": "⚽", "color": "#22d47a"}
            breakdown[key]["count"] += 1
            breakdown[key]["pts"]   += round(r["total_pts"])
            event_type = "goal"

        total += r["total_pts"]
        score_before_str = f"{home_g}-{away_g}" if player_team_id == home_team_id else f"{away_g}-{home_g}"
        pending_events.append({
            "event_type":   event_type,
            "minute":       real_min,
            "score_before": score_before_str,
            "score_diff":   score_diff,
            "m1":           r.get("m1"),
            "m2":           r.get("m2"),
            "m3":           r.get("m3"),
            "pts":          round(r["total_pts"]),
        })


    # ── Asistencias con M3 real ──────────────────────────────────────────────
    assists = 0
    for a_event in player_assist_events:
        minute   = (a_event.get("time", {}).get("elapsed") or 0)
        extra    = (a_event.get("time", {}).get("extra") or 0)
        real_min = minute + extra

        home_g, away_g = get_score_at_minute(events, real_min, home_team_id)
        if player_team_id == home_team_id:
            score_diff = home_g - away_g
        else:
            score_diff = away_g - home_g

        r = score_event("assist", player_team_pos, opponent_pos,
                       league_name, stage, real_min, score_diff)
        total += r["total_pts"]
        assists += 1
        if "Asistencias" not in breakdown:
            breakdown["Asistencias"] = {"count": 0, "pts": 0, "icon": "🎯", "color": "#3b9eff"}
        breakdown["Asistencias"]["count"] += 1
        breakdown["Asistencias"]["pts"]   += round(r["total_pts"])
        a_home_g, a_away_g = get_score_at_minute(events, real_min, home_team_id)
        a_score_before = f"{a_home_g}-{a_away_g}" if player_team_id == home_team_id else f"{a_away_g}-{a_home_g}"
        pending_events.append({
            "event_type":   "assist",
            "minute":       real_min,
            "score_before": a_score_before,
            "score_diff":   score_diff,
            "m1":           r.get("m1"),
            "m2":           r.get("m2"),
            "m3":           r.get("m3"),
            "pts":          round(r["total_pts"]),
        })

    # ── xG sin gol (desde shots_on del partido) ──────────────────────────────
    shots_on   = player_stats.get("shots_on", 0) or 0
    total_goals = goals_normal + goals_penalty
    xg_est     = shots_on * 0.12
    xg_no_goal = max(0, xg_est - total_goals * 0.32)
    if xg_no_goal > 0.2:
        r = score_event("shot", player_team_pos, opponent_pos,
                       league_name, stage, 55, 0, xg=xg_no_goal)
        total += r["total_pts"]
        breakdown["Disparos (xG)"] = {"count": round(xg_no_goal, 1), "pts": round(r["total_pts"]),
                                       "icon": "🔫", "color": "#ff8c42", "unit": "xG"}

    # ── Pases clave ──────────────────────────────────────────────────────────
    passes_key = player_stats.get("passes_key", 0) or 0
    if passes_key > 0:
        xa_est    = passes_key * 0.18
        xa_no_ast = max(0, xa_est - assists * 0.3)
        if xa_no_ast > 0.1:
            r = score_event("key_pass", player_team_pos, opponent_pos,
                           league_name, stage, 55, 0, xa=xa_no_ast)
            total += r["total_pts"]
            breakdown["Pases clave"] = {"count": passes_key, "pts": round(r["total_pts"]),
                                         "icon": "🔑", "color": "#a855f7"}

    # ── Stats defensivas/físicas (M1 y M2 aplican, M3 no por naturaleza) ────
    dribbles = player_stats.get("dribbles_success", 0) or 0
    if dribbles > 0:
        m1 = max(0.5, min(2.0, 1.0 + (player_team_pos - opponent_pos) / 20.0))
        pts = round(dribbles * 22 * cf * m1)
        total += pts
        breakdown["Regates"] = {"count": dribbles, "pts": pts, "icon": "🏃", "color": "#06b6d4"}

    duels = player_stats.get("duels_won", 0) or 0
    if duels > 0:
        m1  = max(0.5, min(2.0, 1.0 + (player_team_pos - opponent_pos) / 20.0))
        pts = round(duels * 10 * cf * m1)
        total += pts
        breakdown["Duelos ganados"] = {"count": duels, "pts": pts, "icon": "🤼", "color": "#f97316"}

    tck = (player_stats.get("tackles", 0) or 0) + (player_stats.get("interceptions", 0) or 0)
    if tck > 0:
        m1  = max(0.5, min(2.0, 1.0 + (player_team_pos - opponent_pos) / 20.0))
        pts = round(tck * 18 * cf * m1)
        total += pts
        breakdown["Tackles / Intercep."] = {"count": tck, "pts": pts, "icon": "🛡️", "color": "#ef4444"}

    blocks = player_stats.get("blocks", 0) or 0
    if blocks > 0:
        pts = round(blocks * 30 * cf)
        total += pts
        breakdown["Bloqueos"] = {"count": blocks, "pts": pts, "icon": "🧱", "color": "#8b5cf6"}

    return breakdown, round(total, 2), pending_events


# ── PIPELINE PRINCIPAL ────────────────────────────────────────────────────────

def run_pipeline():
    print("\n" + "="*60)
    print("🚀 SFA — Ingesta v4 (eventos por partido)")
    print(f"   Temporada: {SEASON_STR}")
    print(f"   M1✅ M2✅ M3✅ M4(fijo)")
    print("="*60)

    create_tables()
    db = SessionLocal()

    # Asegurar columnas extra
    for col in ["photo_url TEXT", "breakdown_json TEXT"]:
        try:
            db.execute(text(f"ALTER TABLE players ADD COLUMN {col}"))
            db.commit()
        except Exception:
            pass

    # Dict de posiciones por liga para lookup rápido
    # {league_name: {team_id: position}}
    standings_cache = {}

    total_players = 0
    total_fixtures = 0

    try:
        for league_info in LEAGUES:
            if requests_used >= requests_limit:
                print(f"\n⚠️  Límite de requests alcanzado ({requests_used})")
                break

            league_id   = league_info["id"]
            league_name = league_info["name"]
            top_n       = league_info["top_n"]

            print(f"\n{'─'*60}")
            print(f"📋 {league_name} (top {top_n} equipos)")

            # ── Standings ────────────────────────────────────────────────────
            standings = fetch_standings(league_id)
            time.sleep(1)

            if not standings:
                print(f"  ⚠️  Sin datos de standings")
                continue

            # Cache de posiciones {team_id: position}
            pos_cache = {s["team_id"]: s["position"] for s in standings}
            standings_cache[league_name] = pos_cache

            # Guardar en DB
            comp = db.query(Competition).filter_by(name=league_name).first()
            if not comp:
                comp = Competition(name=league_name,
                                   country=league_info["country"],
                                   level=league_info["comp_factor"])
                db.add(comp)
                db.flush()

            team_db_map = {}  # {team_name: Team object}
            for s in standings:
                team = db.query(Team).filter_by(name=s["team_name"],
                                                 competition_id=comp.id).first()
                if not team:
                    team = Team(name=s["team_name"], competition_id=comp.id)
                    db.add(team)
                    db.flush()
                snap = StandingSnapshot(
                    competition_id=comp.id, team_id=team.id,
                    season=SEASON_STR, position=s["position"], points=s["points"]
                )
                db.add(snap)
                team_db_map[s["team_name"]] = team
            db.commit()

            # ── Procesar equipos ──────────────────────────────────────────────
            top_teams = standings[:top_n]

            # Acumulador de stats por jugador (para la temporada completa)
            # {player_api_id: {name, position, season_breakdown, season_total, appearances, minutes}}
            player_accumulator = {}

            for team_data in top_teams:
                if requests_used >= requests_limit:
                    break

                team_name = team_data["team_name"]
                team_id   = team_data["team_id"]
                team_pos  = team_data["position"]

                print(f"\n  🏟️  {team_name} (pos #{team_pos})")

                # Fixtures del equipo
                fixtures = fetch_team_fixtures(team_id, league_id)
                time.sleep(1)

                if not fixtures:
                    print(f"    ⚠️  Sin fixtures")
                    continue

                print(f"    {len(fixtures)} partidos encontrados")
                team_fixture_count = 0

                for fixture_data in fixtures:
                    if requests_used >= requests_limit:
                        break

                    fix_id      = fixture_data["fixture"]["id"]
                    home_id     = fixture_data["teams"]["home"]["id"]
                    away_id     = fixture_data["teams"]["away"]["id"]
                    home_name   = fixture_data["teams"]["home"]["name"]
                    away_name   = fixture_data["teams"]["away"]["name"]
                    is_home     = (home_id == team_id)
                    opponent_id   = away_id if is_home else home_id
                    opponent_name = away_name if is_home else home_name
                    opponent_pos  = pos_cache.get(opponent_id, 10)  # default 10 si no está en top
                    stage = get_stage(fixture_data)

                    # Eventos del partido
                    events = fetch_fixture_events(fix_id)
                    time.sleep(0.5)

                    # Stats de jugadores en este partido
                    fix_players = fetch_fixture_players(fix_id)
                    time.sleep(0.5)

                    player_stats_map = parse_fixture_player_stats(fix_players, team_id)

                    if not player_stats_map:
                        continue

                    team_fixture_count += 1
                    total_fixtures += 1

                    # Calcular SFA para cada jugador del equipo en este partido
                    for api_player_id, pstats in player_stats_map.items():
                        if (pstats.get("minutes") or 0) < 20:
                            continue  # ignorar jugadores que casi no jugaron

                        bd, match_pts, match_events = calc_match_sfa(
                            player_stats   = pstats,
                            events         = events,
                            home_team_id   = home_id,
                            player_team_id = team_id,
                            opponent_pos   = opponent_pos,
                            player_team_pos= team_pos,
                            league_name    = league_name,
                            stage          = stage,
                        )

                        # Acumular en el dict del jugador
                        if api_player_id not in player_accumulator:
                            player_accumulator[api_player_id] = {
                                "name":        pstats["name"],
                                "position":    pstats["position"],
                                "total_pts":   0.0,
                                "appearances": 0,
                                "minutes":     0,
                                "breakdown":   {},
                                # Stats brutas acumuladas
                                "goals_normal":     0,
                                "goals_penalty":    0,
                                "assists":          0,
                                "shots_on":         0,
                                "passes_key":       0,
                                "dribbles_success": 0,
                                "duels_won":        0,
                                "tackles":          0,
                                "interceptions":    0,
                                "blocks":           0,
                                "pending_events":   [],
                            }

                        acc = player_accumulator[api_player_id]
                        acc["total_pts"]   += match_pts
                        # Guardar eventos individuales con contexto del partido
                        for ev in match_events:
                            acc["pending_events"].append({
                                **ev,
                                "fixture_id":   fix_id,
                                "home_team":    home_name,
                                "away_team":    away_name,
                                "opponent":     opponent_name,
                                "opponent_pos": opponent_pos,
                            })
                        acc["appearances"] += 1
                        acc["minutes"]     += pstats.get("minutes", 0) or 0

                        # Acumular stats brutas
                        acc["goals_normal"]     += pstats.get("goals", 0) or 0
                        acc["assists"]          += pstats.get("assists", 0) or 0
                        acc["shots_on"]         += pstats.get("shots_on", 0) or 0
                        acc["passes_key"]       += pstats.get("passes_key", 0) or 0
                        acc["dribbles_success"] += pstats.get("dribbles_success", 0) or 0
                        acc["duels_won"]        += pstats.get("duels_won", 0) or 0
                        acc["tackles"]          += pstats.get("tackles", 0) or 0
                        acc["interceptions"]    += pstats.get("interceptions", 0) or 0
                        acc["blocks"]           += pstats.get("blocks", 0) or 0

                        # Merge breakdown (sumar pts por categoría)
                        for cat, val in bd.items():
                            if cat not in acc["breakdown"]:
                                acc["breakdown"][cat] = {
                                    "count": 0, "pts": 0,
                                    "icon": val.get("icon", ""),
                                    "color": val.get("color", "#fff"),
                                }
                                if "unit" in val:
                                    acc["breakdown"][cat]["unit"] = val["unit"]
                            acc["breakdown"][cat]["count"] += val.get("count", 0)
                            acc["breakdown"][cat]["pts"]   += val.get("pts", 0)

                print(f"    ✅ {team_fixture_count} partidos procesados")

                # ── Guardar acumulado en DB ────────────────────────────────
                team_obj = team_db_map.get(team_name)
                if not team_obj:
                    team_obj = db.query(Team).filter_by(name=team_name,
                                                         competition_id=comp.id).first()

                saved_count = 0
                for api_pid, acc in player_accumulator.items():
                    if acc["appearances"] == 0 or acc["minutes"] < 90:
                        continue

                    position = POSITION_MAP.get(acc["position"], "MC")
                    name     = acc["name"]

                    # Buscar o crear jugador
                    player = db.query(Player).filter(Player.name == name).first()
                    if not player:
                        player = Player(name=name, team_id=team_obj.id, position=position)
                        db.add(player)
                        db.flush()

                    # Recalcular % contribución en breakdown
                    total_bd_pts = sum(v["pts"] for v in acc["breakdown"].values())
                    if total_bd_pts > 0:
                        for cat in acc["breakdown"]:
                            acc["breakdown"][cat]["pct"] = round(
                                acc["breakdown"][cat]["pts"] / total_bd_pts * 100
                            )

                    # Season score
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
                    score.last_updated   = datetime.now(timezone.utc)

                    # PlayerStats
                    ps = db.query(PlayerStats).filter_by(
                        player_id=player.id, season=SEASON_STR, competition=league_name
                    ).first()
                    if not ps:
                        ps = PlayerStats(player_id=player.id, season=SEASON_STR,
                                         competition=league_name)
                        db.add(ps)
                    ps.goals_normal      = acc["goals_normal"]
                    ps.goals_penalty     = acc["goals_penalty"]
                    ps.assists           = acc["assists"]
                    ps.shots_on          = acc["shots_on"]
                    ps.passes_key        = acc["passes_key"]
                    ps.dribbles_success  = acc["dribbles_success"]
                    ps.duels_won         = acc["duels_won"]
                    ps.tackles           = acc["tackles"]
                    ps.interceptions     = acc["interceptions"]
                    ps.blocks            = acc["blocks"]
                    ps.minutes           = acc["minutes"]
                    ps.appearances       = acc["appearances"]
                    ps.last_updated      = datetime.now(timezone.utc)

                    # Guardar PlayerEvents individuales
                    # Borrar eventos previos de esta temporada+competición para este jugador
                    db.query(PlayerEvent).filter_by(
                        player_id=player.id,
                        season=SEASON_STR,
                        competition=league_name
                    ).delete()
                    now = datetime.now(timezone.utc)
                    for ev in acc.get("pending_events", []):
                        db.add(PlayerEvent(
                            player_id    = player.id,
                            season       = SEASON_STR,
                            competition  = league_name,
                            stage        = ev.get("stage", stage),
                            fixture_id   = ev["fixture_id"],
                            home_team    = ev["home_team"],
                            away_team    = ev["away_team"],
                            opponent     = ev["opponent"],
                            opponent_pos = ev.get("opponent_pos"),
                            minute       = ev["minute"],
                            event_type   = ev["event_type"],
                            score_before = ev.get("score_before"),
                            score_diff   = ev.get("score_diff"),
                            m1           = ev.get("m1"),
                            m2           = ev.get("m2"),
                            m3           = ev.get("m3"),
                            pts          = ev["pts"],
                            last_updated = now,
                        ))

                    saved_count += 1
                    total_players += 1

                # Limpiar acumulador para siguiente equipo
                player_accumulator.clear()
                db.commit()
                print(f"    💾 {saved_count} jugadores guardados")
                time.sleep(1)

        print(f"\n{'='*60}")
        print(f"✅ INGESTA COMPLETADA")
        print(f"   Jugadores guardados: {total_players}")
        print(f"   Partidos procesados: {total_fixtures}")
        print(f"   Requests usados:     {requests_used}")
        print(f"\n   Siguiente:")
        print(f"   python understat_merge_v2.py  (venv311)")
        print(f"   python fetch_photos.py")
        print(f"   python run.py")
        print(f"{'='*60}\n")

    except KeyboardInterrupt:
        print(f"\n⚠️  Interrumpido por usuario — guardando...")
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        import traceback; traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    run_pipeline()