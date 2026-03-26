from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.literacy_test import LiteracyTest, LiteracyTestResult
from app.models.semester import Semester
from app.models.proficiency_assessment import ProficiencyAssessment
from app.models.guardian import Guardian
from app.models.student import Student
from app.services.auth import get_current_guardian
from pydantic import BaseModel

router = APIRouter(prefix="/literacy-test", tags=["literacy-test"])

class TestSubmit(BaseModel):
    student_id: int
    recognized: list[str]  # list of recognized characters
    total: int

def score_to_vocab_level(score_percent: int) -> int:
    if score_percent < 20: return 1
    if score_percent < 40: return 2
    if score_percent < 60: return 3
    if score_percent < 80: return 4
    return 5

@router.get("/current")
async def get_current_test(db: AsyncSession = Depends(get_db)):
    """Get active literacy test for current semester."""
    sem_result = await db.execute(select(Semester).where(Semester.is_active == True))
    semester = sem_result.scalar_one_or_none()
    if not semester:
        raise HTTPException(status_code=404, detail="没有开放的学期")

    test_result = await db.execute(
        select(LiteracyTest).where(
            LiteracyTest.semester_id == semester.id,
            LiteracyTest.is_active == True
        ).order_by(LiteracyTest.id.desc())
    )
    test = test_result.scalar_one_or_none()
    if not test:
        raise HTTPException(status_code=404, detail="当前没有识字量测试")

    return {
        "id": test.id,
        "name": test.name,
        "characters": test.characters,
        "total": len(test.characters)
    }

@router.post("/submit")
async def submit_test(
    data: TestSubmit,
    guardian: Guardian = Depends(get_current_guardian),
    db: AsyncSession = Depends(get_db),
):
    """Submit literacy test result and update vocab_level."""
    # Verify student belongs to this guardian
    student_result = await db.execute(
        select(Student).where(Student.id == data.student_id, Student.guardian_id == guardian.id)
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    # Get active test
    sem_result = await db.execute(select(Semester).where(Semester.is_active == True))
    semester = sem_result.scalar_one_or_none()

    test_result = await db.execute(
        select(LiteracyTest).where(
            LiteracyTest.semester_id == semester.id,
            LiteracyTest.is_active == True
        ).order_by(LiteracyTest.id.desc())
    )
    test = test_result.scalar_one_or_none()
    if not test:
        raise HTTPException(status_code=404, detail="测试不存在")

    recognized_count = len(data.recognized)
    total = data.total or len(test.characters)
    score_percent = round(recognized_count / total * 100) if total > 0 else 0
    vocab_level = score_to_vocab_level(score_percent)

    # Save result
    result = LiteracyTestResult(
        student_id=data.student_id,
        test_id=test.id,
        total_chars=total,
        recognized_count=recognized_count,
        score_percent=score_percent,
        derived_vocab_level=vocab_level,
    )
    db.add(result)

    # Update proficiency assessment vocab_level with test result
    assessment_result = await db.execute(
        select(ProficiencyAssessment).where(
            ProficiencyAssessment.student_id == data.student_id,
            ProficiencyAssessment.semester_id == semester.id,
        )
    )
    assessment = assessment_result.scalar_one_or_none()
    if assessment:
        assessment.vocab_level = vocab_level
        assessment.computed_level = assessment.compute_level()

    await db.flush()
    return {
        "score_percent": score_percent,
        "recognized_count": recognized_count,
        "total": total,
        "derived_vocab_level": vocab_level,
        "computed_level": assessment.computed_level if assessment else None,
    }
