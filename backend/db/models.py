"""
SFA — Modelos de base de datos (SQLite con SQLAlchemy)
"""
from sqlalchemy import (
    create_engine, Column, Integer, String, Float,
    DateTime, Boolean, ForeignKey, Text
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sfa.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── TABLAS ──────────────────────────────────────────────────────────────────

class Competition(Base):
    __tablename__ = "competitions"
    id          = Column(Integer, primary_key=True)
    name        = Column(String, unique=True)
    country     = Column(String)
    level       = Column(Float, default=1.0)
    created_at  = Column(DateTime, default=datetime.utcnow)


class Team(Base):
    __tablename__ = "teams"
    id             = Column(Integer, primary_key=True)
    name           = Column(String)
    fbref_id       = Column(String, unique=True, nullable=True)
    competition_id = Column(Integer, ForeignKey("competitions.id"))


class Player(Base):
    __tablename__ = "players"
    id          = Column(Integer, primary_key=True)
    name        = Column(String)
    fbref_id    = Column(String, unique=True, nullable=True)
    team_id     = Column(Integer, ForeignKey("teams.id"))
    position    = Column(String)
    nationality = Column(String, nullable=True)
    photo_url   = Column(String, nullable=True)
    team        = relationship("Team", backref="players")
    events      = relationship("PlayerEvent", back_populates="player", cascade="all, delete-orphan")


class StandingSnapshot(Base):
    __tablename__ = "standings_snapshots"
    id             = Column(Integer, primary_key=True)
    competition_id = Column(Integer, ForeignKey("competitions.id"))
    team_id        = Column(Integer, ForeignKey("teams.id"))
    season         = Column(String)
    position       = Column(Integer)
    points         = Column(Integer, default=0)
    snapshot_date  = Column(DateTime, default=datetime.utcnow)


class Match(Base):
    __tablename__ = "matches"
    id             = Column(Integer, primary_key=True)
    fbref_id       = Column(String, unique=True, nullable=True)
    competition_id = Column(Integer, ForeignKey("competitions.id"))
    season         = Column(String)
    matchday       = Column(Integer, nullable=True)
    stage          = Column(String, default="regular")
    date           = Column(DateTime, nullable=True)
    home_team_id   = Column(Integer, ForeignKey("teams.id"))
    away_team_id   = Column(Integer, ForeignKey("teams.id"))
    home_goals     = Column(Integer, nullable=True)
    away_goals     = Column(Integer, nullable=True)
    processed      = Column(Boolean, default=False)


class Event(Base):
    __tablename__ = "events"
    id             = Column(Integer, primary_key=True)
    match_id       = Column(Integer, ForeignKey("matches.id"))
    player_id      = Column(Integer, ForeignKey("players.id"))
    team_id        = Column(Integer, ForeignKey("teams.id"))
    action_type    = Column(String)
    minute         = Column(Integer, nullable=True)
    score_home_at_moment = Column(Integer, nullable=True)
    score_away_at_moment = Column(Integer, nullable=True)
    is_penalty     = Column(Boolean, default=False)
    xg_value       = Column(Float, nullable=True)
    psxg_value     = Column(Float, nullable=True)
    xa_value       = Column(Float, nullable=True)
    player_team_position   = Column(Integer, nullable=True)
    opponent_team_position = Column(Integer, nullable=True)
    data_available = Column(Boolean, default=True)


class SFAEventScore(Base):
    __tablename__ = "sfa_event_scores"
    id          = Column(Integer, primary_key=True)
    event_id    = Column(Integer, ForeignKey("events.id"), unique=True)
    player_id   = Column(Integer, ForeignKey("players.id"))
    match_id    = Column(Integer, ForeignKey("matches.id"))
    base_pts    = Column(Float)
    m1_rival    = Column(Float)
    m2_comp     = Column(Float)
    m3_moment   = Column(Float)
    m4_psxg     = Column(Float)
    m_final     = Column(Float)
    total_pts   = Column(Float)
    calculated_at = Column(DateTime, default=datetime.utcnow)


class SFAMatchScore(Base):
    __tablename__ = "sfa_match_scores"
    id            = Column(Integer, primary_key=True)
    player_id     = Column(Integer, ForeignKey("players.id"))
    match_id      = Column(Integer, ForeignKey("matches.id"))
    total_pts     = Column(Float, default=0)
    events_count  = Column(Integer, default=0)
    calculated_at = Column(DateTime, default=datetime.utcnow)


class SFASeasonScore(Base):
    __tablename__ = "sfa_season_scores"
    id             = Column(Integer, primary_key=True)
    player_id      = Column(Integer, ForeignKey("players.id"))
    season         = Column(String)
    total_pts      = Column(Float, default=0)
    matches_played = Column(Integer, default=0)
    breakdown_json = Column(Text, nullable=True)
    last_updated   = Column(DateTime, default=datetime.utcnow)
    player         = relationship("Player", backref="season_scores")


class PlayerStats(Base):
    __tablename__ = "player_stats"
    id               = Column(Integer, primary_key=True)
    player_id        = Column(Integer, ForeignKey("players.id"))
    season           = Column(String)
    competition      = Column(String)
    goals_normal     = Column(Integer, default=0)
    goals_penalty    = Column(Integer, default=0)
    assists          = Column(Integer, default=0)
    shots_on         = Column(Integer, default=0)
    passes_key       = Column(Integer, default=0)
    dribbles_success = Column(Integer, default=0)
    duels_won        = Column(Integer, default=0)
    tackles          = Column(Integer, default=0)
    interceptions    = Column(Integer, default=0)
    blocks           = Column(Integer, default=0)
    minutes          = Column(Integer, default=0)
    appearances      = Column(Integer, default=0)
    pts_goals_normal  = Column(Float, default=0)
    pts_goals_penalty = Column(Float, default=0)
    pts_assists       = Column(Float, default=0)
    pts_xg            = Column(Float, default=0)
    pts_key_passes    = Column(Float, default=0)
    pts_dribbles      = Column(Float, default=0)
    pts_duels         = Column(Float, default=0)
    pts_tackles       = Column(Float, default=0)
    pts_blocks        = Column(Float, default=0)
    last_updated      = Column(DateTime, default=datetime.utcnow)
    player            = relationship("Player", backref="stats")


class PlayerEvent(Base):
    """Goles, asistencias y pases clave individuales con contexto real."""
    __tablename__ = "player_events"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    player_id    = Column(Integer, ForeignKey("players.id"), nullable=False)
    season       = Column(String, nullable=False)       # "2024-25"
    competition  = Column(String, nullable=False)       # "La Liga"
    stage        = Column(String, nullable=False)       # "regular" / "semi" / "final" etc
    fixture_id   = Column(Integer, nullable=False)
    home_team    = Column(String, nullable=False)
    away_team    = Column(String, nullable=False)
    opponent     = Column(String, nullable=False)       # equipo rival
    opponent_pos = Column(Integer, nullable=True)       # posición rival en tabla
    minute       = Column(Integer, nullable=False)
    event_type   = Column(String, nullable=False)       # "goal" | "goal_penalty" | "assist" | "key_pass"
    score_before = Column(String, nullable=True)        # "1-0" marcador antes del evento
    score_diff   = Column(Integer, nullable=True)       # diferencia a favor antes del evento
    m1           = Column(Float, nullable=True)
    m2           = Column(Float, nullable=True)
    m3           = Column(Float, nullable=True)
    pts          = Column(Float, nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow)

    player = relationship("Player", back_populates="events")


def create_tables():
    Base.metadata.create_all(bind=engine)
    print("✅ Tablas creadas correctamente")


if __name__ == "__main__":
    create_tables()
