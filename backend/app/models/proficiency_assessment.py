from sqlalchemy import Boolean, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from app.models.base import Base, TimestampMixin


class ProficiencyAssessment(Base, TimestampMixin):
    __tablename__ = "proficiency_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id"), nullable=False
    )
    semester_id: Mapped[int] = mapped_column(
        ForeignKey("semesters.id"), nullable=False
    )
    listening_level: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-4
    speaking_level: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    writing_level: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-6
    pinyin_level: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-3
    vocab_level: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    computed_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    admin_override_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    placement_recommended_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    placement_alternatives_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    has_audited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    student: Mapped["Student"] = relationship(  # noqa: F821
        back_populates="proficiency_assessments"
    )

    def compute_level(self) -> int:
        raw = (
            self.vocab_level * 0.4
            + self.listening_level * 0.15
            + self.speaking_level * 0.2
            + self.writing_level * 0.15
            + self.pinyin_level * 0.1
        )
        return round(raw)

    @property
    def effective_level(self) -> int:
        if self.admin_override_level is not None:
            return self.admin_override_level
        return self.computed_level or self.compute_level()
