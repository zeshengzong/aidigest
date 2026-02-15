# 🤖 AIDigest

**Automated daily AI news digest** — crawls Hacker News, GitHub Trends, and Hugging Face, then uses an LLM to summarise everything into a clean Markdown report.

## Features

- **Multi-source scraping** — Hacker News (API), GitHub Trending (HTML), Hugging Face models & papers
- **Smart filtering** — Keyword-based AI/ML content detection across all sources
- **LLM summarisation** — Pluggable backend (OpenAI *or* Anthropic) generates concise summaries
- **Graceful degradation** — If one scraper or the LLM fails, the rest still runs
- **Daily automation** — GitHub Actions workflow runs on a cron schedule and commits results
- **Markdown output** — Clean, readable digest with tables, top-story highlight, and archive index

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/yourname/aidigest.git
cd aidigest
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your API key(s)
```

| Variable | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | Yes | `openai` or `anthropic` |
| `OPENAI_API_KEY` | If using OpenAI | Your OpenAI API key |
| `ANTHROPIC_API_KEY` | If using Anthropic | Your Anthropic API key |

### 3. Run

```bash
python main.py              # Generate today's digest
python main.py --date 2026-02-14  # Override the date
```

The digest is saved to `archives/YYYY-MM-DD.md` and an index is maintained at `DIGEST.md`.

## Project Structure

```
aidigest/
├── main.py                          # Entry point
├── requirements.txt
├── .env.example
├── .github/workflows/
│   └── daily_digest.yml             # Cron-based GitHub Actions workflow
├── src/
│   ├── config.py                    # Settings & env loading (Pydantic)
│   ├── models.py                    # Article / Digest data models
│   ├── summarizer.py                # LLM summarisation (OpenAI / Anthropic)
│   ├── generator.py                 # Jinja2 → Markdown rendering
│   ├── templates/
│   │   └── digest.md.j2             # Digest Markdown template
│   └── scrapers/
│       ├── __init__.py              # run_all_scrapers() orchestrator
│       ├── hackernews.py            # Hacker News API scraper
│       ├── github_trends.py         # GitHub Trending HTML scraper
│       └── huggingface.py           # HF models API + papers scraper
└── archives/                        # Generated digests (git-tracked)
```

## GitHub Actions (Automation)

The included workflow runs daily at 08:00 UTC. To enable it:

1. Push this repo to GitHub.
2. Go to **Settings → Secrets and variables → Actions**.
3. Add `LLM_PROVIDER`, `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`).
4. The workflow will auto-commit each day's digest.

You can also trigger it manually from the **Actions** tab.

## How It Works

```
┌─────────────┐   ┌──────────────┐   ┌──────────────┐
│ Hacker News │   │ GitHub Trends│   │ Hugging Face │
└──────┬──────┘   └──────┬───────┘   └──────┬───────┘
       │                 │                   │
       └────────┬────────┘───────────────────┘
                │
         ┌──────▼──────┐
         │  AI Keyword  │
         │   Filter     │
         └──────┬──────┘
                │
         ┌──────▼──────┐
         │  LLM Summary │  (OpenAI / Anthropic)
         └──────┬──────┘
                │
         ┌──────▼──────┐
         │  Jinja2      │
         │  Renderer    │
         └──────┬──────┘
                │
         ┌──────▼──────┐
         │ archives/    │
         │ 2026-02-14.md│
         └─────────────┘
```

## License

MIT — see [LICENSE](LICENSE).