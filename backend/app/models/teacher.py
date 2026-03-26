from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from app.models.base import Base, TimestampMixin


class Teacher(Base, TimestampMixin):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # male/female
    max_classes: Mapped[int] = mapped_column(Integer, default=3)

    class_teachers: Mapped[list["ClassTeacher"]] = relationship(  # noqa: F821
        back_populates="teacher"
    )
