from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from sfa.infrastructure.database import Base


class PlayerStats(Base):
    __tablename__ = "player_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), nullable=False)
    season: Mapped[str] = mapped_column(String(10), nullable=False)
    goals: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    assists: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    corner_assists: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    shots_on: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    xg: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    xa: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    passes_key: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    progressive_passes: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    progressive_carries: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    recoveries_opp_half: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    pressures_success: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    duels_won: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    dribbles_won: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    tackles_won: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    interceptions: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    blocks: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    clearances_goal_line: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    minutes: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    appearances: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("player_id", "fixture_id", name="uq_player_stats"),
        CheckConstraint("goals >= 0", name="ck_ps_goals"),
        CheckConstraint("assists >= 0", name="ck_ps_assists"),
        CheckConstraint("corner_assists >= 0", name="ck_ps_corner_assists"),
        CheckConstraint("shots_on >= 0", name="ck_ps_shots_on"),
        CheckConstraint("xg >= 0", name="ck_ps_xg"),
        CheckConstraint("xa >= 0", name="ck_ps_xa"),
        CheckConstraint("passes_key >= 0", name="ck_ps_passes_key"),
        CheckConstraint("progressive_passes >= 0", name="ck_ps_progressive_passes"),
        CheckConstraint("progressive_carries >= 0", name="ck_ps_progressive_carries"),
        CheckConstraint("recoveries_opp_half >= 0", name="ck_ps_recoveries_opp_half"),
        CheckConstraint("pressures_success >= 0", name="ck_ps_pressures_success"),
        CheckConstraint("duels_won >= 0", name="ck_ps_duels_won"),
        CheckConstraint("dribbles_won >= 0", name="ck_ps_dribbles_won"),
        CheckConstraint("tackles_won >= 0", name="ck_ps_tackles_won"),
        CheckConstraint("interceptions >= 0", name="ck_ps_interceptions"),
        CheckConstraint("blocks >= 0", name="ck_ps_blocks"),
        CheckConstraint("clearances_goal_line >= 0", name="ck_ps_clearances_goal_line"),
        CheckConstraint("minutes BETWEEN 0 AND 120", name="ck_ps_minutes"),
        CheckConstraint("appearances >= 0", name="ck_ps_appearances"),
    )
