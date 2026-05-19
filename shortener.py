"""URL shortener using Spoo.me public API.

Spoo.me is a free, no-auth-required URL shortener.
Docs: https://spoo.me
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

SPOO_API_URL = "https://spoo.me/"


def shorten_url(url: str, timeout: float = 10.0) -> str:
    """Shorten a URL using Spoo.me. Returns shortened URL without http(s):// prefix.
    
    Removing the protocol prevents X/Twitter from detecting it as a clickable link
    (which would trigger the $0.20/link API fee on premium accounts).
    """
    if not url or not url.startswith(("http://", "https://")):
        return url

    try:
        response = httpx.post(
            SPOO_API_URL,
            data={"url": url},
            headers={
                "Accept": "application/json",
                "User-Agent": "JobBot/1.0",
            },
            timeout=timeout,
            follow_redirects=False,
        )

        if response.status_code in (200, 201):
            data = response.json()
            short_url = data.get("short_url") or data.get("shortUrl")
            if short_url:
                # Strip protocol so X/Twitter does not auto-link it
                bare = short_url.replace("https://", "").replace("http://", "")
                logger.info("Shortened %s -> %s", url[:60], bare)
                return bare
            logger.warning("Spoo.me returned 200 but no short_url field: %s", data)
        else:
            logger.warning("Spoo.me returned %d: %s", response.status_code, response.text[:200])
    except Exception as exc:
        logger.warning("URL shortener failed for %s: %s", url[:60], exc)

    # Fallback: strip protocol from original URL
    return url.replace("https://", "").replace("http://", "")
