from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class ClassTeacher(Base):
    __tablename__ = "class_teachers"

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), nullable=False)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(20), default="primary"
    )  # primary/assistant

    class_: Mapped["Class"] = relationship(back_populates="class_teachers")  # noqa: F821
    teacher: Mapped["Teacher"] = relationship(back_populates="class_teachers")  # noqa: F821
