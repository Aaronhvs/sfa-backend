from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from sfa.infrastructure.database import Base
from sfa.infrastructure.models.enums import IngestionStatus


class IngestionLog(Base):
    __tablename__ = "ingestion_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id"), nullable=False
    )
    season: Mapped[str] = mapped_column(String(10), nullable=False)
    started_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[IngestionStatus] = mapped_column(
        Enum(IngestionStatus, native_enum=False), nullable=False
    )
    players_processed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("players_processed >= 0", name="ck_ingestion_players_processed"),
    )
