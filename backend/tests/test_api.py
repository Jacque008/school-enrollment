"""
Integration tests for the FastAPI registration → placement → confirm flow.
Uses SQLite in-memory DB via AsyncClient + TestClient.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from datetime import date, timedelta

from app.main import app
from app.database import get_db
from app.models.base import Base
from app.models import *  # noqa: F401, F403
from app.models.admin_user import AdminUser
from app.models.semester import Semester
from app.services.auth import hash_password, create_access_token, get_current_admin

# Shared in-memory SQLite via shared cache URI
TEST_DATABASE_URL = "sqlite+aiosqlite:///file:testdb?mode=memory&cache=shared&uri=true"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Seed admin and active semester
    async with TestSession() as db:
        admin = AdminUser(
            username="testadmin",
            hashed_password=hash_password("testpass"),
            is_superadmin=True,
        )
        today = date.today()
        semester = Semester(
            name="2026春季",
            start_date=today,
            end_date=today + timedelta(days=120),
            reg_open_date=today - timedelta(days=7),
            reg_close_date=today + timedelta(days=30),
            is_active=True,
        )
        db.add(admin)
        db.add(semester)
        await db.commit()

    # Override DB and admin auth
    mock_admin = AdminUser(id=1, username="testadmin", is_active=True, is_superadmin=True)

    async def mock_get_admin():
        return mock_admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin] = mock_get_admin

    yield

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest_asyncio.fixture
async def admin_token():
    """Dummy token - auth is mocked via dependency override."""
    return "test-admin-token"


REGISTRATION_PAYLOAD = {
    "student": {
        "name_zh": "张小明",
        "name_en": "Xiaoming Zhang",
        "gender": "male",
        "birth_date": "2018-03-15",
        "city_region": "Sollentuna",
    },
    "guardian": {
        "name": "张大明",
        "email": "zhang@example.com",
        "phone": "+46701234567",
        "wechat_id": "zhangdaming",
        "sibling_in_school": False,
    },
    "schedule": {"slot_types": ["sat_onsite_am", "weekend_online_am"]},
    "proficiency": {
        "listening_level": 3,
        "speaking_level": 3,
        "writing_level": 3,
    },
    "literacy": {
        "pinyin_level": 2,
        "vocab_level": 3,
        "reading_ability": "independent",
        "reading_interest": ["喜欢读儿童绘本"],
        "reading_habits": ["能长时间安静看书"],
    },
    "background": {
        "home_language": "mixed",
        "accept_alternative": True,
        "referral_source": "朋友推荐",
    },
}


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_get_current_semester(client):
    resp = await client.get("/api/v1/semesters/current")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "2026春季"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_admin_login_success(client):
    resp = await client.post(
        "/api/v1/auth/admin-login",
        json={"username": "testadmin", "password": "testpass"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_admin_login_wrong_password(client):
    resp = await client.post(
        "/api/v1/auth/admin-login",
        json={"username": "testadmin", "password": "wrongpass"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_list_students_empty(client, admin_token):
    resp = await client.get(
        "/api/v1/admin/students",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_admin_create_semester(client, admin_token):
    resp = await client.post(
        "/api/v1/admin/semesters",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "2026秋季",
            "start_date": "2026-09-01",
            "end_date": "2026-12-31",
            "reg_open_date": "2026-07-01",
            "reg_close_date": "2026-08-15",
            "is_active": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "2026秋季"
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_admin_create_class(client, admin_token):
    # First get the active semester id
    sem_resp = await client.get("/api/v1/semesters/current")
    semester_id = sem_resp.json()["id"]

    resp = await client.post(
        "/api/v1/admin/classes",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "semester_id": semester_id,
            "name": "初级班A",
            "level": 3,
            "slot_type": "sat_onsite_am",
            "schedule_day": "SAT",
            "schedule_time": "09:00:00",
            "duration_min": 120,
            "modality": "onsite",
            "capacity": 15,
            "overflow_cap": 18,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "初级班A"
    assert data["level"] == 3


@pytest.mark.asyncio
async def test_admin_run_placement_no_students(client, admin_token):
    sem_resp = await client.get("/api/v1/semesters/current")
    semester_id = sem_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/admin/placement/run?semester_id={semester_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_placement_requires_auth(client):
    """Without auth override, real HTTPBearer should reject missing token."""
    # Temporarily remove the auth mock to test actual auth enforcement
    saved = app.dependency_overrides.pop(get_current_admin, None)
    try:
        resp = await client.post("/api/v1/admin/placement/run?semester_id=1")
        assert resp.status_code in (401, 403)
    finally:
        if saved is not None:
            app.dependency_overrides[get_current_admin] = saved
