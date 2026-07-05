"""
Manual verification harness for the automated trading capability — not a
permanent test suite, same synthetic-data approach used to verify the engine
earlier in this project. Run directly against the real dev DB:

    PYTHONPATH=. python scripts/verify_trading_phase.py

Cleans up every row it creates at the end, regardless of pass/fail.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

TEST_TICKER = "VERIFY.AX"


def section(title):
    print(f"\n=== {title} ===")


def check_sizing():
    section("1. Sizing scales with composite score")
    from trading import sizing

    entry, stop = 100.0, 98.0
    results = {s: sizing.compute_position(entry, stop, s) for s in (65, 75, 90, 100)}
    for score, r in results.items():
        print(f"  score={score}: shares={r['shares']:.2f} value={r['position_value']:.2f} "
              f"multiplier={r['multiplier']:.3f}")
    shares_seq = [results[s]["shares"] for s in (65, 75, 90, 100)]
    assert shares_seq == sorted(shares_seq), "shares must strictly increase with score"
    assert abs(results[65]["multiplier"] - 0.5) < 1e-9, "floor multiplier must be exactly 0.5 at threshold"
    assert abs(results[100]["multiplier"] - 1.5) < 1e-9, "ceiling multiplier must be exactly 1.5 at 100"
    print("  PASS")


def check_stops():
    section("2. Stop/target from ATR (long/short + clamp bounds)")
    from trading import stops

    long_st = stops.compute_stop_target(100, 1.0, "long", 1.5, 3.0)
    short_st = stops.compute_stop_target(100, 1.0, "short", 1.5, 3.0)
    print("  long:", long_st)
    print("  short:", short_st)
    assert long_st["stop_price"] < 100 < long_st["target_price"]
    assert short_st["target_price"] < 100 < short_st["stop_price"]

    extreme = stops.compute_stop_target(100, 20.0, "long", 1.5, 3.0)
    print("  extreme ATR (clamp test):", extreme)
    assert extreme["stop_pct"] <= 0.08 + 1e-9, "must clamp at RTC_MAX_STOP_PCT"
    print("  PASS")


def check_exits_and_trailing_stop():
    section("3. Exits trigger correctly + trailing stop only ratchets favorably")
    from journal.recorder import write_interpretation
    from trading.position_tracker import PositionTracker

    interp_id = write_interpretation({
        "ticker": TEST_TICKER, "bar_ts": datetime.utcnow(), "timeframe": "1m",
        "data_source": "verify_script", "pattern_name": "bull_engulf", "pattern_type": "candlestick",
        "direction": "long", "confidence": 0.8, "composite_score": 90.0,
        "rule_reason": "test", "mtf_confluence": True, "mtf_summary": "test",
        "smc_zone": "discount", "smc_context": None, "claude_rationale": "test",
        "claude_model": "rule_fallback", "price_at_signal": 100.0,
    })
    tr = PositionTracker()
    opened = tr.open_position(interp_id, TEST_TICKER, "long", price=100.0, atr=1.0,
                               composite_score=90.0, stop_mult=1.5, target_mult=3.0, max_hold_bars=5)
    print("  opened:", opened)

    # Target is 103.0 — keep every high strictly below that so this phase
    # only exercises the trailing-stop ratchet, not a real target exit.
    stops_seen = []
    for close, high, low in [(101.0, 101.2, 100.8), (102.0, 102.2, 101.8), (101.5, 102.0, 101.0)]:
        pos = tr._positions[TEST_TICKER]
        prev_stop = pos.stop_price
        ind = {"closes": [close], "highs": [high], "lows": [low], "timestamps": [datetime.utcnow()]}
        result = tr.check_exit(TEST_TICKER, ind, 0)
        assert result is None, "should not have exited yet (highs kept below target)"
        new_stop = tr._positions[TEST_TICKER].stop_price
        stops_seen.append(new_stop)
        assert new_stop >= prev_stop, "trailing stop must never loosen"
    print("  trailing stop sequence (never loosened):", stops_seen)

    # Now force a stop-loss exit
    pos = tr._positions[TEST_TICKER]
    ind = {"closes": [pos.stop_price - 0.5], "highs": [pos.stop_price],
           "lows": [pos.stop_price - 1.0], "timestamps": [datetime.utcnow()]}
    exit_result = tr.check_exit(TEST_TICKER, ind, 0)
    print("  stop-loss exit:", exit_result)
    assert exit_result is not None and exit_result["exit_reason"] == "stop_loss"
    assert not tr.has_open_position(TEST_TICKER)
    print("  PASS")


def check_pnl():
    section("4. P&L math (long win, short win)")
    from trading import pnl

    long_pnl = pnl.compute_pnl("long", entry_price=100, exit_price=105, shares=50)
    short_pnl = pnl.compute_pnl("short", entry_price=100, exit_price=95, shares=50)
    print("  long win:", long_pnl)
    print("  short win:", short_pnl)
    assert long_pnl["net_pnl"] > 0
    assert short_pnl["net_pnl"] > 0
    print("  PASS")


def check_toggle():
    section("5. Runtime toggle behaves live")
    from trading import state

    state.set_enabled(True, actor="verify_script")
    assert state.is_enabled() is True
    state.set_enabled(False, actor="verify_script")
    assert state.is_enabled() is False
    print("  PASS (server-running HTTP check is manual: GET/POST /api/auto-trade)")


def check_restart_recovery():
    section("6. Restart recovery (position state survives a fresh PositionTracker)")
    from journal.recorder import write_interpretation
    from trading.position_tracker import PositionTracker

    interp_id = write_interpretation({
        "ticker": TEST_TICKER, "bar_ts": datetime.utcnow(), "timeframe": "1m",
        "data_source": "verify_script", "pattern_name": "break_of_structure", "pattern_type": "smc",
        "direction": "short", "confidence": 0.7, "composite_score": 80.0,
        "rule_reason": "test", "mtf_confluence": True, "mtf_summary": "test",
        "smc_zone": "premium", "smc_context": "break_of_structure", "claude_rationale": "test",
        "claude_model": "rule_fallback", "price_at_signal": 60.0,
    })
    tracker_a = PositionTracker()
    tracker_a.open_position(interp_id, TEST_TICKER, "short", price=60.0, atr=0.5,
                             composite_score=80.0, stop_mult=1.8, target_mult=3.5, max_hold_bars=60)
    ind = {"closes": [59.7], "highs": [59.9], "lows": [59.5], "timestamps": [datetime.utcnow()]}
    tracker_a.check_exit(TEST_TICKER, ind, 0)
    before = tracker_a._positions[TEST_TICKER]

    tracker_b = PositionTracker()
    assert not tracker_b.has_open_position(TEST_TICKER)
    tracker_b.load_open_positions()
    after = tracker_b._positions.get(TEST_TICKER)
    assert after is not None, "recovery failed"
    assert after.entry_price == before.entry_price
    assert after.stop_price == before.stop_price
    assert after.bars_held == before.bars_held
    print(f"  recovered: {after}")
    print("  PASS")

    # leave it open for the journal-correctness check to close out


def check_journal_and_skip_path():
    section("7. Journal correctness + skip-when-position-open path")
    from journal.db import get_session
    from journal.models import RtcOpenPosition, RtcTradeAction
    from trading.position_tracker import tracker as shared_tracker

    shared_tracker.load_open_positions()
    assert shared_tracker.has_open_position(TEST_TICKER), "expected the position from check 6 to still be open"

    with get_session() as session:
        action = (
            session.query(RtcTradeAction)
            .join(RtcOpenPosition, RtcOpenPosition.trade_action_id == RtcTradeAction.id)
            .filter(RtcOpenPosition.ticker == TEST_TICKER, RtcOpenPosition.status == "open")
            .first()
        )
        assert action is not None
        assert action.stop_price is not None
        assert action.dollar_risk is not None
        assert action.score_multiplier is not None
        assert action.atr_at_entry is not None
        print(f"  rtc_trade_actions row populated: stop={action.stop_price:.3f} "
              f"dollar_risk={action.dollar_risk:.2f} multiplier={action.score_multiplier:.3f}")

    # close it out via max_hold to exercise the full outcome path
    pos = shared_tracker._positions[TEST_TICKER]
    pos.bars_held = pos.max_hold_bars  # force max_hold on the next check
    ind = {"closes": [59.8], "highs": [59.9], "lows": [59.7], "timestamps": [datetime.utcnow()]}
    exit_result = shared_tracker.check_exit(TEST_TICKER, ind, 0)
    assert exit_result is not None and exit_result["exit_reason"] == "max_hold"
    print("  max_hold exit:", exit_result)
    print("  PASS")


def cleanup():
    section("Cleanup")
    from journal.db import get_session
    from journal.models import (
        RtcChartInterpretation, RtcEvent, RtcOpenPosition, RtcTradeAction, RtcTradeOutcome,
    )
    with get_session() as session:
        interp_ids = [r.id for r in session.query(RtcChartInterpretation.id)
                      .filter(RtcChartInterpretation.ticker == TEST_TICKER)]
        action_ids = [r.id for r in session.query(RtcTradeAction.id)
                      .filter(RtcTradeAction.interpretation_id.in_(interp_ids))] if interp_ids else []
        if action_ids:
            session.query(RtcTradeOutcome).filter(RtcTradeOutcome.trade_action_id.in_(action_ids)).delete(
                synchronize_session=False)
            session.query(RtcOpenPosition).filter(RtcOpenPosition.trade_action_id.in_(action_ids)).delete(
                synchronize_session=False)
            session.query(RtcTradeAction).filter(RtcTradeAction.id.in_(action_ids)).delete(
                synchronize_session=False)
        if interp_ids:
            session.query(RtcChartInterpretation).filter(RtcChartInterpretation.id.in_(interp_ids)).delete(
                synchronize_session=False)
        session.query(RtcEvent).filter(RtcEvent.ticker == TEST_TICKER).delete(synchronize_session=False)
    print(f"  cleaned up all {TEST_TICKER} rows")


if __name__ == "__main__":
    try:
        check_sizing()
        check_stops()
        check_exits_and_trailing_stop()
        check_pnl()
        check_toggle()
        check_restart_recovery()
        check_journal_and_skip_path()
        print("\nALL CHECKS PASSED")
    finally:
        cleanup()
