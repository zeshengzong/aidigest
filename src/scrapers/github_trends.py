"""
github_trends.py – GitHub Trending scraper.

Scrapes the GitHub Trending page for repositories and filters for AI/ML
projects by matching descriptions and topics against keyword patterns.
"""

from __future__ import annotations

import logging
import re
from typing import List

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.models import Article

logger = logging.getLogger(__name__)

GITHUB_TRENDING_URL = "https://github.com/trending"


class GithubTrendsScraper:
    """Scrape today's trending GitHub repos and filter for AI content."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": settings.user_agent,
                "Accept": "text/html",
            }
        )
        self.ai_re = re.compile(settings.ai_pattern())

    # -- public --------------------------------------------------------------

    def scrape(self) -> List[Article]:
        """Return AI-related trending repos."""
        logger.info("Fetching GitHub Trending page …")
        articles: list[Article] = []

        for lang in ("python", ""):
            try:
                repos = self._fetch_trending(language=lang)
                for repo in repos[: settings.github_max_repos]:
                    if self._is_ai_related(repo):
                        articles.append(repo)
            except Exception as exc:
                logger.error("GitHub Trends scrape failed (lang=%s): %s", lang, exc)

        # Deduplicate by URL
        seen: set[str] = set()
        unique: list[Article] = []
        for a in articles:
            if a.url not in seen:
                seen.add(a.url)
                unique.append(a)

        logger.info("GitHub: found %d AI-related repos.", len(unique))
        return unique[: settings.github_max_repos]

    # -- private -------------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def _fetch_trending(self, language: str = "") -> list[Article]:
        url = GITHUB_TRENDING_URL
        params: dict = {"since": "daily"}
        if language:
            url = f"{GITHUB_TRENDING_URL}/{language}"

        resp = self.session.get(url, params=params, timeout=settings.request_timeout)
        resp.raise_for_status()
        return self._parse_html(resp.text)

    def _parse_html(self, html: str) -> list[Article]:
        soup = BeautifulSoup(html, "lxml")
        articles: list[Article] = []

        for row in soup.select("article.Box-row"):
            # Repo name (e.g. "owner / repo")
            h2 = row.select_one("h2 a")
            if not h2:
                continue
            href = h2.get("href", "").strip()
            full_name = href.lstrip("/")
            repo_url = f"https://github.com{href}"

            # Description
            desc_tag = row.select_one("p")
            description = desc_tag.get_text(strip=True) if desc_tag else ""

            # Total stars – try multiple selectors for robustness
            total_stars = self._extract_total_stars(row)

            # Stars today
            stars_today = self._extract_today_stars(row)

            # Language
            lang_span = row.select_one("span[itemprop='programmingLanguage']")
            language = lang_span.get_text(strip=True) if lang_span else ""

            tags = [t for t in ["github-trending", language.lower()] if t]

            articles.append(
                Article(
                    title=full_name,
                    url=repo_url,
                    source="github",
                    description=description,
                    score=total_stars,
                    stars_today=stars_today,
                    language=language,
                    tags=tags,
                )
            )

        return articles

    @staticmethod
    def _extract_total_stars(row) -> int:
        """Try multiple strategies to find the total star count."""
        # Strategy 1: <a> linking to /stargazers with star icon nearby
        for link in row.select("a[href$='/stargazers']"):
            text = link.get_text(strip=True).replace(",", "")
            digits = re.sub(r"[^\d]", "", text)
            if digits:
                return int(digits)

        # Strategy 2: generic star links (older layout)
        for link in row.select("a.Link--muted"):
            href = link.get("href", "")
            if "/stargazers" in href:
                text = link.get_text(strip=True).replace(",", "")
                digits = re.sub(r"[^\d]", "", text)
                if digits:
                    return int(digits)

        # Strategy 3: any <a> with class containing 'muted' and a number
        for link in row.select("a[class*='muted']"):
            text = link.get_text(strip=True).replace(",", "")
            if text.isdigit():
                return int(text)

        return 0

    @staticmethod
    def _extract_today_stars(row) -> int:
        """Extract the 'stars today' count."""
        # Usually in a <span> with text like "1,234 stars today"
        for span in row.select("span"):
            text = span.get_text(strip=True)
            if "stars today" in text.lower() or "stars this" in text.lower():
                digits = re.sub(r"[^\d]", "", text.replace(",", ""))
                if digits:
                    return int(digits)
        return 0

    def _is_ai_related(self, article: Article) -> bool:
        text = f"{article.title} {article.description} {' '.join(article.tags)}"
        return bool(self.ai_re.search(text))
