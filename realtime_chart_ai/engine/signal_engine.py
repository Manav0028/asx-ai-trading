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
from settings import (
    RTC_SIGNAL_THRESHOLD, WEIGHT_MTF_CONFLUENCE,
    WEIGHT_PATTERN_CONFIDENCE, WEIGHT_SMC_ZONE_QUALITY, WEIGHT_TREND_ALIGNMENT,
    WEIGHT_VOLUME_CONFIRMATION,
)
from trading import state
from trading.position_tracker import tracker as position_tracker

logger = logging.getLogger(__name__)

CONTEXT_BIAS_TIMEFRAMES = ("5m", "15m")


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
        self._signal_callbacks: List[Callable[[Dict], None]] = []
        self._bar_callbacks: List[Callable[[str, str, Dict], None]] = []

        self.store.on_bar_closed(self._handle_bar_closed)

    def on_signal(self, callback: Callable[[Dict], None]) -> None:
        self._signal_callbacks.append(callback)

    def on_bar(self, callback: Callable[[str, str, Dict], None]) -> None:
        """For broadcasting candle_update regardless of whether a pattern fired."""
        self._bar_callbacks.append(callback)

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

        if timeframe != EXECUTION_TIMEFRAME:
            return

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
            tf: confluence.bias_for(self.store.latest_ind(tf))
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
            if position_tracker.has_open_position(self.ticker):
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
