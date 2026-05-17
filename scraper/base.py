"""Abstract base classes for job sources.

Defines `JobSource`, the abstract base every concrete scraper (primary or
fallback) inherits from, and `FallbackJobSource`, a marker subclass used at
runtime to distinguish fallback (RSS / aggregator) sources from primary
(browser-driven) ones.

The `_throttle()` helper enforces a minimum inter-request delay so that
subclasses can comply with Requirement 1.5 ("at least 2 seconds between
consecutive HTTP requests to the same source") without each implementation
re-deriving the timing logic.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import List, Optional

from models import JobListing


class JobSource(ABC):
    """Abstract base class for any job source (primary or fallback).

    Subclasses MUST set the class attribute `name` to a short identifier
    (e.g. "indeed", "glints", "indeed-rss") used in log records and for
    debugging.
    """

    # Each concrete subclass overrides this. Declared on the base for type
    # checkers and to make the contract explicit.
    name: str = ""

    def __init__(self, inter_request_delay_seconds: int = 2) -> None:
        self.inter_request_delay_seconds = inter_request_delay_seconds
        # `None` means "no request has been issued yet"; the first call to
        # `_throttle()` does not sleep.
        self._last_request_time: Optional[float] = None

    @abstractmethod
    def fetch(self, limit: int) -> List[JobListing]:
        """Return up to `limit` recent listings.

        Raises on unrecoverable failure so the aggregator (`fetch_all`) can
        catch the exception and try the corresponding fallback source.
        """

    def _throttle(self) -> None:
        """Sleep just enough to enforce `inter_request_delay_seconds`.

        Uses `time.monotonic()` for delay calculations so that adjustments
        to the system clock (NTP, DST) cannot cause negative or unbounded
        sleeps.
        """
        if self._last_request_time is not None:
            elapsed = time.monotonic() - self._last_request_time
            remaining = self.inter_request_delay_seconds - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_time = time.monotonic()


class FallbackJobSource(JobSource):
    """Marker subclass for fallback sources (e.g. RSS, aggregator API).

    `Scraper.fetch_all` distinguishes primary from fallback sources at
    runtime by `isinstance(source, FallbackJobSource)`. No additional
    behavior is added here.
    """

    pass
