from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from app.models.base import Base, TimestampMixin


class Enrollment(Base, TimestampMixin):
    __tablename__ = "enrollments"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id"), nullable=False
    )
    class_id: Mapped[int] = mapped_column(
        ForeignKey("classes.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="enrolled"
    )  # enrolled/waitlisted/dropped/completed
    waitlist_pos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    student: Mapped["Student"] = relationship(back_populates="enrollments")  # noqa: F821
    class_: Mapped["Class"] = relationship(back_populates="enrollments")  # noqa: F821
