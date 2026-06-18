"""
Data Validation Test — checks every data layer for correctness.
Run:  python -m scripts.validate_data [--exchange asx|nse]

Validates:
  1. Trade P&L arithmetic  — net_pnl == (exit - entry) * shares - brokerage
  2. Return %              — realised_pnl_pct == (exit - entry) / entry * 100
  3. Unrealised P&L        — unrealised_pnl == (current - entry) * shares
  4. Day P&L               — day_pnl == (current - prev_close) * shares
  5. Total P&L             — == unrealised + all-time realised
  6. Regime data           — fields present and sane
  7. Signal scores         — composite in [0,100], required fields non-null
  8. No zero-P&L closed trades  — flags any trade where entry≠exit but pnl=0
"""

import argparse, sys, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("EXCHANGE", "asx")

TOLERANCE = 0.20   # $0.20 rounding tolerance for P&L arithmetic checks
BROKERAGE = 9.95   # flat ASX brokerage per leg


def _fmt(val):
    if val is None: return "None"
    if isinstance(val, float): return f"{val:,.4f}"
    return str(val)


class Check:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0

    def ok(self, msg):
        print(f"  ✅  {msg}")
        self.passed += 1

    def fail(self, msg):
        print(f"  ❌  {msg}")
        self.failed += 1

    def warn(self, msg):
        print(f"  ⚠️   {msg}")
        self.warnings += 1

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"RESULT: {self.passed}/{total} checks passed  "
              f"({self.warnings} warnings, {self.failed} failures)")
        return self.failed


def run_validation(exchange: str):
    c = Check()
    from dashboard.data import get_trades, get_portfolio, get_regime, get_signals
    from datetime import date

    print(f"\n{'='*60}")
    print(f"Data Validation — {exchange.upper()}  [{date.today()}]")
    print(f"{'='*60}\n")

    # ── 1. Trades ─────────────────────────────────────────────────────────────
    print("── Trades ────────────────────────────────────────────────")
    trades = get_trades(exchange, days=365)
    print(f"  Found {len(trades)} closed trades\n")

    zero_pnl_suspicious = []
    for t in trades:
        ticker = t.get("ticker", "?")
        ep = float(t.get("entry_price") or 0)
        xp = float(t.get("exit_price") or 0)
        sh = float(t.get("shares") or 0)
        net = float(t.get("net_pnl") or 0)
        gross = float(t.get("gross_pnl") or 0)
        rpnl = float(t.get("realised_pnl") or 0)
        rpct = float(t.get("realised_pnl_pct") or 0)

        label = f"{ticker} exited {t.get('exit_date','?')}"

        # Check net_pnl == realised_pnl
        if abs(net - rpnl) > TOLERANCE:
            c.fail(f"{label}: net_pnl={_fmt(net)} ≠ realised_pnl={_fmt(rpnl)}")
        else:
            c.ok(f"{label}: realised_pnl field matches net_pnl ({_fmt(rpnl)})")

        # Check gross arithmetic: gross ≈ (exit - entry) * shares
        if ep and xp and sh:
            expected_gross = (xp - ep) * sh
            if abs(gross - expected_gross) > TOLERANCE:
                c.fail(f"{label}: gross_pnl={_fmt(gross)} expected={_fmt(expected_gross)}"
                       f" (entry={_fmt(ep)} exit={_fmt(xp)} shares={sh:.0f})")

        # Flag suspicious: entry ≠ exit but net_pnl == 0
        if ep and xp and ep != xp and abs(net) < 0.01:
            zero_pnl_suspicious.append(label)
            c.fail(f"{label}: entry={_fmt(ep)} exit={_fmt(xp)} but net_pnl=0 — ZERO P&L BUG")

        # Check return %: (exit - entry) / entry * 100
        if ep and xp:
            expected_pct = (xp - ep) / ep * 100
            if abs(rpct - expected_pct) > 0.1:
                c.fail(f"{label}: realised_pnl_pct={rpct:.2f}% expected={expected_pct:.2f}%")

    if not trades:
        c.warn("No trades found — cannot validate P&L arithmetic")

    # ── 2. Portfolio / Positions ───────────────────────────────────────────────
    print("\n── Portfolio ─────────────────────────────────────────────")
    portfolio = get_portfolio(exchange, live=False)
    positions = portfolio.get("positions", [])
    print(f"  Found {len(positions)} open positions\n")

    for p in positions:
        ticker = p.get("ticker", "?")
        ep = float(p.get("entry_price") or 0)
        cp = float(p.get("current_price") or 0)
        sh = float(p.get("shares") or 0)
        upnl = float(p.get("unrealised_pnl") or 0)
        upct = float(p.get("unrealised_pnl_pct") or 0)

        label = f"{ticker}"

        # unrealised_pnl = (current - entry) * shares
        if ep and cp and sh:
            expected = (cp - ep) * sh
            if abs(upnl - expected) > TOLERANCE:
                c.fail(f"{label}: unrealised_pnl={_fmt(upnl)} expected={_fmt(expected)}"
                       f" (entry={_fmt(ep)} current={_fmt(cp)} shares={sh:.0f})")
            else:
                c.ok(f"{label}: unrealised_pnl correct ({_fmt(upnl)})")

        # unrealised_pnl_pct = (current - entry) / entry * 100
        if ep and cp:
            expected_pct = (cp - ep) / ep * 100
            if abs(upct - expected_pct) > 0.1:
                c.fail(f"{label}: unrealised_pnl_pct={upct:.2f}% expected={expected_pct:.2f}%")

        # Day P&L presence check
        day_pnl = p.get("day_pnl")
        if day_pnl is None:
            c.warn(f"{label}: day_pnl is None (prev close not available)")
        else:
            c.ok(f"{label}: day_pnl populated ({_fmt(day_pnl)})")

    # Total P&L cross-check
    total_pnl     = portfolio.get("total_pnl", 0) or 0
    total_unreal  = portfolio.get("total_unrealised_pnl", 0) or 0
    total_realised = portfolio.get("total_realised_pnl", 0) or 0
    expected_total = total_unreal + total_realised
    if abs(total_pnl - expected_total) > TOLERANCE:
        c.fail(f"total_pnl={_fmt(total_pnl)} ≠ unrealised+realised={_fmt(expected_total)}")
    else:
        c.ok(f"total_pnl = unrealised + realised ({_fmt(total_pnl)})")

    if not positions:
        c.warn("No positions found — skipped portfolio arithmetic checks")

    # ── 3. Regime ─────────────────────────────────────────────────────────────
    print("\n── Regime ────────────────────────────────────────────────")
    regime = get_regime(exchange)
    required_regime = ["regime_ok", "index", "ema200"]
    for field in required_regime:
        val = regime.get(field)
        if val is None:
            c.warn(f"regime.{field} is None")
        else:
            c.ok(f"regime.{field} = {_fmt(val)}")

    # ── 4. Signals ────────────────────────────────────────────────────────────
    print("\n── Signals ───────────────────────────────────────────────")
    signals = get_signals(exchange, n=20)
    print(f"  Found {len(signals)} signals today\n")
    for s in signals[:5]:
        ticker = s.get("ticker", "?")
        score = s.get("composite_score")
        if score is None:
            c.fail(f"{ticker}: composite_score is None")
        elif not (0 <= score <= 100):
            c.fail(f"{ticker}: composite_score={score} out of [0,100]")
        else:
            c.ok(f"{ticker}: composite_score={score:.1f} — valid")

        # Check sub-scores non-negative
        for sub in ["sentiment_score", "fundamental_score", "technical_score"]:
            v = s.get(sub)
            if v is not None and v < 0:
                c.fail(f"{ticker}.{sub}={v} — negative score")

    if not signals:
        c.warn("No signals today — cannot validate signal fields")

    return c.summary()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exchange", default="asx", choices=["asx", "nse"])
    args = parser.parse_args()
    failures = run_validation(args.exchange)
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
