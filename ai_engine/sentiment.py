"""
Layer 03 · AI Engine — Ollama Sentiment (Llama 3.1)
Parallelised across tickers using ThreadPoolExecutor (3 workers).
Scores each stock's recent news headlines 0-100 (50 = neutral).
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests

from config.settings import OLLAMA_HOST, OLLAMA_MODEL
from data_ingestion.news_fetcher import get_recent_headlines
from storage.cache import cache_score, get_cached_score
from storage.database import get_session
from storage.models import NewsItem

logger = logging.getLogger(__name__)

SENTIMENT_PROMPT = """\
You are a financial news analyst for the {market_name} stock market.

Analyse these recent news headlines about {ticker} ({company_hint}) and rate the overall sentiment.

Headlines:
{headlines}

Reply ONLY with valid JSON — no extra text:
{{"score": <float -1.0 to 1.0>, "label": "<positive|neutral|negative>", "key_theme": "<5 words max describing the main story>", "reasoning": "<one plain-English sentence>"}}

Scoring guide:
 1.0 = very bullish (strong earnings beat, major contract win, buyout premium)
 0.5 = mildly positive (guidance raised, analyst upgrade)
 0.0 = neutral (routine update, no market impact)
-0.5 = mildly negative (cost pressures, downgrade)
-1.0 = very bearish (profit warning, scandal, regulatory action)"""

# Ticker → company name for better LLM context. Covers both ASX and NSE.
_COMPANY_NAMES = {
    # ASX
    "CBA.AX": "Commonwealth Bank", "BHP.AX": "BHP Group", "CSL.AX": "CSL Limited",
    "WBC.AX": "Westpac Banking", "ANZ.AX": "ANZ Bank", "NAB.AX": "NAB Bank",
    "WES.AX": "Wesfarmers", "MQG.AX": "Macquarie Group", "RIO.AX": "Rio Tinto",
    "WOW.AX": "Woolworths", "GMG.AX": "Goodman Group", "TLS.AX": "Telstra",
    "FMG.AX": "Fortescue Metals", "COL.AX": "Coles Group", "STO.AX": "Santos",
    "ALL.AX": "Aristocrat Leisure", "TCL.AX": "Transurban", "IAG.AX": "IAG Insurance",
    "QBE.AX": "QBE Insurance", "SHL.AX": "Sonic Healthcare",
    # NSE NIFTY 100
    "RELIANCE.NS": "Reliance Industries", "TCS.NS": "Tata Consultancy Services",
    "HDFCBANK.NS": "HDFC Bank", "INFY.NS": "Infosys", "ICICIBANK.NS": "ICICI Bank",
    "HINDUNILVR.NS": "Hindustan Unilever", "ITC.NS": "ITC Limited",
    "SBIN.NS": "State Bank of India", "BHARTIARTL.NS": "Bharti Airtel",
    "KOTAKBANK.NS": "Kotak Mahindra Bank", "LT.NS": "Larsen & Toubro",
    "AXISBANK.NS": "Axis Bank", "ASIANPAINT.NS": "Asian Paints",
    "MARUTI.NS": "Maruti Suzuki", "TITAN.NS": "Titan Company",
    "SUNPHARMA.NS": "Sun Pharmaceutical", "BAJFINANCE.NS": "Bajaj Finance",
    "WIPRO.NS": "Wipro", "ULTRACEMCO.NS": "UltraTech Cement",
    "NESTLEIND.NS": "Nestle India", "TECHM.NS": "Tech Mahindra",
    "POWERGRID.NS": "Power Grid Corporation", "HCLTECH.NS": "HCL Technologies",
    "BAJAJFINSV.NS": "Bajaj Finserv", "ONGC.NS": "ONGC",
    "NTPC.NS": "NTPC", "JSWSTEEL.NS": "JSW Steel",
    "TATAMOTORS.NS": "Tata Motors", "M&M.NS": "Mahindra & Mahindra",
    "TATASTEEL.NS": "Tata Steel", "DRREDDY.NS": "Dr. Reddy's Laboratories",
    "HDFCLIFE.NS": "HDFC Life Insurance", "GRASIM.NS": "Grasim Industries",
    "CIPLA.NS": "Cipla", "COALINDIA.NS": "Coal India",
    "ADANIPORTS.NS": "Adani Ports", "DIVISLAB.NS": "Divi's Laboratories",
    "EICHERMOT.NS": "Eicher Motors", "BPCL.NS": "BPCL",
    "BRITANNIA.NS": "Britannia Industries", "INDUSINDBK.NS": "IndusInd Bank",
    "TATACONSUM.NS": "Tata Consumer Products", "HINDALCO.NS": "Hindalco Industries",
    "VEDL.NS": "Vedanta", "ADANIENT.NS": "Adani Enterprises",
    "SIEMENS.NS": "Siemens India", "HAVELLS.NS": "Havells India",
    "BAJAJ-AUTO.NS": "Bajaj Auto", "HEROMOTOCO.NS": "Hero MotoCorp",
    "TORNTPHARM.NS": "Torrent Pharmaceuticals", "COLPAL.NS": "Colgate-Palmolive India",
    "ABB.NS": "ABB India", "MUTHOOTFIN.NS": "Muthoot Finance",
    "CHOLAFIN.NS": "Cholamandalam Finance", "DLF.NS": "DLF",
    "GODREJCP.NS": "Godrej Consumer Products", "BANKBARODA.NS": "Bank of Baroda",
    "CANBK.NS": "Canara Bank", "HAL.NS": "Hindustan Aeronautics",
    "IRFC.NS": "Indian Railway Finance Corp", "RECLTD.NS": "REC Limited",
    "PFC.NS": "Power Finance Corporation", "LICI.NS": "LIC India",
    "ZOMATO.NS": "Zomato", "NYKAA.NS": "Nykaa", "IRCTC.NS": "IRCTC",
    "TRENT.NS": "Trent", "DMART.NS": "DMart (Avenue Supermarts)",
    "PAGEIND.NS": "Page Industries", "PIDILITIND.NS": "Pidilite Industries",
    "LUPIN.NS": "Lupin", "MARICO.NS": "Marico", "NMDC.NS": "NMDC",
}


def _call_ollama(prompt: str, timeout: int = 90) -> Optional[dict]:
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
        # Strip markdown fences if present
        if "```" in raw:
            raw = raw.split("```")[1].replace("json", "").strip()
        return json.loads(raw)
    except Exception as e:
        logger.debug("Ollama call failed: %s", e)
        return None


def score_sentiment(ticker: str, hours: int = 72) -> float:
    """Returns sentiment score 0-100 (50 = neutral). Uses Redis/memory cache."""
    cached = get_cached_score(ticker, "sentiment")
    if cached is not None:
        return cached

    headlines = get_recent_headlines(ticker, hours=hours)
    if not headlines:
        cache_score(ticker, "sentiment", 50.0, ttl=1800)
        return 50.0

    from config import get_active_exchange
    exchange = get_active_exchange()
    # Fallback company name: strip exchange suffix
    suffix = f".{ticker.split('.')[-1]}" if "." in ticker else ""
    company = _COMPANY_NAMES.get(ticker, ticker.replace(suffix, ""))
    headline_text = "\n".join(f"- {h}" for h in headlines[:15])
    prompt = SENTIMENT_PROMPT.format(
        ticker=ticker,
        company_hint=company,
        market_name=exchange.name,
        headlines=headline_text,
    )
    result = _call_ollama(prompt)

    if result and "score" in result:
        raw = float(result["score"])
        raw = max(-1.0, min(1.0, raw))
        score_0_100 = round((raw + 1.0) / 2.0 * 100, 2)
        _update_news_sentiment(ticker, raw, result.get("label", "neutral"), hours)
        # Store rich metadata in cache for alerts
        cache_score(ticker, f"sentiment_meta_{ticker}", {
            "score": score_0_100,
            "label": result.get("label", "neutral"),
            "key_theme": result.get("key_theme", ""),
            "reasoning": result.get("reasoning", ""),
        }, ttl=3600 * 4)
    else:
        score_0_100 = 50.0

    cache_score(ticker, "sentiment", score_0_100)
    return score_0_100


def get_sentiment_meta(ticker: str) -> dict:
    """Returns rich sentiment metadata for use in alerts."""
    from storage.cache import get_value
    meta = get_value(f"score:{ticker}:sentiment_meta_{ticker}")
    return meta or {"score": 50.0, "label": "neutral", "key_theme": "", "reasoning": ""}


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


def _score_one(ticker: str, hours: int) -> tuple:
    try:
        return ticker, score_sentiment(ticker, hours=hours)
    except Exception as e:
        logger.warning("Sentiment failed for %s: %s", ticker, e)
        return ticker, 50.0


def batch_score_sentiment(tickers: List[str], hours: int = 72, workers: int = 3) -> Dict[str, float]:
    """
    Score all tickers in parallel using ThreadPoolExecutor.
    workers=3 avoids overloading Ollama on a single machine.
    """
    results = {}
    # Check cache first — only call Ollama for uncached tickers
    to_score = []
    for t in tickers:
        cached = get_cached_score(t, "sentiment")
        if cached is not None:
            results[t] = cached
        else:
            to_score.append(t)

    if not to_score:
        return results

    logger.info("Running Ollama sentiment for %d tickers (%d workers)", len(to_score), workers)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_score_one, t, hours): t for t in to_score}
        for future in as_completed(futures):
            ticker, score = future.result()
            results[ticker] = score

    return results
