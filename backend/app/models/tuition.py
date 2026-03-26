from sqlalchemy import String, Integer, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from app.models.base import Base, TimestampMixin


class GuardianFlag(Base):
    """Extra flags for guardians (teacher family, etc.). New table, no migration needed."""
    __tablename__ = "guardian_flags"
    guardian_id: Mapped[int] = mapped_column(ForeignKey("guardians.id"), primary_key=True)
    is_teacher_family: Mapped[bool] = mapped_column(Boolean, default=False)


class TuitionRecord(Base, TimestampMixin):
    """Calculated tuition per student per semester."""
    __tablename__ = "tuition_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id"), nullable=False)
    base_fee: Mapped[int] = mapped_column(Integer, default=0)
    family_discount: Mapped[int] = mapped_column(Integer, default=0)
    final_fee: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    student: Mapped["Student"] = relationship("Student")  # noqa
