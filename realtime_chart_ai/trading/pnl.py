"""
Simulated fill + P&L — identical slippage/brokerage formulas to
execution/paper_trader.py, cloned not imported. Shared by both the entry and
exit paths in position_tracker.py so fill/brokerage math isn't duplicated.
"""
from typing import Dict

from settings import RTC_PAPER_BROKERAGE, RTC_PAPER_SLIPPAGE


def simulate_fill(price: float, side: str) -> float:
    """side: 'buy' | 'sell'. Slippage always works against the trader."""
    if side == "buy":
        return price * (1 + RTC_PAPER_SLIPPAGE)
    return price * (1 - RTC_PAPER_SLIPPAGE)


def compute_pnl(direction: str, entry_price: float, exit_price: float, shares: float) -> Dict:
    entry_side = "buy" if direction == "long" else "sell"
    exit_side = "sell" if direction == "long" else "buy"
    entry_fill = simulate_fill(entry_price, entry_side)
    exit_fill = simulate_fill(exit_price, exit_side)
    if direction == "long":
        gross_pnl = (exit_fill - entry_fill) * shares
    else:
        gross_pnl = (entry_fill - exit_fill) * shares
    brokerage_total = RTC_PAPER_BROKERAGE * 2  # one leg each side
    net_pnl = gross_pnl - brokerage_total
    return {"gross_pnl": gross_pnl, "net_pnl": net_pnl, "brokerage_total": brokerage_total}
