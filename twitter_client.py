"""Twitter/X API v2 client using OAuth 1.0a (User Context) for posting tweets and threads."""

from dataclasses import dataclass, field
from typing import List, Optional
import time
import logging

import tweepy

logger = logging.getLogger(__name__)


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
    """Posts tweets via X API v2 using OAuth 1.0a User Context (tweepy.Client)."""

    _sleep_func = staticmethod(time.sleep)
    MAX_RETRIES_5XX = 3
    BACKOFF_BASE_SECONDS = 2

    def __init__(self, consumer_key: str, consumer_secret: str,
                 access_token: str, access_token_secret: str) -> None:
        if not all([consumer_key, consumer_secret, access_token, access_token_secret]):
            self._client = None
            return

        self._client = tweepy.Client(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
            wait_on_rate_limit=False,
        )

    def post(self, body: str, reply_to: Optional[str] = None) -> PostResult:
        if self._client is None:
            return PostResult(success=False, error_code=401, error_message="Authentication failed")

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
            return PostResult(success=False, error_code=401, error_message="Authentication failed")
        except tweepy.Forbidden as exc:
            return PostResult(success=False, error_code=403, error_message=str(exc))
        except tweepy.BadRequest as exc:
            return PostResult(success=False, error_code=400, error_message=str(exc))
        except tweepy.HTTPException as exc:
            code = exc.response.status_code if hasattr(exc, "response") and exc.response else 500
            return PostResult(success=False, error_code=code, error_message=str(exc))
        except Exception as exc:
            return PostResult(success=False, error_code=500, error_message=str(exc))

    def post_thread(self, tweets: List[str]) -> ThreadResult:
        if not tweets:
            return ThreadResult(success=False, error_message="Empty thread")
        if self._client is None:
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

    def _handle_429(self, exc, body: str, reply_to: Optional[str]) -> PostResult:
        wait = 60
        if hasattr(exc, "response") and exc.response:
            reset = exc.response.headers.get("x-rate-limit-reset")
            if reset:
                try:
                    wait = min(max(0, int(reset) - int(time.time())), 900)
                except (ValueError, TypeError):
                    pass
        logger.warning("Rate limited. Waiting %ds.", wait)
        self._sleep_func(wait)
        return self.post(body, reply_to)

    def _handle_5xx(self, exc, body: str, reply_to: Optional[str]) -> PostResult:
        for attempt in range(self.MAX_RETRIES_5XX):
            wait = self.BACKOFF_BASE_SECONDS * (2 ** attempt)
            logger.warning("5xx. Retry %d/%d after %ds.", attempt + 1, self.MAX_RETRIES_5XX, wait)
            self._sleep_func(wait)
            result = self.post(body, reply_to)
            if result.success or (result.error_code and result.error_code < 500):
                return result
        return PostResult(success=False, error_code=500, error_message="All retries exhausted")
