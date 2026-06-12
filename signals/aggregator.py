"""
Layer 04 · Signal Intelligence — Signal Aggregator (Enhanced)
Weights: Sentiment×30% + Fundamental×25% + Technical×25% + Insider×20%
Quality filters: component minimums, liquidity check, diversification.
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
    MAX_POSITION_PCT, PORTFOLIO_CAPITAL, SIGNAL_THRESHOLD,
    WEIGHT_FUNDAMENTAL, WEIGHT_INSIDER, WEIGHT_SENTIMENT, WEIGHT_TECHNICAL,
)
from data_ingestion.price_fetcher import get_latest_price
from storage.database import get_session
from storage.models import Price, Signal

logger = logging.getLogger(__name__)

# Minimum component scores — prevents one great score masking weak areas
MIN_SENTIMENT   = 35.0   # Not deeply negative news
MIN_FUNDAMENTAL = 40.0   # Some basic financial health
MIN_TECHNICAL   = 35.0   # Not in free-fall


def _quality_check(sentiment: float, fundamental: float, technical: float, insider: float) -> tuple:
    """
    Returns (passes: bool, reason: str).
    Filters out stocks where one dimension is dangerously weak.
    """
    if sentiment < MIN_SENTIMENT:
        return False, f"blocked: very negative news (sentiment {sentiment:.0f}/100)"
    if fundamental < MIN_FUNDAMENTAL:
        return False, f"blocked: weak fundamentals (score {fundamental:.0f}/100)"
    if technical < MIN_TECHNICAL:
        return False, f"blocked: bad technicals (score {technical:.0f}/100)"
    return True, "ok"


def _liquidity_check(ticker: str) -> tuple:
    """Returns (passes: bool, avg_volume). Skips illiquid stocks."""
    with get_session() as session:
        rows = (
            session.query(Price.volume)
            .filter(Price.ticker == ticker)
            .order_by(Price.date.desc())
            .limit(20)
            .all()
        )
    volumes = [r.volume for r in rows if r.volume and r.volume > 0]
    if not volumes:
        return True, 0  # No data — don't block
    avg_vol = sum(volumes) / len(volumes)
    price = get_latest_price(ticker) or 1
    avg_daily_turnover = avg_vol * price
    # Require at least $500k average daily turnover (avoids micro-caps)
    if avg_daily_turnover < 500_000:
        return False, avg_daily_turnover
    return True, avg_daily_turnover


def compute_signal(ticker: str, today: date = None) -> Optional[Dict]:
    today = today or date.today()
    regime_ok = is_regime_ok()

    sentiment   = score_sentiment(ticker)
    fundamental = score_fundamental(ticker)
    technical   = score_technical(ticker)
    insider     = score_insider(ticker)

    # Quality gate
    quality_ok, quality_reason = _quality_check(sentiment, fundamental, technical, insider)

    # Liquidity gate
    liquid_ok, avg_turnover = _liquidity_check(ticker)

    composite = (
        sentiment   * WEIGHT_SENTIMENT
        + fundamental * WEIGHT_FUNDAMENTAL
        + technical   * WEIGHT_TECHNICAL
        + insider     * WEIGHT_INSIDER
    )
    composite = round(max(0.0, min(100.0, composite)), 2)

    # ── Per-stock strategy gate ───────────────────────────────────────────────
    # Each ticker trades only its own backtest+forward-validated strategy.
    # No assignment yet → legacy composite-only behaviour (selection job fills
    # these in weekly). Assigned but unvalidated → never actionable (no proven
    # edge on this stock). Validated → actionable only when the strategy's
    # entry condition fires today.
    from strategies.selector import get_strategy_signal
    strat = None
    try:
        strat = get_strategy_signal(ticker)
    except Exception as e:
        logger.debug("Strategy lookup failed for %s: %s", ticker, e)

    direction = (strat or {}).get("direction") or "long"
    if strat is None:
        strategy_ok, strategy_name, strategy_state = True, None, "unassigned"
    elif not strat["validated"]:
        strategy_ok, strategy_name, strategy_state = False, strat["strategy"], "unvalidated"
    elif strat["fires"]:
        strategy_ok, strategy_name, strategy_state = True, strat["strategy"], f"fires ({strat['reason']})"
    else:
        strategy_ok, strategy_name, strategy_state = False, strat["strategy"], "no entry today"

    # Scores are pure quality — regime affects position sizing, not score.
    # Shorts mirror the gate: a weak composite is exactly what a short wants,
    # so they require the BEARISH composite (100 - composite) over threshold.
    # The news-quality gate is long-biased (blocks negative news) so shorts
    # rely on the strategy validation + liquidity gates instead.
    if direction == "short":
        actionable = liquid_ok and strategy_ok and (100 - composite) >= SIGNAL_THRESHOLD
    else:
        actionable = quality_ok and liquid_ok and strategy_ok and composite >= SIGNAL_THRESHOLD

    # ── Prices + dynamic risk parameters ─────────────────────────────────────
    from ai_engine.technical_engine import get_technical_meta
    from signals.risk_params import get_all_risk_params

    tech_meta   = get_technical_meta(ticker)
    entry_price = get_latest_price(ticker)
    atr         = tech_meta.get("atr")    # 14-period ATR from price history
    adx         = tech_meta.get("adx")    # 14-period ADX (trend strength)

    if actionable and entry_price:
        risk = get_all_risk_params(
            ticker           = ticker,
            entry_price      = entry_price,
            atr              = atr,
            adx              = adx,
            composite_score  = composite,
            fundamental_score = fundamental,
            regime_ok        = regime_ok,
            # Strategy-specific risk geometry (e.g. mean reversion exits tighter)
            stop_mult        = strat.get("stop_mult") if strat else None,
            target_mult      = strat.get("target_mult") if strat else None,
            direction        = direction,
        )
        target_price    = risk["target_price"]
        stop_loss_price = risk["stop_loss_price"]
        position_aud    = risk["position_size_aud"]
        kelly_f         = round(position_aud / max(entry_price * 1, 1), 4)  # shares approx
    elif direction == "short" and entry_price:
        # Non-actionable short — display geometry must still be inverted
        from signals.risk_params import compute_stop_target
        st_ = compute_stop_target(entry_price, atr, regime_ok,
                                  strat.get("stop_mult") if strat else None,
                                  strat.get("target_mult") if strat else None,
                                  direction="short")
        target_price    = st_["target_price"]
        stop_loss_price = st_["stop_loss_price"]
        position_aud    = 0.0
        kelly_f         = 0.0
    else:
        # Non-actionable signal — store scores but no position
        target_price    = tech_meta.get("target") or (round(entry_price * 1.10, 3) if entry_price else None)
        stop_loss_price = tech_meta.get("stop")   or (round(entry_price * 0.93, 3) if entry_price else None)
        position_aud    = 0.0
        kelly_f         = 0.0

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
        "strategy_name": strategy_name,
        "direction": direction,
    }

    with get_session() as session:
        stmt = insert(Signal).values(**signal_dict).on_conflict_do_update(
            constraint="uq_signal_ticker_date",
            set_={k: v for k, v in signal_dict.items() if k not in ("ticker", "date")},
        )
        session.execute(stmt)

    logger.info(
        "%s → %.1f (S=%.0f F=%.0f T=%.0f I=%.0f) regime=%s quality=%s liquid=%s strategy=%s",
        ticker, composite, sentiment, fundamental, technical, insider,
        "OK" if regime_ok else "OFF",
        "OK" if quality_ok else quality_reason,
        "OK" if liquid_ok else f"low (${avg_turnover:,.0f}/day)",
        f"{strategy_name or '-'}:{strategy_state}",
    )
    return signal_dict


def run_full_scan(tickers: List[str]) -> List[Dict]:
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


def _active_ticker_suffix() -> Optional[str]:
    """Return the ticker suffix for the active exchange (e.g. '.AX' or '.NS').
    Ensures signals from the ASX scheduler never appear in NSE reports and vice-versa."""
    try:
        from config import get_active_exchange
        tickers = get_active_exchange().tickers
        if tickers:
            t = tickers[0]
            dot = t.rfind(".")
            return t[dot:] if dot >= 0 else None
    except Exception:
        pass
    return None


def get_top_signals(n: int = 10, min_score: float = None) -> List[Dict]:
    today = date.today()
    min_score = min_score or SIGNAL_THRESHOLD
    suffix = _active_ticker_suffix()

    from sqlalchemy import and_, or_

    with get_session() as session:
        # Over-fetch to allow post-filter by exchange suffix when DB has rows from both exchanges.
        # Shorts qualify on the BEARISH composite (low score = strong short), so
        # include rows that are either strong longs or actionable shorts.
        rows = (
            session.query(Signal)
            .filter(
                Signal.date == today,
                or_(
                    Signal.composite_score >= min_score,
                    and_(Signal.direction == "short", Signal.position_size_aud > 0),
                ),
            )
            .order_by(Signal.position_size_aud.desc(), Signal.composite_score.desc())
            .limit(n * 4 if suffix else n)
            .all()
        )
        results = [
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
                "strategy_name": getattr(r, "strategy_name", None),
                "direction": getattr(r, "direction", None) or "long",
            }
            for r in rows
            if suffix is None or r.ticker.endswith(suffix)
        ]
        return results[:n]
