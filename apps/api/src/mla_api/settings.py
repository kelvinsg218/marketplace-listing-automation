"""Configuration from environment variables (prefix MLA_), with a .env file for development."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MLA_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    # SQLite is accepted only outside production, so the API runs on a laptop without PostgreSQL.
    database_url: str = f"sqlite:///{(API_ROOT / '.data' / 'mla_dev.db').as_posix()}"
    storage_dir: Path = API_ROOT / ".data" / "storage"
    web_dist_dir: Path | None = None  # static Next.js export served on "/" when set
    public_url: str = "http://localhost:3000"  # used in password reset links

    session_ttl_hours: int = 24 * 7
    session_cookie: str = "mla_session"
    cookie_secure: bool = True
    allow_signup: bool = True
    reset_token_ttl_minutes: int = 30
    login_max_failures: int = 5
    login_window_seconds: int = 15 * 60
    cors_origins: list[str] = []

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.environment == "production":
            if not self.database_url.startswith("postgresql"):
                raise ValueError("Em produção MLA_DATABASE_URL precisa ser PostgreSQL.")
            if not self.cookie_secure:
                raise ValueError("Em produção o cookie de sessão precisa ser Secure (HTTPS).")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
