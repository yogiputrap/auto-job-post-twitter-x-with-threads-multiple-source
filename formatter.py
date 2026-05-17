"""Tweet formatting for the Job Vacancy Twitter Bot.

Since the account has X Premium (25,000 char limit), we format each
job listing as a single rich, detailed long-form post instead of threads.
"""

from __future__ import annotations

import re
from models import JobListing

POST_LIMIT = 25000
HASHTAGS = "#RemoteJobs #WFH #Freelance #LokerRemote"
HASHTAGS_LONG = "#RemoteJobs #WFH #Freelance #LokerRemote #HiringNow"


def _strip_html(html: str) -> str:
    """Convert HTML to clean plain text."""
    if not html:
        return ""
    
    # Replace common block elements with newlines
    text = re.sub(r'<br\s*/?>', '\n', html)
    text = re.sub(r'</p>', '\n\n', text)
    text = re.sub(r'</div>', '\n', text)
    text = re.sub(r'</li>', '\n', text)
    text = re.sub(r'<li[^>]*>', '• ', text)
    text = re.sub(r'<h[1-6][^>]*>', '\n', text)
    text = re.sub(r'</h[1-6]>', '\n', text)
    
    # Remove all remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Decode common HTML entities
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&quot;', '"')
    text = text.replace('&#39;', "'")
    text = text.replace('&rsquo;', "'")
    text = text.replace('&lsquo;', "'")
    text = text.replace('&rdquo;', '"')
    text = text.replace('&ldquo;', '"')
    text = text.replace('&mdash;', '—')
    text = text.replace('&ndash;', '–')
    text = text.replace('&bull;', '•')
    
    # Clean up excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    
    return text.strip()


def _extract_tags(listing: JobListing) -> list[str]:
    """Extract category tags from listing fields."""
    tags = ["REMOTE"]

    title_lower = listing.title.lower()
    
    # Job type from field or title
    if listing.job_type:
        jt = listing.job_type.lower()
        if "intern" in jt:
            tags.append("INTERNSHIP")
        elif "freelance" in jt or "contract" in jt:
            tags.append("CONTRACT")
        elif "part" in jt:
            tags.append("PART-TIME")
        else:
            tags.append("FULL-TIME")
    elif "intern" in title_lower:
        tags.append("INTERNSHIP")
    elif "freelance" in title_lower or "contract" in title_lower:
        tags.append("CONTRACT")
    elif "part-time" in title_lower or "part time" in title_lower:
        tags.append("PART-TIME")
    else:
        tags.append("FULL-TIME")

    # Category detection
    categories = {
        "hr": "HR",
        "recruit": "RECRUITMENT",
        "machine learning": "AI/ML",
        "ai ": "AI/ML",
        "data": "DATA",
        "devops": "DEVOPS",
        "sre": "DEVOPS",
        "frontend": "ENGINEERING",
        "backend": "ENGINEERING",
        "fullstack": "ENGINEERING",
        "full stack": "ENGINEERING",
        "full-stack": "ENGINEERING",
        "engineer": "ENGINEERING",
        "developer": "ENGINEERING",
        "software": "ENGINEERING",
        "programmer": "ENGINEERING",
        "design": "DESIGN",
        "ui": "DESIGN",
        "ux": "DESIGN",
        "marketing": "MARKETING",
        "seo": "MARKETING",
        "sales": "SALES",
        "product": "PRODUCT",
        "manager": "MANAGEMENT",
        "lead": "LEADERSHIP",
        "support": "SUPPORT",
        "writer": "CONTENT",
        "content": "CONTENT",
        "finance": "FINANCE",
        "account": "FINANCE",
        "security": "SECURITY",
        "cyber": "SECURITY",
        "qa": "QA",
        "test": "QA",
        "mobile": "MOBILE",
        "ios": "MOBILE",
        "android": "MOBILE",
    }

    for keyword, category in categories.items():
        if keyword in title_lower:
            tags.append(category)
            break

    return tags


def format_long_post(listing: JobListing) -> str:
    """Format a JobListing as a single rich long-form post (max 25000 chars).
    
    Structure:
    🔥[REMOTE | TYPE | CATEGORY]
    Title
    
    Company is hiring!
    
    📍 Location
    💼 Company
    💰 Salary (if available)
    📋 Type (if available)
    
    ━━━━━━━━━━━━━━━━━━━━
    
    📝 About This Role
    (description from API, cleaned up)
    
    ━━━━━━━━━━━━━━━━━━━━
    
    Apply Now 👇
    🔗 URL
    
    #hashtags
    """
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
    
    if listing.job_type:
        lines.append(f"📋 Type: {listing.job_type}")

    # Add description if available
    if listing.description:
        description = _strip_html(listing.description)
        if description:
            lines.append("")
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append("")
            lines.append("📝 About This Role")
            lines.append("")
            
            # Truncate description if needed to stay within limit
            # Reserve space for header + footer (~500 chars)
            max_desc_len = POST_LIMIT - 600
            if len(description) > max_desc_len:
                description = description[:max_desc_len].rsplit('\n', 1)[0] + "\n..."
            
            lines.append(description)

    # Footer
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append("Apply Now 👇")
    lines.append(f"🔗 {listing.url}")
    lines.append("")
    lines.append(HASHTAGS_LONG)

    post = "\n".join(lines)
    
    # Final safety truncation
    if len(post) > POST_LIMIT:
        post = post[:POST_LIMIT - 10] + "\n..."
    
    return post


# Keep format_thread as alias that returns single-item list for backward compat
def format_thread(listing: JobListing) -> list[str]:
    """Format as a single long post (returned as 1-item list for API compat)."""
    return [format_long_post(listing)]


def format_rich_post(listing: JobListing) -> str:
    """Alias for format_long_post."""
    return format_long_post(listing)


# =============================================================================
# Compact Format (legacy, for dashboard preview)
# =============================================================================

TWEET_LIMIT = 280
_ELLIPSIS = "…"


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
    """Format a JobListing into a compact Tweet_Body of at most 280 characters."""
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
