from datetime import datetime, timezone
from enum import Enum
from typing import Any, TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

if TYPE_CHECKING:
    from .category import Category
    from .user import User


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProcessingStatus(str, Enum):
    uploaded = "uploaded"
    processing = "processing"
    complete = "complete"
    needs_review = "needs_review"
    failed = "failed"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    original_image_path: Mapped[str] = mapped_column(String(500), default="")
    scanned_image_path: Mapped[str] = mapped_column(String(500), default="")
    bw_image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Retain the legacy column name while storing layout-aware Markdown transcription.
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_status: Mapped[str] = mapped_column(String(30), default=ProcessingStatus.uploaded.value)
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    detected_corners: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    scan_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    scan_debug: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    scan_mode: Mapped[str] = mapped_column(String(20), default="color")
    scan_revision: Mapped[int] = mapped_column(default=0)
    embedding_json: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    category: Mapped["Category"] = relationship(back_populates="documents")
    user: Mapped["User"] = relationship(back_populates="documents")
