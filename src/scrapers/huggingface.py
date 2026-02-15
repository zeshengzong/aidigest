"""
huggingface.py – Hugging Face scraper.

Fetches trending models and papers from the Hugging Face API and website.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import List

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.models import Article

logger = logging.getLogger(__name__)

HF_API_BASE = "https://huggingface.co/api"
HF_PAPERS_URL = "https://huggingface.co/papers"


class HuggingFaceScraper:
    """Scrape trending models and daily papers from Hugging Face."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": settings.user_agent})
        self.ai_re = re.compile(settings.ai_pattern())

    # -- public --------------------------------------------------------------

    def scrape(self) -> List[Article]:
        """Return a combined list of trending models + daily papers."""
        articles: list[Article] = []

        # 1. Trending models via API
        try:
            articles.extend(self._fetch_trending_models())
        except Exception as exc:
            logger.error("HuggingFace models fetch failed: %s", exc)

        # 2. Daily papers page
        try:
            articles.extend(self._fetch_daily_papers())
        except Exception as exc:
            logger.error("HuggingFace papers fetch failed: %s", exc)

        logger.info("HuggingFace: found %d items.", len(articles))
        return articles[: settings.hf_max_items]

    # -- private: models -----------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def _fetch_trending_models(self) -> list[Article]:
        """Use the HF API to get recently popular models."""
        resp = self.session.get(
            f"{HF_API_BASE}/models",
            params={
                "sort": "trending",
                "direction": "-1",
                "limit": settings.hf_max_items,
            },
            timeout=settings.request_timeout,
        )
        resp.raise_for_status()
        models = resp.json()

        articles: list[Article] = []
        for m in models:
            model_id: str = m.get("modelId", m.get("id", ""))
            if not model_id:
                continue

            tags = m.get("tags", [])
            description = ", ".join(tags[:10]) if tags else ""
            likes = m.get("likes", 0)

            article = Article(
                title=model_id,
                url=f"https://huggingface.co/{model_id}",
                source="huggingface",
                description=description,
                score=likes,
                tags=["model"] + tags[:5],
            )

            # HF models are inherently AI; keep all of them
            articles.append(article)

        return articles

    # -- private: papers -----------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def _fetch_daily_papers(self) -> list[Article]:
        """Scrape the Hugging Face daily papers page."""
        resp = self.session.get(HF_PAPERS_URL, timeout=settings.request_timeout)
        resp.raise_for_status()
        return self._parse_papers_html(resp.text)

    def _parse_papers_html(self, html: str) -> list[Article]:
        soup = BeautifulSoup(html, "lxml")
        articles: list[Article] = []

        # Each paper card is typically an <article> or a link block
        for card in soup.select("article, div.paper-card, a[href*='/papers/']"):
            # Try to extract title
            title_tag = card.select_one("h3, h2, .paper-title")
            if not title_tag:
                # If the card itself is an <a>, use its text
                text = card.get_text(strip=True)
                if len(text) < 10:
                    continue
                title = text[:200]
            else:
                title = title_tag.get_text(strip=True)

            # Extract link
            link_tag = card if card.name == "a" else card.select_one("a[href*='/papers/']")
            if link_tag and link_tag.get("href"):
                href = link_tag["href"]
                url = href if href.startswith("http") else f"https://huggingface.co{href}"
            else:
                continue

            # Avoid duplicates within the same parse
            articles.append(
                Article(
                    title=title,
                    url=url,
                    source="huggingface",
                    description="",
                    tags=["paper"],
                )
            )

        # Deduplicate by URL
        seen: set[str] = set()
        unique: list[Article] = []
        for a in articles:
            if a.url not in seen:
                seen.add(a.url)
                unique.append(a)

        return unique
