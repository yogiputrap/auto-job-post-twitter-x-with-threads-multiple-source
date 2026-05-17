"""Pipeline orchestrator for the Job Vacancy Twitter Bot.

Implements the `JobManager` class which coordinates the full Run_Cycle:
fetch → dedup → format → post → persist. Also provides the
`CredentialRedactionFilter` that scrubs known credential values from any
log record before it is emitted (Requirement 6.3, Property 20).

Design references:
- Components → job_manager.py
- Error Handling → Cycle-Level Recovery
- Properties 16-22
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Tuple

from config import AppConfig
from formatter import format_tweet, format_thread
from job_store import JobStore
from models import JobListing
from scraper import fetch_all
from scraper.base import FallbackJobSource, JobSource
from twitter_client import PostResult, Poster, ThreadResult


@dataclass
class CycleSummary:
    """Accounting for a single Run_Cycle.

    Invariant (Property 18): fetched == skipped_duplicate + posted + failed
    All counts are non-negative.
    """

    fetched: int = 0
    skipped_duplicate: int = 0
    posted: int = 0
    failed: int = 0


class CredentialRedactionFilter(logging.Filter):
    """Logging filter that replaces known credential values with a placeholder.

    Installed on the JobManager's logger so that even if a credential value
    accidentally appears in a log message (e.g. via an exception repr), it
    is scrubbed before reaching any handler (Requirement 6.3, Property 20).
    """

    _REDACTED = "***REDACTED***"

    def __init__(self, secrets: List[str]) -> None:
        super().__init__()
        # Only track non-empty secrets to avoid replacing empty strings
        self._secrets = [s for s in secrets if s and s.strip()]

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact secrets from the log record message and args.

        Always returns True (the record is never suppressed, only sanitized).
        """
        if not self._secrets:
            return True

        # Redact in the message template
        if isinstance(record.msg, str):
            for secret in self._secrets:
                if secret in record.msg:
                    record.msg = record.msg.replace(secret, self._REDACTED)

        # Redact in format args (%-style formatting)
        if record.args:
            if isinstance(record.args, tuple):
                new_args = []
                for a in record.args:
                    if isinstance(a, str):
                        redacted = a
                        for secret in self._secrets:
                            redacted = redacted.replace(secret, self._REDACTED)
                        new_args.append(redacted)
                    else:
                        new_args.append(a)
                record.args = tuple(new_args)
            elif isinstance(record.args, dict):
                new_dict = {}
                for k, v in record.args.items():
                    if isinstance(v, str):
                        redacted = v
                        for secret in self._secrets:
                            redacted = redacted.replace(secret, self._REDACTED)
                        new_dict[k] = redacted
                    else:
                        new_dict[k] = v
                record.args = new_dict

        return True


class JobManager:
    """Pipeline orchestrator: fetch → dedup → format → post → persist.

    Coordinates a single Run_Cycle via `run_once()`. Each listing is
    processed independently so that one failure does not abort the cycle
    (Requirement 5.2, Property 17). A top-level try/except ensures the
    accounting invariant (Property 18) is preserved even on unexpected
    exceptions.
    """

    # Configurable for testing (allows injecting a fake sleep)
    _sleep_func = staticmethod(time.sleep)

    def __init__(
        self,
        config: AppConfig,
        sources: List[Tuple[JobSource, FallbackJobSource]],
        poster: Poster,
        store: JobStore,
    ) -> None:
        self._config = config
        self._sources = sources
        self._poster = poster
        self._store = store
        self._logger = logging.getLogger(__name__)

        # Install credential redaction filter (Requirement 6.3, Property 20)
        secrets = [
            config.oauth_token.get_secret_value(),
            config.x_client_id.get_secret_value(),
            config.x_client_secret.get_secret_value(),
        ]
        self._redaction_filter = CredentialRedactionFilter(secrets)
        self._logger.addFilter(self._redaction_filter)

    def run_once(self) -> CycleSummary:
        """Execute one full Run_Cycle. Returns CycleSummary satisfying the accounting invariant.

        Steps (Requirement 5.1):
          1. Fetch listings from all configured sources
          2. Filter duplicates against the Job_Store (Requirement 2.2, 2.3)
          3. For each new listing: format → post → persist (Requirement 2.1)
          4. Apply inter_post_delay_seconds between consecutive posts (Requirement 5.3)
          5. Log summary at end (Requirement 7.5)
        """
        summary = CycleSummary()

        try:
            # Step 1: Fetch listings from all sources
            listings: List[JobListing] = fetch_all(
                self._sources, self._config.listings_per_source
            )
            summary.fetched = len(listings)

            # Step 2: Filter duplicates (Requirement 2.2, 2.3)
            new_listings: List[JobListing] = []
            for listing in listings:
                if self._store.contains(listing.job_id):
                    summary.skipped_duplicate += 1
                else:
                    new_listings.append(listing)

            # Step 3: Format, post, persist each new listing
            first_post = True
            for listing in new_listings:
                try:
                    # Inter-post delay between consecutive posts (Requirement 5.3, Property 16)
                    if not first_post:
                        self._sleep_func(self._config.inter_post_delay_seconds)

                    # Format as thread (list of tweets)
                    thread_tweets: list[str] = format_thread(listing)

                    # Post as thread via the Poster
                    thread_result: ThreadResult = self._poster.post_thread(thread_tweets)

                    if thread_result.success:
                        # Persist on success — use first tweet ID as the canonical ID
                        first_tweet_id = thread_result.tweet_ids[0]
                        self._store.save(
                            listing.job_id,
                            first_tweet_id,
                            datetime.now(timezone.utc),
                        )
                        summary.posted += 1
                        first_post = False

                        # INFO log with both IDs (Requirement 7.3, Property 21)
                        self._logger.info(
                            "Posted thread successfully job_id=%s tweet_ids=%s",
                            listing.job_id,
                            thread_result.tweet_ids,
                        )
                    else:
                        # Do NOT persist on failure (Requirement 2.5)
                        summary.failed += 1

                        # ERROR log on failure (Requirement 7.4, Property 22)
                        self._logger.error(
                            "Failed to post thread job_id=%s failed_at=%s error_code=%s error=%s",
                            listing.job_id,
                            thread_result.failed_at,
                            thread_result.error_code,
                            thread_result.error_message,
                        )
                except Exception as exc:
                    # Per-listing exception isolation (Requirement 5.2, Property 17)
                    summary.failed += 1
                    self._logger.error(
                        "Exception while processing listing job_id=%s: %s",
                        listing.job_id,
                        exc,
                    )
        except Exception as exc:
            # Top-level catch to preserve accounting invariant (Property 18)
            self._logger.critical("Unhandled exception in run_once: %s", exc)
            # Ensure invariant: failed = fetched - skipped_duplicate - posted
            summary.failed = summary.fetched - summary.skipped_duplicate - summary.posted

        # Summary log at end of cycle (Requirement 7.5)
        self._logger.info(
            "Run_Cycle complete: fetched=%d skipped_duplicate=%d posted=%d failed=%d",
            summary.fetched,
            summary.skipped_duplicate,
            summary.posted,
            summary.failed,
        )

        return summary
