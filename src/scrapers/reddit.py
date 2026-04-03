"""
reddit.py – Reddit AI subreddit scraper.

Fetches hot posts from AI-related subreddits using Reddit's public JSON API
(no OAuth required). Subreddits: r/MachineLearning, r/LocalLLaMA,
r/StableDiffusion, r/artificial.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import List

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.models import Article

logger = logging.getLogger(__name__)

# Subreddits to scrape (public JSON, no auth required)
AI_SUBREDDITS = [
    "MachineLearning",
    "LocalLLaMA",
    "StableDiffusion",
    "artificial",
]


class RedditScraper:
    """Scrape hot AI posts from selected subreddits."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            # Reddit blocks the default python-requests UA; a descriptive UA is fine
            "User-Agent": f"{settings.user_agent} reddit-scraper",
        })
        self.ai_re = re.compile(settings.ai_pattern())

    # -- public --------------------------------------------------------------

    def scrape(self) -> List[Article]:
        """Return hot AI-related posts from target subreddits."""
        logger.info("Fetching Reddit AI subreddits …")
        articles: list[Article] = []

        for subreddit in AI_SUBREDDITS:
            try:
                posts = self._fetch_subreddit(subreddit)
                articles.extend(posts)
            except Exception as exc:
                logger.error("Reddit r/%s fetch failed: %s", subreddit, exc)

        # Deduplicate by URL
        seen: set[str] = set()
        unique: list[Article] = []
        for a in articles:
            if a.url not in seen:
                seen.add(a.url)
                unique.append(a)

        # Sort by score and take top N
        unique.sort(key=lambda a: a.score or 0, reverse=True)
        result = unique[: settings.reddit_max_posts]
        logger.info("Reddit: found %d posts.", len(result))
        return result

    # -- private -------------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
    def _fetch_subreddit(self, subreddit: str) -> list[Article]:
        """Fetch hot posts from a subreddit using public JSON endpoint."""
        url = f"https://www.reddit.com/r/{subreddit}/hot.json"
        params = {"limit": 25, "t": "day"}

        resp = self.session.get(url, params=params, timeout=settings.request_timeout)
        resp.raise_for_status()
        data = resp.json()

        articles: list[Article] = []
        children = data.get("data", {}).get("children", [])

        for child in children:
            post = child.get("data", {})
            if not post:
                continue

            # Skip stickied / pinned posts
            if post.get("stickied"):
                continue

            title = post.get("title", "").strip()
            if not title:
                continue

            # Post URL (prefer external link, fall back to Reddit permalink)
            post_url = post.get("url", "")
            permalink = f"https://www.reddit.com{post.get('permalink', '')}"
            # If url is just the reddit post itself, use permalink
            if not post_url or "reddit.com" in post_url:
                post_url = permalink

            selftext = post.get("selftext", "")[:500]
            score = post.get("score", 0)
            author = post.get("author", "")
            comment_count = post.get("num_comments", 0)

            published = None
            created_utc = post.get("created_utc")
            if created_utc:
                published = datetime.fromtimestamp(created_utc, tz=timezone.utc)

            # Flair as a tag
            flair = post.get("link_flair_text", "")
            tags = [f"r/{subreddit}"]
            if flair:
                tags.append(flair)

            articles.append(
                Article(
                    title=title,
                    url=post_url,
                    source="reddit",
                    description=selftext,
                    score=score,
                    author=f"u/{author}" if author else None,
                    comment_count=comment_count,
                    tags=tags,
                    published_at=published,
                )
            )

        return articles
