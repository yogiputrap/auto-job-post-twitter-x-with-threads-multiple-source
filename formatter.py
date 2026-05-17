"""Tweet formatting for the Job Vacancy Twitter Bot.

Supports two formats:
1. `format_tweet()` — compact 280-char format for standard tweets
2. `format_rich_post()` — detailed rich format for X threads or long posts
"""

from __future__ import annotations

from models import JobListing

TWEET_LIMIT = 280
HASHTAGS = "#RemoteJobs #WFH #Freelance #LokerRemote"
_ELLIPSIS = "…"


# =============================================================================
# Rich Format (for threads / long posts)
# =============================================================================

def format_rich_post(listing: JobListing) -> str:
    """Format a JobListing into a rich, detailed post.
    
    Template:
    🔥[REMOTE | {TYPE} | {CATEGORY}]
    {title}
    
    {company} is hiring!
    
    📍 Location: {location}
    💼 Company: {company}
    💰 Salary: {salary}
    
    Apply Now 👇
    🔗 {url}
    
    #RemoteJobs #WFH #Freelance #LokerRemote
    """
    # Determine job type tags from title/location
    tags = _extract_tags(listing)
    tag_line = " | ".join(tags)

    lines = [
        f"🔥[{tag_line}]",
        f"{listing.title}",
        "",
        f"{listing.company} is hiring!",
        "",
        f"📍 Location: {listing.location}",
        f"💼 Company: {listing.company}",
    ]

    if listing.salary:
        lines.append(f"💰 Salary: {listing.salary}")

    lines.extend([
        "",
        "Apply Now 👇",
        f"🔗 {listing.url}",
        "",
        HASHTAGS,
    ])

    return "\n".join(lines)


def format_thread(listing: JobListing) -> list[str]:
    """Format a JobListing as a Twitter thread (list of tweets, each ≤280 chars).
    
    Tweet 1: Header + title + company
    Tweet 2: Details (location, salary, type)
    Tweet 3: Apply link + hashtags
    """
    tags = _extract_tags(listing)
    tag_line = " | ".join(tags)

    # Tweet 1: Hook + Title
    tweet1 = f"🔥[{tag_line}]\n\n{listing.title}\n\n{listing.company} is hiring!"
    if len(tweet1) > TWEET_LIMIT:
        # Truncate title
        max_title = TWEET_LIMIT - len(f"🔥[{tag_line}]\n\n\n\n{listing.company} is hiring!") - 1
        tweet1 = f"🔥[{tag_line}]\n\n{listing.title[:max_title]}{_ELLIPSIS}\n\n{listing.company} is hiring!"

    # Tweet 2: Details
    details = [f"📍 {listing.location}", f"💼 {listing.company}"]
    if listing.salary:
        details.append(f"💰 {listing.salary}")
    tweet2 = "\n".join(details)

    # Tweet 3: CTA + link + hashtags
    tweet3 = f"Apply Now 👇\n🔗 {listing.url}\n\n{HASHTAGS}"
    if len(tweet3) > TWEET_LIMIT:
        tweet3 = f"🔗 {listing.url}\n\n{HASHTAGS}"

    return [tweet1, tweet2, tweet3]


def _extract_tags(listing: JobListing) -> list[str]:
    """Extract category tags from listing fields."""
    tags = ["REMOTE"]

    title_lower = listing.title.lower()
    location_lower = listing.location.lower()

    # Employment type
    if "intern" in title_lower:
        tags.append("INTERNSHIP")
    elif "freelance" in title_lower or "contract" in title_lower:
        tags.append("FREELANCE")
    elif "part-time" in title_lower or "part time" in title_lower:
        tags.append("PART-TIME")
    else:
        tags.append("FULL-TIME")

    # Category detection
    categories = {
        "hr": "HR",
        "recruit": "RECRUITMENT",
        "machine learning": "AI/ML",
        "ai": "AI/ML",
        "data": "DATA",
        "devops": "DEVOPS",
        "frontend": "ENGINEERING",
        "backend": "ENGINEERING",
        "fullstack": "ENGINEERING",
        "full stack": "ENGINEERING",
        "engineer": "ENGINEERING",
        "developer": "ENGINEERING",
        "software": "ENGINEERING",
        "design": "DESIGN",
        "ui": "DESIGN",
        "ux": "DESIGN",
        "marketing": "MARKETING",
        "sales": "SALES",
        "product": "PRODUCT",
        "manager": "MANAGEMENT",
        "lead": "LEADERSHIP",
        "support": "SUPPORT",
        "writer": "CONTENT",
        "content": "CONTENT",
        "finance": "FINANCE",
        "account": "FINANCE",
    }

    for keyword, category in categories.items():
        if keyword in title_lower:
            tags.append(category)
            break

    return tags


# =============================================================================
# Compact Format (original 280-char tweet)
# =============================================================================

def _build_body(
    title: str,
    company: str,
    location: str,
    salary: str | None,
    url: str,
) -> str:
    """Compose the compact tweet body."""
    lines = [f"{title} at {company}", f"📍 {location}"]
    if salary is not None:
        lines.append(f"💰 {salary}")
    lines.append(f"Apply here: {url}")
    lines.append(HASHTAGS)
    return "\n".join(lines)


def format_tweet(listing: JobListing) -> str:
    """Format a JobListing into a compact Tweet_Body of at most 280 characters.

    If the body exceeds 280 characters:
      1. The salary line is dropped (when present).
      2. If still over the limit, the title is truncated with trailing "…".
    """
    title = listing.title
    company = listing.company
    location = listing.location
    salary = listing.salary
    url = listing.url

    body = _build_body(title, company, location, salary, url)
    if len(body) <= TWEET_LIMIT:
        return body

    if salary is not None:
        body = _build_body(title, company, location, None, url)
        if len(body) <= TWEET_LIMIT:
            return body

    fixed_overhead = len(_build_body("", company, location, None, url))
    available = TWEET_LIMIT - fixed_overhead

    if available < 2:
        raise ValueError(
            "Cannot fit tweet within 280 characters: non-title content "
            f"alone occupies {fixed_overhead} characters."
        )

    truncated_title = title[: available - 1] + _ELLIPSIS
    return _build_body(truncated_title, company, location, None, url)
