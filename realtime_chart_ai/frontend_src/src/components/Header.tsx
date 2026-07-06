import { useEffect, useRef, useState, type CSSProperties } from 'react';

const TFS = ['1m', '5m', '15m', '1D'] as const;

function sourceLabel(source: string): string {
  if (source === 'yfinance_delayed') return 'Yahoo · ~15-20min delayed';
  if (source === 'ibkr') return 'IBKR · real-time';
  if (source === 'scripted_mock') return 'Demo data · not live';
  return source;
}

export function Header({
  tf,
  setTf,
  beginner,
  toggleBeginner,
  autoTrade,
  toggleAutoTrade,
  ticker = 'BHP',
  availableTickers = [],
  onSelectTicker,
  activeSource = 'connecting',
  exchangeLabel = 'ASX 200',
}: {
  tf: string;
  setTf: (v: string) => void;
  beginner: boolean;
  toggleBeginner: () => void;
  autoTrade: boolean;
  toggleAutoTrade: () => void;
  ticker?: string;
  availableTickers?: string[];
  onSelectTicker?: (ticker: string) => void;
  activeSource?: string;
  exchangeLabel?: string;
}) {
  const displayTicker = ticker.replace(/\.(AX|NS)$/i, '');
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  const pillStyle = (v: string): CSSProperties => ({
    border: 'none',
    background: tf === v ? 'var(--bg-secondary)' : 'transparent',
    color: tf === v ? 'var(--text-primary)' : 'var(--text-tertiary)',
    fontFamily: 'var(--font-mono)',
    fontSize: 12,
    fontWeight: 600,
    padding: '5px 10px',
    borderRadius: 6,
    cursor: 'pointer',
  });

  return (
    <header
      id="rcai-header"
      style={{
        flex: 'none', height: 56, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: 14, padding: '0 18px', borderBottom: '1px solid var(--border)', background: 'var(--bg-secondary)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div
            style={{
              width: 30, height: 30, borderRadius: 8, background: 'var(--accent-dim)',
              border: '1px solid rgba(105,147,255,.3)', display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontFamily: 'var(--font-mono)', color: 'var(--accent)', fontSize: 15, fontWeight: 600,
            }}
          >
            ▲
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.15 }}>
            <span style={{ fontSize: 13.5, fontWeight: 600, letterSpacing: '-.01em' }}>Realtime Chart AI</span>
            <span id="rcai-brandtag" style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
              reads the tape live, explains every call
            </span>
          </div>
        </div>
        <div style={{ width: 1, height: 26, background: 'var(--border)' }} />
        <div ref={menuRef} style={{ position: 'relative' }}>
          <button
            onClick={() => setOpen((v) => !v)}
            aria-haspopup="listbox"
            aria-expanded={open}
            style={{
              display: 'flex', alignItems: 'center', gap: 8, background: 'var(--bg-tertiary)', border: '1px solid var(--border)',
              borderRadius: 8, padding: '6px 10px', cursor: 'pointer', color: 'var(--text-primary)',
            }}
          >
            <span style={{ fontSize: 13 }}>🇦🇺</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 13 }}>{displayTicker}</span>
            <span style={{ fontSize: 10.5, color: 'var(--text-tertiary)', letterSpacing: '.04em' }}>{exchangeLabel}</span>
            <span style={{ color: 'var(--text-tertiary)', fontSize: 11 }}>▾</span>
          </button>
          {open && availableTickers.length > 0 && (
            <div
              role="listbox"
              style={{
                position: 'absolute', top: 'calc(100% + 6px)', left: 0, minWidth: 160, zIndex: 20,
                background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8,
                padding: 4, boxShadow: '0 8px 24px rgba(0,0,0,.35)',
              }}
            >
              {availableTickers.map((t) => {
                const active = t === ticker;
                return (
                  <button
                    key={t}
                    role="option"
                    aria-selected={active}
                    onClick={() => { onSelectTicker?.(t); setOpen(false); }}
                    style={{
                      display: 'block', width: '100%', textAlign: 'left', border: 'none', cursor: 'pointer',
                      padding: '7px 10px', borderRadius: 6, fontFamily: 'var(--font-mono)', fontSize: 12.5,
                      background: active ? 'var(--accent-dim)' : 'transparent',
                      color: active ? 'var(--accent)' : 'var(--text-primary)', fontWeight: active ? 600 : 400,
                    }}
                  >
                    {t.replace(/\.(AX|NS)$/i, '')}
                  </button>
                );
              })}
            </div>
          )}
        </div>
        <div
          id="rcai-tfpills"
          style={{ display: 'flex', alignItems: 'center', gap: 3, background: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 8, padding: 3 }}
        >
          {TFS.map((v) => (
            <button key={v} onClick={() => setTf(v)} style={pillStyle(v)}>
              {v}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 7, background: 'var(--profit-dim)', borderRadius: 999,
            padding: '5px 11px', fontSize: 12, fontWeight: 600, color: 'var(--profit)',
          }}
        >
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--profit)', animation: 'rcaiPulse 1.8s ease-out infinite' }} />
          LIVE
        </span>
        <span
          id="rcai-sourcechip"
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6, background: 'var(--bg-tertiary)', border: '1px solid var(--border)',
            borderRadius: 999, padding: '5px 11px', fontSize: 11, color: 'var(--text-secondary)', letterSpacing: '.03em',
          }}
        >
          {sourceLabel(activeSource)}
        </span>
        <button
          onClick={toggleBeginner}
          title="Plain-English teaching notes"
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6, borderRadius: 999, padding: '5px 12px', fontSize: 12,
            fontWeight: 500, cursor: 'pointer', border: '1px solid ' + (beginner ? 'transparent' : 'var(--border)'),
            background: beginner ? 'var(--accent-dim)' : 'var(--bg-tertiary)', color: beginner ? 'var(--accent)' : 'var(--text-secondary)',
          }}
        >
          <span style={{ fontSize: 12.5 }}>🎓</span>
          <span>Learn</span>
        </button>
        <div
          style={{
            display: 'flex', alignItems: 'center', gap: 9, background: 'var(--bg-tertiary)', border: '1px solid var(--border)',
            borderRadius: 999, padding: '5px 12px 5px 13px',
          }}
        >
          <span style={{ fontSize: 12, color: autoTrade ? 'var(--warning)' : 'var(--text-tertiary)', fontWeight: 500 }}>
            Auto-trade
          </span>
          <button
            onClick={toggleAutoTrade}
            role="switch"
            aria-checked={autoTrade}
            style={{
              position: 'relative', width: 34, height: 18, borderRadius: 999, border: 'none', cursor: 'pointer', padding: 0,
              background: autoTrade ? 'var(--warning)' : 'var(--border-strong)', transition: 'background .15s',
            }}
          >
            <span
              style={{
                position: 'absolute', top: 2, left: 2, width: 14, height: 14, borderRadius: '50%', background: '#fff',
                transition: 'transform .15s', transform: 'translateX(' + (autoTrade ? '16px' : '0') + ')',
              }}
            />
          </button>
        </div>
      </div>
    </header>
  );
}
