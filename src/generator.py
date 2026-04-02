"""
generator.py – Render the daily digest to Markdown.

Takes a ``Digest`` model and writes it to the archives folder as
``YYYY-MM-DD.md``, then updates a top-level ``DIGEST.md`` index file.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.config import settings
from src.models import Article, Digest

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def render_digest(digest: Digest) -> str:
    """Render a Digest object into a Markdown string."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("digest.md.j2")

    return template.render(
        date=digest.date,
        overview=digest.overview,
        top_story=digest.top_story,
        articles=digest.articles,
        generated_at=digest.generated_at.strftime("%Y-%m-%d %H:%M UTC"),
    )


def save_digest(digest: Digest) -> Path:
    """Render and write the digest to ``archives/YYYY-MM-DD.md``."""
    md_content = render_digest(digest)

    out_path = settings.archives_path / f"{digest.date}.md"
    out_path.write_text(md_content, encoding="utf-8")
    logger.info("Digest saved to %s", out_path)

    # Also update the top-level index
    _update_index(digest.date, out_path)

    return out_path


def _update_index(date: str, digest_path: Path) -> None:
    """Add the latest digest link to the top of DIGEST.md."""
    index_path = settings.project_root / "DIGEST.md"
    relative = digest_path.relative_to(settings.project_root)

    new_entry = f"- [{date}]({relative})\n"

    if index_path.exists():
        existing = index_path.read_text(encoding="utf-8")
        # Avoid duplicate entries
        if new_entry.strip() in existing:
            return
        # Insert after the header line
        lines = existing.splitlines(keepends=True)
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("# "):
                insert_idx = i + 1
                break
        lines.insert(insert_idx, "\n" + new_entry)
        index_path.write_text("".join(lines), encoding="utf-8")
    else:
        content = "# 🤖 AI Digest – Archive Index\n\n" + new_entry
        index_path.write_text(content, encoding="utf-8")

    logger.info("Updated index at %s", index_path)
