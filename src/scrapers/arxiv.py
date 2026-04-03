"""
arxiv.py – ArXiv paper scraper.

Fetches recent AI-related papers from the ArXiv API across key categories:
cs.AI, cs.CL, cs.CV, cs.LG, cs.MA, stat.ML.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import List
from xml.etree import ElementTree as ET

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.models import Article

logger = logging.getLogger(__name__)

# ArXiv API base URL
ARXIV_API_URL = "http://export.arxiv.org/api/query"

# ArXiv categories relevant to AI
AI_CATEGORIES = ["cs.AI", "cs.CL", "cs.CV", "cs.LG", "cs.MA", "stat.ML"]

# Atom XML namespaces
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


class ArxivScraper:
    """Fetch recent AI papers from the ArXiv API."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": settings.user_agent})

    # -- public --------------------------------------------------------------

    def scrape(self) -> List[Article]:
        """Return recent AI papers from ArXiv."""
        logger.info("Fetching ArXiv papers …")

        try:
            articles = self._fetch_papers()
        except Exception as exc:
            logger.error("ArXiv scrape failed: %s", exc)
            return []

        # Deduplicate by URL
        seen: set[str] = set()
        unique: list[Article] = []
        for a in articles:
            if a.url not in seen:
                seen.add(a.url)
                unique.append(a)

        logger.info("ArXiv: found %d papers.", len(unique))
        return unique[: settings.arxiv_max_papers]

    # -- private -------------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
    def _fetch_papers(self) -> list[Article]:
        """Query ArXiv API for recent papers in AI categories."""
        # Build search query: OR across AI categories
        cat_query = " OR ".join(f"cat:{cat}" for cat in AI_CATEGORIES)
        search_query = f"({cat_query})"

        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": settings.arxiv_max_papers,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        resp = self.session.get(ARXIV_API_URL, params=params, timeout=settings.request_timeout)
        resp.raise_for_status()

        return self._parse_atom(resp.text)

    def _parse_atom(self, xml_text: str) -> list[Article]:
        """Parse the Atom XML feed from ArXiv."""
        root = ET.fromstring(xml_text)
        articles: list[Article] = []

        for entry in root.findall("atom:entry", _NS):
            title_el = entry.find("atom:title", _NS)
            summary_el = entry.find("atom:summary", _NS)
            published_el = entry.find("atom:published", _NS)

            if title_el is None:
                continue

            # Clean title (ArXiv titles often have line breaks)
            title = re.sub(r"\s+", " ", (title_el.text or "")).strip()

            # Abstract
            abstract = ""
            if summary_el is not None and summary_el.text:
                abstract = re.sub(r"\s+", " ", summary_el.text).strip()

            # URL – prefer the abstract page link
            url = ""
            for link in entry.findall("atom:link", _NS):
                if link.get("type") == "text/html":
                    url = link.get("href", "")
                    break
            if not url:
                id_el = entry.find("atom:id", _NS)
                url = id_el.text.strip() if id_el is not None and id_el.text else ""

            # Published date
            published = None
            if published_el is not None and published_el.text:
                try:
                    published = datetime.fromisoformat(
                        published_el.text.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            # Authors
            authors = []
            for author_el in entry.findall("atom:author", _NS):
                name_el = author_el.find("atom:name", _NS)
                if name_el is not None and name_el.text:
                    authors.append(name_el.text.strip())
            author_str = ", ".join(authors[:3])
            if len(authors) > 3:
                author_str += f" et al. ({len(authors)} authors)"

            # Categories as tags
            tags = ["paper"]
            for cat_el in entry.findall("arxiv:primary_category", _NS):
                cat_term = cat_el.get("term", "")
                if cat_term:
                    tags.append(cat_term)
            for cat_el in entry.findall("atom:category", _NS):
                cat_term = cat_el.get("term", "")
                if cat_term and cat_term not in tags:
                    tags.append(cat_term)

            articles.append(
                Article(
                    title=title,
                    url=url,
                    source="arxiv",
                    description=abstract[:500],
                    author=author_str,
                    tags=tags[:8],
                    published_at=published,
                )
            )

        return articles
