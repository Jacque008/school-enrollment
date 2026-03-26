from pydantic import BaseModel, EmailStr, Field
from datetime import date
from typing import Optional
from enum import Enum


class Gender(str, Enum):
    male = "male"
    female = "female"


class HomeLanguage(str, Enum):
    chinese = "chinese"
    swedish = "swedish"
    mixed = "mixed"
    other = "other"


class SlotType(str, Enum):
    sat_onsite_am = "sat_onsite_am"
    sat_onsite_noon = "sat_onsite_noon"
    sat_onsite_pm = "sat_onsite_pm"
    weekend_online_am = "weekend_online_am"
    weekend_online_noon = "weekend_online_noon"
    weekend_online_pm = "weekend_online_pm"
    mini_online = "mini_online"


class ReadingAbility(str, Enum):
    independent = "independent"
    needs_help = "needs_help"


# Step 1: Student basic info
class StudentBasicInfo(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    gender: Gender
    birth_date: date
    city_region: str = Field(..., min_length=1, max_length=200)
    nationality: Optional[str] = None


# Step 2: Guardian info
class GuardianInfo(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    relationship_to_child: Optional[str] = None  # mom/dad/other
    gender: Optional[str] = None  # male/female — derived from relationship
    nationality: Optional[str] = None
    language: Optional[str] = None
    email: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=50)
    wechat_id: str = Field(..., min_length=1, max_length=100)
    sibling_in_school: bool = False
    sibling_info: Optional[str] = None


# Step 3: Schedule preferences
class SchedulePreferences(BaseModel):
    slot_types: list[SlotType] = Field(..., min_length=1)


# Step 4: Proficiency self-assessment
class ProficiencyInfo(BaseModel):
    listening_level: int = Field(..., ge=1, le=4)
    speaking_level: int = Field(..., ge=1, le=5)
    writing_level: int = Field(..., ge=1, le=6)


# Step 5: Literacy assessment
class LiteracyInfo(BaseModel):
    pinyin_level: int = Field(..., ge=1, le=3)
    vocab_level: int = Field(..., ge=1, le=5)
    reading_interest: Optional[list[str]] = None
    reading_ability: Optional[ReadingAbility] = None
    reading_habits: Optional[list[str]] = None


# Step 6: Background and expectations
class BackgroundInfo(BaseModel):
    home_language: HomeLanguage = HomeLanguage.mixed
    learning_history: Optional[str] = None
    other_hobbies: Optional[str] = None
    parent_expectations: Optional[str] = None
    school_feedback: Optional[str] = None
    other_notes: Optional[str] = None
    referral_source: Optional[str] = None
    accept_alternative: bool = True


# Combined registration request
class RegistrationCreate(BaseModel):
    student: StudentBasicInfo
    guardian: GuardianInfo
    schedule: SchedulePreferences
    proficiency: ProficiencyInfo
    literacy: LiteracyInfo
    background: BackgroundInfo = BackgroundInfo()


class RegistrationResponse(BaseModel):
    id: int
    student_name: str
    computed_level: Optional[int] = None
    status: str = "submitted"

    model_config = {"from_attributes": True}
