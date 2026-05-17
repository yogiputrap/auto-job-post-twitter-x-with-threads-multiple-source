"""Unit tests for job_store.py — SQLite persistence."""

import os
import tempfile
from datetime import datetime, timezone

import pytest
from job_store import JobStore


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    s = JobStore(db_path)
    yield s
    s.close()


class TestJobStore:
    def test_fresh_db_is_empty(self, store):
        assert store.all_ids() == set()

    def test_contains_returns_false_for_unknown(self, store):
        assert store.contains("abcdef1234567890") is False

    def test_save_and_contains(self, store):
        store.save("abcdef1234567890", "tweet_001", datetime.now(timezone.utc))
        assert store.contains("abcdef1234567890") is True

    def test_save_and_all_ids(self, store):
        store.save("aaaa111122223333", "t1", datetime.now(timezone.utc))
        store.save("bbbb444455556666", "t2", datetime.now(timezone.utc))
        assert store.all_ids() == {"aaaa111122223333", "bbbb444455556666"}

    def test_idempotent_save(self, store):
        now = datetime.now(timezone.utc)
        store.save("abcdef1234567890", "tweet_001", now)
        store.save("abcdef1234567890", "tweet_001", now)  # no error
        assert store.all_ids() == {"abcdef1234567890"}

    def test_persistence_across_reopen(self, tmp_path):
        db_path = str(tmp_path / "persist.sqlite")
        s1 = JobStore(db_path)
        s1.save("1111222233334444", "tw1", datetime.now(timezone.utc))
        s1.close()

        s2 = JobStore(db_path)
        assert s2.contains("1111222233334444") is True
        assert s2.all_ids() == {"1111222233334444"}
        s2.close()

    def test_creates_db_file(self, tmp_path):
        db_path = str(tmp_path / "subdir" / "new.sqlite")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        s = JobStore(db_path)
        assert os.path.exists(db_path)
        s.close()
