"""Unit tests for formatter.py — tweet formatting and truncation."""

import pytest
from formatter import format_tweet, TWEET_LIMIT, HASHTAGS
from models import JobListing


def _listing(**overrides):
    defaults = {
        "job_id": "a" * 16,
        "title": "Backend Developer",
        "company": "Tokopedia",
        "location": "Remote",
        "salary": None,
        "url": "https://example.com/jobs/123",
        "source": "indeed",
    }
    defaults.update(overrides)
    return JobListing(**defaults)


class TestFormatTweet:
    def test_basic_format_within_limit(self):
        result = format_tweet(_listing())
        assert len(result) <= TWEET_LIMIT
        assert "Backend Developer" in result
        assert "Tokopedia" in result
        assert "https://example.com/jobs/123" in result
        assert HASHTAGS in result

    def test_contains_location(self):
        result = format_tweet(_listing(location="Jakarta"))
        assert "Jakarta" in result

    def test_salary_included_when_present(self):
        result = format_tweet(_listing(salary="Rp 15-20jt"))
        assert "Rp 15-20jt" in result

    def test_salary_line_omitted_when_none(self):
        result = format_tweet(_listing(salary=None))
        assert "💰" not in result

    def test_all_hashtags_present(self):
        result = format_tweet(_listing())
        assert "#RemoteJobs" in result
        assert "#WFH" in result
        assert "#Freelance" in result
        assert "#LokerRemote" in result

    def test_url_appears_exactly_once(self):
        listing = _listing()
        result = format_tweet(listing)
        assert result.count(listing.url) == 1

    def test_long_title_gets_truncated(self):
        long_title = "A" * 300
        result = format_tweet(_listing(title=long_title))
        assert len(result) <= TWEET_LIMIT
        assert "…" in result

    def test_truncation_preserves_url(self):
        long_title = "B" * 300
        listing = _listing(title=long_title)
        result = format_tweet(listing)
        assert listing.url in result

    def test_truncation_preserves_hashtags(self):
        long_title = "C" * 300
        result = format_tweet(_listing(title=long_title))
        assert HASHTAGS in result

    def test_indonesian_title(self):
        result = format_tweet(_listing(title="Pengembang Perangkat Lunak Senior"))
        assert "Pengembang Perangkat Lunak Senior" in result
        assert len(result) <= TWEET_LIMIT

    def test_emoji_in_title(self):
        result = format_tweet(_listing(title="🚀 Full Stack Dev"))
        assert "🚀 Full Stack Dev" in result
        assert len(result) <= TWEET_LIMIT

    def test_salary_dropped_before_title_truncation(self):
        # Title that fits without salary but not with salary
        title = "D" * 200
        listing = _listing(title=title, salary="Rp 50.000.000/bulan yang sangat besar sekali")
        result = format_tweet(listing)
        assert len(result) <= TWEET_LIMIT
