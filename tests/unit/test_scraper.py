"""Unit tests for scraper aggregator — fetch_all behavior."""

from typing import List

import pytest
from models import JobListing
from scraper import fetch_all
from scraper.base import FallbackJobSource, JobSource


def _make_listing(job_id_suffix: str, source: str = "indeed") -> JobListing:
    jid = job_id_suffix.ljust(16, "0")[:16]
    return JobListing(
        job_id=jid,
        title="Test Job",
        company="Test Co",
        location="Remote",
        salary=None,
        url="https://example.com/job",
        source=source,
    )


class MockSource(JobSource):
    name = "mock-primary"

    def __init__(self, listings=None, should_fail=False):
        super().__init__(inter_request_delay_seconds=0)
        self._listings = listings or []
        self._should_fail = should_fail

    def fetch(self, limit: int) -> List[JobListing]:
        if self._should_fail:
            raise RuntimeError("Primary failed")
        return self._listings[:limit]


class MockFallback(FallbackJobSource):
    name = "mock-fallback"

    def __init__(self, listings=None, should_fail=False):
        super().__init__(inter_request_delay_seconds=0)
        self._listings = listings or []
        self._should_fail = should_fail

    def fetch(self, limit: int) -> List[JobListing]:
        if self._should_fail:
            raise RuntimeError("Fallback failed")
        return self._listings[:limit]


class TestFetchAll:
    def test_empty_sources_returns_empty(self):
        assert fetch_all([], limit_per_source=10) == []

    def test_primary_success_returns_listings(self):
        listings = [_make_listing("aaa"), _make_listing("bbb")]
        primary = MockSource(listings=listings)
        fallback = MockFallback()
        result = fetch_all([(primary, fallback)], limit_per_source=10)
        assert len(result) == 2

    def test_primary_fail_uses_fallback(self):
        fallback_listings = [_make_listing("ccc")]
        primary = MockSource(should_fail=True)
        fallback = MockFallback(listings=fallback_listings)
        result = fetch_all([(primary, fallback)], limit_per_source=10)
        assert len(result) == 1
        assert result[0].job_id == "ccc0000000000000"

    def test_both_fail_returns_empty_for_pair(self):
        primary = MockSource(should_fail=True)
        fallback = MockFallback(should_fail=True)
        result = fetch_all([(primary, fallback)], limit_per_source=10)
        assert result == []

    def test_limit_per_source_respected(self):
        listings = [_make_listing(f"{i:016x}") for i in range(20)]
        primary = MockSource(listings=listings)
        fallback = MockFallback()
        result = fetch_all([(primary, fallback)], limit_per_source=5)
        assert len(result) == 5

    def test_multiple_sources_aggregated(self):
        l1 = [_make_listing("aaa")]
        l2 = [_make_listing("bbb", source="glints")]
        p1 = MockSource(listings=l1)
        f1 = MockFallback()
        p2 = MockSource(listings=l2)
        p2.name = "mock-primary-2"
        f2 = MockFallback()
        f2.name = "mock-fallback-2"
        result = fetch_all([(p1, f1), (p2, f2)], limit_per_source=10)
        assert len(result) == 2

    def test_one_pair_fails_other_succeeds(self):
        l2 = [_make_listing("ddd", source="glints")]
        p1 = MockSource(should_fail=True)
        f1 = MockFallback(should_fail=True)
        p2 = MockSource(listings=l2)
        p2.name = "p2"
        f2 = MockFallback()
        f2.name = "f2"
        result = fetch_all([(p1, f1), (p2, f2)], limit_per_source=10)
        assert len(result) == 1
