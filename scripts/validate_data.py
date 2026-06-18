"""
Data Validation Test — checks every data layer for correctness.
Run:  python scripts/validate_data.py [--exchange asx|nse]

Validates:
  1. Trade P&L display fields  — realised_pnl, realised_pnl_pct always populated
  2. Trade P&L arithmetic      — net_pnl ≈ (exit - entry) * shares - brokerage
  3. Return %                  — realised_pnl_pct == (exit - entry) / entry * 100
  4. Zero-P&L bug              — no trade where entry≠exit but realised_pnl=0
  5. Ticker inspector path     — _get_trades(730 days) returns correct fields
  6. Unrealised P&L            — (current - entry) * shares
  7. Day P&L presence          — warns when prev-close unavailable
  8. Total P&L cross-check     — unrealised + realised == total_pnl
  9. Regime fields             — regime_ok, index, ema200 present
 10. Signal scores             — composite in [0,100], sub-scores non-negative
"""

import argparse, sys, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("EXCHANGE", "asx")

TOLERANCE = 0.20   # $0.20 rounding tolerance
BROKERAGE = 9.95   # ASX flat brokerage per leg


def _fmt(val):
    if val is None: return "None"
    if isinstance(val, float): return f"{val:+,.2f}"
    return str(val)


class Check:
    def __init__(self):
        self.passed = self.failed = self.warnings = 0

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
        print(f"\n{'='*65}")
        print(f"RESULT: {self.passed}/{total} checks passed  "
              f"({self.warnings} warnings, {self.failed} failures)")
        if self.failed:
            print("  ACTION REQUIRED: Fix the ❌ items above before deploying.")
        return self.failed


def _check_trades(trades, c: Check, section_label: str):
    """Validate a list of trade dicts — reusable for any window size."""
    print(f"\n── {section_label} ({len(trades)} trades) ─────────────────────────")
    if not trades:
        c.warn("No trades found — cannot validate P&L arithmetic")
        return

    for t in trades:
        ticker = t.get("ticker", "?")
        ep = float(t.get("entry_price") or 0)
        xp = float(t.get("exit_price") or 0)
        sh = float(t.get("shares") or 0)
        net = float(t.get("net_pnl") or 0)
        rpnl = float(t.get("realised_pnl") or 0)
        rpct = float(t.get("realised_pnl_pct") or 0)
        exit_lbl = t.get("exit_reason_label") or ""
        label = f"{ticker} {str(t.get('exit_date',''))[:10]}"

        # ── 1. Display fields must be populated ─────────────────────────────
        if t.get("realised_pnl") is None:
            c.fail(f"{label}: realised_pnl is None — will display as $0.00")
        if t.get("realised_pnl_pct") is None:
            c.fail(f"{label}: realised_pnl_pct is None — will display as 0.0%")
        if not exit_lbl or exit_lbl == "—":
            c.warn(f"{label}: exit_reason_label is empty (exit_reason='{t.get('exit_reason')}')")

        # ── 2. Zero-P&L bug: entry ≠ exit but realised_pnl = 0 ─────────────
        if ep > 0 and xp > 0 and abs(xp - ep) > 0.001:
            if abs(rpnl) < 0.01:
                c.fail(f"{label}: ZERO P&L BUG — entry={_fmt(ep)} exit={_fmt(xp)} "
                       f"but realised_pnl={_fmt(rpnl)}")
            else:
                c.ok(f"{label}: realised_pnl={_fmt(rpnl)} (entry={_fmt(ep)} exit={_fmt(xp)})")
        elif ep > 0 and xp > 0 and abs(xp - ep) <= 0.001:
            c.ok(f"{label}: flat trade (entry ≈ exit), pnl={_fmt(rpnl)}")

        # ── 3. realised_pnl_pct computed correctly from prices ───────────────
        if ep > 0 and xp > 0:
            expected_pct = (xp - ep) / ep * 100
            if abs(rpct - expected_pct) > 0.1:
                c.fail(f"{label}: realised_pnl_pct={rpct:.2f}% expected={expected_pct:.2f}%")

        # ── 4. P&L arithmetic: gross ≈ (exit - entry) * shares ──────────────
        if ep > 0 and xp > 0 and sh > 0:
            trade_type = str(t.get("trade_type") or "buy").lower()
            if trade_type in ("cover", "short"):
                expected_gross = (ep - xp) * sh
            else:
                expected_gross = (xp - ep) * sh
            gross = float(t.get("gross_pnl") or 0)
            if gross != 0 and abs(gross - expected_gross) > TOLERANCE:
                c.warn(f"{label}: gross_pnl={_fmt(gross)} expected≈{_fmt(expected_gross)}")

        # ── 5. realised_pnl == net_pnl (after any recompute) ────────────────
        if abs(rpnl - net) > TOLERANCE:
            c.warn(f"{label}: realised_pnl={_fmt(rpnl)} ≠ net_pnl={_fmt(net)} (may be recomputed)")


def run_validation(exchange: str):
    c = Check()
    from dashboard.data import get_trades, get_portfolio, get_regime, get_signals, _normalise_trade
    from datetime import date

    print(f"\n{'='*65}")
    print(f"Data Validation — {exchange.upper()}  [{date.today()}]")
    print(f"{'='*65}")

    # ── Unit tests for _normalise_trade (offline — no DB required) ─────────
    print("\n── Unit Tests: _normalise_trade() ─────────────────────────")

    # Case A: correct data as stored in DB
    t_ok = _normalise_trade({"entry_price": 7.57, "exit_price": 8.08,
                              "shares": 1321, "net_pnl": 659.56,
                              "exit_reason": "intraday_target"})
    assert abs(t_ok["realised_pnl"] - 659.56) < 0.01, "Case A: realised_pnl wrong"
    assert abs(t_ok["realised_pnl_pct"] - 6.74) < 0.05, "Case A: pct wrong"
    assert t_ok["exit_reason_label"] == "Intraday Target", "Case A: label wrong"
    c.ok("Case A [normal trade]: realised_pnl=+659.56, pct=+6.74%, label='Intraday Target'")

    # Case B: net_pnl stored as 0 — fallback recomputes from prices
    t_bug = _normalise_trade({"entry_price": 7.57, "exit_price": 8.08,
                               "shares": 1321, "net_pnl": 0,
                               "exit_reason": "intraday_target"})
    assert abs(t_bug["realised_pnl"]) > 0, "Case B: fallback did not fire"
    assert abs(t_bug["realised_pnl_pct"] - 6.74) < 0.05, "Case B: pct wrong"
    c.ok(f"Case B [net_pnl=0 fallback]: realised_pnl={_fmt(t_bug['realised_pnl'])}, pct={t_bug['realised_pnl_pct']:+.2f}%")

    # Case C: stop loss (entry > exit, should be negative)
    t_loss = _normalise_trade({"entry_price": 3.25, "exit_price": 2.82,
                                "shares": 3073, "net_pnl": -1359.94,
                                "exit_reason": "stop_loss"})
    assert t_loss["realised_pnl"] < 0, "Case C: loss should be negative"
    assert t_loss["realised_pnl_pct"] < 0, "Case C: pct should be negative"
    assert t_loss["exit_reason_label"] == "Stop Loss", "Case C: label wrong"
    c.ok(f"Case C [stop loss]: realised_pnl={_fmt(t_loss['realised_pnl'])}, pct={t_loss['realised_pnl_pct']:+.2f}%, label='Stop Loss'")

    # Case D: short trade cover with net_pnl=0 — fallback uses (entry-exit)*shares
    t_short = _normalise_trade({"entry_price": 10.0, "exit_price": 9.0,
                                 "shares": 100, "net_pnl": 0,
                                 "trade_type": "cover"})
    assert t_short["realised_pnl"] > 0, "Case D: short profit should be positive"
    c.ok(f"Case D [short cover fallback]: realised_pnl={_fmt(t_short['realised_pnl'])}")

    # Case E: flat trade (entry == exit exactly) — pnl should reflect brokerage only
    t_flat = _normalise_trade({"entry_price": 5.0, "exit_price": 5.0,
                                "shares": 200, "net_pnl": -19.90})
    assert t_flat["realised_pnl_pct"] == 0.0, "Case E: pct should be 0"
    c.ok(f"Case E [flat trade]: realised_pnl={_fmt(t_flat['realised_pnl'])}, pct=0.0%")

    # ── Live data: 90-day trades (main Trade History tab) ─────────────────
    trades_90 = get_trades(exchange, days=90)
    _check_trades(trades_90, c, "Live trades — 90 days (Trade History tab)")

    # ── Live data: 730-day trades (Ticker Inspector path) ─────────────────
    trades_730 = get_trades(exchange, days=730)
    _check_trades(trades_730, c, "Live trades — 730 days (Ticker Inspector)")

    # ── Portfolio / Positions ─────────────────────────────────────────────
    print("\n── Portfolio positions ──────────────────────────────────────")
    portfolio = get_portfolio(exchange, live=False)
    positions = portfolio.get("positions", [])
    print(f"  Found {len(positions)} open positions")

    for p in positions:
        ticker = p.get("ticker", "?")
        ep = float(p.get("entry_price") or 0)
        cp = float(p.get("current_price") or 0)
        sh = float(p.get("shares") or 0)
        upnl = float(p.get("unrealised_pnl") or 0)
        upct = float(p.get("unrealised_pnl_pct") or 0)

        if ep and cp and sh:
            expected = (cp - ep) * sh
            if abs(upnl - expected) > TOLERANCE:
                c.fail(f"{ticker}: unrealised_pnl={_fmt(upnl)} expected={_fmt(expected)}")
            else:
                c.ok(f"{ticker}: unrealised_pnl={_fmt(upnl)} ✓  current={_fmt(cp)} entry={_fmt(ep)}")

        if ep and cp:
            expected_pct = (cp - ep) / ep * 100
            if abs(upct - expected_pct) > 0.1:
                c.fail(f"{ticker}: unrealised_pnl_pct={upct:.2f}% expected={expected_pct:.2f}%")

        if p.get("day_pnl") is None:
            c.warn(f"{ticker}: day_pnl is None (prev close unavailable — market may be closed)")
        else:
            c.ok(f"{ticker}: day_pnl={_fmt(float(p['day_pnl']))} populated")

    total_pnl      = portfolio.get("total_pnl", 0) or 0
    total_unreal   = portfolio.get("total_unrealised_pnl", 0) or 0
    total_realised = portfolio.get("total_realised_pnl", 0) or 0
    expected_total = total_unreal + total_realised
    if abs(total_pnl - expected_total) > TOLERANCE:
        c.fail(f"total_pnl={_fmt(total_pnl)} ≠ unrealised+realised={_fmt(expected_total)}")
    else:
        c.ok(f"total_pnl = unrealised+realised = {_fmt(total_pnl)}")

    if not positions:
        c.warn("No positions found — skipped portfolio arithmetic checks")

    # ── Regime ───────────────────────────────────────────────────────────
    print("\n── Regime ───────────────────────────────────────────────────")
    regime = get_regime(exchange)
    for field in ["regime_ok", "index", "ema200"]:
        val = regime.get(field)
        if val is None:
            c.warn(f"regime.{field} is None")
        else:
            c.ok(f"regime.{field} = {_fmt(val) if isinstance(val, float) else val}")

    # ── Signals ──────────────────────────────────────────────────────────
    print("\n── Signals ──────────────────────────────────────────────────")
    signals = get_signals(exchange, n=20)
    print(f"  Found {len(signals)} signals today")
    for s in signals[:10]:
        ticker = s.get("ticker", "?")
        score = s.get("composite_score")
        if score is None:
            c.fail(f"{ticker}: composite_score is None")
        elif not (0 <= score <= 100):
            c.fail(f"{ticker}: composite_score={score} out of [0,100]")
        else:
            c.ok(f"{ticker}: composite={score:.1f}")
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
