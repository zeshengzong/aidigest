"""
hackernews.py – Scrape AI-related stories from Hacker News.

Uses the official Firebase-backed HN API:
    https://github.com/HackerNews/API
"""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone
from typing import List

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.models import Article

logger = logging.getLogger(__name__)

HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"


class HackerNewsScraper:
    """Fetch top Hacker News stories and filter for AI-related content."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": settings.user_agent})
        self._pattern = re.compile(settings.ai_pattern())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def scrape(self) -> List[Article]:
        """Return AI-filtered articles from HN top stories."""
        logger.info("Fetching Hacker News top stories …")
        try:
            story_ids = self._fetch_top_ids()
        except Exception as exc:
            logger.error("Failed to fetch HN top story IDs: %s", exc)
            return []

        articles: list[Article] = []
        for sid in story_ids[: settings.hn_max_stories]:
            try:
                item = self._fetch_item(sid)
                if item and self._is_ai_related(item):
                    articles.append(self._to_article(item))
            except Exception as exc:
                logger.warning("Skipping HN story %s: %s", sid, exc)

        logger.info("HackerNews: collected %d AI-related stories.", len(articles))
        return articles

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    def _fetch_top_ids(self) -> list[int]:
        resp = self.session.get(HN_TOP_URL, timeout=settings.request_timeout)
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=0.5, max=4))
    def _fetch_item(self, item_id: int) -> dict | None:
        resp = self.session.get(
            HN_ITEM_URL.format(item_id=item_id), timeout=settings.request_timeout
        )
        resp.raise_for_status()
        return resp.json()

    def _is_ai_related(self, item: dict) -> bool:
        """Check title + text against the AI keyword pattern."""
        text = " ".join(
            filter(None, [item.get("title", ""), item.get("text", "")])
        )
        return bool(self._pattern.search(text))

    @staticmethod
    def _clean_html(text: str) -> str:
        """Strip HTML tags and decode entities."""
        if not text:
            return ""
        # Remove HTML tags
        clean = re.sub(r"<[^>]+>", " ", text)
        # Decode HTML entities (&#x2F; -> /, &amp; -> &, etc.)
        clean = html.unescape(clean)
        # Collapse whitespace
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    @staticmethod
    def _to_article(item: dict) -> Article:
        # HN "Ask HN" / "Show HN" posts may lack a url field
        url = item.get("url") or f"https://news.ycombinator.com/item?id={item['id']}"
        published = None
        if ts := item.get("time"):
            published = datetime.fromtimestamp(ts, tz=timezone.utc)

        raw_text = item.get("text", "")
        description = HackerNewsScraper._clean_html(raw_text)[:300]

        return Article(
            title=item.get("title", "(no title)"),
            url=url,
            source="hackernews",
            description=description,
            score=item.get("score"),
            author=item.get("by"),
            comment_count=item.get("descendants", 0),
            published_at=published,
        )
