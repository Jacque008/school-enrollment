from sqlalchemy import String, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from app.models.base import Base, TimestampMixin


class ReadingAssessment(Base, TimestampMixin):
    __tablename__ = "reading_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id"), nullable=False
    )
    semester_id: Mapped[int] = mapped_column(
        ForeignKey("semesters.id"), nullable=False
    )
    reading_interest: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    reading_ability: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # independent / needs_help
    reading_habits: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    other_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    student: Mapped["Student"] = relationship(  # noqa: F821
        back_populates="reading_assessments"
    )
