"""
classifier.py – Rule-based topic classifier for articles.

Assigns a human-readable category (e.g. "LLM", "Agent", "CV") to each
article based on keyword matching against title + description + tags.
"""

from __future__ import annotations

import re
from typing import List

from src.models import Article

# Ordered by specificity – first match wins
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("LLM", [
        r"llm", r"large language model", r"gpt", r"claude", r"gemini",
        r"mistral", r"llama", r"qwen", r"deepseek", r"phi-\d",
        r"chat\s*bot", r"instruction.?tun", r"fine.?tun", r"rlhf", r"grpo",
        r"tokeniz", r"prompt",
    ]),
    ("Agent", [
        r"agent", r"multi.?agent", r"orchestrat", r"tool.?use",
        r"function.?call", r"agentic", r"swarm", r"autogen",
        r"crew.?ai", r"langchain", r"langgraph",
    ]),
    ("RAG / Search", [
        r"\brag\b", r"retrieval.?augment", r"vector.?d", r"embedding",
        r"semantic.?search", r"knowledge.?graph", r"rerank",
    ]),
    ("Image / Video", [
        r"diffusion", r"stable.?diffusion", r"image.?gen", r"video.?gen",
        r"text.?to.?image", r"text.?to.?video", r"sora", r"flux",
        r"comfyui", r"controlnet", r"lora",
    ]),
    ("Computer Vision", [
        r"computer.?vision", r"\bcv\b", r"object.?detect", r"segment",
        r"yolo", r"ocr", r"visual", r"3d\b", r"point.?cloud", r"nerf",
    ]),
    ("NLP", [
        r"\bnlp\b", r"natural.?language", r"text.?classif", r"sentiment",
        r"named.?entity", r"translat", r"summar",
    ]),
    ("Audio / Speech", [
        r"speech", r"tts", r"text.?to.?speech", r"asr", r"whisper",
        r"audio", r"music.?gen", r"voice",
    ]),
    ("Robotics", [
        r"robot", r"embodied", r"manipulat", r"locomotion", r"simulation",
    ]),
    ("MLOps / Infra", [
        r"mlops", r"deploy", r"inference", r"quantiz", r"onnx",
        r"tensor.?rt", r"vllm", r"serve", r"benchmark", r"optim",
        r"distill", r"prune", r"accelerat",
    ]),
    ("Open Source", [
        r"open.?source", r"hugging.?face", r"github", r"release",
        r"model.?card", r"weight",
    ]),
    ("AI Safety / Ethics", [
        r"safety", r"align", r"bias", r"fairness", r"interpret",
        r"explain", r"hallucinat", r"guardrail", r"red.?team",
    ]),
    ("Research", [
        r"paper", r"arxiv", r"survey", r"benchmark", r"dataset",
        r"training", r"pre.?train", r"neural.?net", r"deep.?learn",
        r"reinforcement.?learn", r"transformer",
    ]),
]

# Pre-compile patterns
_COMPILED_RULES: list[tuple[str, re.Pattern]] = [
    (cat, re.compile(r"(?i)\b(?:" + "|".join(kws) + r")"))
    for cat, kws in CATEGORY_RULES
]


def classify_article(article: Article) -> str:
    """Return the best-matching category for an article."""
    text = f"{article.title} {article.description} {' '.join(article.tags)}"
    for category, pattern in _COMPILED_RULES:
        if pattern.search(text):
            return category
    return "AI General"


def classify_articles(articles: List[Article]) -> List[Article]:
    """Assign a category to every article in the list."""
    for article in articles:
        article.category = classify_article(article)
    return articles
