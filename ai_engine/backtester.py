"""
Layer 03 · AI Engine — Walk-Forward Backtester
Pure-Python backtester (no vectorbt dependency).
Runs on stored signals + prices to measure strategy performance.
Reports: win rate, avg return, Sharpe-like ratio, max drawdown.
"""
import logging
from datetime import date, timedelta
from typing import Dict, List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _sharpe(returns: List[float], risk_free: float = 0.0) -> float:
    if len(returns) < 2:
        return 0.0
    arr = np.array(returns)
    excess = arr - risk_free / 252
    return float(np.mean(excess) / (np.std(excess) + 1e-9) * np.sqrt(252))


def _max_drawdown(equity_curve: List[float]) -> float:
    if not equity_curve:
        return 0.0
    arr = np.array(equity_curve)
    peak = np.maximum.accumulate(arr)
    dd = (arr - peak) / (peak + 1e-9)
    return float(np.min(dd))


def _run_ticker_backtest(
    prices: pd.Series,
    signal_dates: List[date],
    stop_pct: float = 0.07,
    target_pct: float = 0.10,
    hold_days: int = 45,
) -> Dict:
    """Simulate entry on signal date, exit on stop/target/timeout."""
    returns = []
    equity = [10_000.0]

    for entry_date in signal_dates:
        try:
            entry_ts = pd.Timestamp(entry_date)
            if entry_ts not in prices.index:
                # Find next available trading day
                future = prices.index[prices.index >= entry_ts]
                if len(future) == 0:
                    continue
                entry_ts = future[0]

            entry_price = prices[entry_ts]
            stop_price  = entry_price * (1 - stop_pct)
            target_price = entry_price * (1 + target_pct)
            exit_price = None
            exit_reason = "timeout"

            # Walk forward day by day
            future_prices = prices[prices.index > entry_ts].head(hold_days)
            for ts, px in future_prices.items():
                if px <= stop_price:
                    exit_price = px
                    exit_reason = "stop"
                    break
                if px >= target_price:
                    exit_price = px
                    exit_reason = "target"
                    break
            if exit_price is None and len(future_prices) > 0:
                exit_price = future_prices.iloc[-1]

            if exit_price is None:
                continue

            ret = (exit_price - entry_price) / entry_price
            returns.append(ret)
            equity.append(equity[-1] * (1 + ret))
        except Exception:
            continue

    if not returns:
        return {
            "num_trades": 0, "win_rate": 0.0, "avg_return_pct": 0.0,
            "sharpe": 0.0, "max_drawdown_pct": 0.0, "total_return_pct": 0.0,
        }

    win_rate = sum(1 for r in returns if r > 0) / len(returns)
    total_ret = (equity[-1] / equity[0] - 1) * 100 if len(equity) > 1 else 0.0

    return {
        "num_trades": len(returns),
        "win_rate": round(win_rate, 3),
        "avg_return_pct": round(float(np.mean(returns)) * 100, 2),
        "sharpe": round(_sharpe(returns), 2),
        "max_drawdown_pct": round(_max_drawdown(equity) * 100, 2),
        "total_return_pct": round(total_ret, 2),
    }


def run_walk_forward(
    tickers: List[str],
    lookback_months: int = 6,
    signal_threshold: float = 75.0,
) -> Dict:
    from data_ingestion.price_fetcher import get_price_series
    from storage.database import get_session
    from storage.models import Signal

    end_date = date.today()
    start_date = end_date - timedelta(days=lookback_months * 30)
    results = {}
    summary_lines = []

    for ticker in tickers:
        # Get price series
        series = get_price_series(ticker, days=lookback_months * 35)
        if len(series) < 20:
            continue
        dates_prices = [(d, c) for d, c in reversed(series)]
        price_series = pd.Series(
            [c for _, c in dates_prices],
            index=pd.to_datetime([d for d, _ in dates_prices]),
        )

        # Get signal dates from DB
        with get_session() as session:
            rows = (
                session.query(Signal.date)
                .filter(
                    Signal.ticker == ticker,
                    Signal.composite_score >= signal_threshold,
                    Signal.date >= start_date,
                    Signal.date <= end_date,
                )
                .all()
            )
        signal_dates = [r.date for r in rows]

        if not signal_dates:
            continue

        result = _run_ticker_backtest(price_series, signal_dates)
        results[ticker] = result

        if result["num_trades"] >= 2:
            summary_lines.append(
                f"  {ticker}: {result['num_trades']} trades | "
                f"win rate {result['win_rate']*100:.0f}% | "
                f"avg {result['avg_return_pct']:+.1f}% | "
                f"Sharpe {result['sharpe']:.2f}"
            )

    if summary_lines:
        logger.info("Walk-forward backtest results:\n%s", "\n".join(summary_lines))

    # Aggregate stats
    all_win_rates = [r["win_rate"] for r in results.values() if r["num_trades"] >= 2]
    if all_win_rates:
        logger.info(
            "Backtest summary: %d tickers | avg win rate %.0f%% | "
            "%d tickers beating 55%%",
            len(all_win_rates),
            np.mean(all_win_rates) * 100,
            sum(1 for w in all_win_rates if w >= 0.55),
        )

    return results
