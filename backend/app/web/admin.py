import asyncio
import json as _json
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jose import JWTError
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.admin_user import AdminUser, ROLE_LABELS, ROLE_SUPERADMIN, ROLE_SENIOR_ADMIN, ROLE_TEACHER
from app.models.class_ import Class
from app.models.class_teacher import ClassTeacher
from app.models.enrollment import Enrollment
from app.models.guardian import Guardian
from app.models.literacy_test import LiteracyTest, LiteracyTestResult
from app.models.material import ClassMaterial, Material
from app.models.proficiency_assessment import ProficiencyAssessment
from app.models.reading_assessment import ReadingAssessment
from app.models.schedule_preference import SchedulePreference
from app.models.semester import Semester
from app.models.student import Student
from app.models.teacher import Teacher
from app.models.tuition import GuardianFlag, TuitionRecord
from app.models.settings import SystemSettings, SETTINGS_DEFAULTS
from app.services.placement import run_placement_for_student
from app.services.auth import (
    _decode_token,
    create_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

SLOT_LABELS = {
    "sat_onsite_am": "周六上午（实体）",
    "sat_onsite_noon": "周六中午（实体）",
    "sat_onsite_pm": "周六下午（实体）",
    "weekend_online_am": "周末上午（网课）",
    "weekend_online_noon": "周末中午（网课）",
    "weekend_online_pm": "周末下午（网课）",
    "mini_online": "迷你网课",
}

VOCAB_LABELS = {1: "不识字", 2: "认识几十个字", 3: "识数百字", 4: "识千字以上", 5: "流利阅读"}

LEVEL_MATERIALS = {
    1: "行知中文1", 2: "行知中文2", 3: "行知中文3",
    4: "华文2", 5: "华文3", 6: "华文4", 7: "华文5",
    8: "华文6", 9: "华文7", 10: "华文8", 11: "华文9",
    12: "华文10", 13: "华文11", 14: "华文12",
    15: "华文初一", 16: "华文初二", 17: "华文初三",
    18: "华文初四", 19: "华文初五",
}

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

async def _get_admin(request: Request, db: AsyncSession) -> AdminUser | None:
    token = request.cookies.get("admin_token")
    if not token:
        return None
    try:
        user_id, user_type = _decode_token(token)
        if user_type != "admin":
            return None
    except (JWTError, ValueError):
        return None
    result = await db.execute(select(AdminUser).where(AdminUser.id == user_id))
    admin = result.scalar_one_or_none()
    return admin if (admin and admin.is_active) else None


def _login_redirect():
    return RedirectResponse("/admin/login", status_code=303)


def _forbidden(redirect_to: str = "/admin/"):
    return RedirectResponse(f"{redirect_to}?err=权限不足", status_code=303)


def _ok(path: str, msg: str = ""):
    url = path + (f"?ok={msg}" if msg else "")
    return RedirectResponse(url, status_code=303)


def _err(path: str, msg: str):
    return RedirectResponse(f"{path}?err={msg}", status_code=303)


async def _active_semester(db: AsyncSession) -> Semester | None:
    r = await db.execute(select(Semester).where(Semester.is_active == True))
    return r.scalar_one_or_none()


async def _get_settings(db: AsyncSession) -> dict:
    """Return all system settings as {key: int_value}, falling back to defaults."""
    r = await db.execute(select(SystemSettings))
    stored = {s.key: s.value for s in r.scalars().all()}
    result = {}
    for key, (default_val, _label) in SETTINGS_DEFAULTS.items():
        result[key] = int(stored.get(key, default_val))
    return result


def _derive_slot_type(schedule_day: str, schedule_time_str: str, modality: str) -> str:
    """Derive slot_type from day + time + modality (replaces manual selection)."""
    if modality == "mini":
        return "mini_online"
    h, m = (int(x) for x in schedule_time_str.split(":"))
    minutes = h * 60 + m
    if minutes < 11 * 60:
        period = "am"
    elif minutes < 13 * 60 + 30:
        period = "noon"
    else:
        period = "pm"
    if modality == "onsite":
        return f"sat_onsite_{period}"
    return f"weekend_online_{period}"


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "admin/login.html")


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AdminUser).where(AdminUser.username == username))
    admin = result.scalar_one_or_none()
    if not admin or not verify_password(password, admin.hashed_password):
        return templates.TemplateResponse(
            request,
            "admin/login.html",
            {"error": "用户名或密码错误"},
            status_code=401,
        )
    token = create_access_token(
        {"sub": str(admin.id), "type": "admin"},
        expires_delta=timedelta(hours=8),
    )
    response = RedirectResponse("/admin/", status_code=303)
    response.set_cookie("admin_token", token, httponly=True, max_age=28800)
    return response


@router.get("/logout")
async def logout():
    response = _login_redirect()
    response.delete_cookie("admin_token")
    return response


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    semester = await _active_semester(db)

    # Enrolled students this semester
    enrolled_count = 0
    unplaced = 0
    new_students_count = 0  # assessed this semester (placed + pending)
    if semester:
        enrolled_r = await db.execute(
            select(func.count(Enrollment.id))
            .join(Class, Class.id == Enrollment.class_id)
            .where(Class.semester_id == semester.id, Enrollment.status == "enrolled")
        )
        enrolled_count = enrolled_r.scalar() or 0

        placed_ids = (
            select(Enrollment.student_id)
            .join(Class, Class.id == Enrollment.class_id)
            .where(
                Class.semester_id == semester.id,
                Enrollment.status.in_(["enrolled", "waitlisted"]),
            )
        )
        assessed_ids = (
            select(ProficiencyAssessment.student_id)
            .where(ProficiencyAssessment.semester_id == semester.id)
            .distinct()
        )
        # Count actual Student rows — same logic as pending_students_list
        unplaced_r = await db.execute(
            select(func.count(Student.id))
            .where(Student.id.in_(assessed_ids), Student.id.not_in(placed_ids))
        )
        unplaced = unplaced_r.scalar() or 0

        # Count actual Student rows to avoid orphaned assessment inflation
        new_r = await db.execute(
            select(func.count(Student.id))
            .where(Student.id.in_(assessed_ids))
        )
        new_students_count = new_r.scalar() or 0

    # Teacher count
    teacher_count_r = await db.execute(select(func.count(Teacher.id)))
    teacher_count = teacher_count_r.scalar() or 0

    # For teacher role: scope everything to their assigned classes
    teacher_class_ids: set[int] = set()
    if admin.role == ROLE_TEACHER and admin.teacher_id and semester:
        tc_r = await db.execute(
            select(ClassTeacher.class_id)
            .join(Class, Class.id == ClassTeacher.class_id)
            .where(ClassTeacher.teacher_id == admin.teacher_id, Class.semester_id == semester.id)
        )
        teacher_class_ids = {row[0] for row in tc_r.all()}

    # Scope people counts to teacher's classes if applicable
    if admin.role == ROLE_TEACHER and semester:
        if teacher_class_ids:
            enrolled_r = await db.execute(
                select(func.count(Enrollment.id))
                .where(Enrollment.class_id.in_(teacher_class_ids), Enrollment.status == "enrolled")
            )
            enrolled_count = enrolled_r.scalar() or 0
        else:
            enrolled_count = 0
        unplaced = 0
        new_students_count = 0
        teacher_count = 0

    # Class capacity overview + stats breakdown
    classes = []
    enrolled_counts = {}
    onsite = {"total": 0, "am": 0, "noon": 0, "pm": 0}
    sat_online = {"total": 0, "am": 0, "noon": 0, "pm": 0}
    sun_online = {"total": 0, "am": 0, "noon": 0, "pm": 0}
    mini = {"total": 0, "1v1": 0, "1v2": 0, "1v3": 0}

    if semester:
        cls_q = (
            select(Class)
            .options(
                selectinload(Class.class_materials).selectinload(ClassMaterial.material),
                selectinload(Class.class_teachers).selectinload(ClassTeacher.teacher),
            )
            .where(Class.semester_id == semester.id)
            .order_by(Class.level, Class.name)
        )
        if admin.role == ROLE_TEACHER:
            cls_q = cls_q.where(Class.id.in_(teacher_class_ids)) if teacher_class_ids else cls_q.where(False)
        r = await db.execute(cls_q)
        classes = r.scalars().all()
        if admin.role == ROLE_TEACHER:
            def _class_sort_key(c):
                is_onsite = 1 if c.modality == "onsite" else 2
                h = c.schedule_time.hour if c.schedule_time else 0
                period = 0 if h < 11 else (1 if h < 14 else 2)
                return (is_onsite, period, c.name)
            classes = sorted(classes, key=_class_sort_key)

        ec_r = await db.execute(
            select(Enrollment.class_id, func.count(Enrollment.id))
            .where(Enrollment.status == "enrolled")
            .group_by(Enrollment.class_id)
        )
        enrolled_counts = {cid: cnt for cid, cnt in ec_r.all()}

        for cls in classes:
            h = cls.schedule_time.hour if cls.schedule_time else 0
            period = "am" if h < 11 else ("noon" if h < 14 else "pm")
            if cls.modality == "onsite":
                onsite["total"] += 1
                onsite[period] += 1
            elif cls.modality == "mini":
                mini["total"] += 1
                if cls.capacity == 1:
                    mini["1v1"] += 1
                elif cls.capacity == 2:
                    mini["1v2"] += 1
                elif cls.capacity >= 3:
                    mini["1v3"] += 1
            elif cls.modality == "online":
                if cls.schedule_day == "SAT":
                    sat_online["total"] += 1
                    sat_online[period] += 1
                elif cls.schedule_day == "SUN":
                    sun_online["total"] += 1
                    sun_online[period] += 1

    # Current lesson: use the upcoming Saturday as the reference date
    # (classes happen on weekends; mid-week we want to show this coming Saturday's lesson)
    current_lesson = None
    if semester and semester.start_date:
        from datetime import date as _date, timedelta as _td
        today = _date.today()
        wd = today.weekday()  # 0=Mon … 5=Sat, 6=Sun
        if wd == 6:            # Sunday — class may be today
            ref_date = today
        else:                  # Mon–Sat: upcoming/current Saturday
            ref_date = today + _td(days=(5 - wd))
        if ref_date >= semester.start_date:
            holiday_set = set()
            if semester.holiday_weeks:
                for w in semester.holiday_weeks.split(","):
                    w = w.strip()
                    if w.isdigit():
                        holiday_set.add(int(w))
            weeks_elapsed = (ref_date - semester.start_date).days // 7
            ref_week = weeks_elapsed + 1  # 1-indexed semester week
            if ref_week not in holiday_set:
                current_lesson = sum(
                    1 for w in range(1, ref_week + 1) if w not in holiday_set
                )
            # else: this weekend is a holiday, current_lesson stays None

    return templates.TemplateResponse(request, "admin/dashboard.html", {
        "admin": admin,
        "current_admin": admin,
        "semester": semester,
        "enrolled_count": enrolled_count,
        "unplaced": unplaced,
        "new_students_count": new_students_count,
        "teacher_count": teacher_count,
        "onsite": onsite,
        "sat_online": sat_online,
        "sun_online": sun_online,
        "classes": classes,
        "enrolled_counts": enrolled_counts,
        "slot_labels": SLOT_LABELS,
        "current_lesson": current_lesson,
        "mini": mini,
    })


# ---------------------------------------------------------------------------
# Classes
# ---------------------------------------------------------------------------

@router.get("/classes", response_class=HTMLResponse)
async def classes_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    f_search: str = "",
    f_modality: str = "",
    f_day: str = "",
    f_status: str = "",
    f_material: str = "",
    f_teacher: str = "",
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    semester = await _active_semester(db)

    # Teacher role: restrict to their own classes
    teacher_class_ids: set[int] = set()
    if admin.role == ROLE_TEACHER and admin.teacher_id and semester:
        tc_r = await db.execute(
            select(ClassTeacher.class_id)
            .join(Class, Class.id == ClassTeacher.class_id)
            .where(ClassTeacher.teacher_id == admin.teacher_id, Class.semester_id == semester.id)
        )
        teacher_class_ids = {row[0] for row in tc_r.all()}

    cls_query = (
        select(Class)
        .options(
            selectinload(Class.class_materials).selectinload(ClassMaterial.material),
            selectinload(Class.class_teachers).selectinload(ClassTeacher.teacher),
        )
        .where(Class.semester_id == semester.id if semester else True)
        .order_by(Class.level, Class.name)
    )
    if admin.role == ROLE_TEACHER:
        cls_query = cls_query.where(Class.id.in_(teacher_class_ids)) if teacher_class_ids else cls_query.where(False)

    if f_search:
        cls_query = cls_query.where(Class.name.contains(f_search))
    if f_modality:
        cls_query = cls_query.where(Class.modality == f_modality)
    if f_day:
        cls_query = cls_query.where(Class.schedule_day == f_day)
    r = await db.execute(cls_query)
    classes = r.scalars().all()

    semesters_r = await db.execute(select(Semester).order_by(Semester.id.desc()))
    semesters = semesters_r.scalars().all()

    # Actual enrolled counts per class
    enrolled_r = await db.execute(
        select(Enrollment.class_id, func.count(Enrollment.id))
        .where(Enrollment.status == "enrolled")
        .group_by(Enrollment.class_id)
    )
    enrolled_counts = {cid: cnt for cid, cnt in enrolled_r.all()}
    cfg = await _get_settings(db)

    # Collect all material/teacher names for filter dropdowns (from full unfiltered list)
    all_material_names = sorted({
        cm.material.name for c in classes for cm in c.class_materials if cm.material
    })
    all_teacher_names = sorted({
        ct.teacher.name for c in classes for ct in c.class_teachers if ct.teacher
    })

    # Apply Python-side filters (material, teacher, status)
    if f_material:
        classes = [c for c in classes if any(
            cm.material and cm.material.name == f_material for cm in c.class_materials
        )]
    if f_teacher:
        classes = [c for c in classes if any(
            ct.teacher and ct.teacher.name == f_teacher for ct in c.class_teachers
        )]
    if f_status:
        def _eff_status(cls):
            n = enrolled_counts.get(cls.id, 0)
            if n > cls.overflow_cap:
                return "overflow"
            if n >= cls.capacity:
                return "full"
            if cls.status == "closed":
                return "closed"
            return "open"
        classes = [c for c in classes if _eff_status(c) == f_status]

    return templates.TemplateResponse(request, "admin/classes.html", {
        "admin": admin,
        "current_admin": admin,
        "classes": classes,
        "semester": semester,
        "semesters": semesters,
        "slot_labels": SLOT_LABELS,
        "enrolled_counts": enrolled_counts,
        "cfg": cfg,
        "ok": request.query_params.get("ok"),
        "err": request.query_params.get("err"),
        "f_search": f_search,
        "f_modality": f_modality,
        "f_day": f_day,
        "f_status": f_status,
        "f_material": f_material,
        "f_teacher": f_teacher,
        "all_material_names": all_material_names,
        "all_teacher_names": all_teacher_names,
    })



@router.get("/classes/new", response_class=HTMLResponse)
async def class_new_form(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()
    if not admin.is_senior_or_above:
        return _forbidden("/admin/classes")

    semester = await _active_semester(db)
    materials_r = await db.execute(select(Material).order_by(Material.name))
    teachers_r = await db.execute(select(Teacher).order_by(Teacher.name))
    semesters_r = await db.execute(select(Semester).order_by(Semester.id.desc()))
    cfg = await _get_settings(db)

    return templates.TemplateResponse(request, "admin/class_form.html", {
        "admin": admin,
        "current_admin": admin,
        "cls": None,
        "semester": semester,
        "semesters": semesters_r.scalars().all(),
        "all_materials": materials_r.scalars().all(),
        "all_teachers": teachers_r.scalars().all(),
        "selected_materials": [],
        "selected_teachers": [],
        "slot_labels": SLOT_LABELS,
        "cfg": cfg,
        "err": request.query_params.get("err"),
    })


@router.post("/classes/new")
async def class_create(
    request: Request,
    db: AsyncSession = Depends(get_db),
    semester_id: int = Form(...),
    name: str = Form(...),
    level: int = Form(...),
    schedule_day: str = Form(...),
    schedule_time: str = Form(...),
    modality: str = Form(...),
    capacity: int = Form(None),
    overflow_cap: int = Form(None),
    room: str = Form(""),
    meeting_link: str = Form(""),
    material_ids: list[int] = Form(default=[]),
    teacher_ids: list[int] = Form(default=[]),
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()
    if not admin.is_senior_or_above:
        return _forbidden("/admin/classes")

    cfg = await _get_settings(db)
    from datetime import time as dt_time
    h, m = schedule_time.split(":")
    cls = Class(
        semester_id=semester_id,
        name=name,
        level=level,
        slot_type=_derive_slot_type(schedule_day, schedule_time, modality),
        schedule_day=schedule_day,
        schedule_time=dt_time(int(h), int(m)),
        modality=modality,
        capacity=capacity if capacity is not None else cfg["default_capacity"],
        overflow_cap=overflow_cap if overflow_cap is not None else cfg["default_overflow_cap"],
        room=room or None,
        meeting_link=meeting_link or None,
    )
    db.add(cls)
    await db.flush()

    for mid in material_ids:
        db.add(ClassMaterial(class_id=cls.id, material_id=mid))
    for tid in teacher_ids:
        db.add(ClassTeacher(class_id=cls.id, teacher_id=tid))
    await db.commit()

    return _ok("/admin/classes", "班级已创建")


@router.get("/classes/{class_id}/edit", response_class=HTMLResponse)
async def class_edit_form(class_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    r = await db.execute(
        select(Class)
        .options(
            selectinload(Class.class_materials),
            selectinload(Class.class_teachers),
        )
        .where(Class.id == class_id)
    )
    cls = r.scalar_one_or_none()
    if not cls:
        return _err("/admin/classes", "班级不存在")

    # Teachers may only edit their own assigned classes
    if admin.role == ROLE_TEACHER:
        teacher_ids_in_class = [ct.teacher_id for ct in cls.class_teachers]
        if admin.teacher_id not in teacher_ids_in_class:
            return _forbidden("/admin/classes")

    materials_r = await db.execute(select(Material).order_by(Material.name))
    teachers_r = await db.execute(select(Teacher).order_by(Teacher.name))
    semesters_r = await db.execute(select(Semester).order_by(Semester.id.desc()))
    semester = await _active_semester(db)
    cfg = await _get_settings(db)

    selected_materials = [cm.material_id for cm in cls.class_materials]
    selected_teachers = [ct.teacher_id for ct in cls.class_teachers]

    # Actual enrolled count from DB
    ec_r = await db.execute(
        select(func.count(Enrollment.id))
        .where(Enrollment.class_id == class_id, Enrollment.status == "enrolled")
    )
    actual_enrolled = ec_r.scalar() or 0

    # Compute effective status from enrollment counts (mirrors list page logic)
    if actual_enrolled > cls.overflow_cap:
        effective_status = "overflow"
    elif actual_enrolled >= cls.capacity:
        effective_status = "full"
    elif cls.status == "closed":
        effective_status = "closed"
    else:
        effective_status = "open"

    return templates.TemplateResponse(request, "admin/class_form.html", {
        "admin": admin,
        "current_admin": admin,
        "cls": cls,
        "semester": semester,
        "semesters": semesters_r.scalars().all(),
        "all_materials": materials_r.scalars().all(),
        "all_teachers": teachers_r.scalars().all(),
        "selected_materials": selected_materials,
        "selected_teachers": selected_teachers,
        "slot_labels": SLOT_LABELS,
        "cfg": cfg,
        "actual_enrolled": actual_enrolled,
        "effective_status": effective_status,
        "err": request.query_params.get("err"),
    })


@router.post("/classes/{class_id}/edit")
async def class_update(
    class_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    name: str = Form(...),
    level: int = Form(...),
    schedule_day: str = Form(...),
    schedule_time: str = Form(...),
    modality: str = Form(...),
    current_count: int = Form(0),
    capacity: int = Form(None),
    overflow_cap: int = Form(None),
    status: str = Form("open"),
    room: str = Form(""),
    meeting_link: str = Form(""),
    material_ids: list[int] = Form(default=[]),
    teacher_ids: list[int] = Form(default=[]),
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    r = await db.execute(
        select(Class).options(selectinload(Class.class_teachers)).where(Class.id == class_id)
    )
    cls = r.scalar_one_or_none()
    if not cls:
        return _err("/admin/classes", "班级不存在")

    # Teachers may only rename their own assigned classes
    if admin.role == ROLE_TEACHER:
        teacher_ids_in_class = [ct.teacher_id for ct in cls.class_teachers]
        if admin.teacher_id not in teacher_ids_in_class:
            return _forbidden("/admin/classes")
        cls.name = name
        await db.commit()
        return _ok("/admin/classes", "班级名称已更新")

    cfg = await _get_settings(db)
    from datetime import time as dt_time
    h, m = schedule_time.split(":")
    cls.name = name
    cls.level = level
    cls.slot_type = _derive_slot_type(schedule_day, schedule_time, modality)
    cls.schedule_day = schedule_day
    cls.schedule_time = dt_time(int(h), int(m))
    cls.modality = modality
    cls.current_count = current_count
    cls.capacity = capacity if capacity is not None else cfg["default_capacity"]
    cls.overflow_cap = overflow_cap if overflow_cap is not None else cfg["default_overflow_cap"]
    cls.status = status
    cls.room = room or None
    cls.meeting_link = meeting_link or None

    # Rebuild materials and teachers
    await db.execute(
        ClassMaterial.__table__.delete().where(ClassMaterial.class_id == class_id)
    )
    await db.execute(
        ClassTeacher.__table__.delete().where(ClassTeacher.class_id == class_id)
    )
    for mid in material_ids:
        db.add(ClassMaterial(class_id=class_id, material_id=mid))
    for tid in teacher_ids:
        db.add(ClassTeacher(class_id=class_id, teacher_id=tid))

    await db.commit()
    return _ok("/admin/classes", "已保存")


@router.post("/classes/{class_id}/delete")
async def class_delete(class_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()
    if not admin.is_senior_or_above:
        return _forbidden("/admin/classes")

    r = await db.execute(select(Class).where(Class.id == class_id))
    cls = r.scalar_one_or_none()
    if cls:
        await db.delete(cls)
        await db.commit()
    return _ok("/admin/classes", "已删除")


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------

@router.get("/materials", response_class=HTMLResponse)
async def materials_list(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    if admin.role == ROLE_TEACHER and admin.teacher_id:
        semester = await _active_semester(db)
        if semester:
            tc_r = await db.execute(
                select(ClassTeacher.class_id)
                .join(Class, Class.id == ClassTeacher.class_id)
                .where(ClassTeacher.teacher_id == admin.teacher_id, Class.semester_id == semester.id)
            )
            teacher_class_ids = {row[0] for row in tc_r.all()}
            mat_ids_r = await db.execute(
                select(ClassMaterial.material_id).where(ClassMaterial.class_id.in_(teacher_class_ids))
            )
            mat_ids = {row[0] for row in mat_ids_r.all()}
            r = await db.execute(select(Material).where(Material.id.in_(mat_ids)).order_by(Material.name))
        else:
            r = await db.execute(select(Material).where(False))
    else:
        r = await db.execute(select(Material).order_by(Material.name))

    return templates.TemplateResponse(request, "admin/materials.html", {
        "admin": admin,
        "current_admin": admin,
        "materials": r.scalars().all(),
        "ok": request.query_params.get("ok"),
        "err": request.query_params.get("err"),
    })


@router.post("/materials/new")
async def material_create(
    request: Request,
    db: AsyncSession = Depends(get_db),
    name: str = Form(...),
    level: int = Form(None),
    lesson_count: int = Form(None),
    char_count: int = Form(None),
    char_set: str = Form(""),
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    db.add(Material(
        name=name,
        level=level or None,
        lesson_count=lesson_count or None,
        char_count=char_count or None,
        char_set=char_set.strip() or None,
    ))
    await db.commit()
    return _ok("/admin/materials", "教材已添加")


@router.post("/materials/{material_id}/edit")
async def material_update(
    material_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    name: str = Form(...),
    level: int = Form(None),
    lesson_count: int = Form(None),
    char_count: int = Form(None),
    char_set: str = Form(""),
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    r = await db.execute(select(Material).where(Material.id == material_id))
    m = r.scalar_one_or_none()
    if m:
        m.name = name
        m.level = level or None
        m.lesson_count = lesson_count or None
        m.char_count = char_count or None
        m.char_set = char_set.strip() or None
        await db.commit()
    return _ok("/admin/materials", "已保存")


@router.post("/materials/{material_id}/delete")
async def material_delete(
    material_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    r = await db.execute(select(Material).where(Material.id == material_id))
    m = r.scalar_one_or_none()
    if m:
        await db.delete(m)
        await db.commit()
    return _ok("/admin/materials", "已删除")


# ---------------------------------------------------------------------------
# Teachers
# ---------------------------------------------------------------------------

@router.get("/teachers", response_class=HTMLResponse)
async def teachers_list(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    r = await db.execute(select(Teacher).order_by(Teacher.name))
    teachers = r.scalars().all()

    return templates.TemplateResponse(request, "admin/teachers.html", {
        "admin": admin,
        "current_admin": admin,
        "teachers": teachers,
        "ok": request.query_params.get("ok"),
        "err": request.query_params.get("err"),
    })


@router.post("/teachers/new")
async def teacher_create(
    request: Request,
    db: AsyncSession = Depends(get_db),
    name: str = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    gender: str = Form(""),
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    if not admin.is_senior_or_above:
        return _forbidden("/admin/teachers")
    db.add(Teacher(name=name, email=email or None, phone=phone or None, gender=gender or None))
    await db.commit()
    return _ok("/admin/teachers", "教师已添加")


@router.post("/teachers/{teacher_id}/edit")
async def teacher_update(
    teacher_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    name: str = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    gender: str = Form(""),
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    if not admin.is_senior_or_above:
        return _forbidden("/admin/teachers")
    r = await db.execute(select(Teacher).where(Teacher.id == teacher_id))
    t = r.scalar_one_or_none()
    if t:
        t.name = name
        t.email = email or None
        t.phone = phone or None
        t.gender = gender or None
        await db.commit()
    return _ok("/admin/teachers", "已保存")


@router.post("/teachers/{teacher_id}/delete")
async def teacher_delete(
    teacher_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()
    if not admin.is_senior_or_above:
        return _forbidden("/admin/teachers")

    r = await db.execute(select(Teacher).where(Teacher.id == teacher_id))
    t = r.scalar_one_or_none()
    if t:
        await db.delete(t)
        await db.commit()
    return _ok("/admin/teachers", "已删除")



@router.post("/students/{student_id}/toggle-teacher-child")
async def toggle_teacher_child(
    student_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    r = await db.execute(select(Student).where(Student.id == student_id))
    s = r.scalar_one_or_none()
    if s:
        s.is_teacher_child = not s.is_teacher_child
        if not s.is_teacher_child:
            s.teacher_id = None  # also clear teacher link when manually unchecking
        await db.commit()
    return RedirectResponse("/admin/enrolled-students", status_code=303)


@router.post("/students/{student_id}/edit")
async def edit_student(
    student_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    name: str = Form(...),
    gender: str = Form(...),
    birth_date: str = Form(""),
    city_region: str = Form(""),
    nationality: str = Form(""),
    other_notes: str = Form(""),
    g_name: str = Form(""),
    g_email: str = Form(""),
    g_phone: str = Form(""),
    g_wechat: str = Form(""),
    is_teacher_child: str = Form(""),
    class_id: int = Form(0),
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    r = await db.execute(
        select(Student).options(selectinload(Student.guardian)).where(Student.id == student_id)
    )
    student = r.scalar_one_or_none()
    if student:
        student.name = name
        student.gender = gender
        if birth_date:
            year, month = birth_date.split("-")
            student.birth_date = date(int(year), int(month), 1)
        student.city_region = city_region
        student.nationality = nationality or None
        student.other_notes = other_notes or None
        student.is_teacher_child = is_teacher_child == "1"

        if student.guardian:
            if g_name:
                student.guardian.name = g_name
            if g_email:
                student.guardian.email = g_email
            if g_phone:
                student.guardian.phone = g_phone
            if g_wechat:
                student.guardian.wechat_id = g_wechat

        # Update enrollment class if changed
        if class_id:
            enr = await db.execute(
                select(Enrollment).where(
                    Enrollment.student_id == student_id,
                    Enrollment.status == "enrolled",
                )
            )
            enrollment = enr.scalar_one_or_none()
            if enrollment and enrollment.class_id != class_id:
                enrollment.class_id = class_id

        await db.commit()

    ref = request.headers.get("referer", "/admin/enrolled-students")
    return RedirectResponse(ref, status_code=303)


@router.post("/students/{student_id}/delete")
async def delete_student(
    student_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    r = await db.execute(select(Student).where(Student.id == student_id))
    student = r.scalar_one_or_none()
    if student:
        # Delete related records first (SQLite does not cascade by default)
        for model in (Enrollment, SchedulePreference, ProficiencyAssessment, ReadingAssessment):
            await db.execute(delete(model).where(model.student_id == student_id))
        await db.delete(student)
        await db.commit()

    return RedirectResponse("/admin/enrolled-students", status_code=303)


# ---------------------------------------------------------------------------
# Literacy tests
# ---------------------------------------------------------------------------

@router.get("/literacy-tests", response_class=HTMLResponse)
async def literacy_tests_list(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    r = await db.execute(
        select(LiteracyTest)
        .options(selectinload(LiteracyTest.results))
        .order_by(LiteracyTest.id.desc())
    )
    tests = r.scalars().all()
    semesters_r = await db.execute(select(Semester).order_by(Semester.id.desc()))

    return templates.TemplateResponse(request, "admin/literacy_tests.html", {
        "admin": admin,
        "current_admin": admin,
        "tests": tests,
        "semesters": semesters_r.scalars().all(),
        "ok": request.query_params.get("ok"),
        "err": request.query_params.get("err"),
    })


@router.post("/literacy-tests/new")
async def literacy_test_create(
    request: Request,
    db: AsyncSession = Depends(get_db),
    name: str = Form(...),
    semester_id: int = Form(...),
    characters_text: str = Form(...),
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    chars = [c.strip() for c in characters_text.splitlines() if c.strip() and not c.startswith("#")]
    if not chars:
        return _err("/admin/literacy-tests", "题目内容不能为空")

    db.add(LiteracyTest(name=name, semester_id=semester_id, characters=chars, is_active=True))
    await db.commit()
    return _ok("/admin/literacy-tests", f"测试已创建，共{len(chars)}题")


@router.post("/literacy-tests/{test_id}/toggle")
async def literacy_test_toggle(
    test_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    r = await db.execute(select(LiteracyTest).where(LiteracyTest.id == test_id))
    t = r.scalar_one_or_none()
    if t:
        t.is_active = not t.is_active
        await db.commit()
    return _ok("/admin/literacy-tests", "状态已更新")


@router.post("/literacy-tests/{test_id}/delete")
async def literacy_test_delete(
    test_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    r = await db.execute(select(LiteracyTest).where(LiteracyTest.id == test_id))
    t = r.scalar_one_or_none()
    if t:
        await db.delete(t)
        await db.commit()
    return _ok("/admin/literacy-tests", "已删除")


@router.get("/literacy-tests/{test_id}/results", response_class=HTMLResponse)
async def literacy_test_results(
    test_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    r = await db.execute(
        select(LiteracyTest)
        .options(selectinload(LiteracyTest.results))
        .where(LiteracyTest.id == test_id)
    )
    test = r.scalar_one_or_none()
    if not test:
        return _err("/admin/literacy-tests", "测试不存在")

    results_with_students = []
    for res in test.results:
        sr = await db.execute(select(Student).where(Student.id == res.student_id))
        student = sr.scalar_one_or_none()
        results_with_students.append({"result": res, "student": student})

    return templates.TemplateResponse(request, "admin/literacy_test_results.html", {
        "admin": admin,
        "current_admin": admin,
        "test": test,
        "results": results_with_students,
    })


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------

@router.get("/students", response_class=HTMLResponse)
async def students_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    search: str = "",
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    semester = await _active_semester(db)
    query = select(Student).options(
        selectinload(Student.guardian),
        selectinload(Student.proficiency_assessments),
        selectinload(Student.enrollments),
        selectinload(Student.schedule_preferences),
    )
    if search:
        query = query.where(
            Student.name.contains(search)
        )
    r = await db.execute(query.order_by(Student.created_at.desc()))
    students = r.scalars().all()

    # Get class names for enrollments
    class_names = {}
    cr = await db.execute(select(Class.id, Class.name))
    for cid, cname in cr.all():
        class_names[cid] = cname

    return templates.TemplateResponse(request, "admin/students.html", {
        "admin": admin,
        "current_admin": admin,
        "students": students,
        "semester": semester,
        "search": search,
        "class_names": class_names,
        "slot_labels": SLOT_LABELS,
        "ok": request.query_params.get("ok"),
    })


@router.post("/students/{student_id}/override-level")
async def student_override_level(
    student_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    semester_id: int = Form(...),
    level: int = Form(...),
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    r = await db.execute(
        select(ProficiencyAssessment).where(
            ProficiencyAssessment.student_id == student_id,
            ProficiencyAssessment.semester_id == semester_id,
        )
    )
    a = r.scalar_one_or_none()
    if a:
        a.admin_override_level = level
        await db.commit()
    return RedirectResponse(f"/admin/students?ok=等级已调整&search=", status_code=303)


# ---------------------------------------------------------------------------
# Guardians list
# ---------------------------------------------------------------------------

@router.get("/guardians", response_class=HTMLResponse)
async def guardians_list(
    request: Request,
    search: str = "",
    f_contact: str = "",
    f_class: str = "",
    f_children: str = "",
    f_gender: str = "",
    db: AsyncSession = Depends(get_db),
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    query = select(Guardian).options(
        selectinload(Guardian.students).selectinload(Student.enrollments).selectinload(Enrollment.class_)
    ).where(Guardian.name != "")

    if search:
        query = query.where(Guardian.name.contains(search))
    if f_contact:
        query = query.where(
            or_(
                Guardian.email.contains(f_contact),
                Guardian.wechat_id.contains(f_contact),
                Guardian.phone.contains(f_contact),
            )
        )
    if f_gender:
        query = query.where(Guardian.gender == f_gender)
    if f_class:
        subq = (
            select(Student.guardian_id)
            .join(Enrollment, (Enrollment.student_id == Student.id) & (Enrollment.status == "enrolled"))
            .join(Class, (Class.id == Enrollment.class_id) & (Class.name == f_class))
            .distinct()
        ).scalar_subquery()
        query = query.where(Guardian.id.in_(subq))

    r = await db.execute(query.order_by(Guardian.name))
    guardians = r.scalars().all()

    # Filter by number of children (Python-side, students already loaded)
    if f_children:
        if f_children == "4+":
            guardians = [g for g in guardians if len(g.students) >= 4]
        else:
            n = int(f_children)
            guardians = [g for g in guardians if len(g.students) == n]

    # All class names for the filter dropdown (restricted to teacher's classes for teacher role)
    semester = await _active_semester(db)
    cls_where = Class.semester_id == semester.id if semester else True
    if admin.role == ROLE_TEACHER and admin.teacher_id and semester:
        tc_r = await db.execute(
            select(ClassTeacher.class_id)
            .join(Class, Class.id == ClassTeacher.class_id)
            .where(ClassTeacher.teacher_id == admin.teacher_id, Class.semester_id == semester.id)
        )
        teacher_class_ids = {row[0] for row in tc_r.all()}
        cls_where = (Class.semester_id == semester.id) & Class.id.in_(teacher_class_ids)
    cr = await db.execute(select(Class.name).where(cls_where).order_by(Class.name))
    all_class_names = [row[0] for row in cr.all()]

    return templates.TemplateResponse(request, "admin/guardians.html", {
        "admin": admin,
        "current_admin": admin,
        "guardians": guardians,
        "search": search,
        "f_contact": f_contact,
        "f_class": f_class,
        "f_children": f_children,
        "f_gender": f_gender,
        "all_class_names": all_class_names,
    })


@router.post("/guardians/{guardian_id}/edit")
async def guardian_edit(
    request: Request,
    guardian_id: int,
    name: str = Form(...),
    email: str = Form(""),
    gender: str = Form(""),
    relationship_to_child: str = Form(""),
    phone: str = Form(""),
    wechat_id: str = Form(""),
    nationality: str = Form(""),
    language: str = Form(""),
    notes: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()
    r = await db.execute(select(Guardian).where(Guardian.id == guardian_id))
    guardian = r.scalar_one_or_none()
    if not guardian:
        return RedirectResponse("/admin/guardians", status_code=303)
    guardian.name = name.strip()
    guardian.email = email.strip()
    guardian.gender = gender or None
    guardian.relationship_to_child = relationship_to_child or None
    guardian.phone = phone.strip()
    guardian.wechat_id = wechat_id.strip() or None
    guardian.nationality = nationality.strip() or None
    guardian.language = language.strip() or None
    guardian.notes = notes.strip() or None
    await db.commit()
    return RedirectResponse("/admin/guardians", status_code=303)


@router.post("/guardians/{guardian_id}/delete")
async def guardian_delete(
    request: Request,
    guardian_id: int,
    db: AsyncSession = Depends(get_db),
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()
    r = await db.execute(select(Guardian).where(Guardian.id == guardian_id))
    guardian = r.scalar_one_or_none()
    if guardian:
        await db.delete(guardian)
        await db.commit()
    return RedirectResponse("/admin/guardians", status_code=303)


# ---------------------------------------------------------------------------
# Enrolled students list
# ---------------------------------------------------------------------------

@router.get("/enrolled-students", response_class=HTMLResponse)
async def enrolled_students_list(request: Request, search: str = "", f_class: str = "", f_gender: str = "", db: AsyncSession = Depends(get_db)):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    semester = await _active_semester(db)

    base_query = (
        select(Student)
        .options(
            selectinload(Student.guardian),
            selectinload(Student.enrollments).selectinload(Enrollment.class_),
        )
        .join(Enrollment, (Enrollment.student_id == Student.id) & (Enrollment.status == "enrolled"))
        .join(Class, (Class.id == Enrollment.class_id) & (Class.semester_id == semester.id if semester else True))
    )
    if search:
        base_query = base_query.where(Student.name.contains(search))
    if f_class:
        base_query = base_query.where(Class.name == f_class)
    if f_gender:
        base_query = base_query.where(Student.gender == f_gender)
    r = await db.execute(base_query.order_by(Student.name))
    students = r.scalars().unique().all()

    # Build sibling map: guardian_id -> list of enrolled students
    sibling_map: dict[int, list] = {}
    for s in students:
        sibling_map.setdefault(s.guardian_id, []).append(s)

    tuition_map: dict[int, object] = {}
    enroll_start_map: dict[int, object] = {}
    all_classes = []
    all_class_names: list[str] = []

    # For teacher role: get their class IDs to restrict the class filter dropdown
    teacher_class_ids: set[int] = set()
    if admin.role == ROLE_TEACHER and admin.teacher_id and semester:
        tc_r = await db.execute(
            select(ClassTeacher.class_id)
            .join(Class, Class.id == ClassTeacher.class_id)
            .where(ClassTeacher.teacher_id == admin.teacher_id, Class.semester_id == semester.id)
        )
        teacher_class_ids = {row[0] for row in tc_r.all()}

    if semester:
        ac_where = (
            (Class.semester_id == semester.id) & Class.id.in_(teacher_class_ids)
            if admin.role == ROLE_TEACHER
            else (Class.semester_id == semester.id)
        )
        tr_res, er_res, ac_res = await asyncio.gather(
            db.execute(select(TuitionRecord).where(TuitionRecord.semester_id == semester.id)),
            db.execute(
                select(Enrollment.student_id, Enrollment.created_at)
                .join(Class, Class.id == Enrollment.class_id)
                .where(Class.semester_id == semester.id, Enrollment.status == "enrolled")
            ),
            db.execute(
                select(Class).where(ac_where).order_by(Class.level, Class.name)
            ),
        )
        tuition_map = {rec.student_id: rec for rec in tr_res.scalars().all()}
        enroll_start_map = {sid: created_at for sid, created_at in er_res.all()}
        all_classes = ac_res.scalars().all()
        all_class_names = sorted({cls.name for cls in all_classes})

    return templates.TemplateResponse(request, "admin/enrolled_students.html", {
        "admin": admin,
        "current_admin": admin,
        "students": students,
        "semester": semester,
        "tuition_map": tuition_map,
        "sibling_map": sibling_map,
        "enroll_start_map": enroll_start_map,
        "search": search,
        "f_class": f_class,
        "f_gender": f_gender,
        "all_class_names": all_class_names,
        "all_classes": all_classes,
    })


# ---------------------------------------------------------------------------
# Pending students list
# ---------------------------------------------------------------------------

@router.get("/pending-students", response_class=HTMLResponse)
async def pending_students_list(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    semester = await _active_semester(db)
    if not semester:
        return templates.TemplateResponse(request, "admin/pending_students.html", {
            "admin": admin,
        "current_admin": admin,
            "students": [],
            "semester": None,
            "all_classes": [],
            "slot_labels": SLOT_LABELS,
            "vocab_labels": VOCAB_LABELS,
        })

    assessed_ids_q = select(ProficiencyAssessment.student_id).where(
        ProficiencyAssessment.semester_id == semester.id
    )
    placed_ids_q = (
        select(Enrollment.student_id)
        .join(Class, Class.id == Enrollment.class_id)
        .where(
            Class.semester_id == semester.id,
            Enrollment.status.in_(["enrolled", "waitlisted"]),
        )
    )

    r = await db.execute(
        select(Student)
        .options(
            selectinload(Student.proficiency_assessments),
            selectinload(Student.schedule_preferences),
            selectinload(Student.guardian),
        )
        .where(
            Student.id.in_(assessed_ids_q),
            Student.id.not_in(placed_ids_q),
        )
        .order_by(Student.name)
    )
    students = r.scalars().all()

    cr = await db.execute(
        select(Class)
        .options(
            selectinload(Class.class_materials).selectinload(ClassMaterial.material),
            selectinload(Class.class_teachers).selectinload(ClassTeacher.teacher),
        )
        .where(Class.semester_id == semester.id)
        .order_by(Class.level, Class.name)
    )
    all_classes = cr.scalars().all()

    # Build placement_map: student_id → {recommended, alternatives, has_audited}
    placement_map: dict[int, dict] = {}
    needs_commit = False
    for s in students:
        for a in s.proficiency_assessments:
            if a.semester_id != semester.id:
                continue
            # Recompute if JSON was never stored (e.g. registered before this feature)
            if not a.placement_recommended_json:
                try:
                    result = await run_placement_for_student(db, s.id, semester.id)
                    a.placement_recommended_json = result.recommended.model_dump_json() if result.recommended else None
                    a.placement_alternatives_json = _json.dumps([x.model_dump() for x in result.alternatives[:3]]) if result.alternatives else None
                    needs_commit = True
                except Exception:
                    pass
            rec = _json.loads(a.placement_recommended_json) if a.placement_recommended_json else None
            alts = _json.loads(a.placement_alternatives_json)[:3] if a.placement_alternatives_json else []
            placement_map[s.id] = {"recommended": rec, "alternatives": alts, "has_audited": a.has_audited}
            break
    if needs_commit:
        await db.commit()

    return templates.TemplateResponse(request, "admin/pending_students.html", {
        "admin": admin,
        "current_admin": admin,
        "students": students,
        "semester": semester,
        "all_classes": all_classes,
        "slot_labels": SLOT_LABELS,
        "vocab_labels": VOCAB_LABELS,
        "material_labels": LEVEL_MATERIALS,
        "placement_map": placement_map,
    })


@router.post("/pending-students/{student_id}/assign")
async def assign_student_to_class(
    student_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    class_id: int = Form(...),
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    # Get semester of the target class
    cls_r = await db.execute(select(Class).where(Class.id == class_id))
    target_cls = cls_r.scalar_one_or_none()
    if not target_cls:
        return _err("/admin/pending-students", "班级不存在")

    # Delete any existing enrollment for this student in the same semester
    # (handles first-time placement and re-enrollment — new created_at = new start date)
    old_r = await db.execute(
        select(Enrollment)
        .join(Class, Class.id == Enrollment.class_id)
        .where(
            Enrollment.student_id == student_id,
            Class.semester_id == target_cls.semester_id,
        )
    )
    for old_e in old_r.scalars().all():
        await db.delete(old_e)

    db.add(Enrollment(student_id=student_id, class_id=class_id, status="enrolled"))
    await db.commit()
    return RedirectResponse("/admin/pending-students?ok=已分班", status_code=303)


@router.post("/pending-students/{student_id}/toggle-audited")
async def toggle_audited(
    student_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    semester = await _active_semester(db)
    if semester:
        r = await db.execute(
            select(ProficiencyAssessment).where(
                ProficiencyAssessment.student_id == student_id,
                ProficiencyAssessment.semester_id == semester.id,
            )
        )
        assessment = r.scalar_one_or_none()
        if assessment:
            assessment.has_audited = not assessment.has_audited
            await db.commit()

    return RedirectResponse("/admin/pending-students", status_code=303)


# ---------------------------------------------------------------------------
# Tuition management
# ---------------------------------------------------------------------------

def _calculate_family_tuition(family_students_with_class, cfg: dict):
    """
    family_students_with_class: list of (student, cls) sorted by birth_date ASC (oldest first)
    cfg: settings dict from _get_settings()
    Returns: list of (student, base_fee, family_discount, final_fee, note)

    Teacher children (student.teacher_id is not None or student.is_teacher_child) are free
    individually. Their siblings pay normal fees with family discount applied only to the
    paying siblings.
    """
    def _is_teacher_child(s):
        return s.teacher_id is not None or s.is_teacher_child

    results = []
    paying = [(s, c) for s, c in family_students_with_class if not _is_teacher_child(s)]
    n = len(paying)

    # Compute family discount on paying siblings only
    base_fees = []
    has_onsite = False
    for student, cls in paying:
        if cls is None:
            base_fees.append(0)
            continue
        if cls.modality == "onsite":
            has_onsite = True
            fee = cfg["fee_beginner"] if cls.level <= 2 else cfg["fee_onsite"]
        else:
            fee = cfg["fee_online"]
        base_fees.append(fee)

    d2, d3, d4 = cfg["discount_2"], cfg["discount_3"], cfg["discount_4"]
    if has_onsite:
        discount = d4 if n >= 4 else (d3 if n == 3 else (d2 if n == 2 else 0))
    else:
        discount = d3 if n >= 3 else (d2 if n == 2 else 0)
    family_total = max(0, sum(base_fees) - discount)

    # Teacher children: free
    for student, cls in family_students_with_class:
        if _is_teacher_child(student):
            results.append((student, 0, 0, 0, "教师子女免费"))

    # Paying siblings: apply family discount on oldest, zero out others
    for i, (student, cls) in enumerate(paying):
        if i == 0:
            note = f"家庭优惠-{discount}kr" if (n > 1 and discount) else "正常收费"
            results.append((student, base_fees[i], discount, family_total, note))
        else:
            results.append((student, base_fees[i], 0, 0, "已计入兄/姐名下"))

    return results



@router.get("/tuition", response_class=HTMLResponse)
async def tuition_list(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()
    if not admin.is_superadmin_role:
        return _forbidden("/admin/")

    semester = await _active_semester(db)
    cfg = await _get_settings(db)

    records = []
    if semester:
        r = await db.execute(
            select(TuitionRecord)
            .options(selectinload(TuitionRecord.student))
            .where(TuitionRecord.semester_id == semester.id)
            .order_by(TuitionRecord.final_fee.desc())
        )
        records = r.scalars().all()

    # Enrolled student count this semester
    enrolled_count = 0
    enroll_map = {}
    if semester:
        er = await db.execute(
            select(Enrollment)
            .join(Class, Class.id == Enrollment.class_id)
            .where(Class.semester_id == semester.id, Enrollment.status == "enrolled")
        )
        for e in er.scalars().all():
            enroll_map[e.student_id] = e
        enrolled_count = len(enroll_map)

    class_map = {}
    cr = await db.execute(select(Class.id, Class.name))
    for cid, cname in cr.all():
        class_map[cid] = cname

    # Stats
    total_fee = sum(rec.final_fee for rec in records)
    paying_count = sum(1 for r in records if r.final_fee > 0)
    teacher_count = sum(1 for r in records if "教师子女" in (r.note or ""))
    sibling_count = sum(1 for r in records if "兄/姐名下" in (r.note or ""))
    discount_count = sum(1 for r in records if r.family_discount > 0)

    return templates.TemplateResponse(request, "admin/tuition.html", {
        "admin": admin,
        "current_admin": admin,
        "semester": semester,
        "cfg": cfg,
        "records": records,
        "class_map": class_map,
        "enroll_map": enroll_map,
        "enrolled_count": enrolled_count,
        "total_fee": total_fee,
        "paying_count": paying_count,
        "teacher_count": teacher_count,
        "sibling_count": sibling_count,
        "discount_count": discount_count,
        "ok": request.query_params.get("ok"),
        "err": request.query_params.get("err"),
    })


@router.post("/tuition/calculate")
async def tuition_calculate(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()
    if not admin.is_superadmin_role:
        return _forbidden("/admin/")

    semester = await _active_semester(db)
    if not semester:
        return _err("/admin/tuition", "没有活跃学期")

    er = await db.execute(
        select(Enrollment)
        .options(
            selectinload(Enrollment.student).selectinload(Student.guardian),
            selectinload(Enrollment.class_),
        )
        .join(Class, Class.id == Enrollment.class_id)
        .where(Class.semester_id == semester.id, Enrollment.status == "enrolled")
    )
    enrollments = er.scalars().all()

    from collections import defaultdict
    guardian_map: dict[int, list] = defaultdict(list)
    for e in enrollments:
        guardian_map[e.student.guardian_id].append((e.student, e.class_))

    cfg = await _get_settings(db)

    await db.execute(
        TuitionRecord.__table__.delete().where(TuitionRecord.semester_id == semester.id)
    )

    total_students = 0
    for guardian_id, students_classes in guardian_map.items():
        students_classes.sort(key=lambda x: x[0].birth_date)
        results = _calculate_family_tuition(students_classes, cfg)
        for student, base_fee, family_discount, final_fee, note in results:
            db.add(TuitionRecord(
                student_id=student.id,
                semester_id=semester.id,
                base_fee=base_fee,
                family_discount=family_discount,
                final_fee=final_fee,
                note=note,
            ))
            total_students += 1

    await db.commit()
    return _ok("/admin/tuition", f"已计算 {total_students} 名学生的学费")


@router.post("/tuition/set-teacher-family")
async def set_teacher_family(
    request: Request,
    db: AsyncSession = Depends(get_db),
    guardian_id: int = Form(...),
    is_teacher: bool = Form(False),
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()
    if not admin.is_superadmin_role:
        return _forbidden("/admin/")

    r = await db.execute(select(GuardianFlag).where(GuardianFlag.guardian_id == guardian_id))
    flag = r.scalar_one_or_none()
    if flag:
        flag.is_teacher_family = is_teacher
    else:
        db.add(GuardianFlag(guardian_id=guardian_id, is_teacher_family=is_teacher))
    await db.commit()
    return _ok("/admin/tuition", "已更新")


# ---------------------------------------------------------------------------
# System Settings
# ---------------------------------------------------------------------------

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()
    if not admin.is_superadmin_role:
        return _forbidden("/admin/")

    cfg = await _get_settings(db)

    # Teacher family flags
    flag_r = await db.execute(select(GuardianFlag))
    teacher_flags = {f.guardian_id: f.is_teacher_family for f in flag_r.scalars().all()}

    guardian_r = await db.execute(
        select(Guardian)
        .options(selectinload(Guardian.students))
        .order_by(Guardian.name)
    )
    guardians = guardian_r.scalars().all()

    return templates.TemplateResponse(request, "admin/settings.html", {
        "admin": admin,
        "current_admin": admin,
        "cfg": cfg,
        "defaults": SETTINGS_DEFAULTS,
        "teacher_flags": teacher_flags,
        "guardians": guardians,
        "ok": request.query_params.get("ok"),
        "err": request.query_params.get("err"),
    })


@router.post("/settings")
async def settings_save(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()
    if not admin.is_superadmin_role:
        return _forbidden("/admin/")

    form = await request.form()
    for key in SETTINGS_DEFAULTS:
        val = form.get(key)
        if val is not None:
            r = await db.execute(select(SystemSettings).where(SystemSettings.key == key))
            existing = r.scalar_one_or_none()
            if existing:
                existing.value = str(int(val))
            else:
                db.add(SystemSettings(key=key, value=str(int(val))))
    await db.commit()
    return _ok("/admin/settings", "常数已保存")


@router.post("/settings/teacher-family")
async def settings_teacher_family(
    request: Request,
    db: AsyncSession = Depends(get_db),
    guardian_id: int = Form(...),
    is_teacher: str = Form("off"),
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()
    if not admin.is_superadmin_role:
        return _forbidden("/admin/")

    is_teacher_bool = (is_teacher == "on")
    r = await db.execute(select(GuardianFlag).where(GuardianFlag.guardian_id == guardian_id))
    flag = r.scalar_one_or_none()
    if flag:
        flag.is_teacher_family = is_teacher_bool
    else:
        db.add(GuardianFlag(guardian_id=guardian_id, is_teacher_family=is_teacher_bool))
    await db.commit()
    return _ok("/admin/settings", "已更新")


# ---------------------------------------------------------------------------
# Semester management
# ---------------------------------------------------------------------------

@router.get("/semesters", response_class=HTMLResponse)
async def semesters_page(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()

    result = await db.execute(select(Semester).order_by(Semester.start_date.desc()))
    semesters = result.scalars().all()
    return templates.TemplateResponse(request, "admin/semesters.html", {
        "current_admin": admin,
        "semesters": semesters,
    })


@router.post("/semesters/new")
async def semester_create(
    request: Request,
    db: AsyncSession = Depends(get_db),
    name: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    reg_open_date: str = Form(...),
    reg_close_date: str = Form(...),
    total_weeks: str = Form(""),
    holiday_weeks: str = Form(""),
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()
    if not admin.is_senior_or_above:
        return _forbidden("/admin/")

    from datetime import date as _date
    s = Semester(
        name=name,
        start_date=_date.fromisoformat(start_date),
        end_date=_date.fromisoformat(end_date),
        reg_open_date=_date.fromisoformat(reg_open_date),
        reg_close_date=_date.fromisoformat(reg_close_date),
        total_weeks=int(total_weeks) if total_weeks.strip() else None,
        holiday_weeks=holiday_weeks.strip() or None,
        is_active=False,
    )
    db.add(s)
    await db.commit()
    return _ok("/admin/semesters", "学期已创建")


@router.post("/semesters/{semester_id}/edit")
async def semester_edit(
    semester_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    name: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    reg_open_date: str = Form(...),
    reg_close_date: str = Form(...),
    total_weeks: str = Form(""),
    holiday_weeks: str = Form(""),
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()
    if not admin.is_senior_or_above:
        return _forbidden("/admin/")

    from datetime import date as _date
    r = await db.execute(select(Semester).where(Semester.id == semester_id))
    s = r.scalar_one_or_none()
    if not s:
        return _err("/admin/semesters", "学期不存在")

    s.name = name
    s.start_date = _date.fromisoformat(start_date)
    s.end_date = _date.fromisoformat(end_date)
    s.reg_open_date = _date.fromisoformat(reg_open_date)
    s.reg_close_date = _date.fromisoformat(reg_close_date)
    s.total_weeks = int(total_weeks) if total_weeks.strip() else None
    s.holiday_weeks = holiday_weeks.strip() or None
    await db.commit()
    return _ok("/admin/semesters", "学期已更新")


@router.post("/semesters/{semester_id}/activate")
async def semester_activate(
    semester_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()
    if not admin.is_senior_or_above:
        return _forbidden("/admin/")

    # Deactivate all, then activate the target
    all_r = await db.execute(select(Semester))
    for s in all_r.scalars().all():
        s.is_active = (s.id == semester_id)
    await db.commit()
    return _ok("/admin/semesters", "已激活该学期")


@router.post("/semesters/{semester_id}/delete")
async def semester_delete(
    semester_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()
    if not admin.is_senior_or_above:
        return _forbidden("/admin/")

    r = await db.execute(select(Semester).where(Semester.id == semester_id))
    s = r.scalar_one_or_none()
    if s:
        await db.delete(s)
        await db.commit()
    return _ok("/admin/semesters", "学期已删除")


# ---------------------------------------------------------------------------
# User / Permission Management (superadmin only)
# ---------------------------------------------------------------------------

@router.get("/users", response_class=HTMLResponse)
async def users_list(request: Request, db: AsyncSession = Depends(get_db)):
    admin = await _get_admin(request, db)
    if not admin:
        return _login_redirect()
    if not admin.is_superadmin_role:
        return _forbidden()

    r = await db.execute(
        select(AdminUser)
        .options(selectinload(AdminUser.teacher))
        .order_by(AdminUser.id)
    )
    users = r.scalars().all()
    teachers_r = await db.execute(select(Teacher).order_by(Teacher.name))
    teachers = teachers_r.scalars().all()

    return templates.TemplateResponse(request, "admin/users.html", {
        "current_admin": admin,
        "users": users,
        "teachers": teachers,
        "role_labels": ROLE_LABELS,
    })


@router.post("/users/new")
async def user_create(
    request: Request,
    db: AsyncSession = Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    teacher_id: int = Form(None),
):
    admin = await _get_admin(request, db)
    if not admin or not admin.is_superadmin_role:
        return _forbidden("/admin/users")

    if role not in (ROLE_SUPERADMIN, ROLE_SENIOR_ADMIN, ROLE_TEACHER):
        return _err("/admin/users", "无效角色")

    existing = await db.execute(select(AdminUser).where(AdminUser.username == username))
    if existing.scalar_one_or_none():
        return _err("/admin/users", "用户名已存在")

    new_user = AdminUser(
        username=username,
        hashed_password=hash_password(password),
        role=role,
        is_superadmin=(role == ROLE_SUPERADMIN),
        teacher_id=teacher_id if role == ROLE_TEACHER else None,
    )
    db.add(new_user)
    await db.commit()
    return _ok("/admin/users", f"用户 {username} 已创建")


@router.post("/users/{user_id}/edit")
async def user_edit(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    role: str = Form(...),
    teacher_id: int = Form(None),
    is_active: str = Form("on"),
    new_password: str = Form(""),
):
    admin = await _get_admin(request, db)
    if not admin or not admin.is_superadmin_role:
        return _forbidden("/admin/users")

    r = await db.execute(select(AdminUser).where(AdminUser.id == user_id))
    user = r.scalar_one_or_none()
    if not user:
        return _err("/admin/users", "用户不存在")

    # Prevent demoting the last superadmin
    if user.is_superadmin_role and role != ROLE_SUPERADMIN:
        count_r = await db.execute(
            select(func.count(AdminUser.id)).where(AdminUser.role == ROLE_SUPERADMIN)
        )
        if (count_r.scalar() or 0) <= 1:
            return _err("/admin/users", "不能降级最后一个超级管理员")

    user.role = role
    user.is_superadmin = (role == ROLE_SUPERADMIN)
    user.teacher_id = teacher_id if role == ROLE_TEACHER else None
    user.is_active = (is_active == "on")
    if new_password:
        user.hashed_password = hash_password(new_password)
    await db.commit()
    return _ok("/admin/users", "已保存")


@router.post("/users/{user_id}/delete")
async def user_delete(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    admin = await _get_admin(request, db)
    if not admin or not admin.is_superadmin_role:
        return _forbidden("/admin/users")

    if user_id == admin.id:
        return _err("/admin/users", "不能删除自己")

    r = await db.execute(select(AdminUser).where(AdminUser.id == user_id))
    user = r.scalar_one_or_none()
    if user:
        await db.delete(user)
        await db.commit()
    return _ok("/admin/users", "用户已删除")
