"""
Content parser for scraped HTML pages.

Extracts structured facts (work history, education, images, bios, social links,
skills) from raw HTML returned by ScrapingAnt.
"""

import re
from html.parser import HTMLParser
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse


class _MetaExtractor(HTMLParser):
    """Lightweight HTML parser that pulls out meta tags, images, links, and text."""

    def __init__(self):
        super().__init__()
        self.meta: Dict[str, str] = {}
        self.images: List[Dict[str, str]] = []
        self.links: List[Dict[str, str]] = []
        self.text_chunks: List[str] = []
        self._current_tag = None
        self._current_attrs = {}
        self._capture = False
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            name = a.get("name", a.get("property", "")).lower()
            content = a.get("content", "")
            if name and content:
                self.meta[name] = content
        elif tag == "img":
            src = a.get("src", "")
            alt = a.get("alt", "")
            cls = a.get("class", "")
            if src:
                self.images.append({"src": src, "alt": alt, "class": cls})
        elif tag == "a":
            href = a.get("href", "")
            text = ""
            if href:
                self.links.append({"href": href, "text": text})
        elif tag in ("p", "span", "div", "h1", "h2", "h3", "li", "td", "section"):
            self._capture = True

    def handle_data(self, data):
        stripped = data.strip()
        if stripped and len(stripped) > 2:
            self.text_chunks.append(stripped)
            if self.links and not self.links[-1].get("text"):
                self.links[-1]["text"] = stripped[:200]

    def handle_endtag(self, tag):
        if tag in ("p", "span", "div", "h1", "h2", "h3", "li", "td", "section"):
            self._capture = False


SOCIAL_PATTERNS = {
    "linkedin.com": "LinkedIn",
    "github.com": "GitHub",
    "twitter.com": "Twitter",
    "x.com": "Twitter/X",
    "facebook.com": "Facebook",
    "instagram.com": "Instagram",
    "medium.com": "Medium",
    "stackoverflow.com": "StackOverflow",
    "youtube.com": "YouTube",
}

WORK_PATTERNS = [
    re.compile(r'(?:(?:Senior|Junior|Lead|Staff|Principal|Chief)\s+)?(?:Software|Data|DevOps|Cloud|ML|AI|Full[\s-]?Stack|Front[\s-]?End|Back[\s-]?End|QA|Product|Project|Program|Marketing|Sales|HR|Finance)[\s\w]*(?:Engineer|Developer|Architect|Manager|Designer|Analyst|Scientist|Director|VP|Officer|Consultant|Specialist|Coordinator|Administrator)\s+(?:at|@|-|,)\s+([A-Z][\w\s&.,]+)', re.IGNORECASE),
    re.compile(r'(?:Works?\s+at|Employed\s+(?:at|by)|Working\s+at)\s+([A-Z][\w\s&.,]+)', re.IGNORECASE),
    re.compile(r'(?:CEO|CTO|CFO|COO|CMO|VP|Director|Manager|Engineer|Developer|Founder|Co-Founder)\s+(?:of|at|@|-|,)\s+([A-Z][\w\s&.,]+)', re.IGNORECASE),
]

EDUCATION_PATTERNS = [
    re.compile(r'(?:University|College|Institute|School)\s+of\s+[\w\s]+', re.IGNORECASE),
    re.compile(r'(?:Studied|Graduated|Alumni|Degree|B\.?S\.?|M\.?S\.?|Ph\.?D\.?|MBA|B\.?A\.?|M\.?A\.?)\s+(?:at|from|in)\s+([\w\s]+(?:University|College|Institute|School))', re.IGNORECASE),
    re.compile(r'([\w\s]+(?:University|College|Institute|School|Academy))', re.IGNORECASE),
]


def _detect_platform(url: str) -> Optional[str]:
    host = urlparse(url).hostname or ""
    host = host.lower().lstrip("www.")
    for domain, name in SOCIAL_PATTERNS.items():
        if domain in host:
            return name
    return None


def _extract_profile_images(images: List[Dict], url: str) -> List[str]:
    """Find likely profile/avatar images."""
    profile_keywords = ("profile", "avatar", "photo", "headshot", "portrait", "user", "pic")
    results = []
    for img in images:
        src = img.get("src", "")
        alt = img.get("alt", "").lower()
        cls = img.get("class", "").lower()
        if not src or src.startswith("data:"):
            continue
        if not src.startswith("http"):
            src = urljoin(url, src)
        if any(kw in alt or kw in cls or kw in src.lower() for kw in profile_keywords):
            results.append(src)
    return results[:3]


def _extract_og_image(meta: Dict[str, str]) -> Optional[str]:
    for key in ("og:image", "twitter:image", "twitter:image:src"):
        val = meta.get(key, "").strip()
        if val and val.startswith("http"):
            return val
    return None


def _extract_bio(meta: Dict[str, str], text_chunks: List[str]) -> Optional[str]:
    for key in ("og:description", "description", "twitter:description"):
        val = meta.get(key, "").strip()
        if val and len(val) > 20:
            return val
    full_text = " ".join(text_chunks)
    about_match = re.search(r'(?:About|Bio|Summary|Description)\s*[:\-]?\s*(.{30,500})', full_text, re.IGNORECASE)
    if about_match:
        return about_match.group(1).strip()
    return None


def _extract_social_links(links: List[Dict], source_url: str) -> List[Dict]:
    """Find links to other social profiles on the page."""
    source_host = (urlparse(source_url).hostname or "").lower()
    results = []
    seen = set()
    for link in links:
        href = link.get("href", "")
        if not href.startswith("http"):
            href = urljoin(source_url, href)
        parsed = urlparse(href)
        host = (parsed.hostname or "").lower().lstrip("www.")
        if host == source_host.lstrip("www.") or host in seen:
            continue
        platform = None
        for domain, name in SOCIAL_PATTERNS.items():
            if domain in host:
                platform = name
                break
        if platform:
            seen.add(host)
            path = parsed.path.strip("/")
            username = path.split("/")[0] if path else ""
            results.append({"url": href, "platform": platform, "username": username})
    return results


def _extract_work_history(text_chunks: List[str]) -> List[Dict]:
    full_text = " ".join(text_chunks)
    results = []
    seen = set()
    for pattern in WORK_PATTERNS:
        for match in pattern.finditer(full_text):
            entry = match.group(0).strip()[:200]
            key = entry.lower()
            if key not in seen:
                seen.add(key)
                company_match = match.groups()
                results.append({
                    "raw": entry,
                    "company": company_match[0].strip() if company_match else "",
                })
    return results[:10]


def _extract_education(text_chunks: List[str]) -> List[str]:
    full_text = " ".join(text_chunks)
    results = []
    seen = set()
    for pattern in EDUCATION_PATTERNS:
        for match in pattern.finditer(full_text):
            entry = match.group(0).strip()[:200]
            key = entry.lower()
            if key not in seen and len(entry) > 15:
                seen.add(key)
                results.append(entry)
    return results[:5]


def _extract_skills(text_chunks: List[str]) -> List[str]:
    skill_keywords = {
        "python", "javascript", "typescript", "java", "c++", "c#", "go", "rust",
        "react", "angular", "vue", "node.js", "django", "flask", "fastapi",
        "aws", "azure", "gcp", "docker", "kubernetes", "terraform",
        "sql", "postgresql", "mongodb", "redis", "elasticsearch",
        "machine learning", "deep learning", "ai", "nlp",
        "project management", "agile", "scrum", "devops", "ci/cd",
        "cybersecurity", "osint", "penetration testing", "incident response",
    }
    full_text = " ".join(text_chunks).lower()
    found = []
    for skill in skill_keywords:
        if re.search(r'\b' + re.escape(skill) + r'\b', full_text):
            found.append(skill)
    return sorted(found)[:15]


def parse_scraped_html(url: str, html: str) -> List[Dict]:
    """
    Parse scraped HTML and extract structured facts.

    Returns a list of fact dicts ready for insert_facts(), each with
    fact_type, value, confidence_score, sources, and context.
    """
    if not html or len(html) < 50:
        return []

    parser = _MetaExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass

    facts: List[Dict] = []
    platform = _detect_platform(url)
    base_confidence = 75.0 if platform else 65.0

    def _add(fact_type: str, value: str, confidence: float, context: Optional[Dict] = None):
        if not value or len(value.strip()) < 3:
            return
        ctx = {"source_url": url}
        if platform:
            ctx["platform"] = platform
        if context:
            ctx.update(context)
        facts.append({
            "fact_type": fact_type,
            "value": value.strip(),
            "confidence_score": confidence,
            "sources": [f"scrape:{urlparse(url).hostname or 'unknown'}"],
            "context": ctx,
        })

    og_image = _extract_og_image(parser.meta)
    if og_image:
        _add("profile_image", og_image, base_confidence, {"image_type": "og:image"})

    profile_imgs = _extract_profile_images(parser.images, url)
    for img_url in profile_imgs:
        if img_url != og_image:
            _add("profile_image", img_url, base_confidence - 10, {"image_type": "profile_img"})

    bio = _extract_bio(parser.meta, parser.text_chunks)
    if bio:
        _add("bio", bio, base_confidence)

    title = parser.meta.get("og:title", parser.meta.get("title", ""))
    if title and len(title) > 5:
        _add("bio", title, base_confidence - 5, {"field": "page_title"})

    work = _extract_work_history(parser.text_chunks)
    work_seen = set()
    for entry in work:
        company = entry.get("company", "").strip().rstrip(".,")
        if company.lower() in work_seen:
            continue
        work_seen.add(company.lower())
        _add("work_history", entry["raw"], base_confidence - 5, {"company": company})

    edu = _extract_education(parser.text_chunks)
    for entry in edu:
        _add("education", entry, base_confidence - 10)

    social = _extract_social_links(parser.links, url)
    for sl in social:
        display = f"{sl['platform']}: {sl['username']}" if sl['username'] else sl['url']
        _add("social_link", display, base_confidence, {"url": sl["url"], "platform": sl["platform"], "username": sl.get("username", "")})

    skills = _extract_skills(parser.text_chunks)
    if skills:
        _add("skill", ", ".join(skills), base_confidence - 15, {"skills_list": skills})

    email_re = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
    full_text = " ".join(parser.text_chunks)
    for email in email_re.findall(full_text):
        if not email.endswith(('.png', '.jpg', '.gif', '.svg', '.css', '.js')):
            _add("email", email.lower(), base_confidence + 5)

    return facts
