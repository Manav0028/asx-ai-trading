import { useEffect, useRef, useState, type CSSProperties } from 'react';

const TFS = ['1m', '5m', '15m', '1D'] as const;

function sourceLabel(source: string): string {
  if (source === 'yfinance_delayed') return 'Yahoo · ~15-20min delayed';
  if (source === 'ibkr') return 'IBKR · real-time';
  if (source === 'scripted_mock') return 'Demo data · not live';
  return source;
}

// ASX regular trading session: 10:00-16:00, Australia/Sydney time, Mon-Fri.
// Deliberately does not account for ASX public holidays (that needs a
// maintained holiday calendar, out of scope here) — treated as a known
// simplification, not a claim of perfect accuracy. Computed from the
// browser's own clock via Intl's timeZone conversion rather than trusting
// the device's local timezone setting, so this is correct regardless of
// where the person viewing the dashboard actually is.
function isAsxMarketOpen(): boolean {
  const parts = new Intl.DateTimeFormat('en-AU', {
    timeZone: 'Australia/Sydney', hour12: false, hour: '2-digit', minute: '2-digit', weekday: 'short',
  }).formatToParts(new Date());
  const weekday = parts.find((p) => p.type === 'weekday')?.value ?? '';
  const hour = Number(parts.find((p) => p.type === 'hour')?.value ?? '0');
  const minute = Number(parts.find((p) => p.type === 'minute')?.value ?? '0');
  if (weekday === 'Sat' || weekday === 'Sun') return false;
  const minutesSinceMidnight = hour * 60 + minute;
  return minutesSinceMidnight >= 10 * 60 && minutesSinceMidnight < 16 * 60;
}

function useAsxMarketOpen(): boolean {
  const [open, setOpen] = useState(isAsxMarketOpen);
  useEffect(() => {
    const timer = setInterval(() => setOpen(isAsxMarketOpen()), 30_000);
    return () => clearInterval(timer);
  }, []);
  return open;
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
  sectors = {},
  heldTickers = new Set(),
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
  sectors?: Record<string, string>;
  heldTickers?: Set<string>;
  exchangeLabel?: string;
}) {
  const displayTicker = ticker.replace(/\.(AX|NS)$/i, '');
  const marketOpen = useAsxMarketOpen();
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState('');
  const [sectorFilter, setSectorFilter] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  useEffect(() => {
    if (!open) { setFilter(''); setSectorFilter(null); }
  }, [open]);

  const sectorList = Array.from(new Set(Object.values(sectors))).sort();
  const filteredTickers = availableTickers.filter((t) => {
    if (sectorFilter && sectors[t] !== sectorFilter) return false;
    if (filter && !t.toLowerCase().includes(filter.toLowerCase())) return false;
    return true;
  });

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
              style={{
                position: 'absolute', top: 'calc(100% + 6px)', left: 0, width: 260, zIndex: 20,
                background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8,
                padding: 4, boxShadow: '0 8px 24px rgba(0,0,0,.35)',
              }}
            >
              {availableTickers.length > 12 && (
                <input
                  autoFocus
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="Filter…"
                  style={{
                    width: '100%', boxSizing: 'border-box', border: '1px solid var(--border)', borderRadius: 6,
                    background: 'var(--bg-tertiary)', color: 'var(--text-primary)', fontSize: 12.5,
                    fontFamily: 'var(--font-mono)', padding: '6px 8px', marginBottom: 4,
                  }}
                />
              )}
              {sectorList.length > 1 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 4, maxWidth: 280 }}>
                  {['All', ...sectorList].map((s) => {
                    const active = s === 'All' ? sectorFilter === null : sectorFilter === s;
                    return (
                      <button
                        key={s}
                        onClick={() => setSectorFilter(s === 'All' ? null : s)}
                        style={{
                          border: 'none', cursor: 'pointer', borderRadius: 999, padding: '3px 8px', fontSize: 10.5,
                          fontWeight: 500, background: active ? 'var(--accent-dim)' : 'var(--bg-tertiary)',
                          color: active ? 'var(--accent)' : 'var(--text-tertiary)',
                        }}
                      >
                        {s}
                      </button>
                    );
                  })}
                </div>
              )}
              <div role="listbox" style={{ maxHeight: 320, overflowY: 'auto' }}>
                {filteredTickers.map((t) => {
                  const active = t === ticker;
                  const held = heldTickers.has(t);
                  return (
                    <button
                      key={t}
                      role="option"
                      aria-selected={active}
                      onClick={() => { onSelectTicker?.(t); setOpen(false); }}
                      title={held ? 'Open position' : undefined}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 7, width: '100%', textAlign: 'left', border: 'none', cursor: 'pointer',
                        padding: '7px 10px', borderRadius: 6, fontFamily: 'var(--font-mono)', fontSize: 12.5,
                        background: active ? 'var(--accent-dim)' : held ? 'var(--profit-dim)' : 'transparent',
                        color: active ? 'var(--accent)' : 'var(--text-primary)', fontWeight: active ? 600 : 400,
                      }}
                    >
                      {held && <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--profit)', flex: 'none' }} />}
                      {t.replace(/\.(AX|NS)$/i, '')}
                      {sectors[t] && (
                        <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 400 }}>
                          {sectors[t]}
                        </span>
                      )}
                    </button>
                  );
                })}
                {filteredTickers.length === 0 && (
                  <div style={{ padding: '10px', fontSize: 12, color: 'var(--text-tertiary)' }}>No match</div>
                )}
              </div>
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
          title={marketOpen ? 'ASX regular session (10:00-16:00 Sydney time)' : 'Outside ASX regular trading hours — showing last available prices'}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 7, borderRadius: 999,
            padding: '5px 11px', fontSize: 12, fontWeight: 600,
            background: marketOpen ? 'var(--profit-dim)' : 'var(--bg-tertiary)',
            color: marketOpen ? 'var(--profit)' : 'var(--text-tertiary)',
            border: marketOpen ? 'none' : '1px solid var(--border)',
          }}
        >
          <span
            style={{
              width: 7, height: 7, borderRadius: '50%',
              background: marketOpen ? 'var(--profit)' : 'var(--text-tertiary)',
              animation: marketOpen ? 'rcaiPulse 1.8s ease-out infinite' : 'none',
            }}
          />
          {marketOpen ? 'LIVE' : 'MARKET CLOSED'}
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
