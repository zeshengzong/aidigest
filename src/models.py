"""
models.py – Shared data models for AIDigest.

Every scraper must return a list of `Article` objects so the rest of the
pipeline is source-agnostic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Article(BaseModel):
    """A single news / repo / paper item."""

    title: str = Field(..., description="Headline or repository name.")
    url: str = Field(..., description="Canonical link to the item.")
    source: str = Field(
        ..., description="Origin platform, e.g. 'hackernews', 'github', 'huggingface'."
    )
    description: str = Field(
        default="", description="Short blurb or repo description."
    )
    score: Optional[int] = Field(
        default=None, description="Upvotes / stars / likes (for ranking)."
    )
    author: Optional[str] = Field(default=None)
    tags: list[str] = Field(default_factory=list)
    published_at: Optional[datetime] = Field(default=None)

    # GitHub-specific
    stars_today: Optional[int] = Field(default=None, description="Stars gained today.")
    language: Optional[str] = Field(default=None, description="Programming language.")

    # HN-specific
    comment_count: Optional[int] = Field(default=None, description="Number of comments.")

    # Topic category assigned by classifier
    category: str = Field(default="", description="Topic category, e.g. 'LLM', 'Agent', 'CV'.")

    # Populated by the summariser
    summary: str = Field(default="", description="LLM-generated summary.")


class Digest(BaseModel):
    """A complete daily digest ready for rendering."""

    date: str = Field(
        ..., description="ISO date string (YYYY-MM-DD) for this digest."
    )
    overview: str = Field(
        default="", description="LLM-generated daily overview paragraph."
    )
    top_story: Optional[Article] = Field(
        default=None, description="The highest-scoring article of the day."
    )
    articles: list[Article] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
