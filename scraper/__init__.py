"""Scraper aggregator.

Exposes `fetch_all`, which iterates over `(primary, fallback)` source pairs
and aggregates their results into a single list of `JobListing`s. The
aggregator is intentionally simple: each source pair is tried independently,
and a failure of one pair does not abort the cycle (Requirements 1.6, 1.7,
1.8, 7.1, 7.2).

Per-element parsing errors are caught inside each `JobSource.fetch`
implementation, so by the time listings reach this aggregator they are
already validated `JobListing` instances. The aggregator still defensively
filters out anything that is not a `JobListing` to make composition with
future sources safe.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from models import JobListing
from .base import JobSource, FallbackJobSource

logger = logging.getLogger(__name__)


def fetch_all(
    sources: List[Tuple[JobSource, FallbackJobSource]],
    limit_per_source: int,
) -> List[JobListing]:
    """Aggregate listings from a list of `(primary, fallback)` source pairs.

    For each pair:
      1. Attempt `primary.fetch(limit_per_source)`. On any exception, log a
         WARNING tagged with `primary.name` and fall through to the fallback.
      2. Attempt `fallback.fetch(limit_per_source)`. On any exception, log
         an ERROR tagged with `fallback.name` and continue with the next
         pair (do not raise).
      3. Whichever tier succeeds, append up to `limit_per_source` of its
         listings to the aggregated result. The slice ensures an over-eager
         source cannot exceed the configured per-source budget (Property 2).

    Listings that are not `JobListing` instances are skipped defensively;
    this is a safety net since `JobListing.__post_init__` already enforces
    field validity at construction time.
    """
    aggregated: List[JobListing] = []

    for primary, fallback in sources:
        listings: List[JobListing] = []

        try:
            listings = primary.fetch(limit_per_source)
        except Exception as exc:
            logger.warning(
                "Primary source %s failed: %s; falling back to %s",
                primary.name,
                exc,
                fallback.name,
            )
            try:
                listings = fallback.fetch(limit_per_source)
            except Exception as fallback_exc:
                logger.error(
                    "Fallback source %s also failed: %s; skipping pair",
                    fallback.name,
                    fallback_exc,
                )
                continue

        # Truncate to the configured per-source limit and defensively filter
        # out anything that is not a JobListing.
        for item in listings[:limit_per_source]:
            if isinstance(item, JobListing):
                aggregated.append(item)

    return aggregated
