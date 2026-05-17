# Job Vacancy Twitter Bot

Automated bot that scrapes remote, WFH, and freelance job listings from Indeed Indonesia and Glints Indonesia, then posts them to X (Twitter) via the v2 API.

## Prerequisites

- Python 3.10+
- Playwright (for browser-based scraping)
- An X Developer account with OAuth 2.0 User Authentication configured

## Local Setup

```bash
# Clone the repository
git clone https://github.com/your-username/job-vacancy-twitter-bot.git
cd job-vacancy-twitter-bot

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium --with-deps

# Set environment variables (see table below)
export OAUTH_TOKEN="your-oauth-token"
export X_CLIENT_ID="your-client-id"
export X_CLIENT_SECRET="your-client-secret"
export INDEED_SEARCH_URL="https://id.indeed.com/jobs?q=remote&l=Indonesia"
export GLINTS_SEARCH_URL="https://glints.com/id/opportunities/jobs/explore?keyword=remote&country=ID"

# Run the bot (single cycle)
python main.py
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OAUTH_TOKEN` | Yes | OAuth 2.0 User Access Token for X API |
| `X_CLIENT_ID` | Yes | X Developer App Client ID |
| `X_CLIENT_SECRET` | Yes | X Developer App Client Secret |
| `INDEED_SEARCH_URL` | Yes | Indeed Indonesia search URL with filters |
| `GLINTS_SEARCH_URL` | Yes | Glints Indonesia search URL with filters |
| `RUN_INTERVAL_MINUTES` | No | Interval between cycles in scheduled mode (default: 60) |
| `DB_PATH` | No | Path to SQLite database file (default: `posted_jobs.sqlite`) |
| `LISTINGS_PER_SOURCE` | No | Max listings to fetch per source (default: 10) |
| `INTER_POST_DELAY_SECONDS` | No | Delay between consecutive tweets (default: 5) |
| `INTER_REQUEST_DELAY_SECONDS` | No | Delay between HTTP requests to same source (default: 2) |

## OAuth 2.0 Token Setup

Follow these steps to obtain an OAuth 2.0 User Access Token from the X Developer Portal:

1. **Create a Developer Account**: Go to [developer.x.com](https://developer.x.com) and sign up or log in.

2. **Create a Project and App**: Navigate to the Developer Portal dashboard and create a new Project. Within the project, create an App.

3. **Configure User Authentication**:
   - In your App settings, go to "User authentication settings" and click "Set up".
   - Set App permissions to **Read and Write**.
   - Set Type of App to **Web App, Automated App or Bot**.
   - Set the Callback URL (e.g., `https://localhost:3000/callback`).
   - Set the Website URL to your project or profile URL.

4. **Configure OAuth 2.0 Scopes**: Ensure the following scopes are enabled:
   - `tweet.read`
   - `tweet.write`
   - `offline.access`

5. **Generate User Token**:
   - Note your **Client ID** and **Client Secret** from the "Keys and tokens" tab.
   - Use the OAuth 2.0 Authorization Code Flow with PKCE to generate a User Access Token. You can use tools like [Insomnia](https://insomnia.rest/) or the [Twitter OAuth 2.0 playground](https://developer.x.com/en/docs/authentication/oauth-2-0) to complete the flow.
   - The authorization URL is: `https://twitter.com/i/oauth2/authorize`
   - The token URL is: `https://api.twitter.com/2/oauth2/token`

6. **Store Credentials**: Save the `OAUTH_TOKEN`, `X_CLIENT_ID`, and `X_CLIENT_SECRET` securely. Never commit them to source control.

## GitHub Actions Deployment

The bot includes a GitHub Actions workflow (`.github/workflows/bot.yml`) that runs automatically on a schedule.

### Setup Steps

1. **Add Secrets** in your repository settings (Settings → Secrets and variables → Actions → Secrets):
   - `OAUTH_TOKEN` — Your OAuth 2.0 User Access Token
   - `X_CLIENT_ID` — Your X App Client ID
   - `X_CLIENT_SECRET` — Your X App Client Secret

2. **Add Variables** (Settings → Secrets and variables → Actions → Variables):
   - `INDEED_SEARCH_URL` — Your Indeed Indonesia search URL
   - `GLINTS_SEARCH_URL` — Your Glints Indonesia search URL

3. **Enable the workflow**: The workflow runs every hour by default via cron (`0 * * * *`). You can also trigger it manually from the Actions tab using "Run workflow".

### How It Works

- The workflow checks out the code, installs Python 3.10, dependencies, and Playwright browsers.
- It restores the `posted_jobs.sqlite` cache from previous runs to maintain deduplication state.
- It runs `python main.py` which executes a single cycle: scrape → deduplicate → format → post → persist.
- The SQLite database is cached between runs so previously posted jobs are not re-posted.

## Configuration Options

### Search URLs

Customize the job search by modifying the search URLs:

- **Indeed**: Use Indeed Indonesia's search with query parameters for remote/WFH roles. Example: `https://id.indeed.com/jobs?q=remote+work+from+home&l=Indonesia`
- **Glints**: Use Glints Indonesia's opportunity explorer with keyword filters. Example: `https://glints.com/id/opportunities/jobs/explore?keyword=remote&country=ID&workArrangement=REMOTE`

### Schedule

The default cron schedule is every hour (`0 * * * *`). To change it, edit the `cron` value in `.github/workflows/bot.yml`:

```yaml
on:
  schedule:
    - cron: '0 */2 * * *'  # Every 2 hours
```

For local scheduled mode, set `RUN_INTERVAL_MINUTES` and run with the `--scheduled` flag:

```bash
export RUN_INTERVAL_MINUTES=30
python main.py --scheduled
```

## Running Tests

```bash
# Run all tests with coverage
pytest tests/ --cov=. --cov-report=term

# Run only unit tests
pytest tests/unit/

# Run only property-based tests
pytest tests/property/
```

## License

MIT
