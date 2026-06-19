"""
Regression Test — Multi-Scenario Signal Gate Diagnostic
========================================================
Tests multiple parameter configurations bar-by-bar across ASX200 tickers
to find the optimal balance of trade frequency vs. quality. Produces a
JSON report consumed by the Research tab.

Scenarios tested:
  conservative  — tight gates, fewer but higher-quality trades
  current       — live deployed params
  aggressive    — relaxed gates, more trades, slightly lower quality bar
  max_trades    — most permissive, catch all validated+firing strategies

Run:
    python -m scripts.regression_test [--n 50] [--out regression_report.json]
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.asx200_tickers import ASX200_TICKERS
from strategies.indicators import precompute
from strategies.library import ALL_STRATEGIES
from strategies.backtest import run_strategy_backtest, rank_score

# ── Parameter scenarios ───────────────────────────────────────────────────────
SCENARIOS = {
    "conservative": dict(
        signal_threshold=65.0,
        min_sentiment=35.0,
        min_fundamental=40.0,
        min_technical=35.0,
        bt_min_trades=5,
        bt_min_pf=1.25,
        bt_min_wr=0.45,
        fw_min_pf=1.05,
    ),
    "current": dict(
        signal_threshold=62.0,
        min_sentiment=30.0,
        min_fundamental=35.0,
        min_technical=28.0,
        bt_min_trades=4,
        bt_min_pf=1.1,
        bt_min_wr=0.40,
        fw_min_pf=1.0,
    ),
    "aggressive": dict(
        signal_threshold=58.0,
        min_sentiment=25.0,
        min_fundamental=30.0,
        min_technical=22.0,
        bt_min_trades=3,
        bt_min_pf=1.05,
        bt_min_wr=0.36,
        fw_min_pf=0.95,
    ),
    "max_trades": dict(
        signal_threshold=55.0,
        min_sentiment=20.0,
        min_fundamental=25.0,
        min_technical=18.0,
        bt_min_trades=3,
        bt_min_pf=1.0,
        bt_min_wr=0.33,
        fw_min_pf=0.90,
    ),
}


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


def _is_validated(result: Dict, cfg: Dict) -> bool:
    bt, fw = result["backtest"], result["forward"]
    if bt["num_trades"] < cfg["bt_min_trades"]:
        return False
    if bt["profit_factor"] < cfg["bt_min_pf"]:
        return False
    if bt["win_rate"] < cfg["bt_min_wr"]:
        return False
    if fw["num_trades"] > 0 and fw["profit_factor"] < cfg["fw_min_pf"]:
        return False
    return True


def evaluate_ticker(ticker: str, ohlcv: Dict, cfg: Dict, ind: Dict) -> Dict:
    n = len(ohlcv["closes"])
    strategies_out = []
    best_validated = None
    best_rank = -1.0

    for strat in ALL_STRATEGIES:
        try:
            result = run_strategy_backtest(strat, ind)
        except Exception:
            continue

        validated = _is_validated(result, cfg)
        r_score = rank_score(result)
        fired_today = None
        try:
            fired_today = strat.evaluate_latest(ind) if hasattr(strat, "evaluate_latest") else strat.fires(ind, n - 1)
        except Exception:
            pass

        entry = strategies_out.__len__()
        strategies_out.append({
            "name":         strat.name,
            "validated":    validated,
            "bt_trades":    result["backtest"]["num_trades"],
            "bt_pf":        round(result["backtest"]["profit_factor"], 2),
            "bt_wr":        round(result["backtest"]["win_rate"], 3),
            "fw_trades":    result["forward"]["num_trades"],
            "fw_pf":        round(result["forward"]["profit_factor"], 2),
            "fw_ret":       round(result["forward"]["total_return_pct"], 2),
            "fw_max_dd":    round(result["forward"].get("max_drawdown_pct", 0), 2),
            "rank":         round(r_score, 3),
            "fires_today":  bool(fired_today),
            "fire_reason":  (fired_today or {}).get("reason", "") if fired_today else "",
        })

        if validated and r_score > best_rank:
            best_rank = r_score
            best_validated = strategies_out[-1]

    latest_close = float(ohlcv["closes"][-1])
    sma200 = float(ind["sma200"][-1])
    rsi_val = float(ind["rsi"][-1])
    adx_val = float(ind["adx"][-1])
    vol_ratio = float(ohlcv["volumes"][-1] / (float(ind["vol_avg_20"][-1]) + 1e-9))

    firing_validated = next(
        (s for s in strategies_out if s["validated"] and s["fires_today"]), None
    )
    fires_today = bool(firing_validated)
    fire_strategy = (firing_validated or best_validated or {}).get("name")
    fire_reason = (firing_validated or {}).get("fire_reason", "")

    # Estimate expected value: avg forward return * win_rate of firing strategy
    expected_value = 0.0
    if firing_validated:
        expected_value = round(
            firing_validated["fw_ret"] * firing_validated["bt_wr"], 2
        )

    blocked_reasons = []
    if not best_validated:
        blocked_reasons.append("no_validated_strategy")
    elif not fires_today:
        blocked_reasons.append(f"strategy_not_firing ({(best_validated or {}).get('name','')})")

    return {
        "ticker":        ticker,
        "latest_close":  round(latest_close, 3),
        "bars":          n,
        "rsi":           round(rsi_val, 1),
        "adx":           round(adx_val, 1),
        "vol_ratio":     round(vol_ratio, 2),
        "above_sma200":  latest_close > sma200,
        "best_strategy": fire_strategy,
        "best_validated": bool(best_validated),
        "fires_today":   fires_today,
        "fire_reason":   fire_reason,
        "expected_value": expected_value,
        "blocked_reasons": [] if fires_today else blocked_reasons,
        "strategies":    strategies_out,
    }


def _strategy_table(results: List[Dict]) -> List[Dict]:
    from collections import defaultdict
    stats = defaultdict(lambda: {
        "validated": 0, "fires_today": 0, "total": 0,
        "fw_pf": [], "fw_ret": [], "fw_dd": [], "bt_trades": [],
    })
    for r in results:
        for s in r["strategies"]:
            nm = s["name"]
            stats[nm]["total"] += 1
            if s["validated"]:
                stats[nm]["validated"] += 1
            if s["fires_today"]:
                stats[nm]["fires_today"] += 1
            stats[nm]["fw_pf"].append(s["fw_pf"])
            stats[nm]["fw_ret"].append(s["fw_ret"])
            stats[nm]["fw_dd"].append(s["fw_max_dd"])
            stats[nm]["bt_trades"].append(s["bt_trades"])

    table = []
    for nm, st in sorted(stats.items(), key=lambda x: -x[1]["validated"]):
        n_t = st["total"]
        table.append({
            "strategy":          nm,
            "tickers_tested":    n_t,
            "validated_count":   st["validated"],
            "validated_pct":     round(st["validated"] / n_t * 100) if n_t else 0,
            "fires_today_count": st["fires_today"],
            "fires_today_pct":   round(st["fires_today"] / n_t * 100) if n_t else 0,
            "avg_fw_pf":         round(float(np.mean(st["fw_pf"])), 2) if st["fw_pf"] else 0,
            "avg_fw_ret_pct":    round(float(np.mean(st["fw_ret"])), 2) if st["fw_ret"] else 0,
            "avg_fw_dd_pct":     round(float(np.mean(st["fw_dd"])), 2) if st["fw_dd"] else 0,
            "avg_bt_trades":     round(float(np.mean(st["bt_trades"])), 1) if st["bt_trades"] else 0,
        })
    return table


def run_regression(tickers: List[str], n_tickers: int = 50) -> Dict:
    tickers = tickers[:n_tickers]
    print(f"Running regression on {len(tickers)} tickers across {len(SCENARIOS)} scenarios...", flush=True)

    # Pre-fetch OHLCV once, reuse across all scenarios
    ohlcv_cache: Dict[str, Optional[Dict]] = {}
    ind_cache:   Dict[str, Optional[Dict]] = {}

    for i, ticker in enumerate(tickers):
        print(f"  [{i+1}/{len(tickers)}] {ticker}", flush=True, end=" ")
        ohlcv = fetch_ohlcv(ticker)
        if ohlcv is None or len(ohlcv["closes"]) < 120:
            print("✗ insufficient data")
            ohlcv_cache[ticker] = None
            continue
        try:
            ohlcv_cache[ticker] = ohlcv
            ind_cache[ticker]   = precompute(ohlcv)
            print("✓")
        except Exception as e:
            print(f"✗ precompute: {e}")
            ohlcv_cache[ticker] = None

    valid_tickers = [t for t in tickers if ohlcv_cache.get(t)]
    print(f"\n{len(valid_tickers)}/{len(tickers)} tickers loaded. Evaluating scenarios...\n", flush=True)

    scenario_results: Dict[str, Dict] = {}

    for scenario_name, cfg in SCENARIOS.items():
        print(f"  Scenario: {scenario_name}", flush=True)
        results = []
        funnel = {"loaded": len(valid_tickers), "any_validated": 0, "fires_today": 0}

        for ticker in valid_tickers:
            r = evaluate_ticker(ticker, ohlcv_cache[ticker], cfg, ind_cache[ticker])
            results.append(r)
            if r["best_validated"]:
                funnel["any_validated"] += 1
            if r["fires_today"]:
                funnel["fires_today"] += 1

        firing = [r for r in results if r["fires_today"]]
        total_ev = round(sum(r["expected_value"] for r in firing), 2)

        scenario_results[scenario_name] = {
            "params":           cfg,
            "funnel":           funnel,
            "fires_today_count": len(firing),
            "avg_expected_value": round(total_ev / max(len(firing), 1), 2),
            "total_expected_value": total_ev,
            "strategy_table":  _strategy_table(results),
            "firing_tickers":  [
                {
                    "ticker":         r["ticker"],
                    "strategy":       r["best_strategy"],
                    "reason":         r["fire_reason"],
                    "adx":            r["adx"],
                    "rsi":            r["rsi"],
                    "above_sma200":   r["above_sma200"],
                    "expected_value": r["expected_value"],
                    "latest_close":   r["latest_close"],
                }
                for r in sorted(firing, key=lambda x: -x["expected_value"])
            ],
            "block_reasons":   {},
        }
        for r in results:
            for reason in r["blocked_reasons"]:
                d = scenario_results[scenario_name]["block_reasons"]
                d[reason] = d.get(reason, 0) + 1

        print(f"    fires_today={len(firing)}, total_EV={total_ev:.1f}%", flush=True)

    report = {
        "run_date":       str(date.today()),
        "tickers_tested": len(valid_tickers),
        "scenarios":      scenario_results,
        "scenario_names": list(SCENARIOS.keys()),
    }
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n",   type=int, default=50)
    parser.add_argument("--out", type=str, default="regression_report.json")
    args = parser.parse_args()

    report = run_regression(ASX200_TICKERS, n_tickers=args.n)

    out_path = Path(__file__).parent.parent / args.out
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n{'='*70}")
    print(f"{'Scenario':<16} {'Loaded':>7} {'Validated':>10} {'Fires':>7} {'TotalEV':>9} {'AvgEV':>8}")
    print("-" * 70)
    for name in report["scenario_names"]:
        s  = report["scenarios"][name]
        fn = s["funnel"]
        print(
            f"{name:<16} {fn['loaded']:>7} {fn['any_validated']:>10} "
            f"{s['fires_today_count']:>7} {s['total_expected_value']:>8.1f}% "
            f"{s['avg_expected_value']:>7.2f}%"
        )

    print(f"\nTop firing tickers by scenario (current):")
    for t in report["scenarios"]["current"]["firing_tickers"][:10]:
        print(f"  {t['ticker']:<12} {t['strategy']:<20} EV={t['expected_value']:+.2f}%  {t['reason']}")

    print(f"\nExtra tickers unlocked in 'aggressive' vs 'current':")
    cur_firing  = {r["ticker"] for r in report["scenarios"]["current"]["firing_tickers"]}
    agg_firing  = {r["ticker"] for r in report["scenarios"]["aggressive"]["firing_tickers"]}
    new_tickers = agg_firing - cur_firing
    for t in report["scenarios"]["aggressive"]["firing_tickers"]:
        if t["ticker"] in new_tickers:
            print(f"  +{t['ticker']:<11} {t['strategy']:<20} EV={t['expected_value']:+.2f}%")

    print(f"\nReport → {out_path}")


if __name__ == "__main__":
    main()
