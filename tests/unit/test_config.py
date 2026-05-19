"""Unit tests for config.py — AppConfig defaults and SecretStr behavior."""

import pytest
from config import AppConfig


@pytest.fixture
def full_env(monkeypatch):
    """Set all required env vars."""
    monkeypatch.setenv("ZERNIO_API_KEY", "test-zernio-key-123")
    monkeypatch.setenv("INDEED_SEARCH_URL", "https://indeed.com/search")
    monkeypatch.setenv("GLINTS_SEARCH_URL", "https://glints.com/search")


class TestAppConfigDefaults:
    def test_default_values(self, full_env):
        config = AppConfig()
        assert config.run_interval_minutes == 60
        assert config.db_path == "posted_jobs.sqlite"
        assert config.listings_per_source == 25
        assert config.inter_post_delay_seconds == 5
        assert config.inter_request_delay_seconds == 2
        assert config.post_format == "summary"

    def test_reads_required_vars(self, full_env):
        config = AppConfig()
        assert config.zernio_api_key.get_secret_value() == "test-zernio-key-123"
        assert config.indeed_search_url == "https://indeed.com/search"


class TestSecretStrSafety:
    def test_repr_does_not_expose_key(self, full_env):
        config = AppConfig()
        repr_str = repr(config.zernio_api_key)
        assert "test-zernio-key-123" not in repr_str
        assert "**********" in repr_str

    def test_str_does_not_expose_key(self, full_env):
        config = AppConfig()
        str_val = str(config.zernio_api_key)
        assert "test-zernio-key-123" not in str_val


class TestMissingVars:
    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.setenv("INDEED_SEARCH_URL", "https://x.com")
        monkeypatch.setenv("GLINTS_SEARCH_URL", "https://y.com")
        monkeypatch.delenv("ZERNIO_API_KEY", raising=False)
        with pytest.raises(Exception):  # ValidationError
            AppConfig()
