"""Unit tests for job_manager.py — CycleSummary and CredentialRedactionFilter."""

import logging

import pytest
from job_manager import CredentialRedactionFilter, CycleSummary


class TestCycleSummary:
    def test_defaults_to_zero(self):
        s = CycleSummary()
        assert s.fetched == 0
        assert s.skipped_duplicate == 0
        assert s.posted == 0
        assert s.failed == 0

    def test_invariant_holds(self):
        s = CycleSummary(fetched=10, skipped_duplicate=3, posted=5, failed=2)
        assert s.fetched == s.skipped_duplicate + s.posted + s.failed


class TestCredentialRedactionFilter:
    def test_redacts_secret_from_message(self):
        filt = CredentialRedactionFilter(["my-secret-token"])
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Token is my-secret-token here", args=(), exc_info=None,
        )
        filt.filter(record)
        assert "my-secret-token" not in record.msg
        assert "***REDACTED***" in record.msg

    def test_redacts_secret_from_args(self):
        filt = CredentialRedactionFilter(["secret123"])
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Value: %s", args=("secret123",), exc_info=None,
        )
        filt.filter(record)
        assert "secret123" not in record.args[0]

    def test_does_not_suppress_record(self):
        filt = CredentialRedactionFilter(["abc"])
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="No secrets here", args=(), exc_info=None,
        )
        result = filt.filter(record)
        assert result is True

    def test_empty_secrets_no_crash(self):
        filt = CredentialRedactionFilter([])
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Hello", args=(), exc_info=None,
        )
        result = filt.filter(record)
        assert result is True
