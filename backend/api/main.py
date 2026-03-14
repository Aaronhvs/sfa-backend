"""
SFA — API Principal v3
Suma puntos y desgloses de todas las competiciones por jugador
"""
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.requests import Request
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
import os, json
from dotenv import load_dotenv

load_dotenv()

from backend.db.models import (
    get_db, Player, Team, Competition,
    SFASeasonScore, StandingSnapshot, PlayerEvent
)

app = FastAPI(title="SFA API", version="3.0.0")

BASE_DIR   = os.getcwd()
STATIC_DIR = os.path.join(BASE_DIR, "frontend", "static")
TMPL_DIR   = os.path.join(BASE_DIR, "frontend", "templates")

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TMPL_DIR) if os.path.exists(TMPL_DIR) else None

SEASON     = os.getenv("SEASON", "2024")
SEASON_STR = f"{SEASON}-{str(int(SEASON)+1)[2:]}"


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def get_player_totals(db: Session, player_id: int, season: str) -> dict:
    scores = db.query(SFASeasonScore).filter(
        SFASeasonScore.player_id == player_id,
        SFASeasonScore.season.like(f"{season}%")
    ).all()

    if not scores:
        return {"total_pts": 0, "matches": 0, "breakdown_json": None, "competitions": []}

    total_pts     = sum(s.total_pts for s in scores)
    total_matches = sum(s.matches_played for s in scores)
    competitions  = [s.season.split("::")[-1] for s in scores if "::" in s.season]

    combined = {}
    for score in scores:
        if not (hasattr(score, 'breakdown_json') and score.breakdown_json):
            continue
        try:
            bd = json.loads(score.breakdown_json)
            for key, val in bd.items():
                if key in combined:
                    combined[key]["count"] += val.get("count", 0)
                    combined[key]["pts"]   += val.get("pts", 0)
                else:
                    combined[key] = dict(val)
        except Exception:
            pass

    return {
        "total_pts":      round(total_pts, 0),
        "matches":        total_matches,
        "breakdown_json": json.dumps(combined, ensure_ascii=False) if combined else None,
        "competitions":   competitions,
    }


def player_to_dict(player: Player, totals: dict) -> dict:
    comps = totals.get("competitions", [])
    comp_str = " + ".join(comps) if comps else "—"
    return {
        "id":          player.id,
        "name":        player.name,
        "team":        player.team.name if player.team else "Unknown",
        "position":    player.position or "MC",
        "competition": comp_str,
        "sfa_pts":     totals.get("total_pts", 0),
        "matches":     totals.get("matches", 0),
        "photo_url":   getattr(player, 'photo_url', None) or "",
    }


# ─── FRONTEND ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if templates:
        return templates.TemplateResponse("index.html", {"request": request})
    return HTMLResponse("<h1>SFA API ✅</h1>")


# ─── ENDPOINTS ───────────────────────────────────────────────────────────────

@app.get("/api/ranking")
def get_ranking(
    season:   str           = Query(default=None),
    position: Optional[str] = Query(default=None),
    league:   Optional[str] = Query(default=None),
    limit:    int           = Query(default=50, le=200),
    db: Session = Depends(get_db)
):
    season = season or SEASON_STR

    from sqlalchemy import text
    rows = db.execute(
        text("SELECT DISTINCT player_id FROM sfa_season_scores WHERE season LIKE :s"),
        {"s": f"{season}%"}
    ).fetchall()
    player_ids = [r[0] for r in rows]

    if not player_ids:
        return {"season": season, "total": 0, "ranking": []}

    players_data = []
    for pid in player_ids:
        player = db.query(Player).filter_by(id=pid).first()
        if not player:
            continue
        if position and player.position != position.upper():
            continue
        totals = get_player_totals(db, pid, season)
        if totals["total_pts"] <= 0:
            continue
        players_data.append((player, totals))

    players_data.sort(key=lambda x: x[1]["total_pts"], reverse=True)
    players_data = players_data[:limit]

    ranking = []
    for rank, (player, totals) in enumerate(players_data, 1):
        d = player_to_dict(player, totals)
        d["rank"] = rank
        ranking.append(d)

    return {"season": season, "total": len(ranking), "ranking": ranking}


@app.get("/api/player/{player_id}")
def get_player(player_id: int, season: str = None, db: Session = Depends(get_db)):
    season = season or SEASON_STR

    player = db.query(Player).filter_by(id=player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Jugador no encontrado")

    totals = get_player_totals(db, player_id, season)

    from sqlalchemy import text
    all_ids = db.execute(
        text("SELECT DISTINCT player_id FROM sfa_season_scores WHERE season LIKE :s"),
        {"s": f"{season}%"}
    ).fetchall()

    better_count = 0
    for row in all_ids:
        if row[0] == player_id:
            continue
        other = get_player_totals(db, row[0], season)
        if other["total_pts"] > totals["total_pts"]:
            better_count += 1

    global_rank = better_count + 1

    breakdown = {}
    if totals.get("breakdown_json"):
        try:
            breakdown = json.loads(totals["breakdown_json"])
        except Exception:
            breakdown = {}

    return {
        "player":       player_to_dict(player, totals),
        "global_rank":  global_rank,
        "season":       season,
        "breakdown":    breakdown,
        "competitions": totals.get("competitions", []),
    }


@app.get("/api/players/{player_id}/events")
def get_player_events(player_id: int, db: Session = Depends(get_db)):
    """Devuelve todos los eventos individuales (goles/asistencias/pases clave) de un jugador."""
    player = db.query(Player).filter_by(id=player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Jugador no encontrado")

    events = (
        db.query(PlayerEvent)
        .filter(PlayerEvent.player_id == player_id)
        .order_by(PlayerEvent.competition, PlayerEvent.minute)
        .all()
    )

    return [
        {
            "id":           e.id,
            "competition":  e.competition,
            "stage":        e.stage,
            "fixture_id":   e.fixture_id,
            "home_team":    e.home_team,
            "away_team":    e.away_team,
            "opponent":     e.opponent,
            "opponent_pos": e.opponent_pos,
            "minute":       e.minute,
            "event_type":   e.event_type,
            "score_before": e.score_before,
            "score_diff":   e.score_diff,
            "m1":           round(e.m1, 2) if e.m1 else None,
            "m2":           round(e.m2, 2) if e.m2 else None,
            "m3":           round(e.m3, 2) if e.m3 else None,
            "pts":          e.pts,
        }
        for e in events
    ]


@app.get("/api/compare")
def compare_players(player_a: int, player_b: int, season: str = None, db: Session = Depends(get_db)):
    season = season or SEASON_STR
    results = []
    for pid in [player_a, player_b]:
        player = db.query(Player).filter_by(id=pid).first()
        if not player:
            raise HTTPException(status_code=404, detail=f"Jugador {pid} no encontrado")
        results.append(player_to_dict(player, get_player_totals(db, pid, season)))
    return {"season": season, "player_a": results[0], "player_b": results[1]}


@app.get("/api/standings")
def get_standings(competition: str = Query(default="La Liga"), db: Session = Depends(get_db)):
    snaps = (
        db.query(StandingSnapshot, Team)
        .join(Team, StandingSnapshot.team_id == Team.id)
        .join(Competition, StandingSnapshot.competition_id == Competition.id)
        .filter(Competition.name.ilike(f"%{competition}%"))
        .order_by(StandingSnapshot.position)
        .all()
    )
    return {"competition": competition, "standings": [{"position": s.position, "team": t.name} for s, t in snaps]}


@app.get("/api/competitions")
def get_competitions(db: Session = Depends(get_db)):
    comps = db.query(Competition).all()
    return [{"id": c.id, "name": c.name, "factor": c.level} for c in comps]


@app.get("/api/status")
def get_status(db: Session = Depends(get_db)):
    from backend.db.models import PlayerEvent
    return {
        "status":       "ok",
        "season":       SEASON_STR,
        "players":      db.query(Player).count(),
        "scores":       db.query(SFASeasonScore).count(),
        "competitions": db.query(Competition).count(),
        "events":       db.query(PlayerEvent).count(),
        "api_version":  "3.1.0",
    }


@app.on_event("startup")
async def start_scheduler():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from backend.pipeline import run_pipeline
    import asyncio
    update_hour = int(os.getenv("UPDATE_HOUR", "7"))
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        lambda: asyncio.get_event_loop().run_in_executor(None, run_pipeline),
        trigger="cron", hour=update_hour, minute=0, id="daily_pipeline",
    )
    scheduler.start()
    print(f"⏰ Scheduler activo — actualización diaria a las {update_hour}:00 AM")