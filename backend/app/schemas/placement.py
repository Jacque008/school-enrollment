from pydantic import BaseModel
from typing import Optional


class PlacementCandidate(BaseModel):
    class_id: int
    class_name: str
    score: int
    reasons: list[str]
    is_overflow: bool = False
    level_diff: int = 0
    band: str = ""          # xiao / zhong / gao
    band_label: str = ""    # 小班 / 中班 / 高班
    slot_match: bool = False
    slot_type: str = ""
    slot_label: str = ""    # 周六上午（实体）等短标签
    current_count: int = 0
    capacity: int = 15
    materials: list[str] = []
    teachers: list[str] = []


class PlacementResult(BaseModel):
    student_id: int
    student_name: str
    computed_level: int
    vocab_level: int        # effective vocab level used (test or self-assessed)
    vocab_label: str = ""   # 学生阅读识字量描述
    band: str               # student's determined band
    band_label: str
    preferred_slot_labels: list[str] = []
    sibling_in_school: bool = False
    sibling_info: Optional[str] = None
    other_notes: Optional[str] = None
    recommended: Optional[PlacementCandidate] = None
    alternatives: list[PlacementCandidate] = []


class ManualPlacement(BaseModel):
    student_id: int
    class_id: int


class PlacementConfirm(BaseModel):
    accepted: bool
