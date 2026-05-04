from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sfa.infrastructure.database import Base


class SFASeasonScore(Base):
    __tablename__ = "sfa_season_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id"), nullable=False
    )
    season: Mapped[str] = mapped_column(String(10), nullable=False)
    total_pts: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    matches_played: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_updated: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "player_id", "competition_id", "season", name="uq_sfa_season_score"
        ),
        CheckConstraint("matches_played >= 0", name="ck_score_matches_played"),
    )
