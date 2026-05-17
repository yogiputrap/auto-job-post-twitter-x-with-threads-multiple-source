# Requirements Document

## Introduction

The Job Vacancy Twitter Bot is a Python-based automation system that periodically fetches remote, work-from-home (WFH), and freelance job listings from Indonesian job portals (Indeed Indonesia and Glints Indonesia), formats each listing into a tweet-ready string, and posts it to X (formerly Twitter) using the X API v2 with OAuth 2.0 User Authentication. The system tracks already-posted jobs to prevent duplicates and supports scheduled execution via GitHub Actions or a local scheduler. The design emphasizes modular architecture, robust error handling for network and DOM parsing failures, and graceful fallbacks when primary scraping is blocked.

## Glossary

- **Bot**: The complete automation system encompassing all modules (Scraper, Formatter, Poster, Job_Manager).
- **Scraper**: Module responsible for extracting job listings from Indeed Indonesia and Glints Indonesia.
- **Fallback_Fetcher**: Secondary data source (RSS feeds or third-party job aggregator APIs) used when primary scraping fails.
- **Formatter**: Module that converts extracted job data into a tweet-formatted string of at most 280 characters.
- **Poster**: Module that authenticates with X API v2 and publishes tweets.
- **Job_Manager**: Orchestrator module that coordinates the fetch → deduplicate → format → post → persist → sleep pipeline.
- **Job_Store**: Persistent storage layer (SQLite database or JSON file) used to record posted Job IDs for deduplication.
- **Job_ID**: A stable, unique identifier for a job listing, derived from source URL and source-specific identifier.
- **Job_Listing**: A record containing Job Title, Company Name, Location, Description/Salary (optional), Application Link, Source, and Job_ID.
- **X_API**: X (Twitter) API v2 endpoint `POST /2/tweets`.
- **OAuth_Token**: An OAuth 2.0 User Access Token with scopes `tweet.read`, `tweet.write`, and `offline.access`.
- **Tweet_Body**: The 280-character formatted string posted to X.
- **Run_Cycle**: One full execution of the Job_Manager pipeline.
- **Rate_Limit**: HTTP 429 response from X API or job portals indicating throttling.

## Requirements

### Requirement 1: Job Data Extraction

**User Story:** As a job seeker following the bot, I want the Bot to fetch the latest remote, WFH, and freelance jobs from Indeed Indonesia and Glints Indonesia, so that I receive timely listings without manually visiting each portal.

#### Acceptance Criteria

1. WHEN a Run_Cycle begins, THE Scraper SHALL fetch job listings from Indeed Indonesia using a search query filtered for Remote, WFH, or Freelance roles.
2. WHEN a Run_Cycle begins, THE Scraper SHALL fetch job listings from Glints Indonesia using a search query filtered for Remote, WFH, or Freelance roles.
3. THE Scraper SHALL extract the following fields per Job_Listing: Job Title, Company Name, Location, Description or Salary (when available), Application Link, Source, and Job_ID.
4. THE Scraper SHALL return between 5 and 10 of the most recent Job_Listings per source per Run_Cycle.
5. WHEN consecutive HTTP requests are made to the same source, THE Scraper SHALL wait at least 2 seconds between requests.
6. IF the primary scraping method fails to retrieve listings from a source, THEN THE Bot SHALL invoke the Fallback_Fetcher for that source.
7. IF both the primary scraper and the Fallback_Fetcher fail for a source, THEN THE Bot SHALL log the failure and continue processing the other source.
8. WHEN a Job_Listing is missing a required field (Job Title, Company Name, or Application Link), THE Scraper SHALL discard that Job_Listing.

### Requirement 2: Duplicate Prevention

**User Story:** As a follower of the bot account, I want each job posted only once, so that my timeline is not flooded with the same listing.

#### Acceptance Criteria

1. THE Job_Manager SHALL persist the Job_ID of every successfully posted Job_Listing in the Job_Store.
2. WHEN a Job_Listing is fetched, THE Job_Manager SHALL check the Job_Store for the presence of its Job_ID before formatting or posting.
3. IF a Job_ID is already present in the Job_Store, THEN THE Job_Manager SHALL skip that Job_Listing.
4. THE Job_Store SHALL persist Job_IDs across Run_Cycles and across process restarts.
5. WHEN a tweet post fails, THE Job_Manager SHALL NOT record the corresponding Job_ID in the Job_Store.

### Requirement 3: Tweet Content Formatting

**User Story:** As a follower scrolling X, I want each job tweet to be readable, structured, and within the character limit, so that I can quickly understand the role and apply.

#### Acceptance Criteria

1. THE Formatter SHALL produce a Tweet_Body of at most 280 characters for any Job_Listing.
2. THE Formatter SHALL include the Job Title, Company Name, Location, Application Link, and the hashtags `#RemoteJobs`, `#WFH`, `#Freelance`, `#LokerRemote` in the Tweet_Body.
3. WHERE a Job_Listing includes a Salary field, THE Formatter SHALL include the Salary in the Tweet_Body.
4. IF the combined Tweet_Body exceeds 280 characters, THEN THE Formatter SHALL truncate the Job Title with a trailing ellipsis (`…`) until the Tweet_Body fits within 280 characters.
5. THE Formatter SHALL place the Application Link as a complete, unmodified URL in the Tweet_Body.
6. THE Formatter SHALL produce a Tweet_Body that contains exactly one Application Link.

### Requirement 4: X API v2 Posting

**User Story:** As the bot operator, I want tweets to be published to X reliably, so that the bot fulfills its purpose.

#### Acceptance Criteria

1. THE Poster SHALL authenticate to X_API using an OAuth_Token configured with scopes `tweet.read`, `tweet.write`, and `offline.access`.
2. WHEN the Poster receives a Tweet_Body, THE Poster SHALL submit it to the `POST /2/tweets` endpoint of X_API.
3. WHEN X_API returns HTTP status 201, THE Poster SHALL return a success result containing the returned tweet ID.
4. IF X_API returns HTTP status 429, THEN THE Poster SHALL wait for the duration indicated by the `x-rate-limit-reset` header (or 15 minutes if absent) and retry once.
5. IF X_API returns HTTP status 5xx, THEN THE Poster SHALL retry the request up to 3 times with exponential backoff starting at 2 seconds.
6. IF X_API returns HTTP status 4xx other than 429, THEN THE Poster SHALL return a failure result containing the status code and error message without retrying.
7. WHEN the OAuth_Token is missing or invalid, THE Poster SHALL return a failure result identifying the authentication error.

### Requirement 5: Pipeline Orchestration

**User Story:** As the bot operator, I want a single entry point that coordinates fetching, deduplication, formatting, posting, and persistence, so that the system runs end-to-end with one command.

#### Acceptance Criteria

1. WHEN the Bot is started, THE Job_Manager SHALL execute the following ordered steps: fetch Job_Listings, filter duplicates against Job_Store, format each remaining Job_Listing, post each Tweet_Body via the Poster, and record each successfully posted Job_ID in the Job_Store.
2. WHEN a single Job_Listing fails to post, THE Job_Manager SHALL continue processing remaining Job_Listings in the same Run_Cycle.
3. WHEN consecutive tweets are posted in the same Run_Cycle, THE Job_Manager SHALL wait at least 5 seconds between posts.
4. WHERE scheduled execution is enabled, THE Job_Manager SHALL support running on a configurable interval via the Python `schedule` library or via an external scheduler such as GitHub Actions cron.

### Requirement 6: Configuration Management

**User Story:** As the bot operator, I want to configure API credentials and search URLs without modifying source code, so that I can deploy the bot to different environments safely.

#### Acceptance Criteria

1. THE Bot SHALL read the OAuth_Token, X API client ID, X API client secret, Indeed search URL, Glints search URL, and Run_Cycle interval from environment variables.
2. WHEN a required environment variable is missing at startup, THE Bot SHALL exit with a non-zero status code and log the name of the missing variable.
3. THE Bot SHALL NOT log the value of the OAuth_Token, client secret, or any credential in plain text.

### Requirement 7: Error Handling and Logging

**User Story:** As the bot operator, I want clear logs and resilient behavior during failures, so that I can diagnose issues without the bot crashing.

#### Acceptance Criteria

1. IF a network request raises a connection or timeout exception, THEN THE Bot SHALL log the exception with the source name and continue the Run_Cycle.
2. IF DOM parsing raises an exception for a single Job_Listing, THEN THE Scraper SHALL log the exception, skip that Job_Listing, and continue parsing remaining Job_Listings.
3. THE Bot SHALL emit log entries at INFO level for each successful tweet post including the Job_ID and tweet ID.
4. THE Bot SHALL emit log entries at ERROR level for any failure that prevents posting a Job_Listing.
5. WHEN the Run_Cycle completes, THE Bot SHALL log a summary containing counts of fetched, skipped-duplicate, posted, and failed Job_Listings.

### Requirement 8: Deployment Support

**User Story:** As the bot operator, I want to deploy the Bot via GitHub Actions or a local scheduler, so that it runs autonomously on a schedule.

#### Acceptance Criteria

1. THE Bot SHALL provide a `requirements.txt` file listing all Python dependencies with pinned versions.
2. THE Bot SHALL provide a documented entry point script (`main.py`) that runs a single Run_Cycle when invoked.
3. THE Bot SHALL provide a `README.md` documenting OAuth 2.0 token setup steps and a sample GitHub Actions workflow for scheduled execution.
4. WHEN invoked with no arguments, THE Bot SHALL execute exactly one Run_Cycle and exit with status code 0 on success or non-zero on unrecoverable failure.
