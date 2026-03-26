from sqlalchemy import String, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from app.models.base import Base, TimestampMixin


class Material(Base, TimestampMixin):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    level: Mapped[Optional[int]] = mapped_column(nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    lesson_count: Mapped[Optional[int]] = mapped_column(nullable=True)   # 课文数
    char_count: Mapped[Optional[int]] = mapped_column(nullable=True)     # 生字数
    char_set: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # 生字集

    class_materials: Mapped[list["ClassMaterial"]] = relationship(
        back_populates="material"
    )


class ClassMaterial(Base):
    __tablename__ = "class_materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), nullable=False)
    material_id: Mapped[int] = mapped_column(
        ForeignKey("materials.id"), nullable=False
    )

    class_: Mapped["Class"] = relationship(back_populates="class_materials")  # noqa: F821
    material: Mapped["Material"] = relationship(back_populates="class_materials")
