"""
scrapers – Unified interface for all data sources.

Usage:
    from src.scrapers import run_all_scrapers
    articles = run_all_scrapers()
"""

from __future__ import annotations

import logging
from typing import List

from src.models import Article
from src.scrapers.hackernews import HackerNewsScraper
from src.scrapers.github_trends import GithubTrendsScraper
from src.scrapers.huggingface import HuggingFaceScraper
from src.scrapers.arxiv import ArxivScraper
from src.scrapers.reddit import RedditScraper
from src.scrapers.producthunt import ProductHuntScraper
from src.scrapers.ai_blogs import AIBlogsScraper

logger = logging.getLogger(__name__)

__all__ = [
    "HackerNewsScraper",
    "GithubTrendsScraper",
    "HuggingFaceScraper",
    "ArxivScraper",
    "RedditScraper",
    "ProductHuntScraper",
    "AIBlogsScraper",
    "run_all_scrapers",
]


def run_all_scrapers() -> List[Article]:
    """Execute every registered scraper and merge results.

    If an individual scraper raises, it is caught and logged so the
    remaining scrapers still run.
    """
    all_articles: list[Article] = []

    scrapers = [
        ("HackerNews", HackerNewsScraper()),
        ("GitHubTrends", GithubTrendsScraper()),
        ("HuggingFace", HuggingFaceScraper()),
        ("ArXiv", ArxivScraper()),
        ("Reddit", RedditScraper()),
        ("ProductHunt", ProductHuntScraper()),
        ("AIBlogs", AIBlogsScraper()),
    ]

    for name, scraper in scrapers:
        try:
            articles = scraper.scrape()
            all_articles.extend(articles)
            logger.info("✓ %s returned %d articles.", name, len(articles))
        except Exception as exc:
            logger.error("✗ %s scraper failed: %s", name, exc)

    logger.info("Total articles collected: %d", len(all_articles))
    return all_articles
