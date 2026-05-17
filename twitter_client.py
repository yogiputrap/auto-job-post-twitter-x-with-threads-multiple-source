"""Twitter/X API v2 client for posting tweets and threads.

Uses direct HTTP calls to X API v2 (no tweepy dependency for posting).
Supports OAuth 2.0 User Context (access_token from PKCE flow).
"""

from dataclasses import dataclass, field
from typing import List, Optional
import time
import logging

import httpx

logger = logging.getLogger(__name__)

X_API_BASE = "https://api.twitter.com/2"


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
    """Posts tweets via X API v2 using OAuth 2.0 User Access Token."""

    _sleep_func = staticmethod(time.sleep)
    _time_func = staticmethod(time.time)

    MAX_RETRIES_5XX = 3
    BACKOFF_BASE_SECONDS = 2
    DEFAULT_RATE_LIMIT_WAIT = 15 * 60
    MAX_RATE_LIMIT_WAIT = 15 * 60

    def __init__(self, oauth_token: str, client_id: str, client_secret: str) -> None:
        self._oauth_token = oauth_token
        self._client_id = client_id
        self._client_secret = client_secret

        if not oauth_token or not oauth_token.strip():
            self._headers = None
            return

        self._headers = {
            "Authorization": f"Bearer {oauth_token}",
            "Content-Type": "application/json",
        }

    def post(self, body: str, reply_to: Optional[str] = None) -> PostResult:
        if self._headers is None:
            return PostResult(success=False, error_code=401, error_message="Authentication failed")

        payload = {"text": body}
        if reply_to:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to}

        try:
            response = httpx.post(
                f"{X_API_BASE}/tweets",
                json=payload,
                headers=self._headers,
                timeout=30.0,
            )

            if response.status_code == 201:
                data = response.json()
                tweet_id = data.get("data", {}).get("id")
                return PostResult(success=True, tweet_id=tweet_id)
            elif response.status_code == 429:
                return self._handle_429(response, body, reply_to)
            elif response.status_code >= 500:
                return self._handle_5xx(response, body, reply_to)
            else:
                error_data = response.json() if response.text else {}
                error_msg = str(error_data.get("detail", error_data.get("errors", response.text)))
                return PostResult(success=False, error_code=response.status_code, error_message=error_msg)

        except httpx.TimeoutException as e:
            return PostResult(success=False, error_code=408, error_message=f"Timeout: {e}")
        except Exception as e:
            return PostResult(success=False, error_code=500, error_message=str(e))

    def post_thread(self, tweets: List[str]) -> ThreadResult:
        if not tweets:
            return ThreadResult(success=False, error_message="Empty thread")
        if self._headers is None:
            return ThreadResult(success=False, failed_at=0, error_code=401, error_message="Authentication failed")

        tweet_ids: List[str] = []
        reply_to: Optional[str] = None

        for i, body in enumerate(tweets):
            result = self.post(body, reply_to=reply_to)
            if not result.success:
                logger.error("Thread failed at tweet %d/%d: %s", i + 1, len(tweets), result.error_message)
                return ThreadResult(success=False, tweet_ids=tweet_ids, failed_at=i,
                                    error_code=result.error_code, error_message=result.error_message)
            tweet_ids.append(result.tweet_id)
            reply_to = result.tweet_id
            if i < len(tweets) - 1:
                self._sleep_func(1)

        logger.info("Thread posted: %d tweets, IDs=%s", len(tweet_ids), tweet_ids)
        return ThreadResult(success=True, tweet_ids=tweet_ids)

    def _handle_429(self, response, body: str, reply_to: Optional[str]) -> PostResult:
        wait = self.DEFAULT_RATE_LIMIT_WAIT
        reset_header = response.headers.get("x-rate-limit-reset")
        if reset_header:
            try:
                wait = min(max(0, int(reset_header) - int(self._time_func())), self.MAX_RATE_LIMIT_WAIT)
            except (ValueError, TypeError):
                pass
        logger.warning("Rate limited (429). Waiting %ds.", wait)
        self._sleep_func(wait)

        retry = httpx.post(f"{X_API_BASE}/tweets", json={"text": body, **({"reply": {"in_reply_to_tweet_id": reply_to}} if reply_to else {})},
                           headers=self._headers, timeout=30.0)
        if retry.status_code == 201:
            return PostResult(success=True, tweet_id=retry.json().get("data", {}).get("id"))
        return PostResult(success=False, error_code=retry.status_code, error_message=retry.text[:200])

    def _handle_5xx(self, response, body: str, reply_to: Optional[str]) -> PostResult:
        for attempt in range(self.MAX_RETRIES_5XX):
            wait = self.BACKOFF_BASE_SECONDS * (2 ** attempt)
            logger.warning("5xx error. Retry %d/%d after %ds.", attempt + 1, self.MAX_RETRIES_5XX, wait)
            self._sleep_func(wait)
            retry = httpx.post(f"{X_API_BASE}/tweets", json={"text": body, **({"reply": {"in_reply_to_tweet_id": reply_to}} if reply_to else {})},
                               headers=self._headers, timeout=30.0)
            if retry.status_code == 201:
                return PostResult(success=True, tweet_id=retry.json().get("data", {}).get("id"))
            if retry.status_code < 500:
                return PostResult(success=False, error_code=retry.status_code, error_message=retry.text[:200])
        return PostResult(success=False, error_code=response.status_code, error_message="All retries exhausted")
