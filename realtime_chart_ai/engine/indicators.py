"""
Incremental streaming indicators — O(1) per-bar update, not a recompute over
the full array like ai_engine/technical_engine.py does once/day. See plan
doc's Core Engine §1 for the formulas this implements.

Each IndicatorEngine tracks ONE (ticker, timeframe) series. `update(candle)`
appends the new bar and returns the full `ind` dict (parallel deques exposed
as lists) in the same shape/contract as strategies/base.py's
`fires(ind, i) -> Optional[Dict]`, so pattern detectors can index `ind[key][i]`
exactly like the EOD daily-bar engine does.
"""
import math
from collections import deque
from typing import Dict, List, Optional

from datasources.base import Candle

MAXLEN = 250
VOL_AVG_PERIOD = 20
BB_PERIOD = 20
RSI_PERIOD = 14
ATR_PERIOD = 14
ADX_PERIOD = 14


class IndicatorEngine:
    def __init__(self):
        # Raw OHLCV series
        self.closes: deque = deque(maxlen=MAXLEN)
        self.opens: deque = deque(maxlen=MAXLEN)
        self.highs: deque = deque(maxlen=MAXLEN)
        self.lows: deque = deque(maxlen=MAXLEN)
        self.volumes: deque = deque(maxlen=MAXLEN)
        self.timestamps: deque = deque(maxlen=MAXLEN)

        # Computed series (parallel to the above, one value appended per bar)
        self.rsi: deque = deque(maxlen=MAXLEN)
        self.ema20: deque = deque(maxlen=MAXLEN)
        self.ema50: deque = deque(maxlen=MAXLEN)
        self.ema200: deque = deque(maxlen=MAXLEN)
        self.macd: deque = deque(maxlen=MAXLEN)
        self.macd_signal: deque = deque(maxlen=MAXLEN)
        self.macd_hist: deque = deque(maxlen=MAXLEN)
        self.atr: deque = deque(maxlen=MAXLEN)
        self.adx: deque = deque(maxlen=MAXLEN)
        self.plus_di: deque = deque(maxlen=MAXLEN)
        self.minus_di: deque = deque(maxlen=MAXLEN)
        self.vwap: deque = deque(maxlen=MAXLEN)
        self.obv: deque = deque(maxlen=MAXLEN)
        self.vol_avg_20: deque = deque(maxlen=MAXLEN)
        self.bb_upper: deque = deque(maxlen=MAXLEN)
        self.bb_mid: deque = deque(maxlen=MAXLEN)
        self.bb_lower: deque = deque(maxlen=MAXLEN)
        self.high_20: deque = deque(maxlen=MAXLEN)   # rolling 20-BAR high/low (not 20-day —
        self.low_20: deque = deque(maxlen=MAXLEN)    # intraday bars accumulate far faster than daily)

        # Internal recursive state (not exposed directly)
        self._ema20_val: Optional[float] = None
        self._ema50_val: Optional[float] = None
        self._ema200_val: Optional[float] = None
        self._ema12_val: Optional[float] = None
        self._ema26_val: Optional[float] = None
        self._ema9_macd_val: Optional[float] = None
        self._avg_gain: Optional[float] = None
        self._avg_loss: Optional[float] = None
        self._atr_val: Optional[float] = None
        self._plus_dm_avg: Optional[float] = None
        self._minus_dm_avg: Optional[float] = None
        self._tr_avg: Optional[float] = None
        self._obv_val: float = 0.0
        self._vwap_cum_pv: float = 0.0
        self._vwap_cum_vol: float = 0.0
        self._session_day: Optional[object] = None

    @staticmethod
    def _ema_step(prev: Optional[float], price: float, period: int) -> float:
        if prev is None:
            return price
        k = 2 / (period + 1)
        return price * k + prev * (1 - k)

    def update(self, candle: Candle) -> Dict[str, List[float]]:
        prev_close = self.closes[-1] if self.closes else None

        self.closes.append(candle.close)
        self.opens.append(candle.open)
        self.highs.append(candle.high)
        self.lows.append(candle.low)
        self.volumes.append(candle.volume)
        self.timestamps.append(candle.ts)

        # ── EMAs ──────────────────────────────────────────────────────────
        self._ema20_val = self._ema_step(self._ema20_val, candle.close, 20)
        self._ema50_val = self._ema_step(self._ema50_val, candle.close, 50)
        self._ema200_val = self._ema_step(self._ema200_val, candle.close, 200)
        self.ema20.append(self._ema20_val)
        self.ema50.append(self._ema50_val)
        self.ema200.append(self._ema200_val)

        # ── MACD (12/26/9 on EMAs of close) ──────────────────────────────
        self._ema12_val = self._ema_step(self._ema12_val, candle.close, 12)
        self._ema26_val = self._ema_step(self._ema26_val, candle.close, 26)
        macd_val = self._ema12_val - self._ema26_val
        self._ema9_macd_val = self._ema_step(self._ema9_macd_val, macd_val, 9)
        self.macd.append(macd_val)
        self.macd_signal.append(self._ema9_macd_val)
        self.macd_hist.append(macd_val - self._ema9_macd_val)

        # ── RSI (true Wilder smoothing) ──────────────────────────────────
        if prev_close is None:
            self.rsi.append(50.0)
        else:
            delta = candle.close - prev_close
            gain = max(delta, 0.0)
            loss = max(-delta, 0.0)
            if self._avg_gain is None:
                self._avg_gain, self._avg_loss = gain, loss
            else:
                self._avg_gain = (self._avg_gain * (RSI_PERIOD - 1) + gain) / RSI_PERIOD
                self._avg_loss = (self._avg_loss * (RSI_PERIOD - 1) + loss) / RSI_PERIOD
            if self._avg_loss == 0:
                self.rsi.append(100.0)
            else:
                rs = self._avg_gain / self._avg_loss
                self.rsi.append(100 - 100 / (1 + rs))

        # ── ATR + ADX/+DI/-DI (Wilder smoothing) ─────────────────────────
        if prev_close is None:
            tr = candle.high - candle.low
            plus_dm = minus_dm = 0.0
        else:
            tr = max(
                candle.high - candle.low,
                abs(candle.high - prev_close),
                abs(candle.low - prev_close),
            )
            prev_high = self.highs[-2] if len(self.highs) > 1 else candle.high
            prev_low = self.lows[-2] if len(self.lows) > 1 else candle.low
            up_move = candle.high - prev_high
            down_move = prev_low - candle.low
            plus_dm = up_move if (up_move > down_move and up_move > 0) else 0.0
            minus_dm = down_move if (down_move > up_move and down_move > 0) else 0.0

        if self._atr_val is None:
            self._atr_val = tr
            self._tr_avg = tr
            self._plus_dm_avg = plus_dm
            self._minus_dm_avg = minus_dm
        else:
            self._atr_val = (self._atr_val * (ATR_PERIOD - 1) + tr) / ATR_PERIOD
            self._tr_avg = (self._tr_avg * (ADX_PERIOD - 1) + tr) / ADX_PERIOD
            self._plus_dm_avg = (self._plus_dm_avg * (ADX_PERIOD - 1) + plus_dm) / ADX_PERIOD
            self._minus_dm_avg = (self._minus_dm_avg * (ADX_PERIOD - 1) + minus_dm) / ADX_PERIOD
        self.atr.append(self._atr_val)

        pdi = 100 * self._plus_dm_avg / self._tr_avg if self._tr_avg else 0.0
        mdi = 100 * self._minus_dm_avg / self._tr_avg if self._tr_avg else 0.0
        dx = 100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) else 0.0
        self.plus_di.append(pdi)
        self.minus_di.append(mdi)
        self.adx.append(dx)

        # ── VWAP (session-anchored — resets when the calendar day changes) ─
        day = candle.ts.date()
        if self._session_day != day:
            self._session_day = day
            self._vwap_cum_pv = 0.0
            self._vwap_cum_vol = 0.0
        typical_price = (candle.high + candle.low + candle.close) / 3
        self._vwap_cum_pv += typical_price * candle.volume
        self._vwap_cum_vol += candle.volume
        self.vwap.append(self._vwap_cum_pv / self._vwap_cum_vol if self._vwap_cum_vol else candle.close)

        # ── OBV ───────────────────────────────────────────────────────────
        if prev_close is not None:
            if candle.close > prev_close:
                self._obv_val += candle.volume
            elif candle.close < prev_close:
                self._obv_val -= candle.volume
        self.obv.append(self._obv_val)

        # ── Volume spike ratio base (rolling 20-bar average) ─────────────
        window = list(self.volumes)[-VOL_AVG_PERIOD:]
        self.vol_avg_20.append(sum(window) / len(window))

        # ── Bollinger Bands (20-bar mean/std) ────────────────────────────
        close_window = list(self.closes)[-BB_PERIOD:]
        mean = sum(close_window) / len(close_window)
        if len(close_window) > 1:
            variance = sum((c - mean) ** 2 for c in close_window) / len(close_window)
            std = math.sqrt(variance)
        else:
            std = 0.0
        self.bb_mid.append(mean)
        self.bb_upper.append(mean + 2 * std)
        self.bb_lower.append(mean - 2 * std)

        # ── Rolling 20-bar high/low (used by hammer/shooting-star/breakdown) ─
        high_window = list(self.highs)[-VOL_AVG_PERIOD:]
        low_window = list(self.lows)[-VOL_AVG_PERIOD:]
        self.high_20.append(max(high_window))
        self.low_20.append(min(low_window))

        return self.snapshot()

    def snapshot(self) -> Dict[str, List[float]]:
        return {
            "closes": list(self.closes), "opens": list(self.opens),
            "highs": list(self.highs), "lows": list(self.lows),
            "volumes": list(self.volumes), "timestamps": list(self.timestamps),
            "rsi": list(self.rsi), "ema20": list(self.ema20), "ema50": list(self.ema50),
            "ema200": list(self.ema200), "macd": list(self.macd),
            "macd_signal": list(self.macd_signal), "macd_hist": list(self.macd_hist),
            "atr": list(self.atr), "adx": list(self.adx), "plus_di": list(self.plus_di),
            "minus_di": list(self.minus_di), "vwap": list(self.vwap), "obv": list(self.obv),
            "vol_avg_20": list(self.vol_avg_20), "bb_upper": list(self.bb_upper),
            "bb_mid": list(self.bb_mid), "bb_lower": list(self.bb_lower),
            "high_20": list(self.high_20), "low_20": list(self.low_20),
        }

    def volume_spike_ratio(self) -> float:
        if not self.vol_avg_20 or self.vol_avg_20[-1] == 0:
            return 1.0
        return self.volumes[-1] / self.vol_avg_20[-1]

    def trend_alignment_score(self) -> float:
        """0-100, mirrors technical_engine.py's _ema_crossover/_adx blend."""
        if self._ema20_val is None or self._ema50_val is None or not self.adx:
            return 50.0
        adx_val = self.adx[-1]
        trend_strength = min(adx_val / 40 * 50, 50)  # up to 50 pts for strong trend
        if self._ema20_val > self._ema50_val and self.closes[-1] > self._ema20_val:
            return 50 + trend_strength
        if self._ema20_val < self._ema50_val and self.closes[-1] < self._ema20_val:
            return 50 - trend_strength
        return 50.0
