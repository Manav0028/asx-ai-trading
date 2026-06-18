"""
Parameter Variation Scanner
============================
Downloads price history ONCE for N tickers, then sweeps a grid of
validation thresholds and entry-condition looseness settings.
Reports how many tickers fire today under each combination so we can
pick the sweet spot between signal quality and signal frequency.

Run:
    python scripts/param_scan.py [--n 80]
"""
import argparse, sys, json
from pathlib import Path
from datetime import date, timedelta
from typing import Dict, List, Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.asx200_tickers import ASX200_TICKERS
from strategies.indicators import precompute
from strategies.library import ALL_STRATEGIES


# ── Download once, test many ──────────────────────────────────────────────────

def fetch_ohlcv(ticker: str, days: int = 720) -> Optional[Dict]:
    try:
        import yfinance as yf
        from datetime import date as d
        end   = d.today()
        start = end - timedelta(days=days)
        df = yf.download(ticker, start=str(start), end=str(end),
                         progress=False, auto_adjust=True)
        if df is None or len(df) < 60:
            return None
        df = df.dropna()

        def _col(name):
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
        print(f"  [yf] {ticker}: {e}", file=sys.stderr)
        return None


# ── Per-strategy backtest with custom thresholds ──────────────────────────────

WARMUP = 60

def _metrics(returns):
    if not returns:
        return {"n": 0, "wr": 0.0, "pf": 0.0}
    arr = np.array(returns)
    wins = arr[arr > 0]
    loss = arr[arr <= 0]
    pf = float(np.sum(wins) / (abs(np.sum(loss)) + 1e-9)) if len(loss) else 99.0
    return {
        "n":  len(arr),
        "wr": round(float(np.mean(arr > 0)), 3),
        "pf": round(min(pf, 99.0), 2),
    }


def run_bt(strat, ind, fw_frac):
    closes = ind["closes"]; highs = ind["highs"]; lows = ind["lows"]; atr = ind["atr"]
    n = len(closes)
    split = int(n * (1 - fw_frac))
    bt_r, fw_r = [], []
    in_pos = False
    ep = st = tg = 0.0
    ei = 0
    for i in range(WARMUP, n):
        if in_pos:
            ex = None
            if lows[i] <= st:  ex = st
            elif highs[i] >= tg: ex = tg
            if ex is None and i - ei >= strat.max_hold_days: ex = closes[i]
            if ex is not None:
                fill = ex * (1 - 0.001)
                ret  = (fill - ep) / ep - 2 * 9.95 / 10000
                (bt_r if ei < split else fw_r).append(ret)
                in_pos = False
            continue
        if i >= n - 1: break
        if strat.fires(ind, i):
            ep = closes[i] * 1.001
            st = ep - strat.stop_mult   * atr[i]
            tg = ep + strat.target_mult * atr[i]
            ei = i
            in_pos = True
    return {"bt": _metrics(bt_r), "fw": _metrics(fw_r)}


def is_valid(r, cfg):
    bt, fw = r["bt"], r["fw"]
    if bt["n"] < cfg["bt_n"]:  return False
    if bt["pf"] < cfg["bt_pf"]: return False
    if bt["wr"] < cfg["bt_wr"]: return False
    if fw["n"] < cfg["fw_n"]:  return False
    if cfg["fw_n"] > 0 and fw["pf"] < cfg["fw_pf"]: return False
    return True


def fires_today(strat, ind):
    try:
        return bool(strat.fires(ind, len(ind["closes"]) - 1))
    except Exception:
        return False


# ── Parameter grid ────────────────────────────────────────────────────────────

CONFIGS = {
    "current":   {"bt_n": 4, "bt_pf": 1.10, "bt_wr": 0.40, "fw_n": 1, "fw_pf": 0.90, "fw_frac": 0.30},
    "loose_bt":  {"bt_n": 3, "bt_pf": 1.00, "bt_wr": 0.38, "fw_n": 1, "fw_pf": 0.80, "fw_frac": 0.30},
    "no_fw":     {"bt_n": 4, "bt_pf": 1.10, "bt_wr": 0.40, "fw_n": 0, "fw_pf": 0.00, "fw_frac": 0.30},
    "loose_all": {"bt_n": 3, "bt_pf": 1.00, "bt_wr": 0.35, "fw_n": 0, "fw_pf": 0.00, "fw_frac": 0.30},
    "longer_fw": {"bt_n": 3, "bt_pf": 1.00, "bt_wr": 0.38, "fw_n": 1, "fw_pf": 0.80, "fw_frac": 0.20},
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=80)
    args = parser.parse_args()

    tickers = ASX200_TICKERS[:args.n]
    print(f"Downloading {len(tickers)} tickers (one batch)...\n")

    # ── Download & precompute ─────────────────────────────────────────────────
    data = []
    for i, t in enumerate(tickers):
        sys.stdout.write(f"\r  Fetching [{i+1}/{len(tickers)}] {t}        ")
        sys.stdout.flush()
        ohlcv = fetch_ohlcv(t)
        if ohlcv is None or len(ohlcv["closes"]) < 120:
            continue
        try:
            ind = precompute(ohlcv)
            data.append((t, ohlcv, ind))
        except Exception:
            pass
    print(f"\n  Loaded {len(data)} tickers with valid indicators.\n")

    # ── Sweep configs ─────────────────────────────────────────────────────────
    results = {}
    for cfg_name, cfg in CONFIGS.items():
        validated_cnt = 0
        firing_cnt    = 0
        firing_list   = []

        for t, ohlcv, ind in data:
            any_valid  = False
            any_firing = False
            best_fire  = None

            for strat in ALL_STRATEGIES:
                try:
                    r = run_bt(strat, ind, cfg["fw_frac"])
                except Exception:
                    continue
                valid = is_valid(r, cfg)
                fire  = fires_today(strat, ind) if valid else False

                if valid:
                    any_valid = True
                if valid and fire:
                    any_firing = True
                    if best_fire is None:
                        best_fire = strat.name

            if any_valid:  validated_cnt += 1
            if any_firing:
                firing_cnt += 1
                firing_list.append((t, best_fire))

        results[cfg_name] = {
            "total":     len(data),
            "validated": validated_cnt,
            "val_pct":   round(validated_cnt / max(len(data), 1) * 100),
            "firing":    firing_cnt,
            "fire_pct":  round(firing_cnt / max(len(data), 1) * 100),
            "tickers":   firing_list,
        }

    # ── Print comparison table ────────────────────────────────────────────────
    print(f"\n{'CONFIG':<12}  {'bt_n':>4}  {'bt_pf':>5}  {'bt_wr':>5}  {'fw_n':>4}  {'fw_pf':>5}  "
          f"{'fw_frac':>7}  │  {'validated':>10}  {'firing':>8}")
    print("─" * 90)
    for cfg_name, cfg in CONFIGS.items():
        r = results[cfg_name]
        print(f"{cfg_name:<12}  {cfg['bt_n']:>4}  {cfg['bt_pf']:>5.2f}  {cfg['bt_wr']:>5.2f}  "
              f"{cfg['fw_n']:>4}  {cfg['fw_pf']:>5.2f}  {cfg['fw_frac']:>7.2f}  │  "
              f"{r['validated']:>4} / {r['total']:<4} ({r['val_pct']:>2}%)  "
              f"{r['firing']:>3} / {r['total']:<4} ({r['fire_pct']:>2}%)")

    print("\n── Firing tickers per config ──────────────────────────────────────")
    for cfg_name, r in results.items():
        tickers_str = ", ".join(f"{t}({s})" for t, s in r["tickers"]) or "—"
        print(f"\n{cfg_name}:  {r['firing']} firing")
        for t, s in r["tickers"]:
            print(f"  {t:<12} {s}")

    # Save
    out = Path(__file__).parent.parent / "param_scan_report.json"
    with open(out, "w") as f:
        json.dump({"run_date": str(date.today()), "configs": CONFIGS, "results": results}, f, indent=2)
    print(f"\nReport saved to: {out}")


if __name__ == "__main__":
    main()
