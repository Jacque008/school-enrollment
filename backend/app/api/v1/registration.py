import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.guardian import Guardian
from app.models.student import Student
from app.models.proficiency_assessment import ProficiencyAssessment
from app.models.reading_assessment import ReadingAssessment
from app.models.schedule_preference import SchedulePreference
from app.models.semester import Semester
from app.schemas.registration import RegistrationCreate, RegistrationResponse
from app.services.auth import get_current_guardian
from app.services.placement import run_placement_for_student
from app.schemas.placement import PlacementResult

router = APIRouter(prefix="/registrations", tags=["registrations"])


async def _get_active_semester(db: AsyncSession) -> Semester:
    result = await db.execute(select(Semester).where(Semester.is_active == True))
    semester = result.scalar_one_or_none()
    if not semester:
        raise HTTPException(status_code=400, detail="当前没有开放的学期")
    return semester


@router.post("", response_model=RegistrationResponse)
async def create_registration(
    data: RegistrationCreate,
    guardian: Guardian = Depends(get_current_guardian),
    db: AsyncSession = Depends(get_db),
):
    """Submit complete registration form (all steps at once)."""
    semester = await _get_active_semester(db)

    from datetime import date

    if date.today() < semester.reg_open_date or date.today() > semester.reg_close_date:
        raise HTTPException(status_code=400, detail="不在报名时间范围内")

    # Update guardian info
    guardian.name = data.guardian.name
    if data.guardian.email:
        guardian.email = data.guardian.email
    if data.guardian.phone:
        guardian.phone = data.guardian.phone
    if data.guardian.wechat_id:
        guardian.wechat_id = data.guardian.wechat_id
    if data.guardian.relationship_to_child:
        guardian.relationship_to_child = data.guardian.relationship_to_child
    if data.guardian.gender:
        guardian.gender = data.guardian.gender
    elif data.guardian.relationship_to_child == 'mom':
        guardian.gender = 'female'
    elif data.guardian.relationship_to_child == 'dad':
        guardian.gender = 'male'
    if data.guardian.nationality:
        guardian.nationality = data.guardian.nationality
    if data.guardian.language:
        guardian.language = data.guardian.language

    # Check if this guardian already has a student registered this semester
    # (same Chinese name = same child re-submitting). If so, update rather than create.
    existing_result = await db.execute(
        select(Student)
        .join(ProficiencyAssessment,
              (ProficiencyAssessment.student_id == Student.id) &
              (ProficiencyAssessment.semester_id == semester.id))
        .where(
            Student.guardian_id == guardian.id,
            Student.name == data.student.name,
        )
        .limit(1)
    )
    student = existing_result.scalar_one_or_none()

    if student:
        # Update existing student record
        student.name = data.student.name
        student.gender = data.student.gender.value
        student.birth_date = data.student.birth_date
        student.city_region = data.student.city_region
        if data.student.nationality:
            student.nationality = data.student.nationality
        student.home_language = data.background.home_language.value
        student.sibling_in_school = data.guardian.sibling_in_school
        student.sibling_info = data.guardian.sibling_info
        student.learning_history = data.background.learning_history
        student.other_hobbies = data.background.other_hobbies
        student.parent_expectations = data.background.parent_expectations
        student.school_feedback = data.background.school_feedback
        student.other_notes = data.background.other_notes
        student.referral_source = data.background.referral_source
        student.accept_alternative = data.background.accept_alternative
        is_update = True
    else:
        student = Student(
            guardian_id=guardian.id,
            name=data.student.name,
            gender=data.student.gender.value,
            birth_date=data.student.birth_date,
            city_region=data.student.city_region,
            nationality=data.student.nationality or None,
            home_language=data.background.home_language.value,
            sibling_in_school=data.guardian.sibling_in_school,
            sibling_info=data.guardian.sibling_info,
            learning_history=data.background.learning_history,
            other_hobbies=data.background.other_hobbies,
            parent_expectations=data.background.parent_expectations,
            school_feedback=data.background.school_feedback,
            other_notes=data.background.other_notes,
            referral_source=data.background.referral_source,
            accept_alternative=data.background.accept_alternative,
        )
        db.add(student)
        is_update = False

    await db.flush()

    # Proficiency assessment — update if exists, else create
    assess_result = await db.execute(
        select(ProficiencyAssessment).where(
            ProficiencyAssessment.student_id == student.id,
            ProficiencyAssessment.semester_id == semester.id,
        )
    )
    assessment = assess_result.scalar_one_or_none()
    if assessment:
        assessment.listening_level = data.proficiency.listening_level
        assessment.speaking_level = data.proficiency.speaking_level
        assessment.writing_level = data.proficiency.writing_level
        assessment.pinyin_level = data.literacy.pinyin_level
        assessment.vocab_level = data.literacy.vocab_level
        assessment.computed_level = assessment.compute_level()
    else:
        assessment = ProficiencyAssessment(
            student_id=student.id,
            semester_id=semester.id,
            listening_level=data.proficiency.listening_level,
            speaking_level=data.proficiency.speaking_level,
            writing_level=data.proficiency.writing_level,
            pinyin_level=data.literacy.pinyin_level,
            vocab_level=data.literacy.vocab_level,
        )
        assessment.computed_level = assessment.compute_level()
        db.add(assessment)

    # Reading assessment — update if exists, else create
    reading_result = await db.execute(
        select(ReadingAssessment).where(
            ReadingAssessment.student_id == student.id,
            ReadingAssessment.semester_id == semester.id,
        )
    )
    reading = reading_result.scalar_one_or_none()
    if reading:
        reading.reading_interest = data.literacy.reading_interest
        reading.reading_ability = data.literacy.reading_ability.value if data.literacy.reading_ability else None
        reading.reading_habits = data.literacy.reading_habits
    else:
        reading = ReadingAssessment(
            student_id=student.id,
            semester_id=semester.id,
            reading_interest=data.literacy.reading_interest,
            reading_ability=data.literacy.reading_ability.value if data.literacy.reading_ability else None,
            reading_habits=data.literacy.reading_habits,
        )
        db.add(reading)

    # Schedule preferences — replace
    old_prefs = await db.execute(
        select(SchedulePreference).where(
            SchedulePreference.student_id == student.id,
            SchedulePreference.semester_id == semester.id,
        )
    )
    for p in old_prefs.scalars().all():
        await db.delete(p)

    for slot in data.schedule.slot_types:
        db.add(SchedulePreference(
            student_id=student.id,
            semester_id=semester.id,
            slot_type=slot.value,
        ))

    await db.flush()

    # Run placement algorithm and cache results on the assessment record
    try:
        placement = await run_placement_for_student(db, student.id, semester.id)
        assessment.placement_recommended_json = (
            placement.recommended.model_dump_json() if placement.recommended else None
        )
        assessment.placement_alternatives_json = (
            json.dumps([a.model_dump() for a in placement.alternatives[:3]])
            if placement.alternatives else None
        )
    except Exception:
        pass  # No classes configured yet — store nothing, admin can re-run later

    await db.commit()

    return RegistrationResponse(
        id=student.id,
        student_name=student.name,
        computed_level=assessment.computed_level,
        status="submitted",
    )


@router.get("/my/placement", response_model=list[PlacementResult])
async def my_placement_recommendations(
    guardian: Guardian = Depends(get_current_guardian),
    db: AsyncSession = Depends(get_db),
):
    """Get placement recommendations for the current guardian's children."""
    semester = await _get_active_semester(db)

    result = await db.execute(
        select(Student).where(Student.guardian_id == guardian.id)
    )
    students = result.scalars().all()

    recommendations = []
    for student in students:
        try:
            placement = await run_placement_for_student(db, student.id, semester.id)
            recommendations.append(placement)
        except ValueError:
            pass  # Student has no assessment yet — skip
    return recommendations


@router.get("/my", response_model=list[RegistrationResponse])
async def my_registrations(
    guardian: Guardian = Depends(get_current_guardian),
    db: AsyncSession = Depends(get_db),
):
    """Get all registrations for the current guardian."""
    result = await db.execute(
        select(Student)
        .options(selectinload(Student.proficiency_assessments))
        .where(Student.guardian_id == guardian.id)
    )
    students = result.scalars().all()

    responses = []
    for s in students:
        latest = max(s.proficiency_assessments, key=lambda a: a.id, default=None)
        responses.append(
            RegistrationResponse(
                id=s.id,
                student_name=s.name,
                computed_level=latest.computed_level if latest else None,
                status="submitted",
            )
        )
    return responses


@router.put("/{student_id}", response_model=RegistrationResponse)
async def update_registration(
    student_id: int,
    data: RegistrationCreate,
    guardian: Guardian = Depends(get_current_guardian),
    db: AsyncSession = Depends(get_db),
):
    """Update registration (before deadline)."""
    semester = await _get_active_semester(db)

    from datetime import date

    if date.today() > semester.reg_close_date:
        raise HTTPException(status_code=400, detail="报名已截止，无法修改")

    result = await db.execute(
        select(Student).where(
            Student.id == student_id, Student.guardian_id == guardian.id
        )
    )
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="未找到该学生记录")

    # Update student fields
    student.name = data.student.name
    student.gender = data.student.gender.value
    student.birth_date = data.student.birth_date
    student.city_region = data.student.city_region
    student.home_language = data.background.home_language.value
    student.sibling_in_school = data.guardian.sibling_in_school
    student.sibling_info = data.guardian.sibling_info
    student.learning_history = data.background.learning_history
    student.other_hobbies = data.background.other_hobbies
    student.parent_expectations = data.background.parent_expectations
    student.school_feedback = data.background.school_feedback
    student.other_notes = data.background.other_notes
    student.referral_source = data.background.referral_source
    student.accept_alternative = data.background.accept_alternative

    # Update assessment
    assess_result = await db.execute(
        select(ProficiencyAssessment).where(
            ProficiencyAssessment.student_id == student_id,
            ProficiencyAssessment.semester_id == semester.id,
        )
    )
    assessment = assess_result.scalar_one_or_none()
    if assessment:
        assessment.listening_level = data.proficiency.listening_level
        assessment.speaking_level = data.proficiency.speaking_level
        assessment.writing_level = data.proficiency.writing_level
        assessment.pinyin_level = data.literacy.pinyin_level
        assessment.vocab_level = data.literacy.vocab_level
        assessment.computed_level = assessment.compute_level()

    # Replace schedule preferences
    old_prefs = await db.execute(
        select(SchedulePreference).where(
            SchedulePreference.student_id == student_id,
            SchedulePreference.semester_id == semester.id,
        )
    )
    for p in old_prefs.scalars().all():
        await db.delete(p)

    for slot in data.schedule.slot_types:
        db.add(
            SchedulePreference(
                student_id=student_id,
                semester_id=semester.id,
                slot_type=slot.value,
            )
        )

    await db.flush()

    return RegistrationResponse(
        id=student.id,
        student_name=student.name,
        computed_level=assessment.computed_level if assessment else None,
        status="submitted",
    )
