"""Glints scrapers.

This module hosts the Glints-specific job sources. Per the design, Glints
is fronted by a primary browser-driven scraper and a fallback (RSS or
aggregator-API) source.

Currently implemented:

- ``GlintsSource``: primary scraper that drives a headless Chromium browser
  via Playwright's synchronous API. The class is intentionally written so
  that ``playwright`` is imported lazily inside ``fetch()``; this lets the
  module be imported (and its tests collected) on environments where
  Playwright's runtime is unavailable.
- ``GlintsRSSSource``: aggregator-API fallback. Glints does not publish a
  public RSS feed for searches, so this class talks to a configurable
  JSON job-aggregator endpoint (typically a RapidAPI provider). The class
  name keeps the ``…RSSSource`` pattern shared with ``IndeedRSSSource``
  for symmetry, even though the transport is JSON over HTTPS.
"""

from __future__ import annotations

import logging
from typing import Any, List
from urllib.parse import urljoin, urlparse

import httpx

from models import JobListing

from .base import FallbackJobSource, JobSource

logger = logging.getLogger(__name__)


# Realistic desktop User-Agent. Glints, like Indeed, runs behind a CDN
# that scrutinises obviously-headless clients, so we present a current
# Chrome on macOS string. Kept identical to indeed.py for consistency.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)

# Glints uses styled-components, which generate hashed class names that
# change between deploys (e.g. ``CompactOpportunityCardsc__Header-sc-...``).
# We therefore prefer ``data-cy`` test hooks where available and fall back
# to attribute-prefix matches on the styled-component class names. ``article``
# is a last-resort structural fallback.
_CARD_SELECTOR = (
    'div[data-cy="job-card"], '
    'a.JobCardsc__JobcardContainer-sc-hmqj50-0, '
    'article'
)

# Per-card selectors. Each is a comma-joined list of fallbacks; the first
# match wins. Kept here so the parser body stays readable.
_TITLE_SELECTOR = 'h3, [data-cy="job-title"]'
_COMPANY_SELECTOR = '[data-cy="company-name"], a[class*="CompanyLink"]'
_LOCATION_SELECTOR = (
    '[data-cy="job-location"], '
    'span[class*="CardJobLocation"]'
)
_SALARY_SELECTOR = (
    '[data-cy="salary"], '
    'span[class*="CompactOpportunityCardsc__Salary"]'
)

# How long to wait for the listing page to settle before we start scraping.
_NAV_TIMEOUT_MS = 30_000

# Marker segment in Glints job URLs. Canonical job links look like
#   https://glints.com/id/opportunities/jobs/<slug-or-id>/...
# We split on this segment to extract the per-job native identifier.
_JOB_PATH_MARKER = "/opportunities/jobs/"


class GlintsSource(JobSource):
    """Primary Glints scraper backed by Playwright + headless Chromium.

    The class drives a real browser so that JS-rendered cards and any
    bot-mitigation challenges are handled transparently. Each per-card
    parse is wrapped in its own try/except so that one malformed card
    does not abort the whole batch (Requirements 1.8, 7.2).
    """

    name = "glints"

    def __init__(
        self,
        search_url: str,
        inter_request_delay_seconds: int = 2,
    ) -> None:
        super().__init__(inter_request_delay_seconds=inter_request_delay_seconds)
        self.search_url = search_url

    def fetch(self, limit: int) -> List[JobListing]:
        """Return up to ``limit`` Glints listings.

        Throttles before the network request (Requirement 1.5), launches
        a headless Chromium with a realistic User-Agent, navigates to
        ``self.search_url``, and parses each visible job card. Per-card
        failures are logged at WARNING and skipped; the returned list
        may therefore be shorter than ``limit``.
        """
        logger.info(
            "GlintsSource.fetch starting: url=%s limit=%d",
            self.search_url,
            limit,
        )

        # Honour the per-source inter-request delay before issuing the
        # network request (Requirement 1.5, Property 3).
        self._throttle()

        # Lazy import: only require Playwright at the moment we actually
        # need it. Lets `import scraper.glints` succeed in test/CI
        # environments that do not have the browser binaries installed.
        from playwright.sync_api import sync_playwright  # type: ignore

        listings: List[JobListing] = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                context = browser.new_context(user_agent=_USER_AGENT)
                page = context.new_page()
                page.goto(
                    self.search_url,
                    wait_until="networkidle",
                    timeout=_NAV_TIMEOUT_MS,
                )

                cards = page.locator(_CARD_SELECTOR)
                total = cards.count()
                logger.info("GlintsSource: located %d card(s) on page", total)

                # Process up to `limit` cards. Each card is parsed in its
                # own try/except so a single malformed entry cannot abort
                # the batch.
                for i in range(min(total, limit)):
                    card = cards.nth(i)
                    try:
                        listing = self._parse_card(card)
                    except Exception as exc:
                        logger.warning("Failed to parse glints card: %s", exc)
                        continue

                    if listing is not None:
                        listings.append(listing)
            finally:
                browser.close()

        logger.info("GlintsSource.fetch returning %d listing(s)", len(listings))
        return listings

    def _parse_card(self, card) -> JobListing | None:
        """Extract a single ``JobListing`` from a Playwright ``Locator``.

        Returns ``None`` only when the URL cannot be resolved (since the
        URL is required by ``JobListing`` validation). Other missing
        optional fields fall back to sensible defaults.
        """
        # Title.
        try:
            title = card.locator(_TITLE_SELECTOR).first.inner_text(timeout=1_000).strip()
        except Exception:
            title = ""

        # Company name.
        try:
            company = card.locator(_COMPANY_SELECTOR).first.inner_text(timeout=1_000).strip()
        except Exception:
            company = ""

        # Location. Glints sometimes leaves this blank for fully-remote
        # roles; default to "Remote" so the listing still passes
        # JobListing's non-empty-location invariant.
        try:
            location = card.locator(_LOCATION_SELECTOR).first.inner_text(timeout=1_000).strip()
        except Exception:
            location = ""
        if not location:
            location = "Remote"

        # Salary is optional.
        salary = None
        try:
            salary_text = card.locator(_SALARY_SELECTOR).first.inner_text(timeout=1_000).strip()
            salary = salary_text or None
        except Exception:
            salary = None

        # URL: relative ``/id/opportunities/jobs/...`` paths are common;
        # resolve them against the search URL so downstream consumers
        # always see an absolute URL (JobListing validation requires
        # http(s)://).
        href = None
        try:
            href = card.locator("a").first.get_attribute("href")
        except Exception:
            href = None
        if not href:
            logger.warning("Glints card had no href; skipping")
            return None
        url = urljoin(self.search_url, href)

        # Native ID: prefer the slug or ID that follows
        # ``/opportunities/jobs/`` in the URL path. Fall back to the full
        # URL so we still derive a stable, deterministic Job_ID even when
        # the marker is absent.
        native_id = self._extract_native_id(url)
        job_id = JobListing.compute_id("glints", native_id)

        return JobListing(
            job_id=job_id,
            title=title,
            company=company,
            location=location,
            salary=salary,
            url=url,
            source="glints",
        )

    @staticmethod
    def _extract_native_id(url: str) -> str:
        """Pull the per-job slug/ID out of a Glints job URL.

        Glints job URLs look like
            https://glints.com/id/opportunities/jobs/<slug-or-id>/details
        We return the segment immediately after ``/opportunities/jobs/``.
        When the marker is absent (defensive fallback for unusual URL
        shapes), the full URL is returned so the resulting Job_ID is still
        stable and deterministic.
        """
        path = urlparse(url).path
        marker_index = path.find(_JOB_PATH_MARKER)
        if marker_index == -1:
            return url
        tail = path[marker_index + len(_JOB_PATH_MARKER):]
        # Take the first path segment; strip trailing slashes and any
        # query/fragment leftovers.
        slug = tail.split("/", 1)[0].strip()
        return slug or url


class GlintsRSSSource(FallbackJobSource):
    """JSON aggregator-API fallback for Glints.

    Glints does not publish a public RSS feed for its job searches, so
    when the primary Playwright-based ``GlintsSource`` fails (anti-bot
    challenge, blocked IP, browser launch error), the aggregator switches
    to a configurable third-party JSON endpoint — typically a RapidAPI
    job-search provider that already indexes Glints listings.

    The class name preserves the ``…RSSSource`` pattern shared with
    ``IndeedRSSSource`` for call-site symmetry; the transport is JSON
    over HTTPS rather than RSS/XML.

    Configuration is intentionally minimal: a single ``feed_url`` and an
    optional ``api_key``. When ``api_key`` is provided it is sent as the
    ``X-RapidAPI-Key`` header, the convention used by the RapidAPI
    marketplace.

    The endpoint's response shape varies by provider; this class accepts
    any of the common shapes:

    - ``[ {...}, {...} ]`` (top-level list of job objects)
    - ``{"jobs": [ ... ]}``
    - ``{"data": [ ... ]}``
    - ``{"data": {"jobs": [ ... ]}}``

    Per-entry parse failures are logged at WARNING and skipped so that a
    single malformed record cannot abort the whole batch (Requirement
    7.2). Non-2xx HTTP responses raise ``httpx.HTTPStatusError`` so the
    aggregator (`fetch_all`) can give up on this source pair and move
    on (Requirements 1.6, 1.7).
    """

    name = "glints-rss"

    def __init__(
        self,
        feed_url: str,
        api_key: str | None = None,
        inter_request_delay_seconds: int = 2,
    ) -> None:
        super().__init__(inter_request_delay_seconds=inter_request_delay_seconds)
        self.feed_url = feed_url
        self.api_key = api_key

    def fetch(self, limit: int) -> List[JobListing]:
        """Return up to ``limit`` listings from the configured aggregator.

        Raises ``httpx.HTTPStatusError`` on non-2xx responses so the
        aggregator can give up on this (primary, fallback) pair and move
        on to the next source.
        """
        logger.info(
            "GlintsRSSSource.fetch starting: url=%s limit=%d",
            self.feed_url,
            limit,
        )

        # Honour the per-source inter-request delay (Requirement 1.5).
        self._throttle()

        headers: dict[str, str] = {"User-Agent": _USER_AGENT}
        if self.api_key:
            # RapidAPI marketplace convention. Providers that don't use
            # RapidAPI typically accept the same header without complaint
            # or simply ignore it; either way it's the right default.
            headers["X-RapidAPI-Key"] = self.api_key

        response = httpx.get(
            self.feed_url,
            timeout=15.0,
            follow_redirects=True,
            headers=headers,
        )
        # Non-2xx -> raise so the aggregator catches it and abandons this
        # (primary, fallback) pair (Requirements 1.6, 1.7).
        response.raise_for_status()

        payload = response.json()
        entries = self._normalize_entries(payload)

        listings: List[JobListing] = []
        for entry in entries[:limit]:
            try:
                listing = self._parse_entry(entry)
            except Exception as exc:
                # Per-entry resilience: one malformed record must not
                # abort the whole batch (Requirement 7.2).
                logger.warning("Failed to parse glints aggregator entry: %s", exc)
                continue
            if listing is not None:
                listings.append(listing)

        logger.info("GlintsRSSSource.fetch returning %d listing(s)", len(listings))
        return listings

    @staticmethod
    def _normalize_entries(payload: Any) -> List[dict]:
        """Reduce an aggregator JSON payload to a flat list of job dicts.

        Accepts the four common shapes documented on the class. Returns
        an empty list for any unrecognised shape so the caller can still
        iterate without special-casing.
        """
        # Top-level list, e.g. ``[ {...}, {...} ]``.
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        if isinstance(payload, dict):
            # ``{"jobs": [...]}``
            jobs = payload.get("jobs")
            if isinstance(jobs, list):
                return [item for item in jobs if isinstance(item, dict)]

            # ``{"data": ...}`` — could be a list, or a dict wrapping
            # a "jobs" list.
            data = payload.get("data")
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
            if isinstance(data, dict):
                inner_jobs = data.get("jobs")
                if isinstance(inner_jobs, list):
                    return [item for item in inner_jobs if isinstance(item, dict)]

        return []

    @staticmethod
    def _parse_entry(entry: dict) -> JobListing | None:
        """Turn a single aggregator job dict into a ``JobListing``.

        Returns ``None`` when the URL is missing, since ``JobListing``
        validation requires a non-empty http(s) URL. Other optional
        fields fall back to sensible defaults so the listing still passes
        validation.
        """
        # URL is mandatory. Without it we can neither apply nor derive a
        # meaningful native_id, so skip the entry early.
        url_raw = entry.get("url") or entry.get("link") or ""
        url = url_raw.strip() if isinstance(url_raw, str) else ""
        if not url:
            logger.warning("Glints aggregator entry had no url/link; skipping")
            return None

        title = (entry.get("title") or entry.get("position") or "").strip()
        company = (entry.get("company") or entry.get("employer") or "Glints").strip() or "Glints"
        location = (entry.get("location") or "Remote").strip() or "Remote"

        salary_raw = entry.get("salary")
        salary = salary_raw.strip() if isinstance(salary_raw, str) and salary_raw.strip() else None

        # Native ID precedence: explicit ``id``/``_id`` fields when
        # present, else the URL itself. Casting to str keeps numeric IDs
        # (common in JSON APIs) compatible with ``compute_id``.
        native_id_raw = entry.get("id") or entry.get("_id") or url
        native_id = str(native_id_raw)
        job_id = JobListing.compute_id("glints", native_id)

        return JobListing(
            job_id=job_id,
            title=title,
            company=company,
            location=location,
            salary=salary,
            url=url,
            source="glints",
        )
