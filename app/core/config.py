"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    """Parse environment bool values."""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_list(value: str | None) -> list[str]:
    """Parse comma-separated env list values."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _as_int(value: str | None, default: int) -> int:
    """Parse integer values from environment variables."""
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""
    app_name: str
    environment: str
    log_level: str
    docs_enabled: bool
    database_url: str
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int
    auth_cookie_name: str
    auth_cookie_max_age: int
    secure_cookies: bool
    openrouter_api_key: str | None
    summary_model: str
    summary_api_url: str
    cors_origins: list[str]


@lru_cache
def get_settings() -> Settings:
    """Build immutable app settings from environment variables."""
    environment = os.getenv("APP_ENV", "development").strip().lower()
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    return Settings(
        app_name=os.getenv("APP_NAME", "BookStore").strip() or "BookStore",
        environment=environment,
        log_level=(os.getenv("LOG_LEVEL", "INFO").strip() or "INFO").upper(),
        docs_enabled=_as_bool(os.getenv("DOCS_ENABLED"), default=environment != "production"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./test.db"),
        secret_key=os.getenv("SECRET_KEY", "change-me"),
        algorithm=os.getenv("ALGORITHM", "HS256"),
        access_token_expire_minutes=_as_int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"), 30),
        auth_cookie_name=os.getenv("AUTH_COOKIE_NAME", "access_token").strip() or "access_token",
        auth_cookie_max_age=_as_int(os.getenv("AUTH_COOKIE_MAX_AGE"), 60 * 30),
        secure_cookies=_as_bool(os.getenv("SECURE_COOKIES"), default=environment == "production"),
        openrouter_api_key=openrouter_api_key,
        summary_model=os.getenv("SUMMARY_MODEL", "meta-llama/llama-3-8b-instruct"),
        summary_api_url=os.getenv("SUMMARY_API_URL", "https://openrouter.ai/api/v1/chat/completions"),
        cors_origins=_as_list(os.getenv("CORS_ORIGINS")),
    )


SETTINGS = get_settings()

# Backward-compatible exports used across the project.
SECRET_KEY = SETTINGS.secret_key
ALGORITHM = SETTINGS.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = SETTINGS.access_token_expire_minutes
