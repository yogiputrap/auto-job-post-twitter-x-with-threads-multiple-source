"""Unit tests for config.py — AppConfig defaults and SecretStr behavior."""

import os

import pytest
from config import AppConfig


@pytest.fixture
def full_env(monkeypatch):
    """Set all required env vars."""
    monkeypatch.setenv("OAUTH_TOKEN", "test-token-123")
    monkeypatch.setenv("X_CLIENT_ID", "client-id-456")
    monkeypatch.setenv("X_CLIENT_SECRET", "client-secret-789")
    monkeypatch.setenv("INDEED_SEARCH_URL", "https://indeed.com/search")
    monkeypatch.setenv("GLINTS_SEARCH_URL", "https://glints.com/search")


class TestAppConfigDefaults:
    def test_default_values(self, full_env):
        config = AppConfig()
        assert config.run_interval_minutes == 60
        assert config.db_path == "posted_jobs.sqlite"
        assert config.listings_per_source == 10
        assert config.inter_post_delay_seconds == 5
        assert config.inter_request_delay_seconds == 2

    def test_reads_required_vars(self, full_env):
        config = AppConfig()
        assert config.oauth_token.get_secret_value() == "test-token-123"
        assert config.indeed_search_url == "https://indeed.com/search"


class TestSecretStrSafety:
    def test_repr_does_not_expose_token(self, full_env):
        config = AppConfig()
        repr_str = repr(config.oauth_token)
        assert "test-token-123" not in repr_str
        assert "**********" in repr_str

    def test_str_does_not_expose_secret(self, full_env):
        config = AppConfig()
        str_val = str(config.x_client_secret)
        assert "client-secret-789" not in str_val


class TestMissingVars:
    def test_missing_oauth_token_raises(self, monkeypatch):
        monkeypatch.setenv("X_CLIENT_ID", "cid")
        monkeypatch.setenv("X_CLIENT_SECRET", "csec")
        monkeypatch.setenv("INDEED_SEARCH_URL", "https://x.com")
        monkeypatch.setenv("GLINTS_SEARCH_URL", "https://y.com")
        monkeypatch.delenv("OAUTH_TOKEN", raising=False)
        with pytest.raises(Exception):  # ValidationError
            AppConfig()
