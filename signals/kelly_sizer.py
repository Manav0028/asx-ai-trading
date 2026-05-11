"""
Layer 04 · Signal Intelligence — Kelly Position Sizer
f* = (bp - q) / b
b = expected gain (mapped from composite score)
p = win probability (mapped from composite score)
q = 1 - p
Caps position at MAX_POSITION_PCT of portfolio.
"""
import logging
from typing import Tuple

from config.settings import MAX_POSITION_PCT, PORTFOLIO_CAPITAL, STOP_LOSS_PCT

logger = logging.getLogger(__name__)


def _estimate_win_prob(composite_score: float) -> float:
    """Map composite score 0-100 → win probability 0.35-0.75."""
    return 0.35 + (composite_score / 100) * 0.40


def _estimate_reward_ratio(composite_score: float) -> float:
    """Map composite score → expected reward/risk ratio 1.0-3.0."""
    return 1.0 + (composite_score / 100) * 2.0


def compute_kelly_size(
    composite_score: float,
    capital: float = None,
    max_position_pct: float = None,
    stop_loss_pct: float = None,
) -> Tuple[float, float]:
    """
    Returns (kelly_fraction, position_size_aud).
    kelly_fraction is half-Kelly for conservatism.
    """
    capital = capital or PORTFOLIO_CAPITAL
    max_pct = max_position_pct or MAX_POSITION_PCT
    sl_pct = stop_loss_pct or STOP_LOSS_PCT

    p = _estimate_win_prob(composite_score)
    q = 1 - p
    b = _estimate_reward_ratio(composite_score)

    # Kelly formula
    kelly_f = (b * p - q) / b
    kelly_f = max(0.0, kelly_f)

    # Half-Kelly for safety
    half_kelly = kelly_f / 2.0

    # Cap at max position pct
    capped = min(half_kelly, max_pct)

    position_aud = round(capital * capped, 2)

    logger.debug(
        "Kelly: score=%.1f p=%.2f b=%.2f f*=%.3f half=%.3f capped=%.3f → $%.2f",
        composite_score, p, b, kelly_f, half_kelly, capped, position_aud,
    )

    return round(capped, 4), position_aud


def compute_shares(position_aud: float, price: float) -> int:
    """Convert dollar position to whole share count."""
    if price <= 0:
        return 0
    return int(position_aud / price)
