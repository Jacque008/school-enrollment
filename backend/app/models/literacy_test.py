from sqlalchemy import String, Integer, ForeignKey, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from app.models.base import Base, TimestampMixin

class LiteracyTest(Base, TimestampMixin):
    __tablename__ = "literacy_tests"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id"), nullable=False)
    characters: Mapped[list] = mapped_column(JSON, nullable=False)  # list of chars/words
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    results: Mapped[list["LiteracyTestResult"]] = relationship(back_populates="test")

class LiteracyTestResult(Base, TimestampMixin):
    __tablename__ = "literacy_test_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    test_id: Mapped[int] = mapped_column(ForeignKey("literacy_tests.id"), nullable=False)
    total_chars: Mapped[int] = mapped_column(Integer, nullable=False)
    recognized_count: Mapped[int] = mapped_column(Integer, nullable=False)
    score_percent: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-100
    derived_vocab_level: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    test: Mapped["LiteracyTest"] = relationship(back_populates="results")
