"""Application configuration loaded from environment variables.

Reads required credentials and search URLs from environment (or `.env`)
using ``pydantic-settings``. Credentials are wrapped in :class:`SecretStr`
so they are never echoed in ``__repr__`` or log output (Requirement 6.3).
"""
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Application configuration sourced from environment variables."""

    # Zernio API key for posting tweets via Zernio
    zernio_api_key: SecretStr

    # AI summarization (Groq - free tier)
    groq_api_key: SecretStr = SecretStr("")

    # Required search URLs
    indeed_search_url: str
    glints_search_url: str

    # Posting format: "raw" (detailed dump) or "summary" (AI-summarized)
    post_format: str = "summary"

    # Optional tuning parameters
    run_interval_minutes: int = 60
    db_path: str = "posted_jobs.sqlite"
    listings_per_source: int = 10
    inter_post_delay_seconds: int = 5
    inter_request_delay_seconds: int = 2

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
