"""Unit tests for twitter_client.py — Poster behavior with Zernio API."""

import pytest
from twitter_client import Poster, PostResult, ThreadResult


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


class TestThreadResult:
    def test_success_thread(self):
        r = ThreadResult(success=True, tweet_ids=["1", "2", "3"])
        assert r.success is True
        assert len(r.tweet_ids) == 3

    def test_empty_thread(self):
        poster = Poster(api_key="test-key")
        result = poster.post_thread([])
        assert result.success is False
        assert "Empty" in result.error_message


class TestPosterInit:
    def test_poster_creates_with_api_key(self):
        poster = Poster(api_key="my-api-key")
        assert poster._api_key == "my-api-key"
        assert poster._account_id is None
