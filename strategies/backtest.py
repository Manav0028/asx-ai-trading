"""
Strategy Engine — Per-Strategy Event Backtester
Replays a strategy bar-by-bar over a ticker's history with ATR stops/targets,
slippage, and brokerage. The history is split 70/30: the first 70% is the
in-sample backtest, the final 30% is the out-of-sample forward test. A
strategy must be profitable in BOTH windows before it may trade real signals.
"""
import logging
from typing import Dict, List

import numpy as np

from config.settings import PAPER_BROKERAGE, PAPER_SLIPPAGE, PORTFOLIO_CAPITAL
from strategies.base import Strategy

logger = logging.getLogger(__name__)

WARMUP_BARS = 60          # indicators need history before they are reliable
FORWARD_FRACTION = 0.30   # last 30% of bars reserved for forward testing
NOTIONAL = 10_000.0       # per-trade notional used to net out brokerage realistically


def _metrics(returns: List[float]) -> Dict:
    if not returns:
        return {"num_trades": 0, "win_rate": 0.0, "avg_return_pct": 0.0,
                "profit_factor": 0.0, "total_return_pct": 0.0, "max_drawdown_pct": 0.0}
    arr = np.array(returns)
    wins = arr[arr > 0]
    losses = arr[arr <= 0]
    profit_factor = float(np.sum(wins) / (abs(np.sum(losses)) + 1e-9)) if len(losses) else 99.0
    equity = np.cumprod(1 + arr)
    peak = np.maximum.accumulate(equity)
    max_dd = float(np.min((equity - peak) / peak)) if len(equity) else 0.0
    return {
        "num_trades": len(arr),
        "win_rate": round(float(np.mean(arr > 0)), 3),
        "avg_return_pct": round(float(np.mean(arr)) * 100, 2),
        "profit_factor": round(min(profit_factor, 99.0), 2),
        "total_return_pct": round(float(equity[-1] - 1) * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
    }


def run_strategy_backtest(strategy: Strategy, ind: Dict[str, np.ndarray]) -> Dict:
    """
    Simulate `strategy` over precomputed indicator arrays.
    Returns {"backtest": metrics, "forward": metrics} split at the 70% mark.
    """
    closes, highs, lows, atr = ind["closes"], ind["highs"], ind["lows"], ind["atr"]
    n = len(closes)
    split_i = int(n * (1 - FORWARD_FRACTION))
    short = getattr(strategy, "direction", "long") == "short"

    bt_returns: List[float] = []
    fw_returns: List[float] = []

    in_pos = False
    entry_price = stop = target = 0.0
    entry_i = 0

    for i in range(WARMUP_BARS, n):
        if in_pos:
            exit_price = None
            # Conservative: if stop and target both touch in a bar, assume stop
            if short:
                if highs[i] >= stop:
                    exit_price = stop
                elif lows[i] <= target:
                    exit_price = target
            else:
                if lows[i] <= stop:
                    exit_price = stop
                elif highs[i] >= target:
                    exit_price = target
            if exit_price is None and i - entry_i >= strategy.max_hold_days:
                exit_price = closes[i]
            if exit_price is not None:
                if short:
                    fill = exit_price * (1 + PAPER_SLIPPAGE)  # buy to cover
                    ret = (entry_price - fill) / entry_price - (2 * PAPER_BROKERAGE) / NOTIONAL
                else:
                    fill = exit_price * (1 - PAPER_SLIPPAGE)
                    ret = (fill - entry_price) / entry_price - (2 * PAPER_BROKERAGE) / NOTIONAL
                (bt_returns if entry_i < split_i else fw_returns).append(ret)
                in_pos = False
            continue

        if i >= n - 1:  # never enter on the final bar — no exit data
            break
        if strategy.fires(ind, i):
            if short:
                entry_price = closes[i] * (1 - PAPER_SLIPPAGE)  # sell to open
                stop = entry_price + strategy.stop_mult * atr[i]
                target = entry_price - strategy.target_mult * atr[i]
            else:
                entry_price = closes[i] * (1 + PAPER_SLIPPAGE)
                stop = entry_price - strategy.stop_mult * atr[i]
                target = entry_price + strategy.target_mult * atr[i]
            entry_i = i
            in_pos = True

    return {"backtest": _metrics(bt_returns), "forward": _metrics(fw_returns)}


# ── Validation gates ──────────────────────────────────────────────────────────
# A strategy may only trade a stock when its history proves the edge in both
# the in-sample backtest AND the out-of-sample forward window.
BT_MIN_TRADES = 5
BT_MIN_PROFIT_FACTOR = 1.2
BT_MIN_WIN_RATE = 0.45
FW_MIN_TRADES = 2
FW_MIN_PROFIT_FACTOR = 1.0


def is_validated(result: Dict) -> bool:
    bt, fw = result["backtest"], result["forward"]
    return (
        bt["num_trades"] >= BT_MIN_TRADES
        and bt["profit_factor"] >= BT_MIN_PROFIT_FACTOR
        and bt["win_rate"] >= BT_MIN_WIN_RATE
        and fw["num_trades"] >= FW_MIN_TRADES
        and fw["profit_factor"] >= FW_MIN_PROFIT_FACTOR
    )


def rank_score(result: Dict) -> float:
    """Forward performance counts more than in-sample — penalises overfit edges."""
    bt_pf = min(result["backtest"]["profit_factor"], 3.0)
    fw_pf = min(result["forward"]["profit_factor"], 3.0)
    return round(0.4 * bt_pf + 0.6 * fw_pf, 3)
