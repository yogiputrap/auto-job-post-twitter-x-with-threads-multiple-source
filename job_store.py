"""SQLite-backed Job_Store for the Job Vacancy Twitter Bot.

Provides the `JobStore` class used by the Job_Manager to persist
Job_IDs of successfully posted listings across Run_Cycles, enabling
duplicate suppression (Requirements 2.1, 2.4).

The schema mirrors the "Job_Store Schema (SQLite)" section of the
design document:

    CREATE TABLE IF NOT EXISTS posted_jobs (
        job_id    TEXT PRIMARY KEY,
        tweet_id  TEXT NOT NULL,
        posted_at TEXT NOT NULL  -- ISO-8601 UTC
    );
    CREATE INDEX IF NOT EXISTS idx_posted_at ON posted_jobs(posted_at);

Only the stdlib `sqlite3` module is used.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Set


# DDL statements kept as module-level constants so they can be reused
# (e.g. by tests) and reviewed against the design schema verbatim.
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS posted_jobs (
    job_id    TEXT PRIMARY KEY,
    tweet_id  TEXT NOT NULL,
    posted_at TEXT NOT NULL
);
""".strip()

_CREATE_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_posted_at ON posted_jobs(posted_at);"
)


class JobStore:
    """Persistent Job_ID store backed by a single SQLite file.

    A single `sqlite3.Connection` is opened in `__init__` and reused
    across calls (per task: "ensure connection is reusable across
    calls"). Callers should invoke `close()` when shutting down.

    All write paths use parameterized SQL to avoid injection and to
    let SQLite handle proper escaping/binding of TEXT values.
    """

    def __init__(self, db_path: str) -> None:
        """Open the SQLite database at `db_path` and ensure schema exists.

        SQLite creates the file automatically if it does not exist,
        so this also covers the "fresh DB file" case from the design.
        """
        self._db_path = db_path
        # `check_same_thread=False` keeps usage simple for the
        # single-threaded Job_Manager while still allowing tests to
        # share the connection across threads if ever needed. The bot
        # itself does not access the store from multiple threads.
        self._conn: sqlite3.Connection = sqlite3.connect(
            db_path, check_same_thread=False
        )
        self._conn.execute(_CREATE_TABLE_SQL)
        self._conn.execute(_CREATE_INDEX_SQL)
        self._conn.commit()

    def contains(self, job_id: str) -> bool:
        """Return True if `job_id` has already been recorded.

        Used by Job_Manager to skip duplicates (Requirement 2.2).
        """
        cursor = self._conn.execute(
            "SELECT 1 FROM posted_jobs WHERE job_id = ? LIMIT 1;",
            (job_id,),
        )
        return cursor.fetchone() is not None

    def save(self, job_id: str, tweet_id: str, posted_at: datetime) -> None:
        """Record a successfully posted listing.

        `posted_at` is serialized as an ISO-8601 string per the schema
        comment ("ISO-8601 UTC"). `INSERT OR REPLACE` makes saving the
        same job_id twice idempotent so callers do not need to guard
        against re-saves on retry paths (Requirement 2.1).
        """
        self._conn.execute(
            "INSERT OR REPLACE INTO posted_jobs (job_id, tweet_id, posted_at) "
            "VALUES (?, ?, ?);",
            (job_id, tweet_id, posted_at.isoformat()),
        )
        self._conn.commit()

    def all_ids(self) -> Set[str]:
        """Return the set of all recorded Job_IDs.

        Returns a `set[str]` so callers can perform fast membership
        checks; this is the shape Property 5 (Job_Store round-trip
        persistence) operates on.
        """
        cursor = self._conn.execute("SELECT job_id FROM posted_jobs;")
        return {row[0] for row in cursor.fetchall()}

    def close(self) -> None:
        """Close the underlying SQLite connection.

        Safe to call multiple times; subsequent calls are no-ops.
        """
        if self._conn is not None:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]
