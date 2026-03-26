from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from app.models.base import Base, TimestampMixin


class Guardian(Base, TimestampMixin):
    __tablename__ = "guardians"

    id: Mapped[int] = mapped_column(primary_key=True)
    wechat_openid: Mapped[Optional[str]] = mapped_column(
        String(100), unique=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    wechat_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)       # male/female
    relationship_to_child: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # 爸爸/妈妈/其他
    nationality: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    students: Mapped[list["Student"]] = relationship(back_populates="guardian")  # noqa: F821
