from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.guardian import Guardian
from app.models.admin_user import AdminUser
from app.schemas.admin import AdminLogin, Token
from app.services.auth import (
    verify_password,
    create_access_token,
    hash_password,
)
from app.services.wechat import code_to_session
from app.config import get_settings
from pydantic import BaseModel

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])


class WechatLoginRequest(BaseModel):
    code: str
    name: str | None = None
    phone: str | None = None


@router.post("/wechat-login", response_model=Token)
async def wechat_login(req: WechatLoginRequest, db: AsyncSession = Depends(get_db)):
    """WeChat mini-program login. Creates guardian if first time."""
    openid = None
    try:
        session_data = await code_to_session(req.code)
        openid = session_data.get("openid")
    except (ValueError, Exception):
        if settings.DEBUG:
            # Dev fallback: use the code itself as a stable fake openid
            openid = f"dev_{req.code}"
        else:
            raise HTTPException(status_code=400, detail="微信登录失败，请重试")

    if not openid:
        if settings.DEBUG:
            openid = f"dev_{req.code}"
        else:
            raise HTTPException(status_code=400, detail="Failed to get openid")

    result = await db.execute(
        select(Guardian).where(Guardian.wechat_openid == openid)
    )
    guardian = result.scalar_one_or_none()

    if not guardian:
        guardian = Guardian(
            wechat_openid=openid,
            name=req.name or "",
            email="",
            phone=req.phone or "",
        )
        db.add(guardian)
        await db.flush()

    token = create_access_token({"sub": str(guardian.id), "type": "guardian"})
    return Token(access_token=token)


class DevLoginRequest(BaseModel):
    fake_openid: str = "dev_user_001"
    name: str = "开发测试用户"
    phone: str = "13800000000"


@router.post("/dev-login", response_model=Token, include_in_schema=settings.DEBUG)
async def dev_login(req: DevLoginRequest, db: AsyncSession = Depends(get_db)):
    """仅限开发模式：用假 openid 直接登录，无需真实微信授权。"""
    if not settings.DEBUG:
        raise HTTPException(status_code=403, detail="仅开发模式可用")

    result = await db.execute(
        select(Guardian).where(Guardian.wechat_openid == req.fake_openid)
    )
    guardian = result.scalar_one_or_none()
    if not guardian:
        guardian = Guardian(
            wechat_openid=req.fake_openid,
            name=req.name,
            email="dev@example.com",
            phone=req.phone,
        )
        db.add(guardian)
        await db.flush()

    token = create_access_token({"sub": str(guardian.id), "type": "guardian"})
    return Token(access_token=token)


@router.post("/admin-login", response_model=Token)
async def admin_login(req: AdminLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AdminUser).where(AdminUser.username == req.username)
    )
    admin = result.scalar_one_or_none()
    if not admin or not verify_password(req.password, admin.hashed_password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token({"sub": str(admin.id), "type": "admin"})
    return Token(access_token=token)
