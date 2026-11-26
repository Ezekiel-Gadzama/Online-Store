from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",  # Allow extra env vars (e.g. POSTGRES_USER, POSTGRES_PASSWORD) from .env
    )

    # Database
    DATABASE_URL: str = "postgresql://yandex_user:yandex_password@postgres:5432/yandex_market"
    
    # Note: Yandex Market API and SMTP settings are now configured per business in the Settings page
    # Each business must configure their own Yandex API credentials and SMTP settings
    
    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1200  # 20 hours
    
    # Frontend URL
    FRONTEND_URL: str = "http://localhost:3000"
    
    # Public URL for media files (used when uploading to Yandex)
    PUBLIC_URL: str = "http://localhost:8000"


settings = Settings()


def get_frontend_url() -> str:
    """Public admin UI base URL for links in email (staff invite, password reset)."""
    raw = (settings.FRONTEND_URL or "").strip().rstrip("/")
    if raw and "localhost" not in raw and "127.0.0.1" not in raw:
        return raw
    pub = (settings.PUBLIC_URL or "").strip().rstrip("/")
    if pub and "localhost" not in pub and "127.0.0.1" not in pub:
        if pub.endswith(":8010"):
            return f"{pub[:-5]}:3010"
        return pub
    return raw or "http://localhost:3000"
