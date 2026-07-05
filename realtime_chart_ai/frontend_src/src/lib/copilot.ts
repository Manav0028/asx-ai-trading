import type { TeachNote } from '../types';

export interface Answer {
  text: string;
  teach: TeachNote | null;
}

const has = (t: string, ...words: string[]) => words.some((w) => t.includes(w));

export function answerQuestion(q: string, risk: number): Answer {
  const t = q.toLowerCase();

  if (has(t, 'why', 'long', 'buy'))
    return {
      text: "It's a long because demand showed up where the system expected it: price dropped into a bullish order block and buyers stepped in. The 5-minute and 15-minute trends are both pointing up, so the smaller timeframe isn't fighting the bigger picture. Aligned trend + a demand zone + a volume uptick = lean long.",
      teach: { term: 'Trend alignment', body: 'When the short and higher timeframes point the same way, a signal is more trustworthy. Trading against the higher timeframe is how beginners get chopped up.' },
    };
  if (has(t, 'order block', 'orderblock'))
    return {
      text: 'An order block is the last down-candle before price pushed up hard. Institutions often leave unfilled buy orders there. When price drifts back into that zone, those resting orders can fire and send it up again — which is the bounce we’re trading here.',
      teach: { term: 'Order block', body: 'Last opposite-colour candle before a strong move. A retest of it is a high-probability spot to enter.' },
    };
  if (has(t, 'score', 'composite', '78', 'rating'))
    return {
      text: "The score is a weighted read-out, 0–100. Pattern strength counts for 35%, trend alignment 20%, volume 15%, agreement across timeframes 15%, and how good the zone is 15%. Add them up and this setup lands at 78 — above the 65 line the system needs to act. Nothing fires below 65; it just gets logged.",
      teach: { term: 'Why a threshold?', body: 'Most reads never clear 65 — and that’s the point. Doing nothing on a weak setup is a decision, not a miss.' },
    };
  if (has(t, 'stop', 'risk', 'lose', 'loss'))
    return {
      text: `Your stop is $41.88 — just below the order block. It's the price that says the idea was wrong. If price closes under it, the system exits for a small, planned loss of about $${risk}. Small losses are the cost of staying in the game.`,
      teach: { term: 'Stop-loss', body: 'A pre-set exit that caps the damage on any single trade. Deciding it before you enter is what keeps one bad trade from becoming a big one.' },
    };
  if (has(t, 'target', 'reward', 'take profit'))
    return {
      text: "The target is $42.48 — twice as far from entry as the stop is. That 2-to-1 reward-to-risk means you can be right well under half the time and still come out ahead over many trades. It's the maths that makes disciplined trading work.",
      teach: { term: 'Reward : risk', body: 'How much you aim to make vs. how much you risk. At 2:1 you only need to win about 1 in 3 to break even.' },
    };
  if (has(t, 'real money', 'real', 'safe', 'paper'))
    return {
      text: 'Nothing here is real money. Every fill is simulated — with realistic slippage and brokerage baked in — so you can learn to read setups without risking a cent. And to be clear: none of this is financial advice.',
      teach: null,
    };
  if (has(t, 'fair value gap', 'fvg', 'gap'))
    return {
      text: "A fair value gap is a jump so fast that price skipped a level, leaving a gap on the chart. Price often comes back to 'fill' it later. Like an order block, it marks an area where supply and demand got out of balance.",
      teach: { term: 'Fair value gap', body: 'A 3-candle imbalance where the move was so quick it left an untraded gap. Price revisits it a majority of the time.' },
    };
  if (has(t, 'liquidity', 'sweep', 'stop hunt'))
    return {
      text: 'A liquidity sweep is when price pokes just past a recent high or low — triggering the stop orders resting there — then snaps straight back. It traps late traders and often marks a turning point.',
      teach: { term: 'Liquidity sweep', body: 'A quick fake-out beyond a swing high/low that reverses within a few bars. Big players use it to fill orders.' },
    };
  if (has(t, 'volume'))
    return {
      text: 'Volume is how many shares changed hands. A move on heavy volume has real participation behind it and is more trustworthy than the same move on quiet volume. Here, volume ticked up on the bounce — a small vote of confidence for the long.',
      teach: null,
    };
  if (has(t, 'rsi', 'momentum'))
    return {
      text: "RSI measures momentum on a 0–100 scale. Under 30 is 'oversold' (stretched down), over 70 'overbought'. It's a helper that adds context — never a trigger on its own.",
      teach: null,
    };
  if (has(t, 'ema', 'moving average', 'trend', 'line'))
    return {
      text: "The blue line is a moving average — the recent average price. When price and that line both slope up, the trend is up. The system only takes longs when the trend agrees, so you're never buying into a falling market.",
      teach: { term: 'Moving average', body: 'A running average of recent prices that smooths out the noise so the underlying trend is easier to see.' },
    };
  return {
    text: "Good question. I read this chart in real time — candlestick patterns, trend, volume and demand/supply zones — and explain what I see in plain English. Try 'why is this a long?', 'what's an order block?', or 'explain the score'.",
    teach: null,
  };
}
