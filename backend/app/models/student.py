from sqlalchemy import String, Date, Boolean, Text, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import date
from typing import Optional
from app.models.base import Base, TimestampMixin


class Student(Base, TimestampMixin):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    guardian_id: Mapped[int] = mapped_column(ForeignKey("guardians.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    gender: Mapped[str] = mapped_column(String(10), nullable=False)  # male/female
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    nationality: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    city_region: Mapped[str] = mapped_column(String(200), nullable=False)
    home_language: Mapped[str] = mapped_column(
        String(20), default="mixed"
    )  # chinese/swedish/mixed/other
    teacher_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teachers.id"), nullable=True)
    is_teacher_child: Mapped[bool] = mapped_column(Boolean, default=False)
    sibling_in_school: Mapped[bool] = mapped_column(Boolean, default=False)
    sibling_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    learning_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    other_hobbies: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_expectations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    school_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    other_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    referral_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    accept_alternative: Mapped[bool] = mapped_column(Boolean, default=True)

    guardian: Mapped["Guardian"] = relationship(back_populates="students")  # noqa: F821
    proficiency_assessments: Mapped[list["ProficiencyAssessment"]] = relationship(  # noqa: F821
        back_populates="student"
    )
    reading_assessments: Mapped[list["ReadingAssessment"]] = relationship(  # noqa: F821
        back_populates="student"
    )
    schedule_preferences: Mapped[list["SchedulePreference"]] = relationship(  # noqa: F821
        back_populates="student"
    )
    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="student")  # noqa: F821
