#!/usr/bin/env python3
"""Entry point for the Job Vacancy Twitter Bot.

Scheduling strategy:
- Posts 5 times per day at random times within natural engagement windows (WIB)
- Pagi (07:30-09:00), Siang (12:00-13:00), Sore (16:30-17:30),
  Malam (19:00-21:00), Larut Malam (22:30-23:30)
- Each slot posts 1 thread
- Bot checks every 2 minutes if a slot is due

Usage:
    python main.py              # Run a single post (if slot is due)
    python main.py --scheduled  # Run continuously, checking slots every 2 min
    python main.py --force      # Force post 1 thread immediately (ignore schedule)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from pydantic import ValidationError

from config import AppConfig
from job_manager import JobManager
from job_store import JobStore
from scheduler import get_next_post_slot, get_todays_schedule, mark_slot_posted, get_schedule_summary
from scraper.base import FallbackJobSource, JobSource
from scraper.glints import GlintsRSSSource, GlintsSource
from scraper.indeed import IndeedRSSSource, IndeedSource
from scraper.httpx_scraper import RemotiveSource, JobicySource
from twitter_client import Poster

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 120  # Check every 2 minutes


def _configure_logging() -> None:
    """Set up root logger with structured format."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )


def _build_sources(config: AppConfig) -> list[tuple[JobSource, FallbackJobSource]]:
    """Construct the (primary, fallback) source pairs from config."""
    delay = config.inter_request_delay_seconds

    indeed_primary = IndeedSource(
        search_url=config.indeed_search_url,
        inter_request_delay_seconds=delay,
    )
    indeed_fallback = RemotiveSource(
        category="software-dev",
        inter_request_delay_seconds=delay,
    )

    glints_primary = GlintsSource(
        search_url=config.glints_search_url,
        inter_request_delay_seconds=delay,
    )
    glints_fallback = JobicySource(
        tag="developer",
        inter_request_delay_seconds=delay,
    )

    return [(indeed_primary, indeed_fallback), (glints_primary, glints_fallback)]


def post_one(config: AppConfig) -> int:
    """Post exactly 1 thread. Returns 0 on success, 1 on failure."""
    store = JobStore(config.db_path)
    try:
        sources = _build_sources(config)
        poster = Poster(api_key=config.zernio_api_key.get_secret_value())
        manager = JobManager(
            config=config,
            sources=sources,
            poster=poster,
            store=store,
        )
        summary = manager.run_once(max_posts=1)
        return 0 if summary.posted > 0 else 1
    except Exception as exc:
        logger.critical("Unrecoverable error: %s", exc)
        return 1
    finally:
        store.close()


def run_scheduled(config: AppConfig) -> None:
    """Run continuously, posting at scheduled times."""
    logger.info("Starting scheduled mode (5 posts/day at natural times WIB)")

    # Log today's schedule
    summary = get_schedule_summary()
    logger.info(
        "Today's schedule (%s): %d posted, %d remaining",
        summary["date"], summary["posts_today"], summary["posts_remaining"],
    )
    for slot in summary["slots"]:
        status = "✓" if slot["posted"] else "○"
        logger.info("  %s %s - %s", status, slot["label"], slot["time"])

    while True:
        try:
            slot = get_next_post_slot()
            if slot:
                logger.info("Slot due: %s — posting 1 thread now", slot["time"])
                result = post_one(config)
                if result == 0:
                    mark_slot_posted(slot["time"])
                    logger.info("Slot %s completed successfully", slot["time"])
                else:
                    # Still mark as posted to avoid infinite retry
                    mark_slot_posted(slot["time"])
                    logger.warning("Slot %s: no new listings to post or post failed", slot["time"])
            
            time.sleep(CHECK_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            logger.info("Shutting down scheduler")
            break
        except Exception as exc:
            logger.error("Error in scheduler loop: %s", exc)
            time.sleep(CHECK_INTERVAL_SECONDS)


def main() -> None:
    """Parse CLI args and run."""
    _configure_logging()

    parser = argparse.ArgumentParser(description="Job Vacancy Twitter Bot")
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="Run continuously, posting at 5 scheduled times per day",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force post 1 thread immediately (ignore schedule)",
    )
    args = parser.parse_args()

    try:
        config = AppConfig()
    except ValidationError as exc:
        for error in exc.errors():
            field = error.get("loc", ("unknown",))[0]
            print(
                f"Missing required environment variable: {str(field).upper()}",
                file=sys.stderr,
            )
        sys.exit(2)

    if args.scheduled:
        run_scheduled(config)
    elif args.force:
        exit_code = post_one(config)
        sys.exit(exit_code)
    else:
        # Default: check if slot is due, post if yes
        slot = get_next_post_slot()
        if slot:
            logger.info("Slot due: %s — posting", slot["time"])
            result = post_one(config)
            if result == 0:
                mark_slot_posted(slot["time"])
        else:
            logger.info("No slot due right now. Next check later.")
        sys.exit(0)


if __name__ == "__main__":
    main()
