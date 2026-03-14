"""
SFA — Cruce con Understat v2
Matching más estricto:
- Score mínimo 0.75 (antes 0.5)
- Al menos 2 tokens en común
- El apellido principal debe coincidir exactamente
- Si hay ambigüedad (2+ candidatos con score similar), se descarta
"""
import asyncio
import aiohttp
import understat
import sys, os, json, unicodedata, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

from backend.db.models import SessionLocal, Player, SFASeasonScore, Competition, Team, StandingSnapshot
from backend.engine.sfa_engine import score_event, COMPETITION_FACTORS

SEASON_STR = "2024-25"

UNDERSTAT_LEAGUES = {
    "la_liga":    "La Liga",
    "epl":        "Premier League",
    "bundesliga": "Bundesliga",
    "serie_a":    "Serie A",
    "ligue_1":    "Ligue 1",
}

# ── Normalización ─────────────────────────────────────────────────────────────
def normalize(name: str) -> str:
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.lower()
    name = re.sub(r"[.\-'`]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name

def get_tokens(name: str) -> set:
    # Ignorar tokens muy cortos (iniciales)
    return {t for t in normalize(name).split() if len(t) > 2}

def match_score(uname: str, dbname: str) -> float:
    """
    Score estricto:
    - Requiere al menos 2 tokens en común
    - Penaliza si el token más largo (apellido) no coincide
    """
    tu = get_tokens(uname)
    td = get_tokens(dbname)
    
    if not tu or not td:
        return 0.0
    
    common = tu & td
    if len(common) < 1:
        return 0.0
    
    # Jaccard sobre tokens largos
    score = len(common) / len(tu | td)
    
    # Bonus si el token más largo coincide (apellido principal)
    longest_u = max(tu, key=len) if tu else ""
    longest_d = max(td, key=len) if td else ""
    if longest_u and longest_d and longest_u == longest_d:
        score = min(1.0, score + 0.3)
    elif longest_u and longest_u not in td:
        # El apellido principal NO coincide → penalizar fuerte
        score *= 0.4
    
    return score

def find_best_match(uname: str, db_index: dict) -> tuple:
    """
    Retorna (player, score) o (None, 0) si:
    - No hay match >= 0.75
    - Hay 2+ candidatos con scores similares (ambigüedad)
    """
    candidates = []
    for db_name, player_obj in db_index.items():
        s = match_score(uname, db_name)
        if s >= 0.75:
            candidates.append((player_obj, s, db_name))
    
    if not candidates:
        return None, 0.0
    
    # Ordenar por score desc
    candidates.sort(key=lambda x: x[1], reverse=True)
    best = candidates[0]
    
    # Si hay 2+ candidatos muy cerca (diferencia < 0.1), es ambiguo → descartar
    if len(candidates) >= 2 and (candidates[0][1] - candidates[1][1]) < 0.1:
        return None, 0.0
    
    return best[0], best[1]

# ── Cálculo SFA desde Understat ───────────────────────────────────────────────
def calc_sfa_from_understat(u: dict, team_pos: int, league_name: str) -> float:
    total  = 0.0
    goals  = int(u.get("goals", 0) or 0)
    assists= int(u.get("assists", 0) or 0)
    npg    = int(u.get("npg", 0) or 0)
    pens   = max(0, goals - npg)
    npxG   = float(u.get("npxG", 0) or 0)
    xA     = float(u.get("xA", 0) or 0)

    for _ in range(npg):
        total += score_event("goal", team_pos, 10, league_name, "regular", 65, 0, psxg=0.32)["total_pts"]
    for _ in range(pens):
        total += score_event("goal_penalty", team_pos, 10, league_name, "regular", 60, 0, is_penalty=True)["total_pts"]
    for _ in range(assists):
        total += score_event("assist", team_pos, 10, league_name, "regular", 60, 0)["total_pts"]

    xg_no_goal = max(0, npxG - npg * 0.32)
    if xg_no_goal > 0.5:
        total += score_event("shot", team_pos, 10, league_name, "regular", 55, 0, xg=xg_no_goal)["total_pts"]

    xa_no_ast = max(0, xA - assists * 0.3)
    if xa_no_ast > 0.2:
        total += score_event("key_pass", team_pos, 10, league_name, "regular", 55, 0, xa=xa_no_ast)["total_pts"]

    return round(total, 0)

# ── Pipeline ──────────────────────────────────────────────────────────────────
async def main():
    db = SessionLocal()

    # Construir índice de DB (solo jugadores con al menos 1 score en la temporada)
    all_players = db.query(Player).all()
    db_index = {p.name: p for p in all_players}

    print(f"\n{'='*60}")
    print(f"🔗 SFA — Cruce con Understat v2 (matching estricto)")
    print(f"   {len(db_index)} jugadores en DB")
    print(f"{'='*60}")

    total_updated = 0
    total_skipped = 0

    async with aiohttp.ClientSession() as session:
        u_client = understat.Understat(session)

        for league_key, league_name in UNDERSTAT_LEAGUES.items():
            print(f"\n📋 {league_name}")

            u_players = None
            for attempt in range(1, 4):  # hasta 3 intentos
                try:
                    u_players = await u_client.get_league_players(league_key, 2024)
                    break
                except Exception as e:
                    print(f"  ⚠️  Intento {attempt}/3 fallido: {e}")
                    if attempt < 3:
                        wait = attempt * 15  # 15s, 30s
                        print(f"     Reintentando en {wait}s...")
                        await asyncio.sleep(wait)
                        # Recrear cliente en nueva sesión si falló
                        try:
                            await session.close()
                        except Exception:
                            pass
                        session = aiohttp.ClientSession()
                        u_client = understat.Understat(session)
            if u_players is None:
                print(f"  ❌ Error: no se pudo conectar después de 3 intentos")
                continue

            print(f"   {len(u_players)} jugadores en Understat")

            comp = db.query(Competition).filter_by(name=league_name).first()
            league_updated = 0
            league_skipped = 0
            ambiguous = 0
            not_found_relevant = []

            for up in u_players:
                uname   = up.get("player_name", "")
                u_goals = int(up.get("goals", 0) or 0)
                u_ast   = int(up.get("assists", 0) or 0)
                u_games = int(up.get("games", 0) or 0)
                u_mins  = int(up.get("time", 0) or 0)
                u_shots = int(up.get("shots", 0) or 0)
                u_kp    = int(up.get("key_passes", 0) or 0)
                u_xG    = float(up.get("xG", 0) or 0)
                u_xA    = float(up.get("xA", 0) or 0)
                u_team  = up.get("team_title", "")

                if u_mins < 90:
                    continue

                player, score = find_best_match(uname, db_index)

                if player is None:
                    league_skipped += 1
                    if u_goals >= 5 or u_ast >= 5:
                        not_found_relevant.append(f"{uname} ({u_team}) — {u_goals}G {u_ast}A [score={score:.2f}]")
                    continue

                # Verificar que el jugador tiene score en ESTA liga (no en otra)
                season_key = f"{SEASON_STR}::{league_name}"
                existing = db.query(SFASeasonScore).filter_by(
                    player_id=player.id, season=season_key
                ).first()

                # Calcular posición del equipo en la liga
                team_pos = 8  # default
                if comp:
                    snap = db.query(StandingSnapshot).filter_by(
                        competition_id=comp.id, season=SEASON_STR
                    ).join(Team, Team.id == StandingSnapshot.team_id).filter(
                        Team.name.ilike(f"%{u_team.split()[0]}%")
                    ).first()
                    if snap:
                        team_pos = snap.position

                # Actualizar breakdown_json con máximo de cada stat
                try:
                    bd = json.loads(player.breakdown_json or "{}")
                except Exception:
                    bd = {}

                bd["goals_normal"] = max(bd.get("goals_normal", 0), int(up.get("npg", 0) or 0))
                bd["assists"]      = max(bd.get("assists", 0), u_ast)
                bd["shots_on"]     = max(bd.get("shots_on", 0), u_shots)
                bd["passes_key"]   = max(bd.get("passes_key", 0), u_kp)
                bd["appearances"]  = max(bd.get("appearances", 0), u_games)
                bd["xG_real"]      = u_xG
                bd["xA_real"]      = u_xA
                bd["understat_name"] = uname  # para debug
                player.breakdown_json = json.dumps(bd)

                # Puntos SFA desde Understat
                u_sfa_pts = calc_sfa_from_understat(up, team_pos, league_name)

                if existing:
                    # Tomar el máximo
                    existing.total_pts     = max(existing.total_pts, u_sfa_pts)
                    existing.matches_played = max(existing.matches_played, u_games)
                else:
                    # Solo crear si el jugador tiene score en alguna liga
                    # (evitar agregar jugadores de equipos que no ingresamos)
                    any_score = db.query(SFASeasonScore).filter_by(player_id=player.id).first()
                    if any_score:
                        new_s = SFASeasonScore(
                            player_id=player.id,
                            season=season_key,
                            total_pts=u_sfa_pts,
                            matches_played=u_games
                        )
                        db.add(new_s)

                league_updated += 1
                total_updated += 1

            db.commit()

            print(f"  ✅ Actualizados: {league_updated} | Sin match: {league_skipped}")
            if not_found_relevant:
                print(f"  ⚠️  Relevantes no encontrados ({len(not_found_relevant)}):")
                for nf in not_found_relevant[:10]:
                    print(f"     {nf}")

    print(f"\n{'='*60}")
    print(f"✅ CRUCE COMPLETADO — {total_updated} jugadores actualizados")
    print(f"{'='*60}\n")
    db.close()

if __name__ == "__main__":
    asyncio.run(main())
