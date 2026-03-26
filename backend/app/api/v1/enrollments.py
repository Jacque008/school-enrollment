from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.guardian import Guardian
from app.models.student import Student
from app.models.enrollment import Enrollment
from app.models.class_ import Class
from app.schemas.placement import PlacementConfirm
from app.services.auth import get_current_guardian
from pydantic import BaseModel

router = APIRouter(prefix="/enrollments", tags=["enrollments"])


class EnrollmentResponse(BaseModel):
    id: int
    student_name: str
    class_name: str
    status: str
    waitlist_pos: int | None = None

    model_config = {"from_attributes": True}


@router.get("/my", response_model=list[EnrollmentResponse])
async def my_enrollments(
    guardian: Guardian = Depends(get_current_guardian),
    db: AsyncSession = Depends(get_db),
):
    """Get enrollment results for the current guardian's children."""
    result = await db.execute(
        select(Enrollment)
        .join(Student)
        .options(
            selectinload(Enrollment.student),
            selectinload(Enrollment.class_),
        )
        .where(Student.guardian_id == guardian.id)
    )
    enrollments = result.scalars().all()

    return [
        EnrollmentResponse(
            id=e.id,
            student_name=e.student.name,
            class_name=e.class_.name,
            status=e.status,
            waitlist_pos=e.waitlist_pos,
        )
        for e in enrollments
    ]


@router.post("/{enrollment_id}/confirm")
async def confirm_enrollment(
    enrollment_id: int,
    data: PlacementConfirm,
    guardian: Guardian = Depends(get_current_guardian),
    db: AsyncSession = Depends(get_db),
):
    """Confirm or reject an enrollment."""
    result = await db.execute(
        select(Enrollment)
        .join(Student)
        .options(selectinload(Enrollment.class_))
        .where(
            Enrollment.id == enrollment_id,
            Student.guardian_id == guardian.id,
        )
    )
    enrollment = result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="未找到该注册记录")

    if data.accepted:
        enrollment.status = "enrolled"
    else:
        enrollment.status = "dropped"
        # Decrement class count
        enrollment.class_.current_count = max(
            0, enrollment.class_.current_count - 1
        )

    await db.flush()
    return {"message": "已确认" if data.accepted else "已取消"}
