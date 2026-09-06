"""Application configuration module using Pydantic BaseSettings."""

from functools import lru_cache
from datetime import date
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Core application settings."""

    # Project metadata
    PROJECT_NAME: str = "Airfare Price Index (APIx)"
    API_V1_STR: str = "/api"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    VERSION: str = "0.1.0"
    LOG_LEVEL: str = "INFO"

    # Server config
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Scraper settings & mode switch
    SCRAPER_MODE: str = "mock"  # "mock" for synthetic testing, "live" for rate-limited web requests
    SCRAPER_RATE_LIMIT_DELAY: float = 3.0
    SCRAPER_USER_AGENT: str = "APIx-Research-Bot/0.1 (Academic Prototype; Contact: research@example.edu)"
    DAILY_COLLECTION_TIME: str = "06:00"
    DAILY_COLLECTION_TIMEZONE: str = "Asia/Kolkata"
    DAILY_COLLECTION_ENABLED_SOURCES: str = "akasa"
    PROTOTYPE_REFERENCE_COLLECTION_DATE: date = date(2026, 9, 6)

    # Database configuration
    USE_SQLITE_FALLBACK: bool = True
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres_password"
    POSTGRES_DB: str = "apix_db"
    DATABASE_URL: Union[str, None] = None

    # CORS origins
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: Union[str, None], info) -> str:
        """Assembles database URL from individual parameters if not explicitly provided."""
        if isinstance(v, str) and v.strip():
            return v
        data = info.data
        if data.get("USE_SQLITE_FALLBACK", False):
            return "sqlite:///./apix.db"
        user = data.get("POSTGRES_USER", "postgres")
        password = data.get("POSTGRES_PASSWORD", "postgres_password")
        server = data.get("POSTGRES_SERVER", "localhost")
        port = data.get("POSTGRES_PORT", 5432)
        db = data.get("POSTGRES_DB", "apix_db")
        return f"postgresql://{user}:{password}@{server}:{port}/{db}"

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Returns cached settings instance."""
    return Settings()


settings = get_settings()
