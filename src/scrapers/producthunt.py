"""
producthunt.py – Product Hunt AI product scraper.

Scrapes today's AI-related product launches from Product Hunt.
Uses the public website with JSON endpoints (no API key required).
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

PH_URL = "https://www.producthunt.com"


class ProductHuntScraper:
    """Scrape today's AI-related products from Product Hunt."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": settings.user_agent,
            "Accept": "text/html,application/xhtml+xml",
        })
        self.ai_re = re.compile(settings.ai_pattern())

    # -- public --------------------------------------------------------------

    def scrape(self) -> List[Article]:
        """Return AI-related products launched today on Product Hunt."""
        logger.info("Fetching Product Hunt …")
        articles: list[Article] = []

        # Try API-style endpoint first, fall back to HTML scraping
        try:
            articles = self._fetch_via_api()
        except Exception as exc:
            logger.warning("PH API-style fetch failed (%s), trying HTML …", exc)
            try:
                articles = self._fetch_via_html()
            except Exception as exc2:
                logger.error("PH HTML fetch also failed: %s", exc2)
                return []

        # Filter for AI-related products
        ai_articles = [a for a in articles if self._is_ai_related(a)]

        # Deduplicate
        seen: set[str] = set()
        unique: list[Article] = []
        for a in ai_articles:
            if a.url not in seen:
                seen.add(a.url)
                unique.append(a)

        result = unique[: settings.ph_max_products]
        logger.info("ProductHunt: found %d AI products.", len(result))
        return result

    # -- private: API-style --------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
    def _fetch_via_api(self) -> list[Article]:
        """Try the Product Hunt frontend API for today's posts."""
        # PH exposes a GraphQL endpoint; we use a lightweight approach
        # by fetching the leaderboard page which contains structured data
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        url = f"{PH_URL}/leaderboard/daily/{today}/all"

        resp = self.session.get(url, timeout=settings.request_timeout)
        resp.raise_for_status()
        return self._parse_html(resp.text)

    # -- private: HTML fallback ----------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
    def _fetch_via_html(self) -> list[Article]:
        """Scrape the Product Hunt homepage."""
        resp = self.session.get(PH_URL, timeout=settings.request_timeout)
        resp.raise_for_status()
        return self._parse_html(resp.text)

    def _parse_html(self, html: str) -> list[Article]:
        """Parse product cards from Product Hunt HTML."""
        soup = BeautifulSoup(html, "lxml")
        articles: list[Article] = []

        # Product Hunt uses various card layouts; try multiple selectors
        # Strategy 1: data-test attributes
        cards = soup.select("[data-test='post-item'], [data-test='post-name']")
        if not cards:
            # Strategy 2: common link patterns to /posts/
            cards = soup.select("a[href*='/posts/']")

        seen_urls: set[str] = set()

        for card in cards:
            # Extract link
            if card.name == "a":
                link = card
            else:
                link = card.select_one("a[href*='/posts/']")
            if not link:
                continue

            href = link.get("href", "")
            if not href or href in seen_urls:
                continue
            seen_urls.add(href)

            url = href if href.startswith("http") else f"{PH_URL}{href}"

            # Extract title
            title = ""
            # Try heading elements inside the card
            for sel in ["h3", "h2", "[data-test='post-name']", "strong"]:
                title_el = card.select_one(sel) if card.name != "a" else None
                if title_el:
                    title = title_el.get_text(strip=True)
                    break
            if not title:
                title = link.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            # Extract tagline / description
            description = ""
            desc_el = card.select_one(
                "[data-test='tagline'], p, .text-secondary, .tagline"
            )
            if desc_el:
                description = desc_el.get_text(strip=True)

            # Extract vote count
            score = 0
            vote_el = card.select_one(
                "[data-test='vote-button'] span, .vote-count, button[class*='vote'] span"
            )
            if vote_el:
                digits = re.sub(r"[^\d]", "", vote_el.get_text(strip=True))
                if digits:
                    score = int(digits)

            articles.append(
                Article(
                    title=title[:200],
                    url=url,
                    source="producthunt",
                    description=description[:300],
                    score=score if score > 0 else None,
                    tags=["product"],
                )
            )

        return articles

    def _is_ai_related(self, article: Article) -> bool:
        text = f"{article.title} {article.description} {' '.join(article.tags)}"
        return bool(self.ai_re.search(text))
