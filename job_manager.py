"""Pipeline orchestrator for the Job Vacancy Twitter Bot.

Implements the `JobManager` class which coordinates the full Run_Cycle:
fetch → dedup → format → post → persist. Also provides the
`CredentialRedactionFilter` that scrubs known credential values from any
log record before it is emitted.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Tuple

from config import AppConfig
from formatter import format_tweet, format_thread, format_summary_post
from job_store import JobStore
from models import JobListing
from scraper import fetch_all
from scraper.base import FallbackJobSource, JobSource
from twitter_client import PostResult, Poster, ThreadResult

from pathlib import Path


@dataclass
class CycleSummary:
    """Accounting for a single Run_Cycle.

    Invariant: fetched == skipped_duplicate + posted + failed
    """

    fetched: int = 0
    skipped_duplicate: int = 0
    posted: int = 0
    failed: int = 0


class CredentialRedactionFilter(logging.Filter):
    """Logging filter that replaces known credential values with a placeholder."""

    _REDACTED = "***REDACTED***"

    def __init__(self, secrets: List[str]) -> None:
        super().__init__()
        self._secrets = [s for s in secrets if s and s.strip()]

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._secrets:
            return True

        if isinstance(record.msg, str):
            for secret in self._secrets:
                if secret in record.msg:
                    record.msg = record.msg.replace(secret, self._REDACTED)

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
    """Pipeline orchestrator: fetch → dedup → format → post → persist."""

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

        # Install credential redaction filter
        secrets = [
            config.zernio_api_key.get_secret_value(),
            config.groq_api_key.get_secret_value(),
        ]
        self._redaction_filter = CredentialRedactionFilter(secrets)
        self._logger.addFilter(self._redaction_filter)

    @staticmethod
    def _is_remote(listing: JobListing) -> bool:
        """Check if a listing is open for Asia or worldwide candidates.
        
        Skip listings that are restricted to specific non-Asia regions
        (e.g., USA only, Europe only, Americas only).
        """
        location_lower = listing.location.lower()
        text_all = f"{location_lower} {listing.title.lower()} {(listing.job_type or '').lower()}"
        
        # Acceptable: explicitly Asia, worldwide, or fully open
        accept_keywords = [
            'asia', 'apac', 'indonesia', 'singapore', 'malaysia', 'philippines',
            'thailand', 'vietnam', 'india', 'japan', 'korea', 'china',
            'hong kong', 'taiwan',
            'worldwide', 'global', 'anywhere', 'any country', 'any location',
            'any timezone', 'any time zone', 'work from anywhere',
        ]
        
        # If location explicitly mentions Asia or worldwide → accept
        if any(kw in text_all for kw in accept_keywords):
            return True
        
        # Reject: location restricted to non-Asia regions
        reject_keywords = [
            'usa only', 'us only', 'united states only', 'us-based only',
            'us residents', 'must be located in the us',
            'eu only', 'europe only', 'eea only',
            'uk only', 'canada only',
            'americas only', 'north america only',
            'emea only', 'latin america only', 'latam only',
        ]
        if any(kw in text_all for kw in reject_keywords):
            return False
        
        # If location is a single restricted region (without "only" wording)
        # Check if the location string is JUST that region
        location_clean = location_lower.strip()
        restricted_regions = ['usa', 'us', 'united states', 'eu', 'europe', 'uk',
                              'canada', 'americas', 'north america', 'latam']
        # If location is exactly one of these (or with country/state), reject
        if location_clean in restricted_regions:
            return False
        # If location is "USA, Canada" or similar (no Asia) — reject
        if any(loc in location_clean for loc in ['usa', 'us ', 'united states']) and \
           not any(kw in text_all for kw in accept_keywords):
            return False
        
        # Default: skip if uncertain (we want strict filter)
        return False

    def run_once(self, max_posts: int = 0) -> CycleSummary:
        """Execute one full Run_Cycle.
        
        Args:
            max_posts: Maximum number of posts to make this cycle.
                       0 means unlimited (post all new listings).
        """
        summary = CycleSummary()

        try:
            listings: List[JobListing] = fetch_all(
                self._sources, self._config.listings_per_source
            )
            summary.fetched = len(listings)

            new_listings: List[JobListing] = []
            for listing in listings:
                if self._store.contains(listing.job_id):
                    summary.skipped_duplicate += 1
                elif not self._is_remote(listing):
                    self._logger.info("Skipping listing not open for Asia/worldwide: %s (%s)", listing.title, listing.location)
                    summary.skipped_duplicate += 1
                else:
                    new_listings.append(listing)

            first_post = True
            for listing in new_listings:
                # Respect max_posts limit
                if max_posts > 0 and summary.posted >= max_posts:
                    self._logger.info("Reached max_posts=%d limit, stopping", max_posts)
                    break

                try:
                    if not first_post:
                        self._sleep_func(self._config.inter_post_delay_seconds)

                    # Read current format preference (can be changed via dashboard)
                    format_file = Path("post_format.txt")
                    current_format = format_file.read_text().strip() if format_file.exists() else self._config.post_format

                    thread_tweets: list[str] = format_thread(
                        listing,
                        post_format=current_format,
                        groq_api_key=self._config.groq_api_key.get_secret_value(),
                    )
                    thread_result: ThreadResult = self._poster.post_thread(thread_tweets)

                    if thread_result.success:
                        first_tweet_id = thread_result.tweet_ids[0]
                        self._store.save(
                            listing.job_id,
                            first_tweet_id,
                            datetime.now(timezone.utc),
                        )
                        summary.posted += 1
                        first_post = False

                        self._logger.info(
                            "Posted thread successfully job_id=%s tweet_ids=%s",
                            listing.job_id,
                            thread_result.tweet_ids,
                        )
                    else:
                        summary.failed += 1
                        self._logger.error(
                            "Failed to post thread job_id=%s failed_at=%s error_code=%s error=%s",
                            listing.job_id,
                            thread_result.failed_at,
                            thread_result.error_code,
                            thread_result.error_message,
                        )
                        # Stop cycle if daily limit reached
                        if thread_result.error_code == 429 and thread_result.error_message and "Daily post limit" in thread_result.error_message:
                            self._logger.warning("Daily post limit reached, stopping cycle")
                            break
                except Exception as exc:
                    summary.failed += 1
                    self._logger.error(
                        "Exception while processing listing job_id=%s: %s",
                        listing.job_id,
                        exc,
                    )
        except Exception as exc:
            self._logger.critical("Unhandled exception in run_once: %s", exc)
            summary.failed = summary.fetched - summary.skipped_duplicate - summary.posted

        self._logger.info(
            "Run_Cycle complete: fetched=%d skipped_duplicate=%d posted=%d failed=%d",
            summary.fetched,
            summary.skipped_duplicate,
            summary.posted,
            summary.failed,
        )

        return summary
