from pydantic import BaseModel
from datetime import time
from typing import Optional


class ClassCreate(BaseModel):
    semester_id: int
    name: str
    level: int
    slot_type: str
    schedule_day: str  # SAT/SUN
    schedule_time: time
    duration_min: int = 120
    modality: str  # onsite/online/mini
    room: Optional[str] = None
    meeting_link: Optional[str] = None
    capacity: int = 15
    overflow_cap: int = 18


class ClassUpdate(BaseModel):
    name: Optional[str] = None
    level: Optional[int] = None
    slot_type: Optional[str] = None
    schedule_day: Optional[str] = None
    schedule_time: Optional[time] = None
    duration_min: Optional[int] = None
    modality: Optional[str] = None
    room: Optional[str] = None
    meeting_link: Optional[str] = None
    capacity: Optional[int] = None
    overflow_cap: Optional[int] = None
    status: Optional[str] = None


class ClassResponse(BaseModel):
    id: int
    semester_id: int
    name: str
    level: int
    slot_type: str
    schedule_day: str
    schedule_time: time
    duration_min: int
    modality: str
    room: Optional[str]
    meeting_link: Optional[str]
    capacity: int
    overflow_cap: int
    current_count: int
    status: str

    model_config = {"from_attributes": True}
