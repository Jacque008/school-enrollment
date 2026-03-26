"""
Import 2026年春季学期教学安排表.csv into the database.
Run from backend/ directory:
    PYTHONPATH=. python scripts/import_schedule.py
"""
import asyncio
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.database import async_session, engine
from app.models.base import Base
from app.models.class_ import Class
from app.models.class_teacher import ClassTeacher
from app.models.material import Material, ClassMaterial
from app.models.semester import Semester
from app.models.teacher import Teacher

CSV_PATH = Path(__file__).parent.parent.parent / "2026年春季学期教学安排表.csv"
SEMESTER_NAME = "2025春季"  # must match existing active semester


from datetime import time as dt_time

def parse_time(time_str: str) -> dt_time:
    """Convert '09:30-11:30' → time(9, 30)"""
    time_str = time_str.strip()
    if not time_str:
        return dt_time(9, 0)
    start = time_str.split("-")[0].strip()
    parts = start.split(":")
    if len(parts) == 2:
        return dt_time(int(parts[0]), int(parts[1]))
    return dt_time(9, 0)


def infer_slot_type(modality: str, schedule_day: str, time_str: str) -> str:
    time_str = time_str.strip()
    start_hour = int(time_str.split(":")[0]) if time_str else 9
    if modality == "onsite":
        if start_hour < 12:
            return "sat_onsite_am"
        elif start_hour < 15:
            return "sat_onsite_noon"
        else:
            return "sat_onsite_pm"
    else:  # online
        if start_hour < 12:
            return "weekend_online_am"
        elif start_hour < 15:
            return "weekend_online_noon"
        else:
            return "weekend_online_pm"


def infer_level(material: str) -> int:
    """Best-effort level from material name."""
    material = material.strip()
    # 华文初X
    m = re.search(r'初(\d+)', material)
    if m:
        return 12 + int(m.group(1))
    # 华文X
    m = re.search(r'华文(\d+)', material)
    if m:
        n = int(m.group(1))
        # Map: 1-8 direct, 10→9, 11→10, 12→11
        mapping = {1:1,2:2,3:3,4:4,5:5,6:6,7:7,8:8,10:9,11:10,12:11}
        return mapping.get(n, n)
    # 行知中文X
    m = re.search(r'行知中文(\d+)', material)
    if m:
        return int(m.group(1))
    # 自编 / 拼音 → beginner
    if '自编' in material or '拼音' in material:
        return 1
    return 1


def parse_csv(path: Path) -> list[dict]:
    """Parse CSV into list of class dicts, handling merged cells."""
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        raw = list(reader)

    current_category = ""
    i = 0
    while i < len(raw):
        row = raw[i]
        # Pad to at least 10 columns
        while len(row) < 10:
            row.append("")

        # Skip header row
        if "班级名称" in row[1] or "班级名称" in row[2]:
            i += 1
            continue

        # Detect category (col 1)
        if row[1].strip():
            current_category = row[1].strip()

        class_name = row[2].strip()
        if not class_name:
            i += 1
            continue

        # Handle multiline CSV cell (狗尾巴草 case)
        # If col 9 (teacher) is empty and next row starts with content that looks like
        # a continuation, merge it
        student_count = row[3].strip()
        time_str = row[4].strip()
        room = row[5].strip()
        material = row[6].strip()
        teacher = row[9].strip()

        # If material ends with quote (split cell), look ahead and merge
        if material.endswith('"') or (not teacher and not student_count and i + 1 < len(raw)):
            next_row = raw[i + 1] if i + 1 < len(raw) else []
            while len(next_row) < 10:
                next_row.append("")
            # Check if next row is a continuation (col 2 empty, col 1 empty)
            if not next_row[1].strip() and not next_row[2].strip() and next_row[0]:
                # continuation row: cols shift left by some amount
                # format: is",17,谈建芬 → student_count=17, teacher=谈建芬
                if not student_count:
                    student_count = next_row[1].strip() if next_row[1].strip() else next_row[3].strip()
                if not teacher:
                    teacher = next_row[2].strip() if next_row[2].strip() else next_row[9].strip()
                material = material.strip('"')
                i += 1  # skip continuation row

        # Determine modality and day
        if current_category == "周六实体课":
            modality = "onsite"
            schedule_day = "SAT"
        elif current_category == "周六网课班":
            modality = "online"
            schedule_day = "SAT"
        elif current_category == "周日网课班":
            modality = "online"
            schedule_day = "SUN"
        else:
            i += 1
            continue

        # Parse meeting link for online classes
        meeting_link = None
        room_clean = room
        if modality == "online" and "/" in room:
            parts = room.split("/")
            meeting_link = f"会议号: {parts[0].strip()} 密码: {parts[1].strip()}"
            room_clean = None

        rows.append({
            "category": current_category,
            "name": class_name,
            "student_count": int(student_count) if student_count.isdigit() else 0,
            "time_str": time_str,
            "room": room_clean if modality == "onsite" else None,
            "meeting_link": meeting_link,
            "material": material,
            "teacher": teacher,
            "modality": modality,
            "schedule_day": schedule_day,
            "level": infer_level(material),
            "slot_type": infer_slot_type(modality, schedule_day, time_str),
            "schedule_time": parse_time(time_str),
        })
        i += 1

    return rows


async def import_data():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    rows = parse_csv(CSV_PATH)
    print(f"Parsed {len(rows)} classes from CSV")

    async with async_session() as db:
        # Get active semester
        result = await db.execute(
            select(Semester).where(Semester.is_active == True)
        )
        semester = result.scalar_one_or_none()
        if not semester:
            print("ERROR: No active semester found. Create one first.")
            return

        print(f"Using semester: {semester.name} (id={semester.id})")

        # Clear existing classes for this semester (fresh import)
        existing = await db.execute(
            select(Class).where(Class.semester_id == semester.id)
        )
        for cls in existing.scalars().all():
            await db.delete(cls)
        await db.flush()
        print("Cleared existing classes.")

        # Cache teachers by name
        teacher_cache: dict[str, Teacher] = {}

        async def get_or_create_teacher(name: str) -> Teacher:
            name = name.strip()
            if not name:
                return None
            if name in teacher_cache:
                return teacher_cache[name]
            result = await db.execute(
                select(Teacher).where(Teacher.name == name)
            )
            t = result.scalar_one_or_none()
            if not t:
                t = Teacher(name=name)
                db.add(t)
                await db.flush()
                print(f"  Created teacher: {name}")
            teacher_cache[name] = t
            return t

        # Cache materials by name
        material_cache: dict[str, Material] = {}

        async def get_or_create_material(name: str, level: int) -> Material:
            name = name.strip()
            if not name:
                return None
            if name in material_cache:
                return material_cache[name]
            result = await db.execute(
                select(Material).where(Material.name == name)
            )
            m = result.scalar_one_or_none()
            if not m:
                m = Material(name=name, level=level)
                db.add(m)
                await db.flush()
            material_cache[name] = m
            return m

        for row in rows:
            cls = Class(
                semester_id=semester.id,
                name=row["name"],
                level=row["level"],
                slot_type=row["slot_type"],
                schedule_day=row["schedule_day"],
                schedule_time=row["schedule_time"],
                duration_min=120,
                modality=row["modality"],
                room=row["room"],
                meeting_link=row["meeting_link"],
                capacity=row["student_count"] if row["student_count"] > 0 else 15,
                overflow_cap=(row["student_count"] + 3) if row["student_count"] > 0 else 18,
                current_count=row["student_count"],
                status="open",
            )
            db.add(cls)
            await db.flush()

            # Teacher
            if row["teacher"]:
                teacher = await get_or_create_teacher(row["teacher"])
                if teacher:
                    ct = ClassTeacher(
                        class_id=cls.id,
                        teacher_id=teacher.id,
                        role="primary",
                    )
                    db.add(ct)

            # Material
            if row["material"]:
                material = await get_or_create_material(row["material"], row["level"])
                if material:
                    cm = ClassMaterial(class_id=cls.id, material_id=material.id)
                    db.add(cm)

            print(f"  [{row['category']}] {row['name']} | {row['time_str']} | "
                  f"级别{row['level']} | {row['modality']} | 教师:{row['teacher'] or '待定'}")

        await db.commit()
        print(f"\n✓ 导入完成：{len(rows)} 个班级")

        # Summary
        result = await db.execute(select(Teacher))
        teachers = result.scalars().all()
        result2 = await db.execute(select(Material))
        materials = result2.scalars().all()
        print(f"  教师: {len(teachers)} 人")
        print(f"  教材: {len(materials)} 种")


if __name__ == "__main__":
    asyncio.run(import_data())
