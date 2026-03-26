from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

# Default values used when no DB record exists yet
SETTINGS_DEFAULTS = {
    "default_capacity":    ("15",   "班级标准人数"),
    "default_overflow_cap":("18",   "班级超员上限"),
    "fee_onsite":          ("2300", "实体课学费（kr/学期）"),
    "fee_beginner":        ("2100", "实体启蒙班学费（kr/学期，L1-L2）"),
    "fee_online":          ("2100", "网课/迷你课学费（kr/学期）"),
    "discount_2":          ("200",  "2子女家庭优惠（kr）"),
    "discount_3":          ("400",  "3子女家庭优惠（kr）"),
    "discount_4":          ("600",  "4子女及以上家庭优惠（kr）"),
}


class SystemSettings(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(200), nullable=False)
