from sqlalchemy import String, Date, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import date
from typing import Optional
from app.models.base import Base, TimestampMixin


class Semester(Base, TimestampMixin):
    __tablename__ = "semesters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reg_open_date: Mapped[date] = mapped_column(Date, nullable=False)
    reg_close_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    total_weeks: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    holiday_weeks: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    classes: Mapped[list["Class"]] = relationship(back_populates="semester")  # noqa: F821
