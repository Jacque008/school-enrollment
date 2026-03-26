from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.class_ import Class
from app.models.admin_user import AdminUser
from app.schemas.class_ import ClassCreate, ClassUpdate, ClassResponse
from app.services.auth import get_current_admin

router = APIRouter(prefix="/classes", tags=["admin-classes"])


@router.get("", response_model=list[ClassResponse])
async def list_classes(
    semester_id: int | None = None,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(Class)
    if semester_id:
        query = query.where(Class.semester_id == semester_id)
    result = await db.execute(query.order_by(Class.level, Class.name))
    return result.scalars().all()


@router.post("", response_model=ClassResponse)
async def create_class(
    data: ClassCreate,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    cls = Class(**data.model_dump())
    db.add(cls)
    await db.flush()
    return cls


@router.put("/{class_id}", response_model=ClassResponse)
async def update_class(
    class_id: int,
    data: ClassUpdate,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Class).where(Class.id == class_id))
    cls = result.scalar_one_or_none()
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(cls, field, value)

    await db.flush()
    return cls


@router.delete("/{class_id}")
async def delete_class(
    class_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Class).where(Class.id == class_id))
    cls = result.scalar_one_or_none()
    if not cls:
        raise HTTPException(status_code=404, detail="班级不存在")

    await db.delete(cls)
    return {"message": "已删除"}
