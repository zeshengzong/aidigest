"""
summarizer.py – LLM-powered summarisation for articles.

Supports OpenAI and Anthropic backends. The provider is chosen via the
``LLM_PROVIDER`` setting. Summaries are generated in the language
specified by ``SUMMARY_LANGUAGE`` (default: "zh" for Chinese).

Rate-limit handling:
  - 429 responses are caught and retried with exponential back-off (up to 60 s).
  - A configurable inter-request delay (SUMMARIZE_DELAY_SECONDS) throttles the
    request cadence to stay within RPM quotas.
  - Only the top-N articles by score are summarised (SUMMARIZE_MAX_ARTICLES)
    to cap total API calls per run.
"""

from __future__ import annotations

import logging
import time
from typing import List

from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
    wait_random_exponential,
)

from src.config import settings
from src.models import Article

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers – detect rate-limit errors across providers
# ---------------------------------------------------------------------------

def _is_rate_limit_error(exc: BaseException) -> bool:
    """Return True for HTTP 429 / RateLimitError from any provider."""
    cls_name = type(exc).__name__.lower()
    if "ratelimit" in cls_name or "rate_limit" in cls_name:
        return True
    # openai raises openai.RateLimitError; anthropic raises anthropic.RateLimitError
    # Both carry a status_code attribute
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status == 429:
        return True
    # httpx / requests wrapped errors
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "too many requests" in msg


# ---------------------------------------------------------------------------
# Language-aware system prompts
# ---------------------------------------------------------------------------

_LANG_INSTRUCTION = {
    "zh": "请使用中文回复。",
    "en": "Reply in English.",
}


def _lang_hint() -> str:
    return _LANG_INSTRUCTION.get(settings.summary_language, "Reply in English.")


SYSTEM_PROMPT = (
    "You are an expert tech journalist. "
    "Given the title and description of an AI-related news item, "
    "write a crisp, informative one-sentence summary (max 40 words). "
    "Return ONLY the summary sentence, nothing else. "
    + _lang_hint()
)

TOP_STORY_SYSTEM_PROMPT = (
    "You are an expert tech journalist. "
    "Given the title and description of the top AI news story of the day, "
    "write a short, engaging paragraph summary (3-5 sentences, max 100 words). "
    "Highlight why this matters for the AI community. "
    "Return ONLY the summary paragraph, nothing else. "
    + _lang_hint()
)

TAGLINE_SYSTEM_PROMPT = (
    "You are an expert tech journalist writing a daily AI newsletter. "
    "Given a list of today's AI news headlines and their categories, "
    "write a summary paragraph (around 200 Chinese characters / 100 English words) "
    "that captures the key themes, notable releases, and most exciting breakthroughs of the day. "
    "Be vivid and specific – name key products, companies, or papers. "
    "Cover 3-5 highlights, weaving them into a cohesive narrative. "
    "Return ONLY the summary paragraph, nothing else. "
    + _lang_hint()
)

OVERVIEW_SYSTEM_PROMPT = (
    "You are an expert tech journalist writing a daily AI newsletter. "
    "Given a list of today's AI news headlines and their categories, "
    "write a concise overview paragraph (3-5 sentences, max 150 words) "
    "that captures the key themes and trends of the day. "
    "Mention the most notable developments. "
    "Do NOT list individual articles – synthesize the overall picture. "
    "Return ONLY the overview paragraph, nothing else. "
    + _lang_hint()
)


# ---------------------------------------------------------------------------
# Provider Clients
# ---------------------------------------------------------------------------

class _OpenAISummarizer:
    """Wrapper around the OpenAI chat completions API."""

    def __init__(self) -> None:
        from openai import OpenAI
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    # Retry on rate limit with long random back-off; retry on transient errors
    @retry(
        retry=retry_if_exception(_is_rate_limit_error),
        wait=wait_random_exponential(min=10, max=90),
        stop=stop_after_attempt(6),
        reraise=True,
    )
    def _complete_with_rate_retry(self, system: str, user: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=300,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()

    # Outer retry for transient network / server errors (non-429)
    @retry(
        retry=retry_if_exception(lambda e: not _is_rate_limit_error(e)),
        wait=wait_exponential(min=2, max=20),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def complete(self, system: str, user: str) -> str:
        return self._complete_with_rate_retry(system, user)


class _AnthropicSummarizer:
    """Wrapper around the Anthropic messages API."""

    def __init__(self) -> None:
        from anthropic import Anthropic
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    @retry(
        retry=retry_if_exception(_is_rate_limit_error),
        wait=wait_random_exponential(min=10, max=90),
        stop=stop_after_attempt(6),
        reraise=True,
    )
    def _complete_with_rate_retry(self, system: str, user: str) -> str:
        resp = self.client.messages.create(
            model=self.model,
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=300,
            temperature=0.3,
        )
        return resp.content[0].text.strip()

    @retry(
        retry=retry_if_exception(lambda e: not _is_rate_limit_error(e)),
        wait=wait_exponential(min=2, max=20),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def complete(self, system: str, user: str) -> str:
        return self._complete_with_rate_retry(system, user)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def _get_backend() -> _OpenAISummarizer | _AnthropicSummarizer:
    if settings.llm_provider == "openai":
        return _OpenAISummarizer()
    elif settings.llm_provider == "anthropic":
        return _AnthropicSummarizer()
    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")


def _has_api_key() -> bool:
    if settings.llm_provider == "openai" and not settings.openai_api_key:
        return False
    if settings.llm_provider == "anthropic" and not settings.anthropic_api_key:
        return False
    return True


def _select_articles_for_summary(
    articles: List[Article], top_story: Article | None
) -> List[Article]:
    """
    Return the subset of articles that will receive LLM summaries.

    Priority order:
      1. Top story (always included)
      2. Remaining articles sorted by score (desc), capped at SUMMARIZE_MAX_ARTICLES
    """
    cap = settings.summarize_max_articles
    if cap <= 0:
        return articles  # 0 means unlimited

    selected: list[Article] = []
    top_url = top_story.url if top_story else None

    # Always summarise the top story first
    if top_story:
        selected.append(top_story)

    # Add remaining articles by score until cap is reached
    others = sorted(
        [a for a in articles if a.url != top_url],
        key=lambda a: a.score or 0,
        reverse=True,
    )
    for a in others:
        if len(selected) >= cap:
            break
        selected.append(a)

    skipped = len(articles) - len(selected)
    if skipped > 0:
        logger.info(
            "Rate-limit protection: summarising %d/%d articles (skipping %d low-priority).",
            len(selected), len(articles), skipped,
        )
    return selected


def summarize_articles(
    articles: List[Article], top_story: Article | None = None
) -> List[Article]:
    """Add an LLM-generated ``summary`` field to each article.

    Articles not selected for summarisation fall back to their description.
    """
    if not _has_api_key():
        logger.warning("No API key configured – skipping summarisation.")
        return _fallback_summaries(articles)

    try:
        backend = _get_backend()
    except Exception as exc:
        logger.error("Could not initialise LLM backend: %s", exc)
        return _fallback_summaries(articles)

    # First, fall back all articles so un-selected ones have a summary
    articles = _fallback_summaries(articles)

    # Determine which articles actually get LLM calls
    to_summarise = _select_articles_for_summary(articles, top_story)
    to_summarise_urls = {a.url for a in to_summarise}

    delay = settings.summarize_delay_seconds
    total = len(to_summarise)

    for i, article in enumerate(articles):
        if article.url not in to_summarise_urls:
            continue  # already has fallback summary

        is_top = top_story and article.url == top_story.url
        system = TOP_STORY_SYSTEM_PROMPT if is_top else SYSTEM_PROMPT
        user_msg = (
            f"Title: {article.title}\n"
            f"Description: {article.description}\n"
            f"Source: {article.source}\n"
            f"Category: {article.category}"
        )

        # Throttle: sleep between calls (skip before the very first call)
        idx_in_batch = sum(1 for a in articles[:i] if a.url in to_summarise_urls)
        if delay > 0 and idx_in_batch > 0:
            time.sleep(delay)

        try:
            article.summary = backend.complete(system, user_msg)
            logger.info(
                "Summarised [%d/%d]: %s",
                idx_in_batch + 1, total, article.title[:60],
            )
        except Exception as exc:
            logger.warning("Summary failed for '%s': %s", article.title[:40], exc)
            # Keep the fallback summary already set

    return articles


def _build_headlines_msg(articles: List[Article]) -> str:
    """Build a user message listing all article headlines for LLM prompts."""
    lines: list[str] = []
    for a in articles:
        cat = a.category or "AI"
        lines.append(f"[{cat}] {a.title} (source: {a.source})")
    return (
        f"Today's AI news headlines ({len(articles)} items):\n"
        + "\n".join(lines)
    )


def generate_tagline(articles: List[Article]) -> str:
    """Generate a one-sentence tagline summarising the day's core content."""
    if not _has_api_key() or not articles:
        return ""

    try:
        backend = _get_backend()
    except Exception:
        return ""

    try:
        return backend.complete(TAGLINE_SYSTEM_PROMPT, _build_headlines_msg(articles))
    except Exception as exc:
        logger.warning("Tagline generation failed: %s", exc)
        return ""


def generate_overview(articles: List[Article]) -> str:
    """Generate a daily overview paragraph from all article headlines."""
    if not _has_api_key():
        return ""

    try:
        backend = _get_backend()
    except Exception:
        return ""

    try:
        return backend.complete(OVERVIEW_SYSTEM_PROMPT, _build_headlines_msg(articles))
    except Exception as exc:
        logger.warning("Overview generation failed: %s", exc)
        return ""


def _fallback_summaries(articles: List[Article]) -> List[Article]:
    """Use the raw description as a fallback summary when no LLM is available."""
    for article in articles:
        if not article.summary:  # don't overwrite existing summaries
            article.summary = (
                article.description[:200] if article.description else article.title
            )
    return articles
