from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

SLOT_TYPES = [
    "sat_onsite_am",
    "sat_onsite_noon",
    "sat_onsite_pm",
    "weekend_online_am",
    "weekend_online_noon",
    "weekend_online_pm",
    "mini_online",
]


class SchedulePreference(Base, TimestampMixin):
    __tablename__ = "schedule_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id"), nullable=False
    )
    semester_id: Mapped[int] = mapped_column(
        ForeignKey("semesters.id"), nullable=False
    )
    slot_type: Mapped[str] = mapped_column(String(30), nullable=False)

    student: Mapped["Student"] = relationship(  # noqa: F821
        back_populates="schedule_preferences"
    )
