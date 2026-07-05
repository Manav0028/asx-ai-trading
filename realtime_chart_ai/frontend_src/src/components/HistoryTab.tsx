import type { Trade } from '../types';

function fmtPnl(v: number) {
  return (v >= 0 ? '+' : '−') + '$' + Math.abs(v).toFixed(2);
}

export function HistoryTab({
  trades,
  expandedTrade,
  toggleTrade,
}: {
  trades: Trade[];
  expandedTrade: number | null;
  toggleTrade: (id: number) => void;
}) {
  const histCount = trades.length;
  const sum = trades.reduce((a, t) => a + t.netPnl, 0);
  const histWin = trades.length ? Math.round((100 * trades.filter((t) => t.netPnl >= 0).length) / trades.length) + '%' : '—';
  const histPnl = fmtPnl(sum);
  const histPnlColor = sum >= 0 ? 'var(--profit)' : 'var(--loss)';

  return (
    <div style={{ position: 'absolute', inset: 0, overflowY: 'auto', padding: '14px 16px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8, marginBottom: 13 }}>
        <div style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 9, padding: '10px 11px' }}>
          <div style={{ fontSize: 9.5, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 4 }}>
            Net P&amp;L
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 600, color: histPnlColor, fontVariantNumeric: 'tabular-nums' }}>
            {histPnl}
          </div>
        </div>
        <div style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 9, padding: '10px 11px' }}>
          <div style={{ fontSize: 9.5, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 4 }}>
            Win rate
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
            {histWin}
          </div>
        </div>
        <div style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 9, padding: '10px 11px' }}>
          <div style={{ fontSize: 9.5, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 4 }}>
            Trades
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
            {histCount}
          </div>
        </div>
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginBottom: 11 }}>
        Every closed paper trade — tap a row for its full journal.
      </div>

      {trades.map((t) => {
        const win = t.netPnl >= 0;
        const isL = t.dir === 'long';
        const expanded = expandedTrade === t.id;
        const dirStyle = {
          display: 'inline-flex' as const,
          alignItems: 'center' as const,
          gap: 3,
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: '.03em',
          padding: '2px 7px',
          borderRadius: 5,
          background: isL ? 'var(--profit-dim)' : 'var(--loss-dim)',
          color: isL ? 'var(--profit)' : 'var(--loss)',
        };
        const reasonStyle = {
          display: 'inline-block' as const,
          marginTop: 3,
          fontSize: 10,
          padding: '1px 6px',
          borderRadius: 5,
          whiteSpace: 'nowrap' as const,
          background: t.exitReason === 'target' ? 'var(--profit-dim)' : t.exitReason === 'stop' ? 'var(--loss-dim)' : 'var(--warning-dim)',
          color: t.exitReason === 'target' ? 'var(--profit)' : t.exitReason === 'stop' ? 'var(--loss)' : 'var(--warning)',
        };
        const reasonText = t.exitReason === 'target' ? '🎯 target' : t.exitReason === 'stop' ? '🔴 stop' : '⏱ time';

        return (
          <div key={t.id} style={{ border: '1px solid var(--border)', borderRadius: 10, marginBottom: 9, overflow: 'hidden', background: 'var(--bg-tertiary)' }}>
            <button
              onClick={() => toggleTrade(t.id)}
              style={{
                width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10,
                background: 'none', border: 'none', padding: '11px 13px', cursor: 'pointer', textAlign: 'left', color: 'inherit',
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4 }}>
                  <span style={dirStyle}>{isL ? '▲ LONG' : '▼ SHORT'}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 12.5, color: 'var(--text-primary)' }}>{t.ticker}</span>
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--text-secondary)' }}>
                  {t.pattern} · <span style={{ color: 'var(--text-tertiary)' }}>{t.time}</span>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 'none' }}>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600, color: win ? 'var(--profit)' : 'var(--loss)', fontVariantNumeric: 'tabular-nums' }}>
                    {fmtPnl(t.netPnl)}
                  </div>
                  <div style={reasonStyle}>{reasonText}</div>
                </div>
                <span style={{ color: 'var(--text-tertiary)', fontSize: 10 }}>{expanded ? '▲' : '▼'}</span>
              </div>
            </button>
            {expanded && (
              <div style={{ padding: '0 13px 13px', animation: 'rcaiIn .2s ease-out' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 7, margin: '2px 0 11px' }}>
                  <div style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 7, padding: '7px 8px' }}>
                    <div style={{ fontSize: 9, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 3 }}>Entry</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>${t.entry.toFixed(2)}</div>
                  </div>
                  <div style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 7, padding: '7px 8px' }}>
                    <div style={{ fontSize: 9, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 3 }}>Exit</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600, color: win ? 'var(--profit)' : 'var(--loss)' }}>${t.exit.toFixed(2)}</div>
                  </div>
                  <div style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 7, padding: '7px 8px' }}>
                    <div style={{ fontSize: 9, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 3 }}>Target</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600, color: 'var(--profit)' }}>${t.target.toFixed(2)}</div>
                  </div>
                  <div style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 7, padding: '7px 8px' }}>
                    <div style={{ fontSize: 9, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 3 }}>Stop</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600, color: 'var(--loss)' }}>${t.stop.toFixed(2)}</div>
                  </div>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 14px', fontSize: 11, color: 'var(--text-tertiary)', marginBottom: 11, fontFamily: 'var(--font-mono)' }}>
                  <span>{t.shares} sh</span>
                  <span>held {t.barsHeld} bars</span>
                  <span>score {t.score}/100</span>
                  <span>{t.zone} zone</span>
                </div>
                <div style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
                    <span
                      style={{
                        width: 16, height: 16, borderRadius: 4, background: 'var(--accent-dim)', color: 'var(--accent)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10,
                      }}
                    >
                      ✦
                    </span>
                    <span style={{ fontSize: 9.5, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--text-tertiary)' }}>
                      Why the system took it
                    </span>
                  </div>
                  <div style={{ fontSize: 12, lineHeight: 1.55, color: 'var(--text-secondary)' }}>{t.rationale}</div>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
