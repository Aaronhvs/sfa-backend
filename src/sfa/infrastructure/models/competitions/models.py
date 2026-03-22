from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from sfa.infrastructure.database import Base


class Competition(Base):
    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    country: Mapped[str] = mapped_column(String(10), nullable=False)
    competition_factor: Mapped[float] = mapped_column(
        Numeric(4, 2), nullable=False, default=1.0
    )

    __table_args__ = (
        CheckConstraint("competition_factor > 0", name="ck_competition_factor_positive"),
    )


class CompetitionStage(Base):
    __tablename__ = "competition_stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    stage_factor: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False)

    __table_args__ = (
        UniqueConstraint("competition_id", "stage", name="uq_competition_stage"),
        CheckConstraint("stage_factor > 0", name="ck_stage_factor_positive"),
    )
