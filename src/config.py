"""
config.py – Centralised configuration for AIDigest.

Reads values from a .env file (or real environment variables) and exposes them
as typed, validated settings via Pydantic.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator

# Load .env from project root (two levels up from this file)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    """Application-wide settings, validated at startup."""

    # ---- LLM Provider ------------------------------------------------------
    llm_provider: Literal["openai", "anthropic"] = Field(
        default="openai",
        description="Which LLM backend to use for summarisation.",
    )

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _default_llm_provider(cls, v: str) -> str:
        """Fall back to 'openai' when the env var is empty or unset."""
        if not v or v.strip() == "":
            return "openai"
        return v.strip().lower()

    # OpenAI
    openai_api_key: str = Field(default="", description="OpenAI API key.")
    openai_model: str = Field(default="gpt-4o", description="OpenAI model name.")

    # Anthropic
    anthropic_api_key: str = Field(default="", description="Anthropic API key.")
    anthropic_model: str = Field(
        default="claude-sonnet-4-20250514", description="Anthropic model name."
    )

    @field_validator("openai_model", "anthropic_model", mode="before")
    @classmethod
    def _default_model(cls, v: str, info) -> str:
        """Keep default model when env var is empty."""
        if not v or v.strip() == "":
            defaults = {"openai_model": "gpt-4o", "anthropic_model": "claude-sonnet-4-20250514"}
            return defaults.get(info.field_name, v)
        return v.strip()

    # ---- Scraping ----------------------------------------------------------
    hn_max_stories: int = Field(default=30, ge=1, le=500)
    github_max_repos: int = Field(default=20, ge=1, le=100)
    hf_max_items: int = Field(default=20, ge=1, le=100)

    # AI-keyword filter (case-insensitive regex fragments)
    ai_keywords: list[str] = Field(
        default=[
            "ai", "artificial intelligence", "machine learning", "deep learning",
            "llm", "large language model", "gpt", "transformer", "diffusion",
            "neural network", "nlp", "computer vision", "reinforcement learning",
            "generative", "openai", "anthropic", "mistral", "llama", "stable diffusion",
            "langchain", "rag", "retrieval augmented", "fine-tune", "fine-tuning",
            "embedding", "vector database", "multimodal", "agent", "copilot",
        ],
    )

    # ---- Output ------------------------------------------------------------
    archives_dir: str = Field(default="archives")
    summary_language: str = Field(
        default="zh",
        description="Language for LLM summaries: 'zh' (Chinese) or 'en' (English).",
    )

    @field_validator("summary_language", mode="before")
    @classmethod
    def _default_summary_language(cls, v: str) -> str:
        if not v or v.strip() == "":
            return "zh"
        return v.strip().lower()

    # ---- Misc --------------------------------------------------------------
    request_timeout: int = Field(default=30, description="HTTP timeout in seconds.")
    user_agent: str = Field(
        default="AIDigest/1.0 (https://github.com/zeshengzong/aidigest)",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    # ---- Helpers -----------------------------------------------------------
    @property
    def project_root(self) -> Path:
        return _PROJECT_ROOT

    @property
    def archives_path(self) -> Path:
        p = _PROJECT_ROOT / self.archives_dir
        p.mkdir(parents=True, exist_ok=True)
        return p

    def ai_pattern(self) -> str:
        """Return a compiled-ready regex pattern from the keyword list."""
        import re
        escaped = [re.escape(kw) for kw in self.ai_keywords]
        return r"(?i)\b(?:" + "|".join(escaped) + r")\b"


# Singleton – import this everywhere
settings = Settings()
