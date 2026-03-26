from pydantic import BaseModel
from datetime import date
from typing import Optional


class SemesterCreate(BaseModel):
    name: str
    start_date: date
    end_date: date
    reg_open_date: date
    reg_close_date: date
    is_active: bool = False


class SemesterUpdate(BaseModel):
    name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    reg_open_date: Optional[date] = None
    reg_close_date: Optional[date] = None
    is_active: Optional[bool] = None


class SemesterResponse(BaseModel):
    id: int
    name: str
    start_date: date
    end_date: date
    reg_open_date: date
    reg_close_date: date
    is_active: bool

    model_config = {"from_attributes": True}
