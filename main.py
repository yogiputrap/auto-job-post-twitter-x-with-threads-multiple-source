#!/usr/bin/env python3
"""Entry point for the Job Vacancy Twitter Bot.

Usage:
    python main.py              # Run a single cycle and exit
    python main.py --scheduled  # Run on a repeating schedule

Requirements: 5.4, 6.2, 8.2, 8.4
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

import schedule
from pydantic import ValidationError

from config import AppConfig
from job_manager import JobManager
from job_store import JobStore
from scraper.base import FallbackJobSource, JobSource
from scraper.glints import GlintsRSSSource, GlintsSource
from scraper.indeed import IndeedRSSSource, IndeedSource
from scraper.httpx_scraper import RemotiveSource, JobicySource
from twitter_client import Poster

logger = logging.getLogger(__name__)


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

    # Indeed: Playwright primary, Remotive API as reliable fallback
    indeed_primary = IndeedSource(
        search_url=config.indeed_search_url,
        inter_request_delay_seconds=delay,
    )
    indeed_fallback = RemotiveSource(
        category="software-dev",
        inter_request_delay_seconds=delay,
    )

    # Glints: Playwright primary, Jobicy API as reliable fallback
    glints_primary = GlintsSource(
        search_url=config.glints_search_url,
        inter_request_delay_seconds=delay,
    )
    glints_fallback = JobicySource(
        tag="developer",
        inter_request_delay_seconds=delay,
    )

    return [(indeed_primary, indeed_fallback), (glints_primary, glints_fallback)]


def run_once(config: AppConfig) -> int:
    """Execute a single Run_Cycle. Returns exit code (0=success, 1=failure)."""
    store = JobStore(config.db_path)
    try:
        sources = _build_sources(config)
        poster = Poster(
            oauth_token=config.oauth_token.get_secret_value(),
            client_id=config.x_client_id.get_secret_value(),
            client_secret=config.x_client_secret.get_secret_value(),
        )
        manager = JobManager(
            config=config,
            sources=sources,
            poster=poster,
            store=store,
        )
        manager.run_once()
        return 0
    except Exception as exc:
        logger.critical("Unrecoverable error: %s", exc)
        return 1
    finally:
        store.close()


def main() -> None:
    """Parse CLI args and run."""
    _configure_logging()

    parser = argparse.ArgumentParser(description="Job Vacancy Twitter Bot")
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="Run on a repeating schedule instead of a single cycle",
    )
    args = parser.parse_args()

    # Load config; exit 2 on missing env vars (Requirement 6.2)
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
        # Requirement 5.4: scheduled execution via the `schedule` library
        logger.info(
            "Starting scheduled mode: every %d minutes",
            config.run_interval_minutes,
        )
        schedule.every(config.run_interval_minutes).minutes.do(run_once, config)
        # Run immediately on start, then on schedule
        run_once(config)
        while True:
            schedule.run_pending()
            time.sleep(1)
    else:
        # Requirement 8.4: single Run_Cycle, exit 0 on success, non-zero on failure
        exit_code = run_once(config)
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
