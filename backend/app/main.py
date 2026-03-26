from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.database import engine, async_session
from app.models.base import Base
from app.models import *  # noqa: F401, F403 - ensure all models are registered
from app.api.v1 import auth, registration, semesters, enrollments
from app.api.v1 import literacy_test
from app.api.v1.admin import semesters as admin_semesters
from app.api.v1.admin import classes as admin_classes
from app.api.v1.admin import students as admin_students
from app.api.v1.admin import placement as admin_placement
from app.api.v1.admin import teachers as admin_teachers
from app.api.v1.admin import literacy_tests as admin_literacy_tests
from app.web import admin as admin_web
from fastapi.templating import Jinja2Templates  # noqa: ensure import available

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (use Alembic for production migrations)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Migrate new columns on existing tables (idempotent)
    async with engine.begin() as conn:
        for col_sql in [
            "ALTER TABLE semesters ADD COLUMN total_weeks INTEGER",
            "ALTER TABLE semesters ADD COLUMN holiday_weeks VARCHAR(200)",
            "ALTER TABLE guardians ADD COLUMN gender VARCHAR(10)",
            "ALTER TABLE guardians ADD COLUMN relationship_to_child VARCHAR(20)",
            "ALTER TABLE guardians ADD COLUMN nationality VARCHAR(100)",
            "ALTER TABLE guardians ADD COLUMN language VARCHAR(100)",
            "ALTER TABLE guardians ADD COLUMN notes TEXT",
            "ALTER TABLE students ADD COLUMN nationality VARCHAR(100)",
            "ALTER TABLE students ADD COLUMN is_teacher_child INTEGER DEFAULT 0",
            "ALTER TABLE teachers ADD COLUMN gender VARCHAR(10)",
            "ALTER TABLE students ADD COLUMN teacher_id INTEGER REFERENCES teachers(id)",
            "ALTER TABLE materials ADD COLUMN lesson_count INTEGER",
            "ALTER TABLE materials ADD COLUMN char_count INTEGER",
            "ALTER TABLE materials ADD COLUMN char_set TEXT",
        ]:
            try:
                await conn.execute(text(col_sql))
            except Exception:
                pass  # column already exists

    # Seed default admin user if none exists
    async with async_session() as db:
        from sqlalchemy import select
        from app.models.admin_user import AdminUser
        from app.services.auth import hash_password

        result = await db.execute(select(AdminUser).limit(1))
        if not result.scalar_one_or_none():
            admin = AdminUser(
                username="admin",
                hashed_password=hash_password(settings.ADMIN_DEFAULT_PASSWORD),
                is_superadmin=True,
            )
            db.add(admin)
            await db.commit()

    yield

    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    description="行知学堂新生报名与排班系统 API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public / guardian routes
app.include_router(auth.router, prefix="/api/v1")
app.include_router(registration.router, prefix="/api/v1")
app.include_router(semesters.router, prefix="/api/v1")
app.include_router(enrollments.router, prefix="/api/v1")

# Admin routes
app.include_router(admin_semesters.router, prefix="/api/v1/admin")
app.include_router(admin_classes.router, prefix="/api/v1/admin")
app.include_router(admin_students.router, prefix="/api/v1/admin")
app.include_router(admin_placement.router, prefix="/api/v1/admin")
app.include_router(admin_teachers.router, prefix="/api/v1/admin")
app.include_router(literacy_test.router, prefix="/api/v1")
app.include_router(admin_literacy_tests.router, prefix="/api/v1/admin")

# Admin web UI
app.include_router(admin_web.router)


@app.get("/")
async def root():
    return {"message": "行知学堂排班系统 API", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok"}
