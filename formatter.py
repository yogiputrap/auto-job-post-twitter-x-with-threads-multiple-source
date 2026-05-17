"""Tweet formatting for the Job Vacancy Twitter Bot.

Two formats available:
1. "raw" — Detailed long-form post with full description dump
2. "summary" — AI-summarized post with human-friendly language (via Groq)
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import httpx

from models import JobListing

logger = logging.getLogger(__name__)

POST_LIMIT = 25000
HASHTAGS = "#RemoteJobs #WFH #Freelance #LokerRemote"
HASHTAGS_LONG = "#RemoteJobs #WFH #Freelance #LokerRemote #HiringNow"

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

SUMMARY_PROMPT = """Kamu adalah copywriter job vacancy di Twitter/X. Tugas kamu adalah merangkum lowongan kerja berikut menjadi post yang menarik, informatif, dan profesional dalam format berikut:

FORMAT OUTPUT (ikuti persis):
📢 JOB VACANCY: [Job Title] ([Salary jika ada])

[1-2 kalimat ringkasan menarik tentang perusahaan dan posisi ini. Gunakan bahasa campuran Indonesia-English yang natural untuk audience tech Indonesia.]

━━━━━━━━━━━━━━━━━━━━

📌 RINGKASAN UTAMA:
Lokasi: [Location]
Gaji: [Salary atau "Tidak disebutkan"]
Tipe: [Full-Time/Part-Time/Contract]

💡 KUALIFIKASI YANG DICARI:
[3-5 bullet points kualifikasi utama, dirangkum dari deskripsi. Gunakan bahasa yang mudah dipahami.]

ATURAN:
- Jangan copy-paste mentah dari deskripsi
- Rangkum dengan bahasa sendiri yang menarik
- Gunakan campuran Bahasa Indonesia dan English yang natural
- Maksimal 5 bullet points untuk kualifikasi
- Jangan tambahkan informasi yang tidak ada di data asli
- Jangan tambahkan link atau hashtag (akan ditambahkan otomatis)
- Jika tidak ada deskripsi detail, buat ringkasan dari title dan company saja"""


def _strip_html(html: str) -> str:
    """Convert HTML to clean plain text."""
    if not html:
        return ""
    text = re.sub(r'<br\s*/?>', '\n', html)
    text = re.sub(r'</p>', '\n\n', text)
    text = re.sub(r'</div>', '\n', text)
    text = re.sub(r'</li>', '\n', text)
    text = re.sub(r'<li[^>]*>', '• ', text)
    text = re.sub(r'<h[1-6][^>]*>', '\n', text)
    text = re.sub(r'</h[1-6]>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
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
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


def _extract_tags(listing: JobListing) -> list[str]:
    """Extract category tags from listing fields."""
    tags = ["REMOTE"]
    title_lower = listing.title.lower()

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

    categories = {
        "hr": "HR", "recruit": "RECRUITMENT", "machine learning": "AI/ML",
        "ai ": "AI/ML", "data": "DATA", "devops": "DEVOPS", "sre": "DEVOPS",
        "frontend": "ENGINEERING", "backend": "ENGINEERING", "fullstack": "ENGINEERING",
        "full stack": "ENGINEERING", "full-stack": "ENGINEERING", "engineer": "ENGINEERING",
        "developer": "ENGINEERING", "software": "ENGINEERING", "programmer": "ENGINEERING",
        "design": "DESIGN", "ui": "DESIGN", "ux": "DESIGN", "marketing": "MARKETING",
        "seo": "MARKETING", "sales": "SALES", "product": "PRODUCT", "manager": "MANAGEMENT",
        "lead": "LEADERSHIP", "support": "SUPPORT", "writer": "CONTENT", "content": "CONTENT",
        "finance": "FINANCE", "account": "FINANCE", "security": "SECURITY",
        "cyber": "SECURITY", "qa": "QA", "test": "QA", "mobile": "MOBILE",
        "ios": "MOBILE", "android": "MOBILE",
    }
    for keyword, category in categories.items():
        if keyword in title_lower:
            tags.append(category)
            break
    return tags


# =============================================================================
# Format 1: "raw" — Full description dump
# =============================================================================

def format_long_post(listing: JobListing) -> str:
    """Format as detailed long-form post with full description."""
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

    if listing.description:
        description = _strip_html(listing.description)
        if description:
            lines.extend(["", "━━━━━━━━━━━━━━━━━━━━", "", "📝 About This Role", ""])
            max_desc_len = POST_LIMIT - 600
            if len(description) > max_desc_len:
                description = description[:max_desc_len].rsplit('\n', 1)[0] + "\n..."
            lines.append(description)

    lines.extend(["", "━━━━━━━━━━━━━━━━━━━━", "", "Apply Now 👇", f"🔗 {listing.url}", "", HASHTAGS_LONG])
    post = "\n".join(lines)
    if len(post) > POST_LIMIT:
        post = post[:POST_LIMIT - 10] + "\n..."
    return post


# =============================================================================
# Format 2: "summary" — AI-summarized post
# =============================================================================

def format_summary_post(listing: JobListing, groq_api_key: str = "") -> str:
    """Format as AI-summarized post using Groq API."""
    if not groq_api_key:
        # Fallback to template-based summary if no API key
        return _format_summary_template(listing)

    # Prepare job data for the AI
    description = _strip_html(listing.description) if listing.description else ""
    # Truncate description to avoid token limits
    if len(description) > 3000:
        description = description[:3000] + "..."

    job_data = f"""Title: {listing.title}
Company: {listing.company}
Location: {listing.location}
Salary: {listing.salary or 'Tidak disebutkan'}
Type: {listing.job_type or 'Full-Time'}
Description: {description or 'Tidak ada deskripsi detail'}"""

    try:
        response = httpx.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {groq_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [
                    {"role": "system", "content": SUMMARY_PROMPT},
                    {"role": "user", "content": job_data},
                ],
                "temperature": 0.7,
                "max_tokens": 1000,
            },
            timeout=30,
        )

        if response.status_code == 200:
            data = response.json()
            summary = data["choices"][0]["message"]["content"].strip()

            # Append link and hashtags
            post = f"{summary}\n\nApply Now 👇\n🔗 {listing.url}\n\n{HASHTAGS_LONG}"
            if len(post) > POST_LIMIT:
                post = post[:POST_LIMIT - 10] + "\n..."
            return post
        else:
            logger.warning("Groq API returned %d, falling back to template", response.status_code)
            return _format_summary_template(listing)

    except Exception as exc:
        logger.warning("Groq API error: %s, falling back to template", exc)
        return _format_summary_template(listing)


def _format_summary_template(listing: JobListing) -> str:
    """Template-based summary (no AI needed)."""
    salary_text = f" ({listing.salary})" if listing.salary else ""
    job_type = listing.job_type or "Full-Time"

    lines = [
        f"📢 JOB VACANCY: {listing.title}{salary_text}",
        "",
        f"{listing.company} membuka lowongan untuk posisi {listing.title}.",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "📌 RINGKASAN UTAMA:",
        f"Lokasi: {listing.location}",
        f"Gaji: {listing.salary or 'Tidak disebutkan'}",
        f"Tipe: {job_type}",
    ]

    # Extract key points from description if available
    if listing.description:
        description = _strip_html(listing.description)
        if description:
            # Try to extract bullet points or key requirements
            bullets = _extract_key_points(description)
            if bullets:
                lines.extend(["", "💡 KUALIFIKASI YANG DICARI:"])
                for bullet in bullets[:5]:
                    lines.append(f"• {bullet}")

    lines.extend(["", f"Apply Now 👇", f"🔗 {listing.url}", "", HASHTAGS_LONG])
    return "\n".join(lines)


def _extract_key_points(text: str) -> list[str]:
    """Extract key bullet points from description text."""
    points = []

    # Look for lines that start with bullet-like patterns
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        # Match bullet points
        if line.startswith(('•', '-', '–', '*', '▪')):
            clean = line.lstrip('•-–*▪ ').strip()
            if 10 < len(clean) < 200:
                points.append(clean)
        # Match numbered items
        elif re.match(r'^\d+[\.\)]\s', line):
            clean = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
            if 10 < len(clean) < 200:
                points.append(clean)

    # If no bullets found, try to extract from sentences with keywords
    if not points:
        keywords = ['experience', 'required', 'must', 'skill', 'knowledge',
                    'proficient', 'ability', 'degree', 'years', 'familiar']
        for line in text.split('\n'):
            line = line.strip()
            if any(kw in line.lower() for kw in keywords) and 15 < len(line) < 200:
                points.append(line)
                if len(points) >= 5:
                    break

    return points[:5]


# =============================================================================
# Main entry point (used by job_manager)
# =============================================================================

def format_thread(listing: JobListing, post_format: str = "raw", groq_api_key: str = "") -> list[str]:
    """Format listing based on selected format. Returns 1-item list."""
    if post_format == "summary":
        return [format_summary_post(listing, groq_api_key)]
    else:
        return [format_long_post(listing)]


def format_rich_post(listing: JobListing) -> str:
    """Alias for format_long_post (used by dashboard)."""
    return format_long_post(listing)


# =============================================================================
# Compact Format (legacy, for dashboard preview)
# =============================================================================

TWEET_LIMIT = 280
_ELLIPSIS = "…"


def _build_body(title: str, company: str, location: str, salary: str | None, url: str) -> str:
    lines = [f"{title} at {company}", f"📍 {location}"]
    if salary is not None:
        lines.append(f"💰 {salary}")
    lines.append(f"Apply here: {url}")
    lines.append(HASHTAGS)
    return "\n".join(lines)


def format_tweet(listing: JobListing) -> str:
    """Format a JobListing into a compact Tweet_Body of at most 280 characters."""
    title, company, location, salary, url = listing.title, listing.company, listing.location, listing.salary, listing.url

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
        raise ValueError(f"Cannot fit tweet within 280 characters: non-title content alone occupies {fixed_overhead} characters.")
    truncated_title = title[:available - 1] + _ELLIPSIS
    return _build_body(truncated_title, company, location, None, url)
