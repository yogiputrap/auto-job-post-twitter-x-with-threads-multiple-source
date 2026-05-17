"""Twitter/X API v2 client for posting tweets and threads via OAuth 2.0 User Context.

Handles rate limiting (429), server errors (5xx with retries), client errors (4xx),
authentication failures, and thread posting (reply chains).
"""

from dataclasses import dataclass, field
from typing import List, Optional
import time
import logging

import tweepy

logger = logging.getLogger(__name__)


@dataclass
class PostResult:
    """Result of a tweet post attempt."""

    success: bool
    tweet_id: Optional[str] = None
    error_code: Optional[int] = None
    error_message: Optional[str] = None


@dataclass
class ThreadResult:
    """Result of posting a thread (multiple tweets as reply chain)."""

    success: bool
    tweet_ids: List[str] = field(default_factory=list)
    failed_at: Optional[int] = None  # index of first failed tweet
    error_code: Optional[int] = None
    error_message: Optional[str] = None


class Poster:
    """Posts tweets via X API v2 using OAuth 2.0 User Context (tweepy.Client).

    Handles:
    - 429 rate limit: sleep per x-rate-limit-reset header (or 15 min default), retry once
    - 5xx server errors: retry up to 3 times with exponential backoff (2s, 4s, 8s)
    - 4xx client errors (!=429): return failure immediately
    - Missing/invalid token: return failure with "Authentication failed"
    """

    # Configurable for testing (inject via constructor or monkey-patch)
    _sleep_func = staticmethod(time.sleep)
    _time_func = staticmethod(time.time)

    MAX_RETRIES_5XX = 3
    BACKOFF_BASE_SECONDS = 2
    DEFAULT_RATE_LIMIT_WAIT = 15 * 60  # 15 minutes
    MAX_RATE_LIMIT_WAIT = 15 * 60  # cap at 15 minutes

    def __init__(self, oauth_token: str, client_id: str, client_secret: str) -> None:
        self._oauth_token = oauth_token
        self._client_id = client_id
        self._client_secret = client_secret

        if not oauth_token or not oauth_token.strip():
            # Store None client so post() can detect and return auth failure
            self._client = None
            return

        # tweepy.Client with OAuth 2.0 User Context for posting
        # Use access_token for user context (can read + write tweets)
        # NOT bearer_token which is app-only (read-only)
        self._client = tweepy.Client(
            access_token=oauth_token,
            wait_on_rate_limit=False,
        )

    def post(self, body: str, reply_to: Optional[str] = None) -> PostResult:
        """Post a tweet, optionally as a reply. Returns PostResult."""
        if self._client is None:
            return PostResult(
                success=False,
                error_code=401,
                error_message="Authentication failed",
            )

        try:
            kwargs = {"text": body}
            if reply_to:
                kwargs["in_reply_to_tweet_id"] = reply_to

            response = self._client.create_tweet(**kwargs)
            tweet_id = str(response.data["id"])
            return PostResult(success=True, tweet_id=tweet_id)
        except tweepy.TooManyRequests as exc:
            return self._handle_429(exc, body, reply_to)
        except tweepy.TwitterServerError as exc:
            return self._handle_5xx(exc, body, reply_to)
        except tweepy.Unauthorized:
            return PostResult(
                success=False,
                error_code=401,
                error_message="Authentication failed",
            )
        except tweepy.Forbidden as exc:
            return PostResult(
                success=False,
                error_code=403,
                error_message=str(exc),
            )
        except tweepy.BadRequest as exc:
            return PostResult(
                success=False,
                error_code=400,
                error_message=str(exc),
            )
        except tweepy.NotFound as exc:
            return PostResult(
                success=False,
                error_code=404,
                error_message=str(exc),
            )
        except tweepy.HTTPException as exc:
            # Catch-all for other HTTP errors from tweepy
            code = (
                exc.response.status_code
                if hasattr(exc, "response") and exc.response
                else 500
            )
            return PostResult(
                success=False,
                error_code=code,
                error_message=str(exc),
            )

    def post_thread(self, tweets: List[str]) -> ThreadResult:
        """Post a thread (list of tweets as a reply chain).
        
        Each tweet after the first is posted as a reply to the previous one.
        If any tweet fails, the thread stops and returns partial results.
        
        Args:
            tweets: List of tweet bodies, each ≤280 chars.
            
        Returns:
            ThreadResult with all posted tweet IDs and failure info if any.
        """
        if not tweets:
            return ThreadResult(success=False, error_message="Empty thread")

        if self._client is None:
            return ThreadResult(
                success=False,
                failed_at=0,
                error_code=401,
                error_message="Authentication failed",
            )

        tweet_ids: List[str] = []
        reply_to: Optional[str] = None

        for i, body in enumerate(tweets):
            result = self.post(body, reply_to=reply_to)

            if not result.success:
                logger.error(
                    "Thread failed at tweet %d/%d: %s",
                    i + 1, len(tweets), result.error_message,
                )
                return ThreadResult(
                    success=False,
                    tweet_ids=tweet_ids,
                    failed_at=i,
                    error_code=result.error_code,
                    error_message=result.error_message,
                )

            tweet_ids.append(result.tweet_id)
            reply_to = result.tweet_id

            # Small delay between thread tweets to avoid rate limits
            if i < len(tweets) - 1:
                self._sleep_func(1)

        logger.info("Thread posted successfully: %d tweets, IDs=%s", len(tweet_ids), tweet_ids)
        return ThreadResult(success=True, tweet_ids=tweet_ids)

    def _handle_429(self, exc: tweepy.TooManyRequests, body: str, reply_to: Optional[str] = None) -> PostResult:
        """Handle rate limit: sleep per reset header, retry once."""
        wait_seconds = self.DEFAULT_RATE_LIMIT_WAIT

        if hasattr(exc, "response") and exc.response is not None:
            reset_header = exc.response.headers.get("x-rate-limit-reset")
            if reset_header:
                try:
                    reset_epoch = int(reset_header)
                    now = int(self._time_func())
                    wait_seconds = max(0, reset_epoch - now)
                    # Cap at 15 minutes
                    wait_seconds = min(wait_seconds, self.MAX_RATE_LIMIT_WAIT)
                except (ValueError, TypeError):
                    wait_seconds = self.DEFAULT_RATE_LIMIT_WAIT

        logger.warning(
            "Rate limited (429). Waiting %d seconds before retry.", wait_seconds
        )
        self._sleep_func(wait_seconds)

        # Retry once
        try:
            kwargs = {"text": body}
            if reply_to:
                kwargs["in_reply_to_tweet_id"] = reply_to
            response = self._client.create_tweet(**kwargs)
            tweet_id = str(response.data["id"])
            return PostResult(success=True, tweet_id=tweet_id)
        except tweepy.HTTPException as retry_exc:
            code = (
                retry_exc.response.status_code
                if hasattr(retry_exc, "response") and retry_exc.response
                else 429
            )
            return PostResult(
                success=False,
                error_code=code,
                error_message=str(retry_exc),
            )

    def _handle_5xx(
        self, exc: tweepy.TwitterServerError, body: str, reply_to: Optional[str] = None
    ) -> PostResult:
        """Handle server errors: retry up to 3 times with exponential backoff."""
        last_exc = exc

        for attempt in range(self.MAX_RETRIES_5XX):
            wait = self.BACKOFF_BASE_SECONDS * (2**attempt)  # 2, 4, 8
            logger.warning(
                "Server error (5xx). Retry %d/%d after %ds.",
                attempt + 1,
                self.MAX_RETRIES_5XX,
                wait,
            )
            self._sleep_func(wait)

            try:
                kwargs = {"text": body}
                if reply_to:
                    kwargs["in_reply_to_tweet_id"] = reply_to
                response = self._client.create_tweet(**kwargs)
                tweet_id = str(response.data["id"])
                return PostResult(success=True, tweet_id=tweet_id)
            except tweepy.TwitterServerError as retry_exc:
                last_exc = retry_exc
                continue
            except tweepy.HTTPException as retry_exc:
                # Non-5xx on retry (e.g. 429 or 4xx) - return failure
                code = (
                    retry_exc.response.status_code
                    if hasattr(retry_exc, "response") and retry_exc.response
                    else 500
                )
                return PostResult(
                    success=False,
                    error_code=code,
                    error_message=str(retry_exc),
                )

        # All retries exhausted
        code = (
            last_exc.response.status_code
            if hasattr(last_exc, "response") and last_exc.response
            else 500
        )
        return PostResult(
            success=False,
            error_code=code,
            error_message=str(last_exc),
        )
