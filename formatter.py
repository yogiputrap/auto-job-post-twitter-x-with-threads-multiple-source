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
    """Format as summarized post. Uses AI if key provided, otherwise smart template."""
    # If Groq key available and not empty, try AI
    if groq_api_key and groq_api_key.strip():
        result = _format_with_ai(listing, groq_api_key)
        if result:
            return result

    # Smart template-based summary (no AI needed)
    return _format_smart_summary(listing)


def _format_smart_summary(listing: JobListing) -> str:
    """Smart template summary — parses description and formats nicely without AI."""
    salary_text = f" ({listing.salary})" if listing.salary else ""
    job_type = listing.job_type or "Full-Time"
    description = _strip_html(listing.description) if listing.description else ""

    lines = [
        f"📢 JOB VACANCY: {listing.title}{salary_text}",
        "",
    ]

    # Generate intro sentence
    intro = f"{listing.company} membuka lowongan untuk posisi {listing.title}"
    location_lower = listing.location.lower()
    url_lower = (listing.url or "").lower()
    is_remote = any(kw in location_lower for kw in ['remote', 'anywhere', 'worldwide', 'wfh']) or \
                any(kw in location_lower for kw in ['americas', 'europe', 'asia', 'oceania', 'global']) or \
                'remotive.com' in url_lower or 'jobicy.com' in url_lower
    
    if is_remote:
        intro += " secara Fully Remote."
    else:
        intro += f" di {listing.location}."
    lines.append(intro)

    # Determine remote status for display
    remote_label = f"{listing.location} (Fully Remote / WFH)" if is_remote else listing.location

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "📌 RINGKASAN UTAMA:",
        f"Lokasi: {remote_label}",
        f"Gaji: {listing.salary or 'Tidak disebutkan'}",
        f"Tipe: {job_type}",
    ])

    if description:
        # Extract requirements/qualifications
        requirements = _extract_requirements(description)
        if requirements:
            lines.extend(["", "💡 KUALIFIKASI YANG DICARI:"])
            for req in requirements[:6]:
                lines.append(f"• {req}")

        # Extract responsibilities
        responsibilities = _extract_responsibilities(description)
        if responsibilities:
            lines.extend(["", "📋 TANGGUNG JAWAB:"])
            for resp in responsibilities[:5]:
                lines.append(f"• {resp}")

        # Extract tech stack / tools if mentioned
        tech = _extract_tech_stack(description)
        if tech:
            lines.extend(["", f"🛠 Tech Stack: {', '.join(tech[:8])}"])

    lines.extend([
        "",
        "Apply Now 👇",
        f"🔗 {listing.url}",
        "",
        HASHTAGS_LONG,
    ])

    post = "\n".join(lines)
    if len(post) > POST_LIMIT:
        post = post[:POST_LIMIT - 10] + "\n..."
    return post


def _extract_requirements(text: str) -> list[str]:
    """Extract requirement/qualification bullet points from description."""
    results = []
    lines = text.split('\n')

    req_keywords = ['requirement', 'qualif', 'must have', 'what you need',
                    'what we look', 'ideal candidate', 'you have', 'you bring',
                    'skills required', 'experience required', 'who you are',
                    'required technical', 'nice to have', 'what you\'ll need',
                    'minimum qualif', 'preferred qualif']
    
    # Keywords that indicate we should STOP (not requirements)
    stop_keywords = ['what we offer', 'benefit', 'perks', 'why join', 'about us',
                     'about the company', 'compensation', 'how to apply',
                     'responsibilit', 'what you will', 'what you\'ll do']

    in_req_section = False
    for line in lines:
        line_stripped = line.strip()
        lower = line_stripped.lower()

        # Detect section start
        if not in_req_section and any(kw in lower for kw in req_keywords) and len(line_stripped) < 120:
            in_req_section = True
            continue

        # Detect section end
        if in_req_section and line_stripped and not line_stripped.startswith(('•', '-', '–', '*', '▪')):
            if any(kw in lower for kw in stop_keywords):
                in_req_section = False
                continue
            # Empty-ish line after bullets = might be end of section
            if len(line_stripped) < 5 and results:
                continue

        # Collect bullets in requirement section
        if in_req_section and line_stripped.startswith(('•', '-', '–', '*', '▪')):
            clean = re.sub(r'^[•\-–*▪]\s*', '', line_stripped).strip()
            if 10 < len(clean) < 200 and not clean.endswith(':'):
                results.append(clean)
        elif in_req_section and re.match(r'^\d+[\.\)]', line_stripped):
            clean = re.sub(r'^\d+[\.\)]\s*', '', line_stripped).strip()
            if 10 < len(clean) < 200 and not clean.endswith(':'):
                results.append(clean)

    # Fallback: grab any bullet that mentions years/experience/skills
    if not results:
        skill_keywords = ['years', 'experience', 'proficient', 'knowledge of',
                         'familiar with', 'strong', 'degree in', 'certification']
        for line in lines:
            line_stripped = line.strip()
            if line_stripped.startswith(('•', '-', '–', '*')):
                clean = re.sub(r'^[•\-–*]\s*', '', line_stripped).strip()
                if any(kw in clean.lower() for kw in skill_keywords) and 10 < len(clean) < 200:
                    results.append(clean)
                    if len(results) >= 6:
                        break

    # Deduplicate
    seen = set()
    unique = []
    for r in results:
        if r.lower() not in seen:
            seen.add(r.lower())
            unique.append(r)

    return unique[:6]


def _extract_responsibilities(text: str) -> list[str]:
    """Extract responsibility bullet points from description."""
    results = []
    lines = text.split('\n')

    resp_keywords = ['responsibilit', 'what you will', 'what you\'ll', 'your role',
                     'you will', 'day to day', 'key duties', 'job description',
                     'about the role', 'the role', 'in this role']

    in_resp_section = False
    for line in lines:
        line_stripped = line.strip()
        lower = line_stripped.lower()

        if any(kw in lower for kw in resp_keywords) and len(line_stripped) < 100:
            in_resp_section = True
            continue

        if in_resp_section and line_stripped:
            is_bullet = line_stripped.startswith(('•', '-', '–', '*', '▪')) or re.match(r'^\d+[\.\)]', line_stripped)
            if not is_bullet and len(line_stripped) < 80:
                if any(kw in lower for kw in ['requirement', 'qualif', 'skill', 'benefit', 'what we offer', 'nice to have']):
                    in_resp_section = False
                    continue

        if in_resp_section and line_stripped:
            is_bullet = line_stripped.startswith(('•', '-', '–', '*', '▪')) or re.match(r'^\d+[\.\)]', line_stripped)
            if is_bullet:
                clean = re.sub(r'^[•\-–*▪]\s*', '', line_stripped)
                clean = re.sub(r'^\d+[\.\)]\s*', '', clean).strip()
                if 10 < len(clean) < 200 and not clean.endswith(':'):
                    results.append(clean)

    return results[:5]


def _extract_tech_stack(text: str) -> list[str]:
    """Extract technology/tool mentions from description."""
    tech_patterns = [
        'Python', 'JavaScript', 'TypeScript', 'Java', 'Go', 'Golang', 'Rust',
        'C\\+\\+', 'C#', 'Ruby', 'PHP', 'Swift', 'Kotlin', 'Scala',
        'React', 'Vue', 'Angular', 'Next\\.js', 'Node\\.js', 'Django', 'Flask',
        'Spring', 'Laravel', 'Rails', 'FastAPI', 'Express',
        'AWS', 'GCP', 'Azure', 'Docker', 'Kubernetes', 'K8s', 'Terraform',
        'PostgreSQL', 'MySQL', 'MongoDB', 'Redis', 'Elasticsearch',
        'GraphQL', 'REST', 'gRPC', 'Kafka', 'RabbitMQ',
        'Git', 'CI/CD', 'Jenkins', 'GitHub Actions',
        'Linux', 'Nginx', 'Apache',
        'TensorFlow', 'PyTorch', 'Pandas', 'NumPy',
        'Figma', 'Sketch', 'Adobe', 'Photoshop', 'Illustrator',
        'Salesforce', 'HubSpot', 'Jira', 'Confluence',
        'SQL', 'NoSQL', 'Spark', 'Hadoop', 'Airflow',
    ]

    found = []
    for tech in tech_patterns:
        if re.search(r'\b' + tech + r'\b', text, re.IGNORECASE):
            # Use the original casing from the pattern
            clean_name = tech.replace('\\', '').replace('.', '.').replace('+', '+')
            if clean_name not in found:
                found.append(clean_name)

    return found[:8]


# =============================================================================
# AI Enhancement (optional, uses Groq if key available)
# =============================================================================

def _format_with_ai(listing: JobListing, groq_api_key: str) -> Optional[str]:
    """Try to format with Groq AI. Returns None on failure."""
    description = _strip_html(listing.description) if listing.description else ""
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
            post = f"{summary}\n\nApply Now 👇\n🔗 {listing.url}\n\n{HASHTAGS_LONG}"
            if len(post) > POST_LIMIT:
                post = post[:POST_LIMIT - 10] + "\n..."
            return post
    except Exception as exc:
        logger.warning("Groq AI failed: %s", exc)
    return None


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
