"""Unit tests for twitter_client.py — Poster behavior."""

import pytest
from twitter_client import Poster, PostResult


class TestPosterAuth:
    def test_empty_token_returns_auth_failure(self):
        poster = Poster(oauth_token="", client_id="cid", client_secret="csec")
        result = poster.post("Hello world")
        assert result.success is False
        assert result.error_code == 401
        assert "Authentication failed" in result.error_message

    def test_whitespace_token_returns_auth_failure(self):
        poster = Poster(oauth_token="   ", client_id="cid", client_secret="csec")
        result = poster.post("Hello world")
        assert result.success is False
        assert result.error_code == 401


class TestPostResult:
    def test_success_result(self):
        r = PostResult(success=True, tweet_id="12345")
        assert r.success is True
        assert r.tweet_id == "12345"
        assert r.error_code is None

    def test_failure_result(self):
        r = PostResult(success=False, error_code=403, error_message="Forbidden")
        assert r.success is False
        assert r.error_code == 403
        assert r.tweet_id is None
