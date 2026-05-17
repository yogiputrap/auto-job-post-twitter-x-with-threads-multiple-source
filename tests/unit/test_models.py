"""Unit tests for models.py — JobListing validation and compute_id."""

import pytest
from models import JobListing


def _valid_listing(**overrides):
    defaults = {
        "job_id": "a" * 16,
        "title": "Software Engineer",
        "company": "Acme Corp",
        "location": "Remote",
        "salary": None,
        "url": "https://example.com/job/1",
        "source": "indeed",
    }
    defaults.update(overrides)
    return JobListing(**defaults)


class TestJobListingValidation:
    def test_valid_listing_constructs(self):
        listing = _valid_listing()
        assert listing.title == "Software Engineer"

    def test_empty_title_raises(self):
        with pytest.raises(ValueError, match="title must be non-empty"):
            _valid_listing(title="")

    def test_whitespace_title_raises(self):
        with pytest.raises(ValueError, match="title must be non-empty"):
            _valid_listing(title="   ")

    def test_empty_company_raises(self):
        with pytest.raises(ValueError, match="company must be non-empty"):
            _valid_listing(company="")

    def test_empty_url_raises(self):
        with pytest.raises(ValueError, match="url must be non-empty"):
            _valid_listing(url="")

    def test_non_http_url_raises(self):
        with pytest.raises(ValueError, match="url must start with http"):
            _valid_listing(url="ftp://example.com")

    def test_invalid_source_raises(self):
        with pytest.raises(ValueError, match="source must be one of"):
            _valid_listing(source="linkedin")

    def test_short_job_id_raises(self):
        with pytest.raises(ValueError, match="16-character hex"):
            _valid_listing(job_id="abc")

    def test_non_hex_job_id_raises(self):
        with pytest.raises(ValueError, match="lowercase hex"):
            _valid_listing(job_id="GGGGGGGGGGGGGGGG")

    def test_frozen_instance(self):
        listing = _valid_listing()
        with pytest.raises(AttributeError):
            listing.title = "New Title"


class TestComputeId:
    def test_produces_16_char_hex(self):
        result = JobListing.compute_id("indeed", "job-123")
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)

    def test_stable_output(self):
        a = JobListing.compute_id("indeed", "job-123")
        b = JobListing.compute_id("indeed", "job-123")
        assert a == b

    def test_different_sources_different_ids(self):
        a = JobListing.compute_id("indeed", "job-123")
        b = JobListing.compute_id("glints", "job-123")
        assert a != b

    def test_different_native_ids_different_output(self):
        a = JobListing.compute_id("indeed", "job-123")
        b = JobListing.compute_id("indeed", "job-456")
        assert a != b
