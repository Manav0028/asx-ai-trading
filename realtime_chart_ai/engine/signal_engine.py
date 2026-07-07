"""
The orchestrator — wires timeframe bars into: indicators (already computed by
TimeframeStore) -> swings -> patterns (candlestick + chart + SMC) -> confluence
+ SMC zone gate -> composite score (volume term includes Volume Profile
proximity) -> journal -> Claude rationale -> optional paper trade -> broadcast.
See plan doc's Core Engine §7 for the composite score formula this implements.
"""
import logging
from typing import Callable, Dict, List, Optional

from engine import confluence, smc
from engine.candlestick_patterns import CANDLESTICK_PATTERNS
from engine.chart_patterns import ChartPatternEngine
from engine.pattern_risk_defaults import apply_risk_defaults
from engine.smc import SMCEngine
from engine.swing_detector import SwingDetector
from engine.levels import LevelTracker
from engine.timeframe_store import EXECUTION_TIMEFRAME, TimeframeStore
from engine.volume_profile import VolumeProfileTracker
from journal.recorder import log_bar, log_event, write_interpretation
from market_hours import is_asx_market_open
from settings import (
    CONTEXT_TIMEFRAMES, RTC_SIGNAL_THRESHOLD, WEIGHT_MTF_CONFLUENCE,
    WEIGHT_PATTERN_CONFIDENCE, WEIGHT_SMC_ZONE_QUALITY, WEIGHT_TREND_ALIGNMENT,
    WEIGHT_VOLUME_CONFIRMATION,
)
from trading import state
from trading.position_tracker import tracker as position_tracker

logger = logging.getLogger(__name__)

CONTEXT_BIAS_TIMEFRAMES = tuple(CONTEXT_TIMEFRAMES)
# How many of a context timeframe's OWN bars a pattern that just fired on it
# stays "active" for confluence purposes — see bias_for()'s recent_pattern_
# direction. 3 bars is deliberately short: on 15m that's 45 minutes, long
# enough to matter for an intraday confluence check without a pattern from
# hours ago still silently biasing new signals.
RECENT_PATTERN_DECAY_BARS = 3


def trend_alignment_score(ind: Dict) -> float:
    """0-100, mirrors ai_engine/technical_engine.py's _ema_crossover/_adx blend."""
    if not ind.get("ema20") or not ind.get("ema50"):
        return 50.0
    ema20, ema50, price = ind["ema20"][-1], ind["ema50"][-1], ind["closes"][-1]
    adx_val = ind["adx"][-1] if ind.get("adx") else 0.0
    trend_strength = min(adx_val / 40 * 50, 50)
    if ema20 > ema50 and price > ema20:
        return 50 + trend_strength
    if ema20 < ema50 and price < ema20:
        return 50 - trend_strength
    return 50.0


def volume_confirmation_score(ind: Dict, i: int, vp_proximity_score: float = 50.0) -> float:
    """0-100, blends volume-spike-ratio (mirrors ai_engine/technical_engine.py's
    _volume_spike, 70% weight) with Volume Profile POC/VAH-VAL proximity
    (30% weight — inside the value area is fair-value/neutral, outside is a
    directional-extension confirmation)."""
    vol = ind["volumes"][i]
    avg = ind["vol_avg_20"][i] if ind.get("vol_avg_20") else vol
    ratio = vol / avg if avg else 1.0
    if ratio >= 3.0:
        spike_score = 90.0
    elif ratio >= 2.0:
        spike_score = 75.0
    elif ratio >= 1.3:
        spike_score = 60.0
    elif ratio < 0.5:
        spike_score = 35.0
    else:
        spike_score = 50.0
    return spike_score * 0.7 + vp_proximity_score * 0.3


class SignalEngine:
    def __init__(self, ticker: str, store: TimeframeStore, data_source_name: str):
        self.ticker = ticker
        self.store = store
        self.data_source_name = data_source_name
        self.swing_detector = SwingDetector()
        self.smc_engine = SMCEngine()
        self.level_tracker = LevelTracker()
        self.chart_pattern_engine = ChartPatternEngine()
        self.volume_profile = VolumeProfileTracker()
        # Every context timeframe (5m/15m/1d) gets its OWN pattern-detector
        # state — previously these timeframes were only ever read as a raw
        # EMA20/50 crossover for the confluence bias; every actual pattern
        # detector (candlestick/chart/SMC) ran exclusively against 1-minute
        # bars, so a real setup forming cleanly on the 15-minute or daily
        # chart was invisible to the system unless it ALSO happened to look
        # like a pattern on 1m bars at the same moment. Separate instances
        # per timeframe (not shared with the 1m ones above) so swing history
        # and SMC structure/order-block state never mix across timeframes.
        self.context_swing_detectors: Dict[str, SwingDetector] = {tf: SwingDetector() for tf in CONTEXT_BIAS_TIMEFRAMES}
        self.context_smc_engines: Dict[str, SMCEngine] = {tf: SMCEngine() for tf in CONTEXT_BIAS_TIMEFRAMES}
        self.context_chart_engines: Dict[str, ChartPatternEngine] = {tf: ChartPatternEngine() for tf in CONTEXT_BIAS_TIMEFRAMES}
        # {timeframe: {"direction": "long"|"short", "bars_ago": int}} — how
        # confluence.bias_for() knows a REAL pattern (not just price-vs-EMA)
        # recently confirmed on that timeframe. See RECENT_PATTERN_DECAY_BARS.
        self.context_recent_pattern: Dict[str, Optional[Dict]] = {tf: None for tf in CONTEXT_BIAS_TIMEFRAMES}
        self._signal_callbacks: List[Callable[[Dict], None]] = []
        self._bar_callbacks: List[Callable[[str, str, Dict], None]] = []

        self.store.on_bar_closed(self._handle_bar_closed)

    def on_signal(self, callback: Callable[[Dict], None]) -> None:
        self._signal_callbacks.append(callback)

    def on_bar(self, callback: Callable[[str, str, Dict], None]) -> None:
        """For broadcasting candle_update regardless of whether a pattern fired."""
        self._bar_callbacks.append(callback)

    def refresh_daily_reference_levels(self) -> None:
        """Called by server/app.py right after it lazily backfills a
        ticker's '1d' engine (see _seed_daily_context) — seed_historical()
        deliberately fires no bar-closed callback (so historical warmup
        doesn't flood the journal), so nothing inside SignalEngine otherwise
        learns that real daily data just became available. Prior session's
        high/low become genuine reference support/resistance levels — a
        prior day's high/low is a well-known intraday reference point
        (yesterday's range), independent of whatever swings have or haven't
        formed yet today."""
        from engine.levels import Level
        ind = self.store.latest_ind("1d")
        if not ind or not ind.get("closes"):
            return
        prev_high, prev_low = ind["highs"][-1], ind["lows"][-1]
        self.level_tracker.set_reference_levels([
            Level(price=prev_high, kind="resistance", touches=2),
            Level(price=prev_low, kind="support", touches=2),
        ])

    def _handle_bar_closed(self, ticker: str, timeframe: str, ind: Dict) -> None:
        # Broad guard: an unexpected data edge case (e.g. a malformed bar
        # from a data source) anywhere in indicator/pattern/signal processing
        # must never take down this ticker's processing thread or the
        # yfinance poll loop that called it — log and skip this bar, next
        # bar tries fresh. Mirrors the same resilience principle already
        # applied to yfinance's own fetch/poll error handling.
        try:
            self._handle_bar_closed_inner(ticker, timeframe, ind)
        except Exception as e:
            logger.exception("bar processing failed for %s/%s", ticker, timeframe)
            log_event("error", source="signal_engine", ticker=ticker,
                       detail=f"bar processing failed ({timeframe}): {type(e).__name__}: {e}")

    def _handle_bar_closed_inner(self, ticker: str, timeframe: str, ind: Dict) -> None:
        log_bar(ticker, timeframe, ind)
        for cb in self._bar_callbacks:
            cb(ticker, timeframe, ind)

        if timeframe == EXECUTION_TIMEFRAME:
            self._handle_execution_bar(ind)
        elif timeframe in self.context_swing_detectors:
            self._handle_context_bar(timeframe, ind)

    def _handle_context_bar(self, timeframe: str, ind: Dict) -> None:
        """Runs the SAME pattern families (candlestick/chart/SMC) against a
        higher timeframe's own closed bar. Never enters a trade from here —
        execution stays 1-minute-granular, since that's the cadence stops/
        targets/trailing-stops/max-hold are actually monitored against — but
        a real confirmed pattern here is journaled (auditable via the
        Journal tab) and remembered for RECENT_PATTERN_DECAY_BARS so the
        confluence gate a 1m signal is checked against reflects an ACTUAL
        higher-timeframe pattern, not just which side of its moving averages
        price happens to be on."""
        i = len(ind["closes"]) - 1
        swing_detector = self.context_swing_detectors[timeframe]
        swing_detector.update(ind)
        swings = list(swing_detector.swings)

        fired: List[Dict] = []
        for pattern in CANDLESTICK_PATTERNS:
            result = pattern.fires(ind, i)
            if result:
                result["pattern_name"] = pattern.name
                result["direction"] = pattern.direction
                result["pattern_type"] = pattern.pattern_type
                fired.append(result)
        for result in self.context_smc_engines[timeframe].evaluate(ind, i, swings):
            fired.append(result)
        for result in self.context_chart_engines[timeframe].evaluate(ind, i, swings):
            fired.append(result)

        if fired:
            self.context_recent_pattern[timeframe] = {"direction": fired[-1]["direction"], "bars_ago": 0}
            for signal in fired:
                self._journal_context_pattern(timeframe, signal, ind, i)
        else:
            recent = self.context_recent_pattern.get(timeframe)
            if recent is not None:
                recent["bars_ago"] += 1
                if recent["bars_ago"] > RECENT_PATTERN_DECAY_BARS:
                    self.context_recent_pattern[timeframe] = None

    def _journal_context_pattern(self, timeframe: str, signal: Dict, ind: Dict, i: int) -> None:
        """Lightweight journal-only path for a context-timeframe pattern
        fire — no Claude call (these are frequent across 5m/15m/1d and
        never trade-actioned, so paying for narration on every one would
        reintroduce the exact API-cost problem already fixed for 1m signals
        below threshold) and no broadcast to the live signal card, since
        these don't represent an actionable-right-now setup the way a 1m
        fire does. Still fully auditable via /api/journal — "always
        journal, only sometimes act" applies here too."""
        price = ind["closes"][i]
        composite = (
            WEIGHT_PATTERN_CONFIDENCE * signal["confidence"] * 100
            + WEIGHT_TREND_ALIGNMENT * trend_alignment_score(ind)
            + WEIGHT_VOLUME_CONFIRMATION * volume_confirmation_score(ind, i)
            + WEIGHT_MTF_CONFLUENCE * 50.0
            + WEIGHT_SMC_ZONE_QUALITY * 50.0
        )
        write_interpretation({
            "ticker": self.ticker, "bar_ts": ind["timestamps"][i], "timeframe": timeframe,
            "data_source": self.data_source_name, "pattern_name": signal["pattern_name"],
            "pattern_type": signal["pattern_type"], "direction": signal["direction"],
            "confidence": signal["confidence"], "composite_score": round(composite, 2),
            "rule_reason": signal["reason"], "mtf_confluence": None, "mtf_summary": None,
            "smc_zone": None, "smc_context": signal["pattern_name"] if signal["pattern_type"] == "smc" else None,
            "claude_rationale": None, "claude_model": None, "price_at_signal": price,
        })

    def _handle_execution_bar(self, ind: Dict) -> None:
        i = len(ind["closes"]) - 1
        self.swing_detector.update(ind)
        atr = ind["atr"][i] if ind.get("atr") else 0.0
        self.level_tracker.rebuild(list(self.swing_detector.swings), atr)
        self.volume_profile.update(ind, i)

        # Exit check runs before pattern evaluation so a close on this bar is
        # settled before any new entry for the same ticker is considered.
        exit_result = position_tracker.check_exit(self.ticker, ind, i)
        if exit_result:
            for cb in self._signal_callbacks:
                cb(exit_result)

        fired = self._evaluate_patterns(ind, i)
        if not fired:
            return

        dealing_range = self.swing_detector.dealing_range()
        biases = {
            tf: confluence.bias_for(
                self.store.latest_ind(tf),
                recent_pattern_direction=(self.context_recent_pattern[tf]["direction"] if self.context_recent_pattern.get(tf) else None),
            )
            for tf in CONTEXT_BIAS_TIMEFRAMES
        }
        for signal in fired:
            self._process_signal(signal, ind, i, dealing_range, biases)

    def _evaluate_patterns(self, ind: Dict, i: int) -> List[Dict]:
        fired = []
        for pattern in CANDLESTICK_PATTERNS:
            result = pattern.fires(ind, i)
            if result:
                result["pattern_name"] = pattern.name
                result["direction"] = pattern.direction
                result["pattern_type"] = pattern.pattern_type
                result["stop_mult"] = pattern.stop_mult
                result["target_mult"] = pattern.target_mult
                result["max_hold_bars"] = pattern.max_hold_bars
                fired.append(result)
        for result in self.smc_engine.evaluate(ind, i, list(self.swing_detector.swings)):
            fired.append(apply_risk_defaults(result))
        for result in self.chart_pattern_engine.evaluate(ind, i, list(self.swing_detector.swings)):
            fired.append(apply_risk_defaults(result))
        return fired

    def _process_signal(self, signal: Dict, ind: Dict, i: int,
                         dealing_range: Optional[tuple], biases: Dict[str, str]) -> None:
        direction = signal["direction"]
        price = ind["closes"][i]

        conf = confluence.check_confluence(direction, biases)
        zone = smc.zone_for_price(price, dealing_range)
        zone_quality = smc.zone_quality(direction, zone)
        vp_proximity = self.volume_profile.proximity_score(price)

        # Named so the raw (0-100, pre-weight) sub-scores can be broadcast for
        # the frontend's composite-score breakdown bars, not just the final
        # weighted total.
        pattern_confidence_raw = signal["confidence"] * 100
        trend_alignment_raw = trend_alignment_score(ind)
        volume_confirmation_raw = volume_confirmation_score(ind, i, vp_proximity)
        mtf_confluence_raw = conf["bonus"]
        zone_quality_raw = zone_quality

        composite = (
            WEIGHT_PATTERN_CONFIDENCE * pattern_confidence_raw
            + WEIGHT_TREND_ALIGNMENT * trend_alignment_raw
            + WEIGHT_VOLUME_CONFIRMATION * volume_confirmation_raw
            + WEIGHT_MTF_CONFLUENCE * mtf_confluence_raw
            + WEIGHT_SMC_ZONE_QUALITY * zone_quality_raw
        )

        nearest = self.level_tracker.nearest(price)
        nearest_desc = f"{nearest.kind} @ {nearest.price:.3f} ({nearest.touches} touches)" if nearest else "none tracked yet"
        volume_ratio = ind["volumes"][i] / ind["vol_avg_20"][i] if ind.get("vol_avg_20") and ind["vol_avg_20"][i] else 1.0
        vp_levels = self.volume_profile.compute()
        vp_desc = (
            f"POC {vp_levels['poc']:.3f}, VA [{vp_levels['val']:.3f}-{vp_levels['vah']:.3f}]"
            if vp_levels else "not enough session data yet"
        )

        interpretation_payload = {
            "ticker": self.ticker,
            "bar_ts": ind["timestamps"][i],
            "timeframe": EXECUTION_TIMEFRAME,
            "data_source": self.data_source_name,
            "pattern_name": signal["pattern_name"],
            "pattern_type": signal["pattern_type"],
            "direction": direction,
            "confidence": signal["confidence"],
            "composite_score": round(composite, 2),
            "rule_reason": signal["reason"],
            "mtf_confluence": conf["confirmed"],
            "mtf_summary": conf["summary"],
            "smc_zone": zone,
            "smc_context": signal["pattern_name"] if signal["pattern_type"] == "smc" else None,
            "price_at_signal": price,
        }

        from ai.rationale import generate_rationale
        rationale = generate_rationale(interpretation_payload, {
            "mtf_summary": conf["summary"], "smc_zone": zone,
            "smc_context": interpretation_payload["smc_context"] or "none",
            "nearest_levels": nearest_desc, "volume_ratio": round(volume_ratio, 2),
            "volume_profile": vp_desc,
        }, use_claude=composite >= RTC_SIGNAL_THRESHOLD)
        interpretation_payload["claude_rationale"] = rationale["text"]
        interpretation_payload["claude_model"] = rationale["model"]

        interpretation_id = write_interpretation(dict(interpretation_payload))
        logger.info(
            "[%s] %s %s fired — composite=%.1f (threshold %.0f) zone=%s",
            self.ticker, signal["pattern_name"], direction, composite, RTC_SIGNAL_THRESHOLD, zone,
        )

        trade_action = None
        if composite >= RTC_SIGNAL_THRESHOLD and state.is_enabled():
            if not is_asx_market_open():
                # Found via direct user report: automated entries had no
                # market-hours check at all — only the manual auto-trade
                # toggle gated them, so a signal firing well after close
                # (against stale/after-hours delayed data) could still open
                # a position if the toggle happened to be left on overnight.
                log_event(
                    "entry_skipped_market_closed", ticker=self.ticker,
                    detail=f"{signal['pattern_name']} ({direction}) skipped — "
                           f"composite={composite:.1f}, outside ASX trading hours",
                )
            elif position_tracker.has_open_position(self.ticker):
                log_event(
                    "entry_skipped_position_open", ticker=self.ticker,
                    detail=f"{signal['pattern_name']} ({direction}) skipped — "
                           f"composite={composite:.1f}, position already open",
                )
            else:
                from trading.paper_or_live_bridge import maybe_enter_trade
                atr = ind["atr"][i] if ind.get("atr") else 0.0
                trade_action = maybe_enter_trade(
                    interpretation_id, self.ticker, direction, price, atr, composite,
                    signal["stop_mult"], signal["target_mult"], signal["max_hold_bars"],
                )

        # Entry/stop/target preview — computed regardless of auto-trade so the
        # frontend can render "here's what would fire" even when nothing was
        # actually taken (the plan's "shown, not taken" UX). Broadcast-only:
        # never merged into interpretation_payload, since write_interpretation
        # passes that dict straight into RtcChartInterpretation(**signal) and
        # these aren't columns on that table.
        from trading.stops import compute_stop_target
        atr_preview = ind["atr"][i] if ind.get("atr") else 0.0
        preview = compute_stop_target(price, atr_preview, direction, signal["stop_mult"], signal["target_mult"])

        broadcast_payload = dict(interpretation_payload)
        broadcast_payload["type"] = "pattern_signal"
        broadcast_payload["interpretation_id"] = interpretation_id
        broadcast_payload["trade_action"] = trade_action
        broadcast_payload["entry_price"] = price
        broadcast_payload["stop_price"] = preview["stop_price"]
        broadcast_payload["target_price"] = preview["target_price"]
        broadcast_payload["rr_ratio"] = round(preview["target_pct"] / preview["stop_pct"], 2) if preview["stop_pct"] else None
        broadcast_payload["breakdown"] = {
            "pattern_confidence": round(pattern_confidence_raw, 1),
            "trend_alignment": round(trend_alignment_raw, 1),
            "volume_confirmation": round(volume_confirmation_raw, 1),
            "mtf_confluence": round(mtf_confluence_raw, 1),
            "zone_quality": round(zone_quality_raw, 1),
        }
        broadcast_payload["bar_ts"] = broadcast_payload["bar_ts"].isoformat()
        for cb in self._signal_callbacks:
            cb(broadcast_payload)
