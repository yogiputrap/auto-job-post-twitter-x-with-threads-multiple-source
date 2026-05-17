"""Data models for the Job Vacancy Twitter Bot.

Defines the `JobListing` frozen dataclass shared across the Scraper,
Formatter, Poster, and Job_Manager modules.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

# Sources the bot supports. Mirrors the constraint in the design's
# Job_Listing table ("source: one of {indeed, glints}").
ALLOWED_SOURCES = frozenset({"indeed", "glints"})

# job_id is sha256(...)[:16], i.e. a 16-character lowercase hex string.
_JOB_ID_LENGTH = 16
_HEX_ALPHABET = frozenset("0123456789abcdef")


@dataclass(frozen=True)
class JobListing:
    """Immutable representation of a single job posting.

    Fields mirror the "Data Models -> Job_Listing" table in the design.
    Validation in `__post_init__` enforces the constraints from that
    table so that downstream consumers (Formatter, Job_Manager) can
    rely on well-formed inputs.
    """

    job_id: str
    title: str
    company: str
    location: str
    salary: Optional[str]
    url: str
    source: str

    def __post_init__(self) -> None:
        # job_id: exactly 16 lowercase hex chars
        if not isinstance(self.job_id, str) or len(self.job_id) != _JOB_ID_LENGTH:
            raise ValueError(
                f"job_id must be a {_JOB_ID_LENGTH}-character hex string, "
                f"got {self.job_id!r}"
            )
        if any(ch not in _HEX_ALPHABET for ch in self.job_id):
            raise ValueError(
                f"job_id must contain only lowercase hex characters, got {self.job_id!r}"
            )

        # title / company / url: non-empty
        if not self.title or not self.title.strip():
            raise ValueError("title must be non-empty")
        if not self.company or not self.company.strip():
            raise ValueError("company must be non-empty")
        if not self.url or not self.url.strip():
            raise ValueError("url must be non-empty")

        # url: HTTP(S) URL (simple prefix check per task spec)
        if not (self.url.startswith("http://") or self.url.startswith("https://")):
            raise ValueError(f"url must start with http:// or https://, got {self.url!r}")

        # source: limited vocabulary
        if self.source not in ALLOWED_SOURCES:
            raise ValueError(
                f"source must be one of {sorted(ALLOWED_SOURCES)}, got {self.source!r}"
            )

    @classmethod
    def compute_id(cls, source: str, native_id: str) -> str:
        """Derive a stable 16-char hex Job_ID from a source-prefixed native ID.

        Uses sha256 truncated to 16 hex chars, matching the design decision
        "Job_ID derivation: sha256(source + ':' + source_native_id)[:16]".
        Source-prefixing prevents cross-source ID collisions.
        """
        digest = hashlib.sha256(f"{source}:{native_id}".encode("utf-8")).hexdigest()
        return digest[:_JOB_ID_LENGTH]
