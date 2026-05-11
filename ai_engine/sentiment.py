"""
Layer 03 · AI Engine — Ollama Sentiment (Llama 3.1)
Scores each stock's recent news headlines -1.0 to +1.0,
then normalises to 0-100 for the signal aggregator.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from config.settings import OLLAMA_HOST, OLLAMA_MODEL
from data_ingestion.news_fetcher import get_recent_headlines
from storage.cache import cache_score, get_cached_score
from storage.database import get_session
from storage.models import NewsItem

logger = logging.getLogger(__name__)

SENTIMENT_PROMPT = """\
You are a financial sentiment analyser for ASX-listed stocks.
Given the following recent news headlines about {ticker}, rate the overall sentiment.

Headlines:
{headlines}

Respond ONLY with valid JSON in this exact format:
{{"score": <float between -1.0 and 1.0>, "label": "<positive|neutral|negative>", "reasoning": "<one sentence>"}}
"""


def _call_ollama(prompt: str) -> Optional[dict]:
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "")
        # Strip any markdown code fences
        raw = raw.strip().strip("```json").strip("```").strip()
        return json.loads(raw)
    except Exception as e:
        logger.warning("Ollama call failed: %s", e)
        return None


def score_sentiment(ticker: str, hours: int = 48) -> float:
    """Returns sentiment score 0-100 (50 = neutral)."""
    cached = get_cached_score(ticker, "sentiment")
    if cached is not None:
        return cached

    headlines = get_recent_headlines(ticker, hours=hours)
    if not headlines:
        score_0_100 = 50.0
        cache_score(ticker, "sentiment", score_0_100)
        return score_0_100

    headline_text = "\n".join(f"- {h}" for h in headlines[:15])
    prompt = SENTIMENT_PROMPT.format(ticker=ticker, headlines=headline_text)
    result = _call_ollama(prompt)

    if result and "score" in result:
        raw_score = float(result["score"])           # -1 to +1
        raw_score = max(-1.0, min(1.0, raw_score))
        score_0_100 = (raw_score + 1.0) / 2.0 * 100  # 0-100
        label = result.get("label", "neutral")

        # Persist sentiment back to news rows (best-effort)
        _update_news_sentiment(ticker, raw_score, label, hours)
    else:
        score_0_100 = 50.0

    cache_score(ticker, "sentiment", score_0_100)
    return round(score_0_100, 2)


def _update_news_sentiment(ticker: str, score: float, label: str, hours: int) -> None:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    with get_session() as session:
        rows = (
            session.query(NewsItem)
            .filter(
                NewsItem.ticker == ticker,
                NewsItem.published_at >= cutoff,
                NewsItem.sentiment_score.is_(None),
            )
            .all()
        )
        for row in rows:
            row.sentiment_score = score
            row.sentiment_label = label


def batch_score_sentiment(tickers: list, hours: int = 72) -> dict:
    """Score all tickers; returns {ticker: score_0_100}."""
    results = {}
    for ticker in tickers:
        try:
            results[ticker] = score_sentiment(ticker, hours=hours)
        except Exception as e:
            logger.warning("Sentiment scoring failed for %s: %s", ticker, e)
            results[ticker] = 50.0
    return results
