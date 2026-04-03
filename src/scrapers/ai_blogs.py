"""
ai_blogs.py – Official AI company blog aggregator.

Scrapes RSS/Atom feeds from major AI labs:
  - OpenAI Blog
  - Anthropic News
  - Google AI Blog (Google DeepMind)
  - Meta AI Blog

Uses feedparser for robust RSS/Atom parsing with fallback to
direct HTML scraping when feeds are unavailable.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import List

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.models import Article

logger = logging.getLogger(__name__)

# Blog feed configurations
# Each entry: (name, feed_url, fallback_html_url, source_tag)
BLOG_FEEDS: list[dict] = [
    {
        "name": "OpenAI",
        "feed_url": "https://openai.com/blog/rss.xml",
        "fallback_url": "https://openai.com/blog",
        "tag": "openai-blog",
    },
    {
        "name": "Anthropic",
        "feed_url": "https://www.anthropic.com/rss.xml",
        "fallback_url": "https://www.anthropic.com/news",
        "tag": "anthropic-blog",
    },
    {
        "name": "Google AI",
        "feed_url": "https://blog.google/technology/ai/rss/",
        "fallback_url": "https://blog.google/technology/ai/",
        "tag": "google-ai-blog",
    },
    {
        "name": "Meta AI",
        "feed_url": "https://ai.meta.com/blog/rss/",
        "fallback_url": "https://ai.meta.com/blog/",
        "tag": "meta-ai-blog",
    },
]


class AIBlogsScraper:
    """Aggregate recent posts from official AI company blogs."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": settings.user_agent,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html",
        })
        # Only keep posts from the last N days
        self._cutoff = datetime.now(tz=timezone.utc) - timedelta(days=settings.blog_days_lookback)

    # -- public --------------------------------------------------------------

    def scrape(self) -> List[Article]:
        """Return recent blog posts from all configured AI blogs."""
        logger.info("Fetching AI company blogs …")
        articles: list[Article] = []

        for blog in BLOG_FEEDS:
            try:
                posts = self._fetch_blog(blog)
                articles.extend(posts)
                logger.info("  ✓ %s: %d posts", blog["name"], len(posts))
            except Exception as exc:
                logger.error("  ✗ %s blog failed: %s", blog["name"], exc)

        # Deduplicate
        seen: set[str] = set()
        unique: list[Article] = []
        for a in articles:
            if a.url not in seen:
                seen.add(a.url)
                unique.append(a)

        # Sort by date (newest first)
        unique.sort(
            key=lambda a: a.published_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

        result = unique[: settings.blog_max_posts]
        logger.info("AIBlogs: found %d recent posts.", len(result))
        return result

    # -- private -------------------------------------------------------------

    def _fetch_blog(self, blog: dict) -> list[Article]:
        """Try RSS feed first, fall back to HTML scraping."""
        try:
            return self._fetch_rss(blog)
        except Exception as exc:
            logger.warning(
                "%s RSS failed (%s), trying HTML fallback …", blog["name"], exc
            )
            return self._fetch_html(blog)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=10))
    def _fetch_rss(self, blog: dict) -> list[Article]:
        """Fetch and parse an RSS/Atom feed."""
        import feedparser

        resp = self.session.get(blog["feed_url"], timeout=settings.request_timeout)
        resp.raise_for_status()

        feed = feedparser.parse(resp.text)
        articles: list[Article] = []

        for entry in feed.entries[:20]:
            title = entry.get("title", "").strip()
            if not title:
                continue

            # URL
            link = entry.get("link", "")
            if not link:
                continue

            # Published date
            published = self._parse_feed_date(entry)

            # Filter by recency
            if published and published < self._cutoff:
                continue

            # Description / summary
            description = ""
            for field in ("summary", "description", "content"):
                val = entry.get(field, "")
                if isinstance(val, list) and val:
                    val = val[0].get("value", "")
                if val:
                    # Strip HTML tags from description
                    description = re.sub(r"<[^>]+>", " ", str(val))
                    description = re.sub(r"\s+", " ", description).strip()[:500]
                    break

            articles.append(
                Article(
                    title=title,
                    url=link,
                    source="ai_blogs",
                    description=description,
                    author=blog["name"],
                    tags=[blog["tag"], "official"],
                    published_at=published,
                )
            )

        return articles

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=10))
    def _fetch_html(self, blog: dict) -> list[Article]:
        """Fallback: scrape the blog listing page for links."""
        from bs4 import BeautifulSoup

        resp = self.session.get(blog["fallback_url"], timeout=settings.request_timeout)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        articles: list[Article] = []

        # Generic strategy: find article/post links
        for link in soup.select("a[href]"):
            href = link.get("href", "")
            text = link.get_text(strip=True)

            # Skip navigation / short links
            if len(text) < 15 or not href:
                continue

            # Filter for blog post patterns
            if not self._looks_like_blog_post(href, blog):
                continue

            url = href if href.startswith("http") else self._resolve_url(href, blog)

            articles.append(
                Article(
                    title=text[:200],
                    url=url,
                    source="ai_blogs",
                    description="",
                    author=blog["name"],
                    tags=[blog["tag"], "official"],
                )
            )

            if len(articles) >= 10:
                break

        return articles

    @staticmethod
    def _looks_like_blog_post(href: str, blog: dict) -> bool:
        """Heuristic check if a URL looks like a blog post."""
        # Must contain blog/news/research path segments
        patterns = [r"/blog/", r"/news/", r"/research/", r"/posts/"]
        href_lower = href.lower()
        if not any(p in href_lower for p in patterns):
            return False
        # Exclude category/tag pages
        if any(x in href_lower for x in ["/category/", "/tag/", "/page/", "/rss"]):
            return False
        return True

    @staticmethod
    def _resolve_url(href: str, blog: dict) -> str:
        """Resolve a relative URL against the blog's base domain."""
        from urllib.parse import urljoin
        return urljoin(blog["fallback_url"], href)

    @staticmethod
    def _parse_feed_date(entry: dict) -> datetime | None:
        """Extract and parse a publication date from a feed entry."""
        import time as _time

        for field in ("published_parsed", "updated_parsed"):
            parsed = entry.get(field)
            if parsed:
                try:
                    return datetime.fromtimestamp(
                        _time.mktime(parsed), tz=timezone.utc
                    )
                except (ValueError, OverflowError):
                    pass

        # Try raw string parsing
        for field in ("published", "updated"):
            raw = entry.get(field, "")
            if raw:
                for fmt in (
                    "%a, %d %b %Y %H:%M:%S %z",
                    "%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%d",
                ):
                    try:
                        dt = datetime.strptime(raw.strip(), fmt)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        return dt
                    except ValueError:
                        continue

        return None
