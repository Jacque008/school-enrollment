from typing import Optional
from sqlalchemy import String, Boolean, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

# Role constants
ROLE_SUPERADMIN = "superadmin"
ROLE_SENIOR_ADMIN = "senior_admin"
ROLE_TEACHER = "teacher"

ROLE_LABELS = {
    ROLE_SUPERADMIN: "超级管理员",
    ROLE_SENIOR_ADMIN: "高级管理员",
    ROLE_TEACHER: "任课老师",
}


class AdminUser(Base, TimestampMixin):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    # Role: "superadmin" | "senior_admin" | "teacher"
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=ROLE_SENIOR_ADMIN)
    # Linked teacher record (only used when role == "teacher")
    teacher_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("teachers.id"), nullable=True
    )
    teacher: Mapped[Optional["Teacher"]] = relationship("Teacher", foreign_keys=[teacher_id])  # noqa: F821

    @property
    def is_superadmin_role(self) -> bool:
        return self.role == ROLE_SUPERADMIN or self.is_superadmin

    @property
    def is_senior_or_above(self) -> bool:
        return self.is_superadmin_role or self.role == ROLE_SENIOR_ADMIN

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, self.role)
