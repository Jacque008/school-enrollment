from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models.student import Student
from app.models.class_ import Class
from app.models.enrollment import Enrollment
from app.models.proficiency_assessment import ProficiencyAssessment
from app.models.schedule_preference import SchedulePreference
from app.models.literacy_test import LiteracyTestResult
from app.models.material import ClassMaterial
from app.models.class_teacher import ClassTeacher
from app.schemas.placement import PlacementCandidate, PlacementResult

# ---------------------------------------------------------------------------
# Band classification
# ---------------------------------------------------------------------------
# Curriculum order: 行知中文1→2→3, 华文2→3→...→10→11→12, 华文初1→2→3→4→5
# DB level mapping:
#   行知中文N  → N          (1-3)
#   华文N      → N+2        (华文3→5, 华文4→6, ..., 华文12→14)
#   华文初N    → N+14       (初1→15, 初2→16, 初3→17, 初4→18, 初5→19)
#
# 小班: 行知中文1-3 + 华文2-3 → level 1-5
# 中班: 华文4-10              → level 6-12
# 高班: 华文11+               → level 13+
# ---------------------------------------------------------------------------

BAND_LABELS = {"xiao": "小班", "zhong": "中班", "gao": "高班"}

SLOT_LABELS = {
    "sat_onsite_am":       "周六上午（实体）",
    "sat_onsite_noon":     "周六中午（实体）",
    "sat_onsite_pm":       "周六下午（实体）",
    "weekend_online_am":   "周末上午（网课）",
    "weekend_online_noon": "周末中午（网课）",
    "weekend_online_pm":   "周末下午（网课）",
    "mini_online":         "迷你网课",
}

VOCAB_LABELS = {
    1: "不识字",
    2: "认识几十个字",
    3: "可以读带拼音的书",
    4: "能读不带拼音的书",
    5: "独立阅读各种中文书",
}

# Characters per level: 10 lessons × 9 chars = 90 new chars per book
CHARS_PER_LEVEL = 90


def get_class_band(level: int) -> str:
    """Return band key for a class given its DB level."""
    if level <= 5:
        return "xiao"
    elif level <= 12:
        return "zhong"
    else:
        return "gao"


def vocab_level_to_target(vocab_level: int, computed_level: int) -> tuple[str, int]:
    """
    Return (band, target_class_level) from student's effective vocab_level (1-5).

      1 → 不识字          → 行知中文1 (level 1)
      2 → 认识几十个字      → 行知中文2 (level 2)
      3 → 可读带拼音的书  → 华文3 (level 5)
      4 → 可读不带拼音的书→ 华文5-7 (level 7-9, 中班)
      5 → 独立阅读        → 华文8-11 (level 10-13, 中班上 / 高班)
    """
    if vocab_level <= 1:
        return "xiao", 1
    elif vocab_level == 2:
        return "xiao", 2
    elif vocab_level == 3:
        return "xiao", 5   # 华文3
    elif vocab_level == 4:
        if computed_level <= 3:
            return "zhong", 7   # 华文5
        else:
            return "zhong", 9   # 华文7
    else:  # vocab_level == 5
        if computed_level >= 4:
            return "gao", 13    # 华文11
        else:
            return "zhong", 10   # 华文8


def estimate_char_count(vocab_level: int) -> int:
    """Rough cumulative character count for display / info."""
    return vocab_level * CHARS_PER_LEVEL * 2  # ~90 new chars per half-year level


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_candidate(
    student: Student,
    cls: Class,
    student_band: str,
    target_level: int,
    preferred_slots: set[str],
    sibling_slots: set[str],
) -> PlacementCandidate | None:
    """
    Score a single class for a student.

    Priority order:
      1. Schedule match (PRIMARY, +100)
      2. Level match within band (SECONDARY, up to +40)
      3. Capacity / overflow
      4. Sibling & buddy bonuses
    """
    class_band = get_class_band(cls.level)

    # Mini classes are handled separately
    if cls.modality == "mini" or cls.slot_type.startswith("mini_online"):
        return None

    # --- Band filtering ---
    # Must be same band; adjacent band allowed only as last resort (penalty applied)
    band_diff = _band_distance(student_band, class_band)
    if band_diff > 1:
        return None  # Too far apart

    score = 0
    reasons = []
    is_overflow = False

    # 1. Band match
    if band_diff == 0:
        score += 60
        reasons.append(f"分班匹配（{BAND_LABELS[class_band]}）")
    else:
        score += 20
        reasons.append(f"相邻分班（学生{BAND_LABELS[student_band]}，班级{BAND_LABELS[class_band]}）")

    # 2. Schedule preference (PRIMARY weight)
    slot_match = cls.slot_type in preferred_slots
    if slot_match:
        score += 100
        reasons.append("时段首选匹配")
    elif student.accept_alternative:
        score += 5
        reasons.append("接受调剂时段")
    else:
        return None  # Doesn't accept non-preferred slot

    # 3. Level match within band
    level_diff = abs(target_level - cls.level)
    if level_diff == 0:
        score += 40
        reasons.append("等级精确匹配")
    elif level_diff == 1:
        score += 25
        reasons.append(f"等级差1（目标{target_level}，班级{cls.level}）")
    elif level_diff == 2:
        score += 10
        reasons.append(f"等级差2（目标{target_level}，班级{cls.level}）")
    elif level_diff >= 3:
        score += 0  # Large diff: still possible but no bonus
        reasons.append(f"等级差{level_diff}（目标{target_level}，班级{cls.level}）")

    # 4. Capacity
    if cls.current_count < cls.capacity:
        score += 20
        reasons.append("有空余名额")
    elif cls.current_count < cls.overflow_cap:
        score += 5
        is_overflow = True
        reasons.append("可超员接收")
    else:
        return None  # Completely full

    # 5. Sibling same slot
    if cls.slot_type in sibling_slots:
        score += 15
        reasons.append("兄弟姐妹同时段")

    # 6. Buddy request
    if student.other_notes and ("同班" in student.other_notes or "一起" in student.other_notes):
        score += 20
        reasons.append("含同班请求（需人工核实）")

    materials = [cm.material.name for cm in cls.class_materials if cm.material]
    teachers = [ct.teacher.name for ct in cls.class_teachers if ct.teacher]

    return PlacementCandidate(
        class_id=cls.id,
        class_name=cls.name,
        score=score,
        reasons=reasons,
        is_overflow=is_overflow,
        level_diff=level_diff,
        band=class_band,
        band_label=BAND_LABELS[class_band],
        slot_match=slot_match,
        slot_type=cls.slot_type,
        slot_label=SLOT_LABELS.get(cls.slot_type, cls.slot_type),
        current_count=cls.current_count,
        capacity=cls.capacity,
        materials=materials,
        teachers=teachers,
    )


def _band_distance(a: str, b: str) -> int:
    order = ["xiao", "zhong", "gao"]
    return abs(order.index(a) - order.index(b))


# ---------------------------------------------------------------------------
# Main placement function
# ---------------------------------------------------------------------------

async def run_placement_for_student(
    db: AsyncSession, student_id: int, semester_id: int
) -> PlacementResult:
    """Run placement algorithm for a single student."""
    result = await db.execute(
        select(Student)
        .options(
            selectinload(Student.proficiency_assessments),
            selectinload(Student.schedule_preferences),
            selectinload(Student.guardian),
        )
        .where(Student.id == student_id)
    )
    student = result.scalar_one_or_none()
    if not student:
        raise ValueError(f"Student {student_id} not found")

    assessment = next(
        (a for a in student.proficiency_assessments if a.semester_id == semester_id),
        None,
    )
    if not assessment:
        raise ValueError(f"No assessment found for student {student_id} in semester {semester_id}")

    # Check for literacy test result — use it if available
    test_result_row = await db.execute(
        select(LiteracyTestResult)
        .where(LiteracyTestResult.student_id == student_id)
        .order_by(LiteracyTestResult.id.desc())
        .limit(1)
    )
    test_result = test_result_row.scalar_one_or_none()

    # Effective vocab level: test result takes priority over self-assessed
    effective_vocab = (
        test_result.derived_vocab_level if test_result else assessment.vocab_level
    )
    student_band, target_level = vocab_level_to_target(
        effective_vocab, assessment.computed_level or 1
    )

    # Preferred schedule slots
    preferred_slots = {
        sp.slot_type
        for sp in student.schedule_preferences
        if sp.semester_id == semester_id
    }

    # Sibling slots (other enrolled children of same guardian)
    sibling_result = await db.execute(
        select(Enrollment)
        .join(Student, Enrollment.student_id == Student.id)
        .join(Class, Enrollment.class_id == Class.id)
        .where(
            Student.guardian_id == student.guardian_id,
            Student.id != student.id,
            Class.semester_id == semester_id,
            Enrollment.status == "enrolled",
        )
    )
    sibling_enrollments = sibling_result.scalars().all()
    sibling_slots: set[str] = set()
    for enr in sibling_enrollments:
        cls_r = await db.execute(select(Class).where(Class.id == enr.class_id))
        c = cls_r.scalar_one_or_none()
        if c:
            sibling_slots.add(c.slot_type)

    # All open non-mini classes for this semester (with materials and teachers)
    classes_result = await db.execute(
        select(Class)
        .options(
            selectinload(Class.class_materials).selectinload(ClassMaterial.material),
            selectinload(Class.class_teachers).selectinload(ClassTeacher.teacher),
        )
        .where(
            Class.semester_id == semester_id,
            Class.status != "closed",
            Class.modality != "mini",
        )
    )
    classes = classes_result.scalars().all()

    # Score each class
    candidates: list[PlacementCandidate] = []
    for cls in classes:
        candidate = score_candidate(
            student, cls, student_band, target_level, preferred_slots, sibling_slots
        )
        if candidate:
            candidates.append(candidate)

    # Sort: level match first (beginners must go to correct level),
    # then slot match as tiebreaker, then overall score.
    candidates.sort(key=lambda c: (c.level_diff, not c.slot_match, -c.score))

    recommended = candidates[0] if candidates else None
    # 3 alternatives (excluding the recommended)
    alternatives = candidates[1:4] if len(candidates) > 1 else []

    preferred_slot_labels = [
        SLOT_LABELS.get(sp.slot_type, sp.slot_type)
        for sp in student.schedule_preferences
        if sp.semester_id == semester_id
    ]

    return PlacementResult(
        student_id=student.id,
        student_name=student.name,
        computed_level=assessment.computed_level or 1,
        vocab_level=effective_vocab,
        vocab_label=VOCAB_LABELS.get(effective_vocab, str(effective_vocab)),
        band=student_band,
        band_label=BAND_LABELS[student_band],
        preferred_slot_labels=preferred_slot_labels,
        sibling_in_school=student.sibling_in_school,
        sibling_info=student.sibling_info,
        other_notes=student.other_notes,
        recommended=recommended,
        alternatives=alternatives,
    )


async def run_batch_placement(
    db: AsyncSession, semester_id: int
) -> list[PlacementResult]:
    """Run placement for all unplaced students in a semester."""
    result = await db.execute(
        select(Student.id)
        .join(ProficiencyAssessment)
        .where(ProficiencyAssessment.semester_id == semester_id)
        .except_(
            select(Student.id)
            .join(Enrollment)
            .join(Class)
            .where(
                Class.semester_id == semester_id,
                Enrollment.status.in_(["enrolled", "waitlisted"]),
            )
        )
    )
    student_ids = [row[0] for row in result.all()]

    results = []
    for sid in student_ids:
        try:
            placement = await run_placement_for_student(db, sid, semester_id)
            results.append(placement)
        except ValueError:
            continue

    return results
