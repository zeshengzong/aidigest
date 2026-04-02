"""
summarizer.py – LLM-powered summarisation for articles.

Supports OpenAI and Anthropic backends. The provider is chosen via the
``LLM_PROVIDER`` setting. Summaries are generated in the language
specified by ``SUMMARY_LANGUAGE`` (default: "zh" for Chinese).
"""

from __future__ import annotations

import logging
from typing import List

from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.models import Article

logger = logging.getLogger(__name__)

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
        from openai import OpenAI  # lazy import

        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
    def complete(self, system: str, user: str) -> str:
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


class _AnthropicSummarizer:
    """Wrapper around the Anthropic messages API."""

    def __init__(self) -> None:
        from anthropic import Anthropic  # lazy import

        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
    def complete(self, system: str, user: str) -> str:
        resp = self.client.messages.create(
            model=self.model,
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=300,
            temperature=0.3,
        )
        return resp.content[0].text.strip()


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------
def _get_backend():
    if settings.llm_provider == "openai":
        return _OpenAISummarizer()
    elif settings.llm_provider == "anthropic":
        return _AnthropicSummarizer()
    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")


def _has_api_key() -> bool:
    """Check whether the active provider has an API key configured."""
    if settings.llm_provider == "openai" and not settings.openai_api_key:
        return False
    if settings.llm_provider == "anthropic" and not settings.anthropic_api_key:
        return False
    return True


def summarize_articles(
    articles: List[Article], top_story: Article | None = None
) -> List[Article]:
    """Add an LLM-generated ``summary`` field to each article.

    If no API key is configured, articles are returned with a placeholder.
    """
    if not _has_api_key():
        logger.warning("No API key configured – skipping summarisation.")
        return _fallback_summaries(articles)

    try:
        backend = _get_backend()
    except Exception as exc:
        logger.error("Could not initialise LLM backend: %s", exc)
        return _fallback_summaries(articles)

    for i, article in enumerate(articles):
        is_top = top_story and article.url == top_story.url
        system = TOP_STORY_SYSTEM_PROMPT if is_top else SYSTEM_PROMPT

        user_msg = (
            f"Title: {article.title}\n"
            f"Description: {article.description}\n"
            f"Source: {article.source}\n"
            f"Category: {article.category}"
        )

        try:
            article.summary = backend.complete(system, user_msg)
            logger.debug("Summarised [%d/%d]: %s", i + 1, len(articles), article.title[:60])
        except Exception as exc:
            logger.warning("Summary failed for '%s': %s", article.title[:40], exc)
            article.summary = article.description[:200] if article.description else article.title

    return articles


def generate_overview(articles: List[Article]) -> str:
    """Generate a daily overview paragraph from all article headlines."""
    if not _has_api_key():
        return ""

    try:
        backend = _get_backend()
    except Exception:
        return ""

    # Build a compact headline list grouped by category
    lines: list[str] = []
    for a in articles:
        cat = a.category or "AI"
        lines.append(f"[{cat}] {a.title} (source: {a.source})")

    user_msg = f"Today's AI news headlines ({len(articles)} items):\n" + "\n".join(lines)

    try:
        return backend.complete(OVERVIEW_SYSTEM_PROMPT, user_msg)
    except Exception as exc:
        logger.warning("Overview generation failed: %s", exc)
        return ""


def _fallback_summaries(articles: List[Article]) -> List[Article]:
    """Use the raw description as a fallback summary when no LLM is available."""
    for article in articles:
        article.summary = article.description[:200] if article.description else article.title
    return articles
