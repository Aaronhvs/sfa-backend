"""
INSTRUCCIONES: Agrega este endpoint en backend/api/main.py
"""

ENDPOINT = '''
from backend.db.models import PlayerEvent, Player

@app.get("/api/players/{player_id}/events")
def get_player_events(player_id: int, db: Session = Depends(get_db)):
    """Devuelve todos los eventos individuales (goles/asistencias/pases) de un jugador."""
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
'''
print(ENDPOINT)
