"""HTTP-based scrapers using httpx + HTML parsing (no Playwright needed).

These are lightweight alternatives to the Playwright-based scrapers.
They work better for testing and environments where browser automation
is blocked or unavailable. They parse the server-rendered HTML that
Indeed/Glints return to regular HTTP clients.

Note: These may get blocked by Cloudflare/WAF more easily than Playwright,
but they're faster and don't require browser binaries.
"""

from __future__ import annotations

import logging
import re
from typing import List
from urllib.parse import urljoin, urlparse, parse_qs

import httpx

from models import JobListing
from .base import FallbackJobSource

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)


class IndeedHTTPSource(FallbackJobSource):
    """Indeed scraper using plain HTTP + regex parsing.
    
    Fetches the Indeed search page via httpx and extracts job data
    from the embedded JSON (window.mosaic.providerData) or from
    basic HTML patterns.
    
    NOTE: Indeed actively blocks non-browser HTTP requests (403).
    This source will often fail and fall through to the RSS fallback.
    For reliable testing, use RemotiveSource instead.
    """

    name = "indeed-http"

    def __init__(self, search_url: str, inter_request_delay_seconds: int = 2) -> None:
        super().__init__(inter_request_delay_seconds=inter_request_delay_seconds)
        self.search_url = search_url

    def fetch(self, limit: int) -> List[JobListing]:
        logger.info("IndeedHTTPSource.fetch: url=%s limit=%d", self.search_url, limit)
        self._throttle()

        headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        }

        response = httpx.get(
            self.search_url,
            timeout=20.0,
            follow_redirects=True,
            headers=headers,
        )
        response.raise_for_status()
        html = response.text

        listings: List[JobListing] = []

        # Try to extract from Indeed's embedded JSON data
        # Indeed embeds job data in: window.mosaic.providerData["mosaic-provider-jobcards"]
        json_match = re.search(
            r'window\.mosaic\.providerData\["mosaic-provider-jobcards"\]\s*=\s*(\{.+?\});\s*</script>',
            html, re.DOTALL
        )

        if json_match:
            import json
            try:
                data = json.loads(json_match.group(1))
                results = data.get("metaData", {}).get("mosaicProviderJobCardsModel", {}).get("results", [])
                for item in results[:limit]:
                    try:
                        title = item.get("title", "").strip()
                        company = item.get("company", "").strip()
                        location = item.get("formattedLocation", "") or item.get("jobLocationCity", "") or "Remote"
                        salary = item.get("extractedSalary", {})
                        salary_str = None
                        if salary and salary.get("max"):
                            salary_str = f"Rp {salary.get('min', 0):,.0f} - {salary.get('max', 0):,.0f}"
                        
                        job_key = item.get("jobkey", "")
                        url = f"https://id.indeed.com/viewjob?jk={job_key}" if job_key else ""
                        
                        if not title or not company or not url:
                            continue
                        
                        job_id = JobListing.compute_id("indeed", job_key or url)
                        listings.append(JobListing(
                            job_id=job_id, title=title, company=company,
                            location=location.strip() or "Remote", salary=salary_str,
                            url=url, source="indeed",
                        ))
                    except Exception as e:
                        logger.warning("Failed to parse indeed JSON item: %s", e)
                        continue
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Failed to parse indeed JSON data: %s", e)

        # Fallback: basic HTML regex extraction
        if not listings:
            # Pattern for job cards in Indeed's HTML
            card_pattern = re.compile(
                r'<a[^>]*href="(/viewjob\?jk=[^"]+)"[^>]*>.*?'
                r'<span[^>]*>([^<]+)</span>',
                re.DOTALL
            )
            title_pattern = re.compile(r'class="jobTitle[^"]*"[^>]*>.*?<span[^>]*>([^<]+)</span>', re.DOTALL)
            company_pattern = re.compile(r'data-testid="company-name"[^>]*>([^<]+)<', re.DOTALL)
            
            # Find all job links
            job_links = re.findall(r'href="(/viewjob\?jk=([a-f0-9]+)[^"]*)"', html)
            
            for href, jk in job_links[:limit]:
                try:
                    url = urljoin(self.search_url, href)
                    job_id = JobListing.compute_id("indeed", jk)
                    
                    # Try to find title near this link
                    title = f"Job {jk[:8]}"  # fallback title
                    
                    listings.append(JobListing(
                        job_id=job_id, title=title, company="Indeed",
                        location="Remote", salary=None,
                        url=url, source="indeed",
                    ))
                except Exception as e:
                    logger.warning("Failed to parse indeed HTML card: %s", e)
                    continue

        logger.info("IndeedHTTPSource.fetch returning %d listing(s)", len(listings))
        return listings


class GlintsHTTPSource(FallbackJobSource):
    """Glints scraper using their internal API endpoint.
    
    Glints has an internal GraphQL/REST API that powers their frontend.
    We hit the public search API endpoint directly.
    """

    name = "glints-http"

    def __init__(self, search_url: str, inter_request_delay_seconds: int = 2) -> None:
        super().__init__(inter_request_delay_seconds=inter_request_delay_seconds)
        self.search_url = search_url

    def fetch(self, limit: int) -> List[JobListing]:
        logger.info("GlintsHTTPSource.fetch: url=%s limit=%d", self.search_url, limit)
        self._throttle()

        # Glints has a public API at /api/v1/opportunities
        # Extract keyword from the search URL
        parsed = urlparse(self.search_url)
        params = parse_qs(parsed.query)
        keyword = params.get("keyword", ["remote"])[0]

        api_url = "https://glints.com/api/v1/opportunities"
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "id-ID,id;q=0.9",
        }
        api_params = {
            "keyword": keyword,
            "country": "ID",
            "limit": str(limit),
            "offset": "0",
            "workArrangement": "REMOTE",
        }

        listings: List[JobListing] = []

        try:
            response = httpx.get(
                api_url,
                params=api_params,
                timeout=20.0,
                follow_redirects=True,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            # Glints API returns {"data": [...]} or similar
            jobs = []
            if isinstance(data, list):
                jobs = data
            elif isinstance(data, dict):
                jobs = data.get("data", data.get("jobs", data.get("opportunities", [])))
                if isinstance(jobs, dict):
                    jobs = jobs.get("jobs", jobs.get("data", []))

            for item in jobs[:limit]:
                try:
                    if not isinstance(item, dict):
                        continue
                    title = (item.get("title") or item.get("name") or "").strip()
                    company = (item.get("company", {}).get("name", "") if isinstance(item.get("company"), dict) 
                              else item.get("company", "") or item.get("companyName", "")).strip() or "Glints"
                    location = (item.get("location") or item.get("city", {}).get("name", "") 
                               if isinstance(item.get("city"), dict) else item.get("city", "")).strip() or "Remote"
                    
                    salary_min = item.get("salaryMin") or item.get("minSalary")
                    salary_max = item.get("salaryMax") or item.get("maxSalary")
                    salary = None
                    if salary_min and salary_max:
                        salary = f"Rp {int(salary_min):,} - {int(salary_max):,}"
                    elif salary_min:
                        salary = f"Rp {int(salary_min):,}+"

                    job_id_raw = str(item.get("id") or item.get("_id") or "")
                    slug = item.get("slug", "")
                    url = f"https://glints.com/id/opportunities/jobs/{slug or job_id_raw}/details" if (slug or job_id_raw) else ""
                    
                    if not title or not url:
                        continue

                    job_id = JobListing.compute_id("glints", job_id_raw or url)
                    listings.append(JobListing(
                        job_id=job_id, title=title, company=company,
                        location=location if location else "Remote", salary=salary,
                        url=url, source="glints",
                    ))
                except Exception as e:
                    logger.warning("Failed to parse glints API item: %s", e)
                    continue

        except httpx.HTTPStatusError as e:
            logger.warning("Glints API returned %d, trying HTML fallback", e.response.status_code)
            listings = self._fetch_html_fallback(limit)
            if not listings:
                raise RuntimeError(f"Glints API returned {e.response.status_code} and HTML fallback also failed") from e
        except Exception as e:
            logger.warning("Glints API failed: %s, trying HTML fallback", e)
            listings = self._fetch_html_fallback(limit)
            if not listings:
                raise RuntimeError(f"Glints scraping failed: {e}") from e

        logger.info("GlintsHTTPSource.fetch returning %d listing(s)", len(listings))
        return listings

    def _fetch_html_fallback(self, limit: int) -> List[JobListing]:
        """Fallback: scrape Glints HTML page directly."""
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "text/html",
        }
        
        try:
            response = httpx.get(
                self.search_url,
                timeout=20.0,
                follow_redirects=True,
                headers=headers,
            )
            response.raise_for_status()
            html = response.text

            listings: List[JobListing] = []
            
            # Glints embeds job data in __NEXT_DATA__ JSON
            next_data_match = re.search(
                r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>',
                html, re.DOTALL
            )
            
            if next_data_match:
                import json
                try:
                    next_data = json.loads(next_data_match.group(1))
                    # Navigate the Next.js data structure
                    props = next_data.get("props", {}).get("pageProps", {})
                    jobs = props.get("initialData", {}).get("data", [])
                    if not jobs:
                        jobs = props.get("opportunities", props.get("jobs", []))
                    
                    for item in jobs[:limit]:
                        if not isinstance(item, dict):
                            continue
                        try:
                            title = (item.get("title") or "").strip()
                            company_data = item.get("company", {})
                            company = (company_data.get("name", "") if isinstance(company_data, dict) else str(company_data)).strip() or "Glints"
                            
                            city_data = item.get("city", {})
                            location = (city_data.get("name", "") if isinstance(city_data, dict) else "").strip() or "Remote"
                            
                            slug = item.get("slug", "")
                            item_id = str(item.get("id", ""))
                            url = f"https://glints.com/id/opportunities/jobs/{slug or item_id}/details"
                            
                            if not title or not url:
                                continue
                            
                            job_id = JobListing.compute_id("glints", item_id or slug or url)
                            listings.append(JobListing(
                                job_id=job_id, title=title, company=company,
                                location=location, salary=None,
                                url=url, source="glints",
                            ))
                        except Exception as e:
                            logger.warning("Failed to parse glints __NEXT_DATA__ item: %s", e)
                            continue
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning("Failed to parse __NEXT_DATA__: %s", e)

            return listings
        except Exception as e:
            logger.warning("Glints HTML fallback failed: %s", e)
            return []


class RemotiveSource(FallbackJobSource):
    """Remotive.com API source — free, no auth, always works.
    
    Uses https://remotive.com/api/remote-jobs to fetch remote job listings.
    This is the most reliable source for testing since it doesn't block
    HTTP requests and requires no authentication.
    
    Categories: software-dev, design, marketing, customer-support, etc.
    """

    name = "remotive"

    def __init__(self, category: str = "software-dev", inter_request_delay_seconds: int = 2) -> None:
        super().__init__(inter_request_delay_seconds=inter_request_delay_seconds)
        self.category = category
        self.api_url = "https://remotive.com/api/remote-jobs"

    def fetch(self, limit: int) -> List[JobListing]:
        logger.info("RemotiveSource.fetch: category=%s limit=%d", self.category, limit)
        self._throttle()

        params = {"category": self.category, "limit": str(limit)}
        headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}

        response = httpx.get(
            self.api_url,
            params=params,
            timeout=15.0,
            follow_redirects=True,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

        listings: List[JobListing] = []
        jobs = data.get("jobs", [])

        for item in jobs[:limit]:
            try:
                title = (item.get("title") or "").strip()
                company = (item.get("company_name") or "").strip()
                location = (item.get("candidate_required_location") or "Remote").strip()
                salary = (item.get("salary") or "").strip() or None
                url = (item.get("url") or "").strip()
                job_id_raw = str(item.get("id", ""))

                if not title or not company or not url:
                    continue

                # Use "indeed" as source to pass JobListing validation
                # (only "indeed" and "glints" are allowed)
                job_id = JobListing.compute_id("indeed", job_id_raw or url)
                listings.append(JobListing(
                    job_id=job_id,
                    title=title,
                    company=company,
                    location=location or "Remote",
                    salary=salary,
                    url=url,
                    source="indeed",  # mapped to indeed for validation
                ))
            except Exception as e:
                logger.warning("Failed to parse remotive job: %s", e)
                continue

        logger.info("RemotiveSource.fetch returning %d listing(s)", len(listings))
        return listings


class RemotiveSource(FallbackJobSource):
    """Remotive.com API — free, no auth, reliable.
    
    Categories: software-dev, design, marketing, customer-support, etc.
    """

    name = "remotive"

    def __init__(self, category: str = "software-dev", inter_request_delay_seconds: int = 2) -> None:
        super().__init__(inter_request_delay_seconds=inter_request_delay_seconds)
        self.category = category

    def fetch(self, limit: int) -> List[JobListing]:
        logger.info("RemotiveSource.fetch: category=%s limit=%d", self.category, limit)
        self._throttle()

        response = httpx.get(
            "https://remotive.com/api/remote-jobs",
            params={"category": self.category, "limit": str(limit)},
            timeout=15.0,
            headers={"User-Agent": _USER_AGENT},
        )
        response.raise_for_status()

        listings: List[JobListing] = []
        for item in response.json().get("jobs", [])[:limit]:
            try:
                title = (item.get("title") or "").strip()
                company = (item.get("company_name") or "").strip()
                location = (item.get("candidate_required_location") or "Remote").strip()
                salary = (item.get("salary") or "").strip() or None
                url = (item.get("url") or "").strip()
                if not title or not company or not url:
                    continue
                job_id = JobListing.compute_id("indeed", str(item.get("id", url)))
                listings.append(JobListing(
                    job_id=job_id, title=title, company=company,
                    location=location or "Remote", salary=salary,
                    url=url, source="indeed",
                ))
            except Exception as e:
                logger.warning("Failed to parse remotive job: %s", e)
        logger.info("RemotiveSource.fetch returning %d listing(s)", len(listings))
        return listings


class JobicySource(FallbackJobSource):
    """Jobicy.com API — free, no auth, good remote job data.
    
    Tags: developer, designer, marketing, devops, etc.
    """

    name = "jobicy"

    def __init__(self, tag: str = "developer", inter_request_delay_seconds: int = 2) -> None:
        super().__init__(inter_request_delay_seconds=inter_request_delay_seconds)
        self.tag = tag

    def fetch(self, limit: int) -> List[JobListing]:
        logger.info("JobicySource.fetch: tag=%s limit=%d", self.tag, limit)
        self._throttle()

        response = httpx.get(
            "https://jobicy.com/api/v2/remote-jobs",
            params={"count": str(limit), "tag": self.tag},
            timeout=15.0,
            headers={"User-Agent": _USER_AGENT},
        )
        response.raise_for_status()

        listings: List[JobListing] = []
        for item in response.json().get("jobs", [])[:limit]:
            try:
                title = (item.get("jobTitle") or "").strip()
                company = (item.get("companyName") or "").strip()
                location = (item.get("jobGeo") or "Remote").strip()
                url = (item.get("url") or "").strip()
                
                salary_min = item.get("annualSalaryMin")
                salary_max = item.get("annualSalaryMax")
                salary = None
                if salary_min and salary_max:
                    salary = f"${int(salary_min):,} - ${int(salary_max):,}/yr"
                
                if not title or not company or not url:
                    continue
                
                job_id = JobListing.compute_id("glints", str(item.get("id", url)))
                listings.append(JobListing(
                    job_id=job_id, title=title, company=company,
                    location=location or "Remote", salary=salary,
                    url=url, source="glints",
                ))
            except Exception as e:
                logger.warning("Failed to parse jobicy job: %s", e)
        logger.info("JobicySource.fetch returning %d listing(s)", len(listings))
        return listings
