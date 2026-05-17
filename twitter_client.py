"""Twitter/X posting client via Zernio API.

Uses Zernio (https://zernio.com) as a proxy to post tweets and threads
to X/Twitter without needing direct OAuth credentials.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import time
import logging

import httpx

logger = logging.getLogger(__name__)

ZERNIO_BASE_URL = "https://zernio.com/api/v1"


@dataclass
class PostResult:
    success: bool
    tweet_id: Optional[str] = None
    error_code: Optional[int] = None
    error_message: Optional[str] = None


@dataclass
class ThreadResult:
    success: bool
    tweet_ids: List[str] = field(default_factory=list)
    failed_at: Optional[int] = None
    error_code: Optional[int] = None
    error_message: Optional[str] = None


class Poster:
    """Posts tweets via Zernio API."""

    _sleep_func = staticmethod(time.sleep)
    MAX_RETRIES = 3
    BACKOFF_BASE_SECONDS = 2

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._account_id: Optional[str] = None
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _get_account_id(self) -> Optional[str]:
        """Fetch the Twitter account ID from Zernio."""
        if self._account_id:
            return self._account_id

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(
                    f"{ZERNIO_BASE_URL}/accounts",
                    headers=self._headers,
                )
                if resp.status_code != 200:
                    logger.error("Failed to fetch Zernio accounts: %d %s", resp.status_code, resp.text)
                    return None

                data = resp.json()
                logger.info("Zernio accounts response: %s", str(data)[:500])

                # Handle various response shapes
                accounts = []
                if isinstance(data, list):
                    accounts = data
                elif isinstance(data, dict):
                    # Try common wrapper keys
                    for key in ("accounts", "data", "items", "results", "socialAccounts"):
                        if key in data and isinstance(data[key], list):
                            accounts = data[key]
                            break
                    # If dict has platform-like fields, treat it as single account
                    if not accounts and ("platform" in data or "provider" in data):
                        accounts = [data]

                for account in accounts:
                    # Check various platform field names
                    platform = (
                        account.get("platform", "") or
                        account.get("provider", "") or
                        account.get("type", "") or
                        account.get("network", "") or
                        account.get("socialNetwork", "")
                    ).lower()

                    if platform in ("twitter", "x", "twitter/x"):
                        # Try various ID field names
                        acct_id = (
                            account.get("id") or
                            account.get("accountId") or
                            account.get("_id") or
                            account.get("socialAccountId") or
                            account.get("uid")
                        )
                        if acct_id:
                            self._account_id = str(acct_id)
                            logger.info("Found Twitter account ID: %s", self._account_id)
                            return self._account_id

                # If we still haven't found it, try first account regardless of platform
                if accounts:
                    first = accounts[0]
                    acct_id = (
                        first.get("id") or
                        first.get("accountId") or
                        first.get("_id") or
                        first.get("socialAccountId") or
                        first.get("uid")
                    )
                    if acct_id:
                        logger.warning(
                            "No explicit Twitter account found, using first account: %s (platform=%s)",
                            acct_id, first.get("platform", first.get("provider", "unknown"))
                        )
                        self._account_id = str(acct_id)
                        return self._account_id

                logger.error("No usable account found in Zernio response")
                return None
        except Exception as exc:
            logger.error("Error fetching Zernio accounts: %s", exc)
            return None

    def _extract_post_id(self, data: dict) -> str:
        """Extract post ID from Zernio response, trying various field names."""
        for key in ("id", "_id", "postId", "post_id"):
            if key in data and data[key]:
                return str(data[key])
        # Check nested
        if "post" in data and isinstance(data["post"], dict):
            nested = data["post"]
            for key in ("id", "_id", "postId"):
                if key in nested and nested[key]:
                    return str(nested[key])
        return "zernio-post"

    def _post_with_retry(self, client: httpx.Client, payload: dict) -> httpx.Response:
        """POST with automatic retry on 429 (rate limit), but not on daily limit."""
        for attempt in range(self.MAX_RETRIES):
            resp = client.post(
                f"{ZERNIO_BASE_URL}/posts",
                headers=self._headers,
                json=payload,
            )
            if resp.status_code == 429:
                # Check if it's a daily limit (no point retrying)
                try:
                    err_data = resp.json()
                    err_msg = err_data.get("error", "")
                    if "Daily post limit" in err_msg or "daily" in err_msg.lower():
                        logger.error("Daily post limit reached, not retrying: %s", err_msg[:150])
                        return resp
                    wait = err_data.get("details", {}).get("retryAfterSeconds", 5)
                except Exception:
                    wait = 5
                logger.warning("Rate limited (429). Waiting %ds before retry %d/%d", wait, attempt + 1, self.MAX_RETRIES)
                self._sleep_func(wait)
                continue
            return resp
        return resp  # Return last response if all retries exhausted

    def post(self, body: str) -> PostResult:
        """Post a single tweet via Zernio."""
        account_id = self._get_account_id()
        if not account_id:
            return PostResult(success=False, error_code=401, error_message="No Twitter account found in Zernio")

        payload = {
            "content": body,
            "platforms": [{"platform": "twitter", "accountId": account_id}],
            "publishNow": True,
        }

        try:
            with httpx.Client(timeout=30) as client:
                resp = self._post_with_retry(client, payload)

                if resp.status_code in (200, 201):
                    data = resp.json()
                    tweet_id = self._extract_post_id(data)
                    return PostResult(success=True, tweet_id=tweet_id)
                else:
                    return PostResult(
                        success=False,
                        error_code=resp.status_code,
                        error_message=resp.text[:200],
                    )
        except Exception as exc:
            return PostResult(success=False, error_code=500, error_message=str(exc))

    def post_thread(self, tweets: List[str]) -> ThreadResult:
        """Post content via Zernio. Since X Premium supports 25k chars,
        we post as a single long post (first item in the list)."""
        if not tweets:
            return ThreadResult(success=False, error_message="Empty content")

        account_id = self._get_account_id()
        if not account_id:
            return ThreadResult(
                success=False, failed_at=0, error_code=401,
                error_message="No Twitter account found in Zernio",
            )

        # Combine all tweets into one post (for X Premium 25k char limit)
        content = tweets[0] if len(tweets) == 1 else "\n\n".join(tweets)

        payload = {
            "content": content,
            "platforms": [{"platform": "twitter", "accountId": account_id}],
            "publishNow": True,
        }

        try:
            with httpx.Client(timeout=60) as client:
                resp = self._post_with_retry(client, payload)

                if resp.status_code in (200, 201):
                    data = resp.json()
                    logger.info("Zernio post response keys: %s", list(data.keys()) if isinstance(data, dict) else type(data))
                    post_id = self._extract_post_id(data)
                    logger.info("Posted via Zernio: post_id=%s, content_length=%d", post_id, len(content))
                    return ThreadResult(success=True, tweet_ids=[post_id])
                else:
                    logger.error("Zernio post failed: %d %s", resp.status_code, resp.text[:200])
                    return ThreadResult(
                        success=False, failed_at=0,
                        error_code=resp.status_code,
                        error_message=resp.text[:200],
                    )
        except Exception as exc:
            logger.error("Exception posting via Zernio: %s", exc)
            return ThreadResult(success=False, failed_at=0, error_code=500, error_message=str(exc))
