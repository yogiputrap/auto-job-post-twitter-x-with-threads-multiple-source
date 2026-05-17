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
                accounts = data if isinstance(data, list) else data.get("accounts", data.get("data", []))

                for account in accounts:
                    platform = account.get("platform", "").lower()
                    if platform in ("twitter", "x"):
                        self._account_id = account.get("id") or account.get("accountId")
                        logger.info("Found Twitter account: %s", self._account_id)
                        return self._account_id

                logger.error("No Twitter/X account found in Zernio accounts")
                return None
        except Exception as exc:
            logger.error("Error fetching Zernio accounts: %s", exc)
            return None

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
                resp = client.post(
                    f"{ZERNIO_BASE_URL}/posts",
                    headers=self._headers,
                    json=payload,
                )

                if resp.status_code in (200, 201):
                    data = resp.json()
                    tweet_id = data.get("id") or data.get("postId") or "unknown"
                    return PostResult(success=True, tweet_id=str(tweet_id))
                else:
                    return PostResult(
                        success=False,
                        error_code=resp.status_code,
                        error_message=resp.text[:200],
                    )
        except Exception as exc:
            return PostResult(success=False, error_code=500, error_message=str(exc))

    def post_thread(self, tweets: List[str]) -> ThreadResult:
        """Post a thread via Zernio using platformSpecificData.threadItems."""
        if not tweets:
            return ThreadResult(success=False, error_message="Empty thread")

        account_id = self._get_account_id()
        if not account_id:
            return ThreadResult(
                success=False, failed_at=0, error_code=401,
                error_message="No Twitter account found in Zernio",
            )

        # Build thread items for Zernio
        thread_items = [{"content": tweet} for tweet in tweets]

        payload = {
            "content": tweets[0],
            "platforms": [{"platform": "twitter", "accountId": account_id}],
            "publishNow": True,
            "platformSpecificData": {
                "threadItems": thread_items,
            },
        }

        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(
                    f"{ZERNIO_BASE_URL}/posts",
                    headers=self._headers,
                    json=payload,
                )

                if resp.status_code in (200, 201):
                    data = resp.json()
                    post_id = str(data.get("id") or data.get("postId") or "unknown")
                    tweet_ids = [post_id] + [f"{post_id}-{i}" for i in range(1, len(tweets))]
                    logger.info("Thread posted via Zernio: %d tweets, post_id=%s", len(tweets), post_id)
                    return ThreadResult(success=True, tweet_ids=tweet_ids)
                else:
                    logger.error("Zernio thread post failed: %d %s", resp.status_code, resp.text[:200])
                    return ThreadResult(
                        success=False, failed_at=0,
                        error_code=resp.status_code,
                        error_message=resp.text[:200],
                    )
        except Exception as exc:
            logger.error("Exception posting thread via Zernio: %s", exc)
            return ThreadResult(success=False, failed_at=0, error_code=500, error_message=str(exc))
