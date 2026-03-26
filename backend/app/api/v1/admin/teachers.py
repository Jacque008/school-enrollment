from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.teacher import Teacher
from app.models.admin_user import AdminUser
from app.schemas.admin import TeacherCreate, TeacherResponse
from app.services.auth import get_current_admin

router = APIRouter(prefix="/teachers", tags=["admin-teachers"])


@router.get("", response_model=list[TeacherResponse])
async def list_teachers(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Teacher).order_by(Teacher.name))
    return result.scalars().all()


@router.post("", response_model=TeacherResponse)
async def create_teacher(
    data: TeacherCreate,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    teacher = Teacher(**data.model_dump())
    db.add(teacher)
    await db.flush()
    return teacher


@router.put("/{teacher_id}", response_model=TeacherResponse)
async def update_teacher(
    teacher_id: int,
    data: TeacherCreate,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Teacher).where(Teacher.id == teacher_id))
    teacher = result.scalar_one_or_none()
    if not teacher:
        raise HTTPException(status_code=404, detail="教师不存在")

    for field, value in data.model_dump().items():
        setattr(teacher, field, value)
    await db.flush()
    return teacher


@router.delete("/{teacher_id}")
async def delete_teacher(
    teacher_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Teacher).where(Teacher.id == teacher_id))
    teacher = result.scalar_one_or_none()
    if not teacher:
        raise HTTPException(status_code=404, detail="教师不存在")

    await db.delete(teacher)
    return {"message": "已删除"}
