from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.semester import Semester
from app.models.admin_user import AdminUser
from app.schemas.semester import SemesterCreate, SemesterUpdate, SemesterResponse
from app.services.auth import get_current_admin

router = APIRouter(prefix="/semesters", tags=["admin-semesters"])


@router.get("", response_model=list[SemesterResponse])
async def list_semesters(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Semester).order_by(Semester.start_date.desc()))
    return result.scalars().all()


@router.post("", response_model=SemesterResponse)
async def create_semester(
    data: SemesterCreate,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    semester = Semester(**data.model_dump())
    db.add(semester)
    await db.flush()
    return semester


@router.put("/{semester_id}", response_model=SemesterResponse)
async def update_semester(
    semester_id: int,
    data: SemesterUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Semester).where(Semester.id == semester_id))
    semester = result.scalar_one_or_none()
    if not semester:
        raise HTTPException(status_code=404, detail="学期不存在")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(semester, field, value)

    await db.flush()
    return semester


@router.delete("/{semester_id}")
async def delete_semester(
    semester_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Semester).where(Semester.id == semester_id))
    semester = result.scalar_one_or_none()
    if not semester:
        raise HTTPException(status_code=404, detail="学期不存在")

    await db.delete(semester)
    return {"message": "已删除"}
