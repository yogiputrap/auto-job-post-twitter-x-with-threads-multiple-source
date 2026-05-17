"""Indeed scrapers.

This module hosts the Indeed-specific job sources. Per the design, Indeed
is fronted by a primary browser-driven scraper and an RSS-based fallback.

Currently implemented:

- ``IndeedSource``: primary scraper that drives a headless Chromium browser
  via Playwright's synchronous API. The class is intentionally written so
  that ``playwright`` is imported lazily inside ``fetch()``; this lets the
  module be imported (and its tests collected) on environments where
  Playwright's runtime is unavailable.

The corresponding ``IndeedRSSSource`` fallback is added by Task 8.2 to this
same file.
"""

from __future__ import annotations

import logging
from typing import List
from urllib.parse import urljoin

import httpx

from models import JobListing

from .base import FallbackJobSource, JobSource

logger = logging.getLogger(__name__)


# Realistic desktop User-Agent. Indeed's WAF rejects obviously-headless
# clients, so we present a current Chrome on macOS string. Standard
# Playwright launch options are otherwise sufficient — we deliberately do
# not depend on a third-party stealth plugin since it is not in
# requirements.txt.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)

# Indeed renders job cards under a few different markups depending on A/B
# test bucket. Listing both selectors keeps the parser resilient.
_CARD_SELECTOR = 'div.job_seen_beacon, [data-testid="slider_item"]'

# Selectors used per-card. Each is a comma-joined list of fallbacks; the
# first match wins. They are kept here so the parser body stays readable.
_TITLE_SELECTOR = 'h2.jobTitle a span'
_TITLE_LINK_SELECTOR = 'h2.jobTitle a'
_COMPANY_SELECTOR = '[data-testid="company-name"], span.companyName'
_LOCATION_SELECTOR = '[data-testid="text-location"], div.companyLocation'
_SALARY_SELECTOR = '[data-testid="attribute_snippet_testid"]'

# How long to wait for the listing page to settle before we start scraping.
_NAV_TIMEOUT_MS = 30_000


class IndeedSource(JobSource):
    """Primary Indeed scraper backed by Playwright + headless Chromium.

    The class drives a real browser so that JS-rendered cards and Indeed's
    Cloudflare-style challenges are handled transparently. Each per-card
    parse is wrapped in its own try/except so that one malformed card does
    not abort the whole batch (Requirements 1.8, 7.2).
    """

    name = "indeed"

    def __init__(
        self,
        search_url: str,
        inter_request_delay_seconds: int = 2,
    ) -> None:
        super().__init__(inter_request_delay_seconds=inter_request_delay_seconds)
        self.search_url = search_url

    def fetch(self, limit: int) -> List[JobListing]:
        """Return up to ``limit`` Indeed listings.

        Throttles before the network request (Requirement 1.5), launches a
        headless Chromium with a realistic User-Agent, navigates to
        ``self.search_url``, and parses each visible job card. Per-card
        failures are logged at WARNING and skipped; the returned list may
        therefore be shorter than ``limit``.
        """
        logger.info("IndeedSource.fetch starting: url=%s limit=%d", self.search_url, limit)

        # Honour the per-source inter-request delay before issuing the
        # network request (Requirement 1.5, Property 3).
        self._throttle()

        # Lazy import: only require Playwright at the moment we actually
        # need it. Lets `import scraper.indeed` succeed in test/CI
        # environments that do not have the browser binaries installed.
        from playwright.sync_api import sync_playwright  # type: ignore

        listings: List[JobListing] = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                context = browser.new_context(user_agent=_USER_AGENT)
                page = context.new_page()
                page.goto(self.search_url, wait_until="networkidle", timeout=_NAV_TIMEOUT_MS)

                cards = page.locator(_CARD_SELECTOR)
                total = cards.count()
                logger.info("IndeedSource: located %d card(s) on page", total)

                # Process up to `limit` cards. Each card is parsed in its
                # own try/except so a single malformed entry cannot abort
                # the batch.
                for i in range(min(total, limit)):
                    card = cards.nth(i)
                    try:
                        listing = self._parse_card(card)
                    except Exception as exc:
                        logger.warning("Failed to parse indeed card: %s", exc)
                        continue

                    if listing is not None:
                        listings.append(listing)
            finally:
                browser.close()

        logger.info("IndeedSource.fetch returning %d listing(s)", len(listings))
        return listings

    def _parse_card(self, card) -> JobListing | None:
        """Extract a single ``JobListing`` from a Playwright ``Locator``.

        Returns ``None`` only when the URL cannot be resolved (since the
        URL is required by ``JobListing`` validation). Other missing
        optional fields fall back to sensible defaults.
        """
        # Title: prefer the visible inner text of the title span. Indeed
        # also exposes the title as a `title` attribute on the inner
        # `<span>`; we fall back to that when the visible text is empty
        # (e.g. when the span is decorated with screen-reader markup).
        title = ""
        title_locator = card.locator(_TITLE_SELECTOR).first
        try:
            title = title_locator.inner_text(timeout=1_000).strip()
        except Exception:
            title = ""
        if not title:
            try:
                title = (title_locator.get_attribute("title") or "").strip()
            except Exception:
                title = ""

        # Company name.
        try:
            company = card.locator(_COMPANY_SELECTOR).first.inner_text(timeout=1_000).strip()
        except Exception:
            company = ""

        # Location. Indeed sometimes leaves this blank for fully-remote
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

        # URL: relative `/viewjob?jk=...` paths are common; resolve them
        # against the search URL so downstream consumers always see an
        # absolute URL (JobListing validation requires http(s)://).
        href = card.locator(_TITLE_LINK_SELECTOR).first.get_attribute("href")
        if not href:
            logger.warning("Indeed card had no href; skipping")
            return None
        url = urljoin(self.search_url, href)

        # Native ID: prefer Indeed's `data-jk` attribute (the canonical
        # job key). Fall back to the resolved URL so we still derive a
        # stable, deterministic Job_ID even when the attribute is absent.
        native_id = card.get_attribute("data-jk") or url
        job_id = JobListing.compute_id("indeed", native_id)

        return JobListing(
            job_id=job_id,
            title=title,
            company=company,
            location=location,
            salary=salary,
            url=url,
            source="indeed",
        )


class IndeedRSSSource(FallbackJobSource):
    """RSS-backed Indeed fallback source.

    When the primary Playwright-based ``IndeedSource`` fails (Cloudflare
    challenge, blocked IP, browser launch error), the aggregator switches
    to this implementation, which reads Indeed's RSS feed for the same
    query via plain HTTP. RSS feeds are far less likely to be blocked
    than the rendered HTML pages and give us a "good enough" view of the
    most recent listings.

    Indeed's RSS title field is conventionally formatted as
    ``"<Job Title> - <Company> - <Location>"``. We split on " - " and
    use a positional heuristic to extract the three pieces. When the
    title does not match that shape, we fall back to using the entire
    title verbatim with sentinel values for company/location.
    """

    name = "indeed-rss"

    def __init__(
        self,
        rss_url: str,
        inter_request_delay_seconds: int = 2,
    ) -> None:
        super().__init__(inter_request_delay_seconds=inter_request_delay_seconds)
        self.rss_url = rss_url

    def fetch(self, limit: int) -> List[JobListing]:
        """Return up to ``limit`` listings from the Indeed RSS feed.

        Raises ``httpx.HTTPStatusError`` on non-2xx responses so the
        aggregator can give up on this (primary, fallback) pair and move
        on to the next source.
        """
        logger.info(
            "IndeedRSSSource.fetch starting: url=%s limit=%d",
            self.rss_url,
            limit,
        )

        # Honour the per-source inter-request delay (Requirement 1.5).
        self._throttle()

        # Lazy import: keeps `import scraper.indeed` cheap and tolerant of
        # environments that have httpx but not feedparser, mirroring the
        # pattern used for Playwright in IndeedSource.
        import feedparser  # type: ignore

        headers = {"User-Agent": _USER_AGENT}
        response = httpx.get(
            self.rss_url,
            timeout=15.0,
            follow_redirects=True,
            headers=headers,
        )
        # Non-2xx -> raise so the aggregator catches it and abandons this
        # (primary, fallback) pair (Requirements 1.6, 1.7).
        response.raise_for_status()

        feed = feedparser.parse(response.text)

        listings: List[JobListing] = []
        for entry in feed.entries[:limit]:
            try:
                title_raw = entry.get("title", "").strip()
                if not title_raw:
                    # No title means we cannot satisfy JobListing's
                    # non-empty-title invariant; skip the entry.
                    continue

                # Indeed RSS titles are conventionally
                #   "<Job Title> - <Company> - <Location>"
                # Use the last two " - "-separated chunks as company and
                # location respectively; treat everything before them as
                # the title. When the title does not have that shape,
                # fall back to sensible defaults.
                parts = title_raw.split(" - ")
                if len(parts) >= 3:
                    parsed_title = parts[0].strip()
                    company = parts[-2].strip() or "Indeed"
                    location = parts[-1].strip() or "Remote"
                else:
                    parsed_title = title_raw
                    company = "Indeed"
                    location = "Remote"

                url = entry.get("link", "").strip()
                if not url:
                    # JobListing requires a non-empty URL.
                    continue

                native_id = entry.get("id", "") or url
                job_id = JobListing.compute_id("indeed", native_id)

                listings.append(
                    JobListing(
                        job_id=job_id,
                        title=parsed_title,
                        company=company,
                        location=location or "Remote",
                        salary=None,
                        url=url,
                        source="indeed",
                    )
                )
            except Exception as exc:
                # Per-entry resilience: one malformed RSS item must not
                # abort the whole batch (Requirement 7.2).
                logger.warning("Failed to parse indeed RSS entry: %s", exc)
                continue

        logger.info("IndeedRSSSource.fetch returning %d listing(s)", len(listings))
        return listings
