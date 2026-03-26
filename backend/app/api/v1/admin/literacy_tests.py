from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.literacy_test import LiteracyTest
from app.models.semester import Semester
from app.models.admin_user import AdminUser
from app.services.auth import get_current_admin
import io

router = APIRouter(prefix="/literacy-tests", tags=["admin-literacy-tests"])

def parse_characters(content: str) -> list[str]:
    """Parse characters from text content. One char/word per line."""
    chars = []
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            chars.append(line)
    return chars

@router.get("")
async def list_tests(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(LiteracyTest).order_by(LiteracyTest.id.desc()))
    tests = result.scalars().all()
    return [
        {"id": t.id, "name": t.name, "semester_id": t.semester_id,
         "is_active": t.is_active, "total_chars": len(t.characters)}
        for t in tests
    ]

@router.post("")
async def upload_test(
    file: UploadFile = File(...),
    name: str = Form(...),
    semester_id: int = Form(...),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Upload a txt or docx file to create a literacy test."""
    filename = file.filename.lower()
    content_bytes = await file.read()

    if filename.endswith(".txt"):
        content = content_bytes.decode("utf-8-sig")
        characters = parse_characters(content)
    elif filename.endswith(".docx"):
        try:
            from docx import Document
            doc = Document(io.BytesIO(content_bytes))
            lines = []
            for para in doc.paragraphs:
                text = para.text.strip()
                if text:
                    lines.append(text)
            characters = lines
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"解析docx失败: {e}")
    else:
        raise HTTPException(status_code=400, detail="仅支持 .txt 或 .docx 文件")

    if not characters:
        raise HTTPException(status_code=400, detail="文件内容为空或格式不正确")

    test = LiteracyTest(
        name=name,
        semester_id=semester_id,
        characters=characters,
        is_active=True,
    )
    db.add(test)
    await db.flush()
    return {"id": test.id, "name": test.name, "total_chars": len(characters), "preview": characters[:10]}

@router.put("/{test_id}/toggle")
async def toggle_test(
    test_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(LiteracyTest).where(LiteracyTest.id == test_id))
    test = result.scalar_one_or_none()
    if not test:
        raise HTTPException(status_code=404, detail="测试不存在")
    test.is_active = not test.is_active
    await db.flush()
    return {"id": test.id, "is_active": test.is_active}

@router.delete("/{test_id}")
async def delete_test(
    test_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(LiteracyTest).where(LiteracyTest.id == test_id))
    test = result.scalar_one_or_none()
    if not test:
        raise HTTPException(status_code=404, detail="测试不存在")
    await db.delete(test)
    return {"message": "已删除"}
