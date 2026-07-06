import type { RefObject } from 'react';
import type { Direction, Phase } from '../types';

const STATUS_MAP: Record<Phase, { t: string; d: string }> = {
  watching: { t: 'Watching for setup', d: 'var(--warning)' },
  active: { t: 'signal firing', d: 'var(--profit)' },
  closed: { t: 'Target reached', d: 'var(--profit)' },
};

export function Chart({
  canvasRef,
  chartStatus,
  ticker = 'BHP',
  direction = 'long',
}: {
  canvasRef: RefObject<HTMLCanvasElement | null>;
  chartStatus: Phase;
  ticker?: string;
  direction?: Direction;
}) {
  const st = STATUS_MAP[chartStatus] ?? STATUS_MAP.watching;
  const label = chartStatus === 'active' ? `${direction.toUpperCase()} ${st.t}` : st.t;
  const displayTicker = ticker.replace(/\.(AX|NS)$/i, '');

  return (
    <section
      id="rcai-chartwrap"
      style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', padding: '14px 14px 8px', gap: 9 }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)' }} />
            {displayTicker} · 1-minute execution timeframe
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-tertiary)' }}>
            <span style={{ width: 14, height: 9, borderRadius: 2, background: 'var(--accent-dim)', border: '1px solid rgba(105,147,255,.4)' }} />
            order block
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-tertiary)' }}>
            <span style={{ width: 16, borderTop: '1.5px dashed var(--profit)' }} />
            target
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-tertiary)' }}>
            <span style={{ width: 16, borderTop: '1.5px dashed var(--loss)' }} />
            stop
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-tertiary)' }}>
            <span style={{ color: 'var(--profit)', fontSize: 11 }}>▲</span>
            signal
          </span>
        </div>
      </div>
      <div
        id="rcai-canvaswrap"
        style={{ position: 'relative', flex: 1, minHeight: 300, border: '1px solid var(--border)', borderRadius: 12, overflow: 'hidden', background: '#0f0f12' }}
      >
        <canvas ref={canvasRef} style={{ display: 'block', width: '100%', height: '100%' }} />
        <div
          style={{
            position: 'absolute', top: 12, left: 12, display: 'inline-flex', alignItems: 'center', gap: 7,
            background: 'rgba(18,18,20,0.82)', border: '1px solid var(--border)', borderRadius: 999, padding: '5px 12px',
            fontSize: 11.5, fontWeight: 600, color: 'var(--text-primary)', backdropFilter: 'blur(2px)',
          }}
        >
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: st.d }} />
          {label}
        </div>
      </div>
    </section>
  );
}
