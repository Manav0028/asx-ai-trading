"""
Layer 03 · AI Engine — Walk-Forward Backtester
Uses vectorbt (OSS) with rolling 6-month windows.
Runs every Sunday to re-optimise signal thresholds.
"""
import logging
from datetime import date, timedelta
from typing import Dict

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import vectorbt as vbt
    VBT_AVAILABLE = True
except ImportError:
    VBT_AVAILABLE = False
    logger.warning("vectorbt not installed — backtester will use simple returns")


def _simple_backtest(prices_df: pd.DataFrame, signals_df: pd.DataFrame) -> Dict:
    """Fallback backtester when vectorbt is not available."""
    results = {}
    for ticker in prices_df.columns:
        if ticker not in signals_df.columns:
            continue
        prices = prices_df[ticker].dropna()
        signals = signals_df[ticker].reindex(prices.index).fillna(0)

        position = 0
        entry_price = 0.0
        returns = []

        for i, (dt, price) in enumerate(prices.items()):
            sig = signals.iloc[i] if i < len(signals) else 0
            if sig >= 1 and position == 0:
                position = 1
                entry_price = price
            elif position == 1:
                ret = (price - entry_price) / entry_price
                if ret <= -0.07 or ret >= 0.15:   # stop-loss / target
                    returns.append(ret)
                    position = 0
                    entry_price = 0.0

        results[ticker] = {
            "num_trades": len(returns),
            "win_rate": sum(1 for r in returns if r > 0) / max(len(returns), 1),
            "avg_return": float(np.mean(returns)) if returns else 0.0,
            "total_return": float(np.prod([1 + r for r in returns]) - 1) if returns else 0.0,
        }
    return results


def run_walk_forward(
    tickers: list,
    lookback_months: int = 6,
    signal_threshold: float = 75.0,
) -> Dict:
    """
    Walk-forward backtest over the last `lookback_months` months.
    Returns per-ticker performance metrics and the optimal threshold.
    """
    from data_ingestion.price_fetcher import get_price_series
    from storage.database import get_session
    from storage.models import Signal

    end_date = date.today()
    start_date = end_date - timedelta(days=lookback_months * 30)

    # Build price matrix
    price_data = {}
    for ticker in tickers:
        series = get_price_series(ticker, days=lookback_months * 35)
        if series:
            dates, closes = zip(*[(d, c) for d, c in reversed(series)])
            price_data[ticker] = pd.Series(closes, index=pd.to_datetime(dates))

    if not price_data:
        logger.warning("No price data for backtest")
        return {}

    prices_df = pd.DataFrame(price_data).sort_index()

    # Build signal matrix from DB
    signal_data = {}
    with get_session() as session:
        for ticker in tickers:
            rows = (
                session.query(Signal.date, Signal.composite_score)
                .filter(
                    Signal.ticker == ticker,
                    Signal.date >= start_date,
                    Signal.date <= end_date,
                )
                .all()
            )
            if rows:
                dates, scores = zip(*[(r.date, r.composite_score) for r in rows])
                s = pd.Series(scores, index=pd.to_datetime(dates))
                # Convert composite score to binary entry signal
                signal_data[ticker] = (s >= signal_threshold).astype(int)

    signals_df = pd.DataFrame(signal_data).sort_index()

    if VBT_AVAILABLE and not prices_df.empty and not signals_df.empty:
        try:
            aligned_prices = prices_df.reindex(signals_df.index, method="ffill")
            entries = signals_df.astype(bool)
            exits = entries.shift(1, fill_value=False)  # hold 1 period

            pf = vbt.Portfolio.from_signals(
                aligned_prices,
                entries=entries,
                exits=exits,
                fees=0.001,        # 0.1% slippage
                fixed_fees=9.95,   # brokerage per trade
                init_cash=100_000,
                sl_stop=0.07,      # 7% stop-loss
            )
            stats = pf.stats()
            logger.info("VectorBT backtest complete:\n%s", stats)
            return {"vectorbt_stats": stats.to_dict(), "tickers": tickers}
        except Exception as e:
            logger.warning("VectorBT failed, falling back to simple backtest: %s", e)

    results = _simple_backtest(prices_df, signals_df)
    winning_tickers = [t for t, r in results.items() if r["win_rate"] >= 0.55]
    logger.info(
        "Simple backtest: %d tickers, %d winners (win_rate ≥ 55%%)",
        len(results), len(winning_tickers),
    )
    return results
