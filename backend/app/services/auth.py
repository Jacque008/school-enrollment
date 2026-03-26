from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import get_settings
from app.database import get_db
from app.models.admin_user import AdminUser
from app.models.guardian import Guardian

security = HTTPBearer()
settings = get_settings()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _decode_token(token: str) -> tuple[int, str]:
    """Decode JWT and return (user_id, user_type). sub is stored as string per JWT spec."""
    payload = jwt.decode(
        token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )
    sub = payload.get("sub")
    user_type = payload.get("type", "")
    if sub is None:
        raise JWTError("Missing sub")
    return int(sub), user_type


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    try:
        user_id, user_type = _decode_token(credentials.credentials)
        if user_type != "admin":
            raise JWTError("Wrong type")
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(AdminUser).where(AdminUser.id == user_id))
    admin = result.scalar_one_or_none()
    if admin is None or not admin.is_active:
        raise HTTPException(status_code=401, detail="Admin not found or inactive")
    return admin


async def get_current_guardian(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Guardian:
    try:
        user_id, user_type = _decode_token(credentials.credentials)
        if user_type != "guardian":
            raise JWTError("Wrong type")
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(Guardian).where(Guardian.id == user_id))
    guardian = result.scalar_one_or_none()
    if guardian is None:
        raise HTTPException(status_code=401, detail="Guardian not found")
    return guardian
