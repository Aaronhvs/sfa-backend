from sqlalchemy import CheckConstraint, Enum, ForeignKey, Integer, Numeric, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from sfa.infrastructure.database import Base
from sfa.infrastructure.models.enums import EventType


class PlayerEvent(Base):
    __tablename__ = "player_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), nullable=False)
    minute: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType, native_enum=False), nullable=False
    )
    score_before: Mapped[str | None] = mapped_column(String(10), nullable=True)
    score_diff: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    psxg: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    m1: Mapped[float] = mapped_column(Numeric(5, 3), nullable=False)
    m2: Mapped[float] = mapped_column(Numeric(5, 3), nullable=False)
    m3: Mapped[float] = mapped_column(Numeric(5, 3), nullable=False)
    m4: Mapped[float] = mapped_column(Numeric(5, 3), nullable=False)
    mvisit: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=1.0)
    pts: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    __table_args__ = (
        CheckConstraint("minute BETWEEN 1 AND 120", name="ck_event_minute"),
        CheckConstraint("psxg BETWEEN 0 AND 1", name="ck_event_psxg"),
        CheckConstraint("m1 BETWEEN 0.5 AND 2.0", name="ck_event_m1"),
        CheckConstraint("m2 > 0", name="ck_event_m2"),
        CheckConstraint("m3 > 0", name="ck_event_m3"),
        CheckConstraint("m4 BETWEEN 1.0 AND 2.0", name="ck_event_m4"),
        CheckConstraint("mvisit IN (1.0, 1.3)", name="ck_event_mvisit"),
    )
