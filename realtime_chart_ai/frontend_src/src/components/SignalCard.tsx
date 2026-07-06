import type { Direction, Phase } from '../types';

const ROWS = [
  { key: 'pattern', label: 'Pattern strength', pct: '35%' },
  { key: 'trend', label: 'Trend alignment', pct: '20%' },
  { key: 'volume', label: 'Volume confirm', pct: '15%' },
  { key: 'mtf', label: 'Timeframe agree', pct: '15%' },
  { key: 'zone', label: 'Zone quality', pct: '15%' },
] as const;

function convictionLabel(score: number): { label: string; stars: string } {
  if (score >= 85) return { label: 'Very high', stars: '⭐⭐⭐' };
  if (score >= 70) return { label: 'High', stars: '⭐⭐' };
  return { label: 'Moderate', stars: '⭐' };
}

export function SignalCard({
  phase,
  dispScore,
  bd,
  pnl,
  patternName = 'Bullish order-block retest',
  direction = 'long',
  entry = 42.08,
  stop = 41.88,
  target = 42.48,
  rr = 2.0,
  posMeta = '190 sh · $8,000 · risk $38',
  hasOpenPosition = false,
}: {
  phase: Phase;
  dispScore: number;
  bd: number[];
  pnl: number;
  patternName?: string;
  direction?: Direction;
  entry?: number;
  stop?: number;
  target?: number;
  rr?: number | null;
  posMeta?: string;
  hasOpenPosition?: boolean;
}) {
  const hasSignal = phase !== 'watching';
  const active = phase === 'active' || phase === 'closed';
  const pnlColor = pnl >= 0 ? 'var(--profit)' : 'var(--loss)';
  const pnlStr = (pnl >= 0 ? '+' : '−') + '$' + Math.abs(pnl).toFixed(2);
  const scoreColor = dispScore >= 70 ? 'var(--profit)' : dispScore >= 60 ? 'var(--warning)' : 'var(--text-primary)';
  // Whether a REAL position is open for this ticker, not whether auto-trade
  // currently happens to be toggled on — those are different facts once a
  // position opened while the toggle was on outlives a later toggle-off
  // (the toggle only gates new entries, per the backend's own design; see
  // trading/state.py). Using the live `autoTrade` flag here previously made
  // every currently-open position wrongly render as "not taken" the moment
  // the toggle was flipped off, hiding its real P&L.
  const showPosition = active && hasOpenPosition;
  const autoOff = active && !hasOpenPosition;
  const isLong = direction === 'long';
  const conv = convictionLabel(dispScore);
  const targetPct = entry ? (((target - entry) / entry) * (isLong ? 100 : -100)).toFixed(2) : '0.00';
  const stopPct = entry ? (((stop - entry) / entry) * (isLong ? 100 : -100)).toFixed(2) : '0.00';

  return (
    <div style={{ flex: 'none', padding: '15px 16px', borderBottom: '1px solid var(--border)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <span style={{ fontSize: 11.5, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.08em', color: 'var(--text-secondary)' }}>
          Live signal
        </span>
        <span
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 10.5, fontWeight: 600, letterSpacing: '.05em',
            textTransform: 'uppercase', borderRadius: 999, padding: '3px 10px',
            color: hasSignal ? 'var(--profit)' : 'var(--warning)',
            background: hasSignal ? 'var(--profit-dim)' : 'var(--warning-dim)',
          }}
        >
          {hasSignal ? (phase === 'closed' ? 'Closed' : 'Firing now') : 'Idle'}
        </span>
      </div>

      {!hasSignal && (
        <div style={{ display: 'flex', gap: 11, alignItems: 'flex-start', padding: '6px 2px 2px' }}>
          <span style={{ fontSize: 17, lineHeight: 1 }}>🔍</span>
          <div>
            <div style={{ fontSize: 13.5, color: 'var(--text-primary)', fontWeight: 500, marginBottom: 3 }}>
              Watching for a confirmed setup
            </div>
            <div style={{ fontSize: 12.5, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              Price is drifting back into an earlier demand zone. No trade until a pattern, the trend and the higher
              timeframe all agree. <span style={{ color: 'var(--text-tertiary)', fontStyle: 'italic' }}>Patience is a position.</span>
            </div>
          </div>
        </div>
      )}

      {hasSignal && (
        <div style={{ animation: 'rcaiIn .3s ease-out' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 12 }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
                <span
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 4,
                    background: isLong ? 'var(--profit-dim)' : 'var(--loss-dim)', color: isLong ? 'var(--profit)' : 'var(--loss)',
                    fontWeight: 700, fontSize: 11, letterSpacing: '.04em', padding: '3px 8px', borderRadius: 6,
                  }}
                >
                  {isLong ? '▲ LONG' : '▼ SHORT'}
                </span>
                <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>conviction {conv.label} {conv.stars}</span>
              </div>
              <div style={{ fontSize: 14.5, fontWeight: 600, color: 'var(--text-primary)' }}>{patternName}</div>
            </div>
            <div style={{ textAlign: 'right', flex: 'none' }}>
              <div
                style={{
                  fontFamily: 'var(--font-mono)', fontSize: 30, fontWeight: 600, lineHeight: 1, color: scoreColor,
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {dispScore}
              </div>
              <div style={{ fontSize: 10, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginTop: 2 }}>
                / 100 score
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 7, marginBottom: 13 }}>
            {ROWS.map((row, i) => (
              <div key={row.key} style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                <span style={{ width: 118, flex: 'none', fontSize: 11.5, color: 'var(--text-secondary)' }}>{row.label}</span>
                <span style={{ flex: 1, height: 6, borderRadius: 3, background: 'var(--bg-tertiary)', overflow: 'hidden' }}>
                  <span
                    style={{
                      display: 'block', height: '100%', background: 'var(--accent)', borderRadius: 3,
                      transition: 'width .3s ease-out', width: (bd[i] ?? 0) + '%',
                    }}
                  />
                </span>
                <span style={{ width: 26, textAlign: 'right', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-tertiary)' }}>
                  {row.pct}
                </span>
              </div>
            ))}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8, marginBottom: 11 }}>
            <div style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 9, padding: '9px 10px' }}>
              <div style={{ fontSize: 9.5, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 4 }}>
                Entry
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600, color: 'var(--accent)' }}>
                ${entry.toFixed(2)}
              </div>
            </div>
            <div style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 9, padding: '9px 10px' }}>
              <div style={{ fontSize: 9.5, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 4 }}>
                Target
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600, color: 'var(--profit)' }}>
                ${target.toFixed(2)}
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--profit)' }}>
                {Number(targetPct) >= 0 ? '+' : ''}{targetPct}%
              </div>
            </div>
            <div style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 9, padding: '9px 10px' }}>
              <div style={{ fontSize: 9.5, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 4 }}>
                Stop
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600, color: 'var(--loss)' }}>
                ${stop.toFixed(2)}
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--loss)' }}>
                {Number(stopPct) >= 0 ? '+' : ''}{stopPct}%
              </div>
            </div>
          </div>

          {showPosition && (
            <div
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--bg-primary)',
                border: '1px solid var(--border)', borderRadius: 9, padding: '10px 12px', marginBottom: 9,
              }}
            >
              <div>
                <div style={{ fontSize: 10, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 3 }}>
                  Paper position · {posMeta}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Unrealised P&amp;L</div>
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 600, color: pnlColor, fontVariantNumeric: 'tabular-nums' }}>
                {pnlStr}
              </div>
            </div>
          )}
          {autoOff && (
            <div
              style={{
                fontSize: 11.5, color: 'var(--warning)', background: 'var(--warning-dim)', borderRadius: 8,
                padding: '8px 11px', marginBottom: 9, lineHeight: 1.45,
              }}
            >
              This setup is shown, not taken as a paper position — either auto-trade is off or the entry conditions weren't fully met.
            </div>
          )}

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
            <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
              Reward : risk <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', fontWeight: 600 }}>{rr != null ? rr.toFixed(1) : '—'} : 1</span>
            </span>
            <span style={{ fontSize: 11, color: 'var(--text-tertiary)', fontStyle: 'italic' }}>
              ⚠️ Paper trade only — not real money
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
