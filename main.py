#!/usr/bin/env python3
"""
main.py – Entry point for AIDigest.

Orchestrates:  Scrape → Summarise → Generate Markdown digest.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timezone

from src.config import settings
from src.models import Article, Digest
from src.scrapers import run_all_scrapers
from src.summarizer import summarize_articles
from src.generator import save_digest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("aidigest")


def build_digest(target_date: str | None = None) -> Digest:
    """Run the full pipeline and return a Digest object."""

    today = target_date or date.today().isoformat()
    logger.info("=" * 60)
    logger.info("AIDigest – building digest for %s", today)
    logger.info("=" * 60)

    # ---- 1. Scrape ---------------------------------------------------------
    logger.info("Step 1/3: Scraping sources …")
    articles = run_all_scrapers()

    if not articles:
        logger.warning("No articles collected from any source. Digest will be empty.")

    # ---- 2. Rank & pick top story ------------------------------------------
    scored = [a for a in articles if a.score is not None]
    scored.sort(key=lambda a: a.score or 0, reverse=True)
    top_story = scored[0] if scored else None

    # ---- 3. Summarise ------------------------------------------------------
    logger.info("Step 2/3: Summarising %d articles …", len(articles))
    articles = summarize_articles(articles, top_story=top_story)

    # Refresh top_story reference after summarisation
    if top_story:
        for a in articles:
            if a.url == top_story.url:
                top_story = a
                break

    # ---- 4. Generate Markdown ----------------------------------------------
    logger.info("Step 3/3: Generating Markdown …")
    digest = Digest(
        date=today,
        top_story=top_story,
        articles=articles,
        generated_at=datetime.now(tz=timezone.utc),
    )
    out_path = save_digest(digest)

    logger.info("✅ Done! Digest written to: %s", out_path)
    return digest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AIDigest – Daily AI News Digest Generator",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Override digest date (YYYY-MM-DD). Defaults to today.",
    )
    args = parser.parse_args()

    try:
        build_digest(target_date=args.date)
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
        sys.exit(130)
    except Exception as exc:
        logger.exception("Fatal error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
