from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.semester import Semester
from app.schemas.semester import SemesterResponse

router = APIRouter(prefix="/semesters", tags=["semesters"])


@router.get("/current", response_model=SemesterResponse | None)
async def get_current_semester(db: AsyncSession = Depends(get_db)):
    """Get the currently active semester."""
    result = await db.execute(select(Semester).where(Semester.is_active == True))
    semester = result.scalar_one_or_none()
    if not semester:
        return None
    return semester
