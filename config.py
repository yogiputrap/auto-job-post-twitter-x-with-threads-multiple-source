"""Application configuration loaded from environment variables.

Reads required credentials and search URLs from environment (or `.env`)
using ``pydantic-settings``. Credentials are wrapped in :class:`SecretStr`
so they are never echoed in ``__repr__`` or log output (Requirement 6.3).
"""
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Application configuration sourced from environment variables.

    Required variables (no default) cause a validation error at instantiation
    time when missing, satisfying Requirements 6.1 and 6.2.
    """

    # Credentials (Requirement 6.3 - never log in plain text)
    oauth_token: SecretStr
    x_client_id: SecretStr
    x_client_secret: SecretStr

    # Required search URLs (Requirement 6.1)
    indeed_search_url: str
    glints_search_url: str

    # Optional tuning parameters with sensible defaults (per design.md)
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
