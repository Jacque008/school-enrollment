from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.student import Student
from app.models.guardian import Guardian
from app.models.proficiency_assessment import ProficiencyAssessment
from app.models.enrollment import Enrollment
from app.models.admin_user import AdminUser
from app.schemas.admin import StudentListItem
from app.services.auth import get_current_admin

router = APIRouter(prefix="/students", tags=["admin-students"])


@router.get("", response_model=list[StudentListItem])
async def list_students(
    search: str | None = None,
    semester_id: int | None = None,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Student)
        .options(
            selectinload(Student.guardian),
            selectinload(Student.proficiency_assessments),
            selectinload(Student.enrollments),
        )
    )

    if search:
        query = query.where(Student.name.contains(search))

    result = await db.execute(query.order_by(Student.created_at.desc()))
    students = result.scalars().all()

    items = []
    for s in students:
        assessment = None
        if semester_id:
            assessment = next(
                (a for a in s.proficiency_assessments if a.semester_id == semester_id),
                None,
            )
        elif s.proficiency_assessments:
            assessment = max(s.proficiency_assessments, key=lambda a: a.id)

        enrollment = None
        if s.enrollments:
            enrollment = max(s.enrollments, key=lambda e: e.id)

        items.append(
            StudentListItem(
                id=s.id,
                name=s.name,
                guardian_name=s.guardian.name if s.guardian else "",
                computed_level=assessment.effective_level if assessment else None,
                enrollment_status=enrollment.status if enrollment else None,
            )
        )
    return items


@router.get("/{student_id}")
async def get_student_detail(
    student_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Student)
        .options(
            selectinload(Student.guardian),
            selectinload(Student.proficiency_assessments),
            selectinload(Student.reading_assessments),
            selectinload(Student.schedule_preferences),
            selectinload(Student.enrollments),
        )
        .where(Student.id == student_id)
    )
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    return {
        "id": student.id,
        "name": student.name,
        "gender": student.gender,
        "birth_date": student.birth_date.isoformat(),
        "city_region": student.city_region,
        "home_language": student.home_language,
        "sibling_in_school": student.sibling_in_school,
        "sibling_info": student.sibling_info,
        "learning_history": student.learning_history,
        "other_hobbies": student.other_hobbies,
        "parent_expectations": student.parent_expectations,
        "school_feedback": student.school_feedback,
        "other_notes": student.other_notes,
        "referral_source": student.referral_source,
        "accept_alternative": student.accept_alternative,
        "guardian": {
            "name": student.guardian.name,
            "email": student.guardian.email,
            "phone": student.guardian.phone,
            "wechat_id": student.guardian.wechat_id,
        },
        "assessments": [
            {
                "semester_id": a.semester_id,
                "listening": a.listening_level,
                "speaking": a.speaking_level,
                "writing": a.writing_level,
                "pinyin": a.pinyin_level,
                "vocab": a.vocab_level,
                "computed_level": a.computed_level,
                "admin_override": a.admin_override_level,
                "effective_level": a.effective_level,
            }
            for a in student.proficiency_assessments
        ],
        "reading": [
            {
                "semester_id": r.semester_id,
                "interest": r.reading_interest,
                "ability": r.reading_ability,
                "habits": r.reading_habits,
            }
            for r in student.reading_assessments
        ],
        "schedule_preferences": [
            {"semester_id": sp.semester_id, "slot_type": sp.slot_type}
            for sp in student.schedule_preferences
        ],
        "enrollments": [
            {
                "id": e.id,
                "class_id": e.class_id,
                "status": e.status,
                "waitlist_pos": e.waitlist_pos,
            }
            for e in student.enrollments
        ],
    }


@router.put("/{student_id}/override-level")
async def override_student_level(
    student_id: int,
    semester_id: int,
    level: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin override of computed level."""
    result = await db.execute(
        select(ProficiencyAssessment).where(
            ProficiencyAssessment.student_id == student_id,
            ProficiencyAssessment.semester_id == semester_id,
        )
    )
    assessment = result.scalar_one_or_none()
    if not assessment:
        raise HTTPException(status_code=404, detail="未找到该学生的评估记录")

    assessment.admin_override_level = level
    await db.flush()
    return {"message": "已覆盖等级", "effective_level": assessment.effective_level}
