"""
Claude rationale layer — mirrors ai_engine/claude_summarizer.py's client
construction + rule-based fallback pattern, adapted for per-signal real-time
commentary instead of weekly batch summaries. Explanatory only: the composite
score / RTC_SIGNAL_THRESHOLD decision (engine/signal_engine.py) is fully
deterministic on its own — this just narrates it.
"""
import logging
from typing import Dict

from settings import ANTHROPIC_API_KEY, CLAUDE_MAX_TOKENS, CLAUDE_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a real-time trading floor analyst. A rule-based pattern just fired "
    "on a live intraday chart. In 2-3 plain-English sentences, explain why this "
    "pattern matters here, right now, given the surrounding context (trend, "
    "volume, support/resistance, multi-timeframe bias, and any Smart Money "
    "Concepts context provided), and what would invalidate it. Be specific and "
    "concise — no generic disclaimers."
)


def _build_prompt(signal: Dict, context: Dict) -> str:
    return (
        f"Ticker: {signal['ticker']}\n"
        f"Pattern: {signal['pattern_name']} ({signal['pattern_type']}, {signal['direction']})\n"
        f"Rule reason: {signal['rule_reason']}\n"
        f"Pattern confidence: {signal['confidence']:.2f}\n"
        f"Composite score: {signal['composite_score']:.1f}/100\n"
        f"Price at signal: {signal['price_at_signal']:.3f}\n"
        f"Multi-timeframe bias: {context.get('mtf_summary', 'n/a')}\n"
        f"SMC zone: {context.get('smc_zone', 'n/a')}\n"
        f"SMC context: {context.get('smc_context', 'none')}\n"
        f"Nearest support/resistance: {context.get('nearest_levels', 'n/a')}\n"
        f"Volume vs 20-bar average: {context.get('volume_ratio', 'n/a')}x\n"
        f"Volume Profile: {context.get('volume_profile', 'n/a')}\n"
    )


def _rule_based_rationale(signal: Dict, context: Dict) -> str:
    conviction = (
        "High-conviction" if signal["composite_score"] >= 75
        else "Moderate-conviction" if signal["composite_score"] >= 60
        else "Low-conviction"
    )
    parts = [
        f"{conviction} {signal['direction']} signal: {signal['rule_reason']} "
        f"(composite {signal['composite_score']:.0f}/100)."
    ]
    if context.get("mtf_summary"):
        parts.append(f"Multi-timeframe: {context['mtf_summary']}.")
    if context.get("smc_zone"):
        parts.append(f"Price is in the {context['smc_zone']} zone.")
    return " ".join(parts)


def generate_rationale(signal: Dict, context: Dict) -> Dict:
    """Returns {'text': str, 'model': str}. Falls back to a rule-based
    template if ANTHROPIC_API_KEY is unset or the API call fails."""
    if not ANTHROPIC_API_KEY:
        return {"text": _rule_based_rationale(signal, context), "model": "rule_fallback"}

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_prompt(signal, context)}],
        )
        return {"text": resp.content[0].text, "model": CLAUDE_MODEL}
    except Exception as e:
        logger.warning("Claude rationale call failed for %s: %s — using rule-based fallback",
                        signal.get("ticker"), e)
        return {"text": _rule_based_rationale(signal, context), "model": "rule_fallback"}
