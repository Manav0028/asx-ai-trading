"""
One-off live test runner for the NSE strategy engine.
Runs a full signal scan, sends a Telegram summary of strategy assignments,
firing signals, and actionable trades, then repeats every INTERVAL_MIN
minutes until NSE market close (15:30 IST).
"""
import logging
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nse_live_test")

INTERVAL_MIN = 10
IST = ZoneInfo("Asia/Kolkata")
MARKET_CLOSE = dtime(15, 30)


def run_once(round_num: int):
    from signals.aggregator import run_full_scan
    from config import get_active_exchange
    from alerts.telegram_bot import _send

    exchange = get_active_exchange()
    results = run_full_scan(exchange.tickers)

    actionable = [r for r in results if r.get("position_size_aud", 0) > 0]
    firing = [r for r in results if r.get("strategy_name") and "fires" in (r.get("strategy_state") or "")]
    top5 = results[:5]

    now_ist = datetime.now(IST).strftime("%H:%M IST")
    lines = [f"🧪 *NSE LIVE TEST — Round {round_num}* ({now_ist})", ""]
    lines.append(f"Scanned: {len(results)} stocks | Actionable trades: {len(actionable)}")
    lines.append("")
    lines.append("*Top 5 by composite score:*")
    for r in top5:
        strat = r.get("strategy_name") or "-"
        lines.append(
            f"  {r['ticker']:15s} score={r['composite_score']:.1f}  strategy={strat}  "
            f"pos={'YES' if r.get('position_size_aud', 0) > 0 else 'no'}"
        )

    if actionable:
        lines.append("")
        lines.append("*🟢 Actionable (validated strategy firing today):*")
        for r in actionable[:5]:
            lines.append(
                f"  {r['ticker']} — {r['strategy_name']} — entry {r.get('entry_price')}"
            )

    msg = "\n".join(lines)
    ok = _send(msg)
    logger.info("Round %d: scanned=%d actionable=%d telegram=%s", round_num, len(results), len(actionable), ok)


def main():
    round_num = 1
    while True:
        try:
            run_once(round_num)
        except Exception:
            logger.exception("Round %d failed", round_num)

        now_ist = datetime.now(IST)
        if now_ist.time() >= MARKET_CLOSE:
            from alerts.telegram_bot import _send
            _send(f"🏁 *NSE LIVE TEST COMPLETE* — market closed, ran {round_num} rounds.")
            logger.info("Market closed, stopping after %d rounds", round_num)
            break

        round_num += 1
        time.sleep(INTERVAL_MIN * 60)


if __name__ == "__main__":
    main()
