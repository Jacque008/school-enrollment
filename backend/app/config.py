from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "行知学堂排班系统"
    DEBUG: bool = False

    DATABASE_URL: str = "sqlite+aiosqlite:///./placement.db"

    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    WECHAT_APP_ID: str = ""
    WECHAT_APP_SECRET: str = ""

    ADMIN_DEFAULT_PASSWORD: str = "admin123"

    model_config = {"env_file": ".env", "env_prefix": "PLACEMENT_"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
