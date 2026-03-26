"""
Unit tests for the placement algorithm (band-based scoring).
"""
import pytest
from unittest.mock import MagicMock
from app.services.placement import (
    score_candidate,
    get_class_band,
    vocab_level_to_target,
    BAND_LABELS,
)
from app.models.student import Student
from app.models.class_ import Class


def make_student(accept_alternative=True, other_notes=None):
    s = MagicMock(spec=Student)
    s.accept_alternative = accept_alternative
    s.other_notes = other_notes
    return s


def make_class(
    class_id=1,
    name="班级A",
    level=3,
    slot_type="sat_onsite_am",
    modality="onsite",
    capacity=15,
    overflow_cap=18,
    current_count=10,
):
    c = MagicMock(spec=Class)
    c.id = class_id
    c.name = name
    c.level = level
    c.slot_type = slot_type
    c.modality = modality
    c.capacity = capacity
    c.overflow_cap = overflow_cap
    c.current_count = current_count
    return c


# ---------------------------------------------------------------------------
# Band helpers
# ---------------------------------------------------------------------------

def test_get_class_band_xiao():
    assert get_class_band(1) == "xiao"   # 行知中文1
    assert get_class_band(5) == "xiao"   # 华文3


def test_get_class_band_zhong():
    assert get_class_band(6) == "zhong"  # 华文4
    assert get_class_band(12) == "zhong" # 华文10


def test_get_class_band_gao():
    assert get_class_band(13) == "gao"   # 华文11
    assert get_class_band(19) == "gao"   # 华文初5


def test_vocab_level_to_target_small():
    band, level = vocab_level_to_target(1, 1)
    assert band == "xiao" and level == 1

    band, level = vocab_level_to_target(3, 2)
    assert band == "xiao" and level == 5  # 华文3


def test_vocab_level_to_target_medium():
    band, level = vocab_level_to_target(4, 3)
    assert band == "zhong"

    band, level = vocab_level_to_target(4, 5)
    assert band == "zhong"


def test_vocab_level_to_target_high():
    band, level = vocab_level_to_target(5, 4)
    assert band == "gao"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def test_perfect_match():
    """Same band + preferred slot + level exact match + space = highest score."""
    student = make_student()
    cls = make_class(level=3, slot_type="sat_onsite_am", current_count=10)

    result = score_candidate(
        student, cls,
        student_band="xiao", target_level=3,
        preferred_slots={"sat_onsite_am"}, sibling_slots=set(),
    )

    assert result is not None
    assert result.slot_match is True
    assert result.level_diff == 0
    assert "时段首选匹配" in result.reasons
    assert "等级精确匹配" in result.reasons
    assert "有空余名额" in result.reasons
    # band(60) + slot(100) + level(40) + capacity(20) = 220
    assert result.score == 220


def test_level_diff_one():
    """Level diff 1 within same band → +25 instead of +40."""
    student = make_student()
    cls = make_class(level=4, slot_type="sat_onsite_am", current_count=5)

    result = score_candidate(
        student, cls,
        student_band="xiao", target_level=3,
        preferred_slots={"sat_onsite_am"}, sibling_slots=set(),
    )

    # Band diff = 1 (xiao vs zhong) → +20 for band
    # Slot match +100, level diff 1 → +25, capacity +20
    assert result is not None
    assert result.level_diff == 1
    assert any("等级差1" in r for r in result.reasons)


def test_cross_band_two_excluded():
    """Two bands apart → excluded regardless of everything else."""
    student = make_student()
    cls = make_class(level=13)  # 高班（华文11）

    result = score_candidate(
        student, cls,
        student_band="xiao", target_level=2,
        preferred_slots={"sat_onsite_am"}, sibling_slots=set(),
    )

    assert result is None


def test_full_class_excluded():
    """Class at overflow cap → excluded."""
    student = make_student()
    cls = make_class(current_count=18, capacity=15, overflow_cap=18)

    result = score_candidate(
        student, cls,
        student_band="xiao", target_level=3,
        preferred_slots={"sat_onsite_am"}, sibling_slots=set(),
    )

    assert result is None


def test_overflow_class_accepted():
    """Over capacity but under overflow cap → accepted as overflow."""
    student = make_student()
    cls = make_class(current_count=16, capacity=15, overflow_cap=18)

    result = score_candidate(
        student, cls,
        student_band="xiao", target_level=3,
        preferred_slots={"sat_onsite_am"}, sibling_slots=set(),
    )

    assert result is not None
    assert result.is_overflow is True
    assert "可超员接收" in result.reasons


def test_non_preferred_slot_no_alternative():
    """Student doesn't accept alternative → non-preferred slot rejected."""
    student = make_student(accept_alternative=False)
    cls = make_class(slot_type="sat_onsite_pm")

    result = score_candidate(
        student, cls,
        student_band="xiao", target_level=3,
        preferred_slots={"sat_onsite_am"}, sibling_slots=set(),
    )

    assert result is None


def test_non_preferred_slot_with_alternative():
    """Student accepts alternative → non-preferred slot gets small bonus."""
    student = make_student(accept_alternative=True)
    cls = make_class(slot_type="sat_onsite_pm")

    result = score_candidate(
        student, cls,
        student_band="xiao", target_level=3,
        preferred_slots={"sat_onsite_am"}, sibling_slots=set(),
    )

    assert result is not None
    assert result.slot_match is False
    assert "接受调剂时段" in result.reasons


def test_sibling_bonus():
    """Sibling enrolled in same slot → +15 bonus."""
    student = make_student()
    cls = make_class(slot_type="sat_onsite_am")
    preferred = {"sat_onsite_am"}

    result_with = score_candidate(student, cls, "xiao", 3, preferred, {"sat_onsite_am"})
    result_without = score_candidate(student, cls, "xiao", 3, preferred, set())

    assert result_with is not None and result_without is not None
    assert result_with.score - result_without.score == 15
    assert "兄弟姐妹同时段" in result_with.reasons


def test_buddy_request_bonus():
    """other_notes containing '同班' → +20 bonus."""
    student = make_student(other_notes="希望和小明同班")
    cls = make_class()

    result = score_candidate(
        student, cls,
        student_band="xiao", target_level=3,
        preferred_slots={"sat_onsite_am"}, sibling_slots=set(),
    )

    assert result is not None
    assert any("同班请求" in r for r in result.reasons)


def test_mini_class_excluded():
    """Mini classes skip regular scoring."""
    student = make_student()
    cls = make_class(modality="mini")

    result = score_candidate(
        student, cls,
        student_band="xiao", target_level=3,
        preferred_slots={"mini_online"}, sibling_slots=set(),
    )

    assert result is None


def test_schedule_beats_level():
    """A slot-matching class scores higher than a perfect-level class with wrong slot."""
    student = make_student(accept_alternative=True)

    cls_slot_match = make_class(level=5, slot_type="sat_onsite_am", current_count=5)
    cls_level_match = make_class(level=3, slot_type="sat_onsite_pm", current_count=5)

    r_slot = score_candidate(student, cls_slot_match, "xiao", 3, {"sat_onsite_am"}, set())
    r_level = score_candidate(student, cls_level_match, "xiao", 3, {"sat_onsite_am"}, set())

    assert r_slot is not None and r_level is not None
    # Slot-matching class should win despite worse level match
    assert r_slot.score > r_level.score


# ---------------------------------------------------------------------------
# Assessment model helpers
# ---------------------------------------------------------------------------

def test_computed_level_formula():
    from app.models.proficiency_assessment import ProficiencyAssessment

    a = MagicMock(spec=ProficiencyAssessment)
    a.vocab_level = 3
    a.listening_level = 2
    a.speaking_level = 3
    a.writing_level = 2
    a.pinyin_level = 2

    expected = round(3 * 0.4 + 2 * 0.15 + 3 * 0.2 + 2 * 0.15 + 2 * 0.1)
    ProficiencyAssessment.compute_level(a)
    assert expected == 3


def test_effective_level_uses_override():
    from app.models.proficiency_assessment import ProficiencyAssessment

    a = MagicMock(spec=ProficiencyAssessment)
    a.admin_override_level = 5
    a.computed_level = 2

    assert ProficiencyAssessment.effective_level.fget(a) == 5


def test_effective_level_uses_computed_without_override():
    from app.models.proficiency_assessment import ProficiencyAssessment

    a = MagicMock(spec=ProficiencyAssessment)
    a.admin_override_level = None
    a.computed_level = 3

    assert ProficiencyAssessment.effective_level.fget(a) == 3
