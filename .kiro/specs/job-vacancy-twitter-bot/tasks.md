# Implementation Plan: Job Vacancy Twitter Bot

## Overview

Convert the feature design into a series of prompts for a code-generation LLM that will implement each step with incremental progress. Make sure that each prompt builds on the previous prompts, and ends with wiring things together. There should be no hanging or orphaned code that isn't integrated into a previous step. Focus ONLY on tasks that involve writing, modifying, or testing code.

The implementation proceeds bottom-up: foundational primitives (config, models, store) are built first with their property tests, then composable components (formatter, scraper, twitter_client) layer on top, and finally the `Job_Manager` orchestrator wires everything into `main.py`.

## Tasks

- [x] 1. Set up project scaffolding and dependencies
  - Create `requirements.txt` with pinned versions: `tweepy==4.14.0`, `playwright==1.48.0`, `httpx==0.27.2`, `pydantic-settings==2.6.1`, `feedparser==6.0.11`, `schedule==1.2.2`, `pytest==7.4.4`, `hypothesis==6.115.5`, `respx==0.21.1`, `pytest-mock==3.14.0`, `freezegun==1.5.1`, `pytest-cov==5.0.0`
  - Create directory structure: `scraper/`, `tests/unit/`, `tests/property/`, `tests/fixtures/`, `.github/workflows/`
  - Add empty `__init__.py` files for `scraper/`, `tests/`, `tests/unit/`, `tests/property/`
  - Create `pytest.ini` configuring test paths and `hypothesis` profile (max_examples=100)
  - _Requirements: 8.1_

- [x] 2. Implement configuration module
  - [x] 2.1 Implement `config.py` with `AppConfig` using `pydantic-settings`
    - Define `BaseSettings` subclass with `oauth_token`, `x_client_id`, `x_client_secret` as `SecretStr`
    - Define `indeed_search_url`, `glints_search_url`, `run_interval_minutes`, `db_path`, `listings_per_source`, `inter_post_delay_seconds`, `inter_request_delay_seconds`
    - Read from environment variables with `model_config = SettingsConfigDict(env_file=".env")`
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]* 2.2 Write property test for config validation
    - **Property 19: Config validation**
    - Use `hypothesis` to generate environment variable subsets that omit at least one required variable
    - Assert `AppConfig()` raises validation error mentioning the missing variable name
    - **Validates: Requirements 6.1, 6.2**

  - [ ]* 2.3 Write unit tests for config edge cases
    - Test default values for optional fields
    - Test that `SecretStr` repr does not echo credential values
    - _Requirements: 6.3_

- [ ] 3. Implement data models
  - [x] 3.1 Create `models.py` with `JobListing` frozen dataclass
    - Fields: `job_id` (str), `title` (str), `company` (str), `location` (str), `salary` (Optional[str]), `url` (str), `source` (str)
    - Add `__post_init__` validation: non-empty title/company/url, source in `{"indeed", "glints"}`
    - Add `JobListing.compute_id(source: str, native_id: str) -> str` classmethod returning `sha256(source + ":" + native_id).hexdigest()[:16]`
    - _Requirements: 1.3_

  - [ ]* 3.2 Write unit tests for JobListing validation
    - Test invalid inputs raise ValueError
    - Test `compute_id` produces stable 16-char hex output
    - _Requirements: 1.3_

- [ ] 4. Implement Job_Store with SQLite
  - [x] 4.1 Create `job_store.py` with `JobStore` class
    - Implement `__init__(db_path)` that opens connection and creates `posted_jobs` table per design schema
    - Implement `contains(job_id) -> bool`, `save(job_id, tweet_id, posted_at)`, `all_ids() -> set[str]`
    - Use parameterized SQL queries; ensure connection is reusable across calls
    - _Requirements: 2.1, 2.4_

  - [ ]* 4.2 Write property test for Job_Store round-trip persistence
    - **Property 5: Job_Store round-trip persistence**
    - Generate sets of `(job_id, tweet_id, posted_at)` tuples, save each, close store, reopen at same path, assert `all_ids()` equals input set
    - **Validates: Requirements 2.4**

  - [ ]* 4.3 Write unit tests for Job_Store edge cases
    - Test idempotent save (saving same job_id twice does not raise)
    - Test fresh DB file creation when path does not exist
    - _Requirements: 2.1, 2.4_

- [ ] 5. Implement Formatter
  - [x] 5.1 Create `formatter.py` with `format_tweet(listing) -> str`
    - Build base body: `"{title} at {company}\n📍 {location}\n💰 {salary}\nApply here: {url}\n#RemoteJobs #WFH #Freelance #LokerRemote"` (omit salary line when None)
    - When length > 280, drop salary line first (if present); if still > 280, truncate `title` with trailing `…` until total ≤ 280
    - Never modify URL or hashtags
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 5.2 Write property test for tweet length bound
    - **Property 8: Tweet length bound**
    - Generate `JobListing` with title/company up to 500 chars, location up to 100 chars, valid URL, optional salary
    - Assert `len(format_tweet(listing)) <= 280`
    - **Validates: Requirements 3.1**

  - [ ]* 5.3 Write property test for tweet content completeness
    - **Property 9: Tweet content completeness**
    - Generate listings, assert formatted output contains company, location, exact URL, and all four hashtags
    - When salary present and inclusion does not violate 280 limit, assert salary substring is present
    - **Validates: Requirements 3.2, 3.3, 3.5**

  - [ ]* 5.4 Write property test for truncation correctness
    - **Property 10: Truncation correctness**
    - Generate listings whose untruncated form exceeds 280
    - Assert URL, company, location, and hashtags appear unmodified, and the title in output ends with `…`
    - **Validates: Requirements 3.4**

  - [ ]* 5.5 Write property test for single URL in tweet
    - **Property 11: Single URL in tweet**
    - Generate listings whose title/company/location do not contain `listing.url`
    - Assert exactly one occurrence of `listing.url` in output
    - **Validates: Requirements 3.6**

  - [ ]* 5.6 Write unit tests for specific tweet examples
    - Test concrete English and Indonesian title examples
    - Test emoji handling in titles
    - _Requirements: 3.1, 3.2_

- [x] 6. Checkpoint - Verify foundation layer
  - Ensure all tests pass for config, models, job_store, and formatter, ask the user if questions arise.

- [ ] 7. Implement Scraper base and source abstractions
  - [x] 7.1 Create `scraper/base.py` with `JobSource` ABC and `FallbackJobSource` marker
    - Define `name: str` class attribute
    - Define abstract `fetch(self, limit: int) -> list[JobListing]`
    - Add `_throttle()` helper enforcing `inter_request_delay_seconds` between calls
    - _Requirements: 1.5_

  - [x] 7.2 Create `scraper/__init__.py` with `fetch_all` aggregator
    - Accept list of `(primary, fallback)` tuples and `limit_per_source`
    - For each tuple, try primary; on exception, log warning and try fallback; on both failures, log error and continue
    - Filter listings missing required fields per `JobListing` validation
    - Filter listings raising parsing exceptions (caught per-element by sources)
    - _Requirements: 1.6, 1.7, 1.8, 7.1, 7.2_

  - [ ]* 7.3 Write property test for scraper count bound
    - **Property 2: Scraper count bound**
    - Mock primary sources returning known counts; assert `fetch_all` returns at most `limit_per_source` per source
    - **Validates: Requirements 1.4**

  - [ ]* 7.4 Write property test for inter-request delay
    - **Property 3: Inter-request delay**
    - Use `freezegun` to control time; mock HTTP layer; invoke consecutive `fetch` calls; assert at least 2s between requests
    - **Validates: Requirements 1.5**

  - [ ]* 7.5 Write property test for source resilience
    - **Property 4: Source resilience via fallback**
    - Generate combinations of (primary success/fail, fallback success/fail) per source
    - Assert listings from working tier are returned; assert other source still produces output when one source pair fails completely
    - **Validates: Requirements 1.6, 1.7, 7.1**

  - [ ]* 7.6 Write property test for output structural completeness
    - **Property 1: Scraper output structural completeness**
    - Inject raw payloads with malformed entries; assert all returned listings have non-empty title/company, valid URL, and 16-char hex job_id
    - **Validates: Requirements 1.3, 1.8, 7.2**

- [ ] 8. Implement Indeed scraper
  - [x] 8.1 Create `scraper/indeed.py` with `IndeedSource` (primary)
    - Use `playwright.sync_api` with stealth plugin; navigate to configured search URL
    - Parse job cards via DOM selectors; extract title, company, location, salary, URL, native ID
    - Wrap each per-element parse in try/except; log warnings and skip on per-element failure
    - Apply `_throttle()` before each network request
    - _Requirements: 1.1, 1.3, 1.5, 7.2_

  - [x] 8.2 Create `IndeedRSSSource` (fallback) in same file
    - Use `httpx` + `feedparser` to read Indeed RSS feed for the same query
    - Map RSS entries to `JobListing` (location defaults to "Remote" when absent)
    - _Requirements: 1.1, 1.6_

  - [ ]* 8.3 Write unit tests with fixture HTML
    - Place real Indeed HTML snapshot in `tests/fixtures/indeed_sample.html`
    - Test parser produces expected listings from fixture
    - Test parser skips malformed cards
    - _Requirements: 1.1, 1.3, 7.2_

- [ ] 9. Implement Glints scraper
  - [x] 9.1 Create `scraper/glints.py` with `GlintsSource` (primary)
    - Use `playwright` with stealth; navigate to configured Glints URL
    - Parse Glints job cards; extract required fields plus salary
    - Wrap per-element parse in try/except
    - Apply `_throttle()`
    - _Requirements: 1.2, 1.3, 1.5, 7.2_

  - [x] 9.2 Create `GlintsRSSSource` or aggregator-API fallback in same file
    - If Glints lacks RSS, use a configured RapidAPI job aggregator endpoint; otherwise feedparser
    - Map results to `JobListing`
    - _Requirements: 1.2, 1.6_

  - [ ]* 9.3 Write unit tests with fixture HTML
    - Place fixture in `tests/fixtures/glints_sample.html`
    - Test parser correctness and malformed-card handling
    - _Requirements: 1.2, 1.3, 7.2_

- [x] 10. Checkpoint - Verify scraper layer
  - Ensure all tests pass for scraper base and both source modules, ask the user if questions arise.

- [ ] 11. Implement Twitter client (Poster)
  - [x] 11.1 Create `twitter_client.py` with `PostResult` dataclass and `Poster` class
    - Implement `__init__` storing OAuth token and creating `tweepy.Client` configured for OAuth 2.0 User Context
    - Implement `post(body) -> PostResult` calling `client.create_tweet(text=body)`
    - Map 201 response to `PostResult(success=True, tweet_id=...)`
    - _Requirements: 4.1, 4.2, 4.3, 4.7_

  - [x] 11.2 Implement retry and rate-limit handling
    - On HTTP 429: read `x-rate-limit-reset` (default 15 min), sleep, retry once
    - On HTTP 5xx: retry up to 3 times with backoff 2s, 4s, 8s
    - On HTTP 4xx ≠ 429: return failure immediately with status code and message
    - On invalid/missing token: return failure with "Authentication failed" message
    - _Requirements: 4.4, 4.5, 4.6, 4.7_

  - [ ]* 11.3 Write property test for successful post
    - **Property 12: Successful post returns tweet ID**
    - Use `respx` to mock 201 responses with arbitrary tweet IDs; generate bodies of length 1-280
    - Assert `success=True` and matching tweet_id; assert exactly one HTTP request
    - **Validates: Requirements 4.2, 4.3**

  - [ ]* 11.4 Write property test for 429 retry behavior
    - **Property 13: 429 retry behavior**
    - Use `respx` to return 429 then 201/429 sequence; use `freezegun` to verify sleep duration matches header
    - Assert exactly one retry; verify final result correctness
    - **Validates: Requirements 4.4**

  - [ ]* 11.5 Write property test for 5xx retry behavior
    - **Property 14: 5xx retry behavior**
    - Generate sequences of `k` 5xx responses (0 ≤ k ≤ 4) followed by 201 or persistent failure
    - Assert at most 4 attempts and correct success/failure outcome; verify 2s/4s/8s backoff via mock clock
    - **Validates: Requirements 4.5**

  - [ ]* 11.6 Write property test for 4xx no retry
    - **Property 15: 4xx no retry**
    - Generate responses with status in `{400, 401, 403, 404, 422}`
    - Assert exactly one HTTP request and failure result with matching status
    - **Validates: Requirements 4.6, 4.7**

- [ ] 12. Implement Job_Manager orchestrator
  - [x] 12.1 Create `job_manager.py` with `CycleSummary` dataclass and `JobManager` class
    - `__init__(config, scraper, formatter, poster, store, logger)` stores dependencies
    - Implement `run_once() -> CycleSummary` executing the pipeline: fetch → dedup → format → post → persist
    - Apply `inter_post_delay_seconds` between consecutive posts
    - Catch exceptions per-listing so one failure does not abort the cycle
    - Wrap entire method in try/except to ensure summary invariant `fetched == skipped + posted + failed` holds
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 5.1, 5.2, 5.3, 7.5_

  - [x] 12.2 Implement structured logging with credential redaction
    - Configure logger with redaction filter that scrubs known credential values from any log record
    - Emit INFO log on successful post containing job_id and tweet_id
    - Emit ERROR log on failed post containing job_id
    - Emit summary INFO log at end of cycle
    - _Requirements: 6.3, 7.3, 7.4, 7.5_

  - [ ]* 12.3 Write property test for duplicate suppression
    - **Property 6: Duplicate suppression**
    - Pre-populate store with subset of job_ids; mock formatter and poster; run cycle
    - Assert formatter and poster not called for pre-existing IDs
    - **Validates: Requirements 2.2, 2.3**

  - [ ]* 12.4 Write property test for persistence iff post succeeds
    - **Property 7: Persistence iff post succeeds**
    - Generate listings with random per-listing post outcomes; run cycle
    - Assert store contains exactly the job_ids of successful posts
    - **Validates: Requirements 2.1, 2.5**

  - [ ]* 12.5 Write property test for inter-post delay
    - **Property 16: Inter-post delay**
    - Generate cycles with 2+ successful posts; record timestamps via `freezegun`
    - Assert ≥5s between consecutive `Poster.post` invocations
    - **Validates: Requirements 5.3**

  - [ ]* 12.6 Write property test for failure isolation
    - **Property 17: Failure isolation**
    - Generate `n` non-duplicate listings with random failure subset `F`
    - Assert poster invoked exactly `n` times; store contains exactly listings outside `F`
    - **Validates: Requirements 5.2**

  - [ ]* 12.7 Write property test for cycle accounting invariant
    - **Property 18: Cycle accounting invariant**
    - Generate diverse cycle scenarios; assert `summary.fetched == summary.skipped_duplicate + summary.posted + summary.failed` and all counts ≥ 0
    - **Validates: Requirements 5.1, 7.5**

  - [ ]* 12.8 Write property test for credential redaction
    - **Property 20: Credentials never logged**
    - Capture all log records during a Run_Cycle; assert no record contains the literal credential values
    - **Validates: Requirements 6.3**

  - [ ]* 12.9 Write property test for success log content
    - **Property 21: Success log contains both IDs**
    - Run cycle with successful posts; assert exactly one INFO record per success containing both job_id and tweet_id
    - **Validates: Requirements 7.3**

  - [ ]* 12.10 Write property test for error log on failure
    - **Property 22: Error log on failure**
    - Run cycle with failed posts; assert at least one ERROR record per failure containing job_id
    - **Validates: Requirements 7.4**

- [x] 13. Checkpoint - Verify orchestrator layer
  - Ensure all tests pass for twitter_client and job_manager, ask the user if questions arise.

- [ ] 14. Implement entry point and scheduling
  - [x] 14.1 Create `main.py` as the CLI entry point
    - Load `AppConfig` from environment; on `ValidationError` print missing-variable name and exit code 2
    - Construct dependencies: `JobStore`, scraper sources, `Formatter`, `Poster`, `JobManager`
    - Run `JobManager.run_once()`; exit 0 on success summary, 1 on uncaught exception
    - Add optional `--scheduled` flag that uses the `schedule` library to run every `run_interval_minutes` minutes
    - _Requirements: 5.4, 6.2, 8.2, 8.4_

  - [ ]* 14.2 Write unit tests for CLI behavior
    - Test exit code 0 when run_once returns successful summary
    - Test exit code 2 when required env var is missing
    - Test exit code 1 on uncaught exception
    - _Requirements: 6.2, 8.4_

- [ ] 15. Create deployment artifacts
  - [x] 15.1 Create `.github/workflows/bot.yml` GitHub Actions workflow
    - Schedule via `cron` (configurable, default every 60 minutes)
    - Set up Python 3.10, install dependencies from `requirements.txt`, install Playwright browsers
    - Inject secrets as environment variables (`OAUTH_TOKEN`, `X_CLIENT_ID`, `X_CLIENT_SECRET`, search URLs)
    - Cache `posted_jobs.sqlite` between runs using actions/cache
    - Run `python main.py`
    - _Requirements: 5.4, 8.3_

  - [x] 15.2 Create `README.md`
    - Document OAuth 2.0 token setup steps for X Developer Portal (creating app, configuring scopes `tweet.read tweet.write offline.access`, generating user token)
    - Document local setup: clone, install requirements, run `playwright install`, set env vars, run `python main.py`
    - Document GitHub Actions deployment steps and required secrets
    - Document configuration options (search URLs, intervals)
    - _Requirements: 8.3_

- [x] 16. Final checkpoint - Ensure all tests pass
  - Run full test suite with coverage report; confirm all property tests pass with at least 100 examples each, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP delivery
- Each task references specific requirements for traceability
- Property tests reference specific properties from the design document
- Checkpoints (tasks 6, 10, 13, 16) ensure incremental validation
- All property-based tests run with minimum 100 examples per `pytest.ini` configuration
- Each property test is annotated with `# Feature: job-vacancy-twitter-bot, Property N: <text>`
