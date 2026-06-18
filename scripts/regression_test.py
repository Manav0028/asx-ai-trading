"""
Regression Test — Signal Gate Funnel Diagnostic
================================================
Pulls the last 400 days of price history for ASX200 tickers via yfinance,
runs every strategy bar-by-bar, and reports exactly where trades are being
blocked today. Produces a JSON report read by the Research tab.

Run:
    python -m scripts.regression_test [--n 30] [--out regression_report.json]
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

# ── allow running as a script from the project root ───────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.asx200_tickers import ASX200_TICKERS
from strategies.indicators import precompute
from strategies.library import ALL_STRATEGIES, STRATEGY_BY_NAME
from strategies.backtest import (
    run_strategy_backtest, is_validated, rank_score,
    BT_MIN_TRADES, BT_MIN_PROFIT_FACTOR, BT_MIN_WIN_RATE,
    FW_MIN_PROFIT_FACTOR,
)

# ── thresholds we want to compare ─────────────────────────────────────────────
# ORIGINAL params (before this regression run)
ORIGINAL = dict(
    signal_threshold=65.0,
    min_sentiment=35.0,
    min_fundamental=40.0,
    min_technical=35.0,
    bt_min_trades=5,
    bt_min_pf=1.2,
    bt_min_wr=0.45,
    fw_min_pf=1.0,
)
# CURRENT params (now deployed in code)
CURRENT = dict(
    signal_threshold=62.0,
    min_sentiment=30.0,
    min_fundamental=35.0,
    min_technical=28.0,
    bt_min_trades=BT_MIN_TRADES,
    bt_min_pf=BT_MIN_PROFIT_FACTOR,
    bt_min_wr=BT_MIN_WIN_RATE,
    fw_min_pf=FW_MIN_PROFIT_FACTOR,
)
PROPOSED = CURRENT  # same — run the single comparison original vs current


def fetch_ohlcv(ticker: str, days: int = 720) -> Optional[Dict[str, np.ndarray]]:
    try:
        import yfinance as yf
        end = date.today()
        start = end - timedelta(days=days)
        df = yf.download(ticker, start=str(start), end=str(end), progress=False, auto_adjust=True)
        if df is None or len(df) < 60:
            return None
        df = df.dropna()

        def _col(name: str) -> np.ndarray:
            col = df[name]
            # newer yfinance returns MultiIndex columns: (name, ticker)
            if hasattr(col, "iloc") and col.ndim == 2:
                col = col.iloc[:, 0]
            return np.array(col, dtype=float).flatten()

        return {
            "opens":   _col("Open"),
            "highs":   _col("High"),
            "lows":    _col("Low"),
            "closes":  _col("Close"),
            "volumes": _col("Volume"),
        }
    except Exception as e:
        print(f"  [yf error] {ticker}: {e}", file=sys.stderr)
        return None


def is_validated_custom(result: Dict, cfg: Dict) -> bool:
    bt, fw = result["backtest"], result["forward"]
    if bt["num_trades"] < cfg["bt_min_trades"]:        return False
    if bt["profit_factor"] < cfg["bt_min_pf"]:         return False
    if bt["win_rate"] < cfg["bt_min_wr"]:              return False
    # FW: if it fired in the forward window it must be profitable; 0 fires = ok
    if fw["num_trades"] > 0 and fw["profit_factor"] < cfg["fw_min_pf"]:
        return False
    return True


def evaluate_ticker(ticker: str, ohlcv: Dict, cfg: Dict, ind: Dict) -> Dict:
    """
    For a given config, run every strategy's backtest+forward test and check
    whether an entry condition fires today (latest bar).
    Returns a dict with gate results and per-strategy breakdown.
    """
    n = len(ohlcv["closes"])

    strategies_out = []
    best_validated = None
    best_rank = -1.0

    for strat in ALL_STRATEGIES:
        try:
            result = run_strategy_backtest(strat, ind)
        except Exception:
            continue

        validated = is_validated_custom(result, cfg)
        r_score = rank_score(result)
        fired_today = None
        try:
            fired_today = strat.evaluate_latest(ind) if hasattr(strat, "evaluate_latest") else strat.fires(ind, n - 1)
        except Exception:
            pass

        strategies_out.append({
            "name": strat.name,
            "validated": validated,
            "bt_trades": result["backtest"]["num_trades"],
            "bt_pf": result["backtest"]["profit_factor"],
            "bt_wr": round(result["backtest"]["win_rate"], 3),
            "fw_trades": result["forward"]["num_trades"],
            "fw_pf": result["forward"]["profit_factor"],
            "fw_ret": result["forward"]["total_return_pct"],
            "rank": r_score,
            "fires_today": bool(fired_today),
            "fire_reason": (fired_today or {}).get("reason", "") if fired_today else "",
        })

        if validated and r_score > best_rank:
            best_rank = r_score
            best_validated = strategies_out[-1]

    # Synthesise scores using simple proxies (proper scorers need full env)
    latest_close = float(ohlcv["closes"][-1])
    ema20 = float(ind["ema20"][-1])
    sma200 = float(ind["sma200"][-1])
    rsi_val = float(ind["rsi"][-1])
    adx_val = float(ind["adx"][-1])
    vol_ratio = float(ohlcv["volumes"][-1] / (float(ind["vol_avg_20"][-1]) + 1e-9))

    # Quick proxy composite (avoids needing Supabase/LLM — price action only)
    price_strength = 50 + 30 * ((latest_close - sma200) / (sma200 + 1e-9)) * 10
    price_strength = max(0, min(100, price_strength))
    rsi_score = 100 - rsi_val  # low RSI = oversold = higher sentiment proxy
    tech_proxy = min(100, max(0, (adx_val / 50) * 60 + (1 - abs(rsi_val - 50) / 50) * 40))

    # Blocked reasons (current config)
    blocked_reasons = []
    if not best_validated:
        any_validated = any(s["validated"] for s in strategies_out)
        if not any_validated:
            blocked_reasons.append("no_validated_strategy")
    elif best_validated and not best_validated["fires_today"]:
        blocked_reasons.append(f"strategy_not_firing ({best_validated['name']})")

    # Any validated strategy that fires today wins — mirrors the new selector logic
    firing_validated = next(
        (s for s in strategies_out if s["validated"] and s["fires_today"]), None
    )
    fires_today = bool(firing_validated)
    fire_strategy = (firing_validated or best_validated or {}).get("name")
    fire_reason = (firing_validated or {}).get("fire_reason", "")

    return {
        "ticker": ticker,
        "latest_close": round(latest_close, 3),
        "bars": n,
        "rsi": round(rsi_val, 1),
        "adx": round(adx_val, 1),
        "vol_ratio": round(vol_ratio, 2),
        "above_sma200": latest_close > sma200,
        "best_strategy": fire_strategy,
        "best_validated": bool(best_validated),
        "fires_today": fires_today,
        "fire_reason": fire_reason,
        "blocked_reasons": [] if fires_today else blocked_reasons,
        "strategies": strategies_out,
    }


def run_regression(tickers: List[str], n_tickers: int = 40) -> Dict:
    tickers = tickers[:n_tickers]
    print(f"Running regression on {len(tickers)} tickers...", flush=True)

    results_current  = []
    results_proposed = []
    gate_funnel_current  = {"loaded": 0, "enough_bars": 0, "any_strategy_validated": 0, "strategy_fires_today": 0}
    gate_funnel_proposed = {"loaded": 0, "enough_bars": 0, "any_strategy_validated": 0, "strategy_fires_today": 0}
    strategy_fire_count: Dict[str, int] = {}
    strategy_block_reasons: Dict[str, int] = {}

    for i, ticker in enumerate(tickers):
        print(f"  [{i+1}/{len(tickers)}] {ticker}", flush=True, end=" ")
        ohlcv = fetch_ohlcv(ticker)
        if ohlcv is None:
            print("✗ no data")
            continue

        gate_funnel_current["loaded"] += 1
        gate_funnel_proposed["loaded"] += 1

        n = len(ohlcv["closes"])
        if n < 120:
            print(f"✗ only {n} bars")
            continue

        gate_funnel_current["enough_bars"] += 1
        gate_funnel_proposed["enough_bars"] += 1

        try:
            ind = precompute(ohlcv)
        except Exception as e:
            print(f"✗ precompute failed: {e}")
            continue

        cur  = evaluate_ticker(ticker, ohlcv, CURRENT,  ind)
        prop = evaluate_ticker(ticker, ohlcv, PROPOSED, ind)

        results_current.append(cur)
        results_proposed.append(prop)

        if cur["best_validated"]:
            gate_funnel_current["any_strategy_validated"] += 1
        if cur["fires_today"]:
            gate_funnel_current["strategy_fires_today"] += 1
            sname = cur["best_strategy"] or "unknown"
            strategy_fire_count[sname] = strategy_fire_count.get(sname, 0) + 1

        if prop["best_validated"]:
            gate_funnel_proposed["any_strategy_validated"] += 1
        if prop["fires_today"]:
            gate_funnel_proposed["strategy_fires_today"] += 1

        for r in cur["blocked_reasons"]:
            strategy_block_reasons[r] = strategy_block_reasons.get(r, 0) + 1

        status = []
        if cur["fires_today"]:  status.append("🟢FIRES")
        elif cur["best_validated"]: status.append("🟡validated/silent")
        else: status.append("🔴blocked")
        if prop["fires_today"] and not cur["fires_today"]: status.append("→proposed unlocks")
        print(" ".join(status))

    # ── per-strategy validation & fire rates ──────────────────────────────────
    strat_stats: Dict[str, Dict] = {}
    for r in results_current:
        for s in r["strategies"]:
            nm = s["name"]
            if nm not in strat_stats:
                strat_stats[nm] = {"validated": 0, "fires_today": 0, "total": 0,
                                   "avg_fw_pf": [], "avg_fw_trades": [], "avg_bt_trades": []}
            strat_stats[nm]["total"] += 1
            if s["validated"]:
                strat_stats[nm]["validated"] += 1
            if s["fires_today"]:
                strat_stats[nm]["fires_today"] += 1
            strat_stats[nm]["avg_fw_pf"].append(s["fw_pf"])
            strat_stats[nm]["avg_fw_trades"].append(s["fw_trades"])
            strat_stats[nm]["avg_bt_trades"].append(s["bt_trades"])

    strat_table = []
    for nm, st in sorted(strat_stats.items(), key=lambda x: -x[1]["validated"]):
        n_t = st["total"]
        strat_table.append({
            "strategy": nm,
            "tickers_tested": n_t,
            "validated_count": st["validated"],
            "validated_pct": round(st["validated"] / n_t * 100) if n_t else 0,
            "fires_today_count": st["fires_today"],
            "fires_today_pct": round(st["fires_today"] / n_t * 100) if n_t else 0,
            "avg_fw_pf": round(float(np.mean(st["avg_fw_pf"])), 2) if st["avg_fw_pf"] else 0,
            "avg_fw_trades": round(float(np.mean(st["avg_fw_trades"])), 1) if st["avg_fw_trades"] else 0,
            "avg_bt_trades": round(float(np.mean(st["avg_bt_trades"])), 1) if st["avg_bt_trades"] else 0,
        })

    # ── tickers that would fire under proposed params ─────────────────────────
    newly_unlocked = [
        {
            "ticker": r["ticker"],
            "strategy": r["best_strategy"],
            "reason": r["fire_reason"],
            "adx": r["adx"],
            "rsi": r["rsi"],
        }
        for r in results_proposed
        if r["fires_today"] and not next(
            (c for c in results_current if c["ticker"] == r["ticker"] and c["fires_today"]),
            None,
        )
    ]

    currently_firing = [
        {
            "ticker": r["ticker"],
            "strategy": r["best_strategy"],
            "reason": r["fire_reason"],
            "adx": r["adx"],
            "rsi": r["rsi"],
            "above_sma200": r["above_sma200"],
        }
        for r in results_current if r["fires_today"]
    ]

    report = {
        "run_date": str(date.today()),
        "tickers_tested": len(results_current),
        "gate_funnel_current": gate_funnel_current,
        "gate_funnel_proposed": gate_funnel_proposed,
        "block_reasons": strategy_block_reasons,
        "strategy_table": strat_table,
        "currently_firing": currently_firing,
        "newly_unlocked": newly_unlocked,
        "current_params": CURRENT,
        "proposed_params": PROPOSED,
    }

    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50, help="Number of tickers to test")
    parser.add_argument("--out", type=str, default="regression_report.json")
    args = parser.parse_args()

    report = run_regression(ASX200_TICKERS, n_tickers=args.n)

    out_path = Path(__file__).parent.parent / args.out
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n{'='*60}")
    print(f"CURRENT PARAMS  — gate funnel:")
    for gate, count in report["gate_funnel_current"].items():
        pct = round(count / max(report["tickers_tested"], 1) * 100)
        print(f"  {gate:<40} {count:>4}  ({pct}%)")

    print(f"\nPROPOSED PARAMS — gate funnel:")
    for gate, count in report["gate_funnel_proposed"].items():
        pct = round(count / max(report["tickers_tested"], 1) * 100)
        print(f"  {gate:<40} {count:>4}  ({pct}%)")

    print(f"\nBlock reasons breakdown:")
    for reason, count in sorted(report["block_reasons"].items(), key=lambda x: -x[1]):
        print(f"  {reason:<45} {count:>4}x")

    print(f"\nStrategy validation rates (current params):")
    for row in report["strategy_table"]:
        print(f"  {row['strategy']:<20} validated={row['validated_pct']:>3}%  "
              f"fires_today={row['fires_today_pct']:>3}%  "
              f"avg_fw_pf={row['avg_fw_pf']:.2f}  avg_fw_trades={row['avg_fw_trades']:.1f}")

    print(f"\nCurrently firing ({len(report['currently_firing'])}):")
    for t in report["currently_firing"]:
        print(f"  {t['ticker']:<12} {t['strategy']:<20} {t['reason']}")

    print(f"\nNewly unlocked by proposed params ({len(report['newly_unlocked'])}):")
    for t in report["newly_unlocked"]:
        print(f"  {t['ticker']:<12} {t['strategy']:<20} {t['reason']}")

    print(f"\nReport saved to: {out_path}")


if __name__ == "__main__":
    main()
