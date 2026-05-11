"""
Layer 04 · Signal Intelligence — Signal Aggregator
Combines sentiment (30%), fundamental (25%), technical (25%), insider (20%)
into a composite score 0-100. Persists to DB.
"""
import logging
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy.dialects.postgresql import insert

from ai_engine.fundamental_scorer import score_fundamental
from ai_engine.insider_pattern import score_insider
from ai_engine.regime_filter import is_regime_ok
from ai_engine.sentiment import score_sentiment
from ai_engine.technical_engine import score_technical
from config.settings import (
    SIGNAL_THRESHOLD,
    WEIGHT_FUNDAMENTAL,
    WEIGHT_INSIDER,
    WEIGHT_SENTIMENT,
    WEIGHT_TECHNICAL,
)
from data_ingestion.price_fetcher import get_latest_price
from storage.database import get_session
from storage.models import Signal

logger = logging.getLogger(__name__)


def compute_signal(ticker: str, today: date = None) -> Optional[Dict]:
    """
    Compute and persist the composite signal for one ticker.
    Returns signal dict or None if regime is off and score is low.
    """
    today = today or date.today()
    regime_ok = is_regime_ok()

    sentiment = score_sentiment(ticker)
    fundamental = score_fundamental(ticker)
    technical = score_technical(ticker)
    insider = score_insider(ticker)

    composite = (
        sentiment * WEIGHT_SENTIMENT
        + fundamental * WEIGHT_FUNDAMENTAL
        + technical * WEIGHT_TECHNICAL
        + insider * WEIGHT_INSIDER
    )
    composite = round(max(0.0, min(100.0, composite)), 2)

    # Suppress if regime is risk-off (dampen score by 20%)
    if not regime_ok:
        composite = round(composite * 0.80, 2)

    entry_price = get_latest_price(ticker)
    target_price = round(entry_price * 1.10, 3) if entry_price else None
    stop_loss_price = round(entry_price * 0.93, 3) if entry_price else None

    from signals.kelly_sizer import compute_kelly_size
    kelly_f, position_aud = compute_kelly_size(composite) if composite >= SIGNAL_THRESHOLD else (0.0, 0.0)

    signal_dict = {
        "ticker": ticker,
        "date": today,
        "sentiment_score": sentiment,
        "fundamental_score": fundamental,
        "technical_score": technical,
        "insider_score": insider,
        "composite_score": composite,
        "regime_ok": regime_ok,
        "kelly_fraction": kelly_f,
        "position_size_aud": position_aud,
        "entry_price": entry_price,
        "target_price": target_price,
        "stop_loss_price": stop_loss_price,
    }

    with get_session() as session:
        stmt = insert(Signal).values(**signal_dict).on_conflict_do_update(
            constraint="uq_signal_ticker_date",
            set_={k: v for k, v in signal_dict.items() if k not in ("ticker", "date")},
        )
        session.execute(stmt)

    logger.info(
        "%s → composite=%.1f (S=%.0f F=%.0f T=%.0f I=%.0f) regime=%s",
        ticker, composite, sentiment, fundamental, technical, insider,
        "OK" if regime_ok else "OFF",
    )

    return signal_dict


def run_full_scan(tickers: List[str]) -> List[Dict]:
    """Score all tickers and return list sorted by composite score desc."""
    results = []
    for ticker in tickers:
        try:
            sig = compute_signal(ticker)
            if sig:
                results.append(sig)
        except Exception as e:
            logger.warning("Signal failed for %s: %s", ticker, e)

    results.sort(key=lambda x: x["composite_score"], reverse=True)
    return results


def get_top_signals(n: int = 10, min_score: float = None) -> List[Dict]:
    """Fetch today's top signals from DB."""
    today = date.today()
    min_score = min_score or SIGNAL_THRESHOLD
    with get_session() as session:
        rows = (
            session.query(Signal)
            .filter(Signal.date == today, Signal.composite_score >= min_score)
            .order_by(Signal.composite_score.desc())
            .limit(n)
            .all()
        )
        return [
            {
                "ticker": r.ticker,
                "composite_score": r.composite_score,
                "sentiment_score": r.sentiment_score,
                "fundamental_score": r.fundamental_score,
                "technical_score": r.technical_score,
                "insider_score": r.insider_score,
                "entry_price": r.entry_price,
                "target_price": r.target_price,
                "stop_loss_price": r.stop_loss_price,
                "position_size_aud": r.position_size_aud,
                "regime_ok": r.regime_ok,
            }
            for r in rows
        ]
