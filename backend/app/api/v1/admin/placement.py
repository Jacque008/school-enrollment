from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.admin_user import AdminUser
from app.models.enrollment import Enrollment
from app.models.class_ import Class
from app.models.student import Student
from app.schemas.placement import PlacementResult, ManualPlacement
from app.services.auth import get_current_admin
from app.services.placement import run_batch_placement, run_placement_for_student

router = APIRouter(prefix="/placement", tags=["admin-placement"])


@router.post("/run", response_model=list[PlacementResult])
async def run_placement(
    semester_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Run batch placement algorithm for all unplaced students."""
    results = await run_batch_placement(db, semester_id)
    return results


@router.post("/run/{student_id}", response_model=PlacementResult)
async def run_single_placement(
    student_id: int,
    semester_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Run placement for a single student."""
    try:
        result = await run_placement_for_student(db, student_id, semester_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.post("/manual")
async def manual_placement(
    data: ManualPlacement,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Manually assign a student to a class."""
    # Verify student exists
    student_result = await db.execute(
        select(Student).where(Student.id == data.student_id)
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    # Verify class exists and has room
    cls_result = await db.execute(select(Class).where(Class.id == data.class_id))
    cls = cls_result.scalar_one_or_none()
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")

    # Check existing enrollment
    existing = await db.execute(
        select(Enrollment).where(
            Enrollment.student_id == data.student_id,
            Enrollment.class_id == data.class_id,
            Enrollment.status.in_(["enrolled", "waitlisted"]),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该学生已在此班级中")

    # Create enrollment
    if cls.current_count < cls.overflow_cap:
        status = "enrolled"
        cls.current_count += 1
        if cls.current_count >= cls.capacity:
            cls.status = "full"
        waitlist_pos = None
    else:
        status = "waitlisted"
        # Find max waitlist position
        max_pos_result = await db.execute(
            select(Enrollment.waitlist_pos)
            .where(
                Enrollment.class_id == data.class_id,
                Enrollment.status == "waitlisted",
            )
            .order_by(Enrollment.waitlist_pos.desc())
        )
        max_pos = max_pos_result.scalar() or 0
        waitlist_pos = max_pos + 1

    enrollment = Enrollment(
        student_id=data.student_id,
        class_id=data.class_id,
        status=status,
        waitlist_pos=waitlist_pos,
    )
    db.add(enrollment)
    await db.flush()

    return {
        "message": "已分配" if status == "enrolled" else "已加入候补",
        "enrollment_id": enrollment.id,
        "status": status,
        "waitlist_pos": waitlist_pos,
    }
