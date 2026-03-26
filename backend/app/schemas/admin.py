from pydantic import BaseModel
from typing import Optional


class AdminLogin(BaseModel):
    username: str
    password: str


class AdminCreate(BaseModel):
    username: str
    password: str
    is_superadmin: bool = False


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class StudentListItem(BaseModel):
    id: int
    name: str
    guardian_name: str
    computed_level: Optional[int] = None
    enrollment_status: Optional[str] = None

    model_config = {"from_attributes": True}


class TeacherCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    max_classes: int = 3


class TeacherResponse(BaseModel):
    id: int
    name: str
    email: Optional[str]
    phone: Optional[str]
    max_classes: int

    model_config = {"from_attributes": True}
