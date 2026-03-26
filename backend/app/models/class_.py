from sqlalchemy import String, Integer, Time, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import time
from typing import Optional
from app.models.base import Base, TimestampMixin


class Class(Base, TimestampMixin):
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(primary_key=True)
    semester_id: Mapped[int] = mapped_column(
        ForeignKey("semesters.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    slot_type: Mapped[str] = mapped_column(String(30), nullable=False)
    schedule_day: Mapped[str] = mapped_column(String(10), nullable=False)  # SAT/SUN
    schedule_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration_min: Mapped[int] = mapped_column(Integer, default=120)
    modality: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # onsite/online/mini
    room: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    meeting_link: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    capacity: Mapped[int] = mapped_column(Integer, default=15)
    overflow_cap: Mapped[int] = mapped_column(Integer, default=18)
    current_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(
        String(20), default="open"
    )  # open/full/closed

    semester: Mapped["Semester"] = relationship(back_populates="classes")  # noqa: F821
    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="class_")  # noqa: F821
    class_teachers: Mapped[list["ClassTeacher"]] = relationship(  # noqa: F821
        back_populates="class_"
    )
    class_materials: Mapped[list["ClassMaterial"]] = relationship(  # noqa: F821
        back_populates="class_"
    )
