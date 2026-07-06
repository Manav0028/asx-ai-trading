import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import type { Direction } from '../types';
import { api } from '../lib/liveApi';

interface MergedTrade {
  key: string;
  status: 'open' | 'closed';
  ticker: string;
  direction: Direction;
  pattern: string;
  entry: number;
  exit: number | null;
  stop: number;
  target: number;
  shares: number;
  investment: number;
  netPnl: number | null;
  exitReason: string | null;
  barsHeld: number;
  score: number | null;
  zone: string | null;
  rationale: string;
  ts: string; // ISO — entry/open time, used for sorting + date filtering
}

function fmtMoney(v: number): string {
  return (v >= 0 ? '+' : '−') + '$' + Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

const inputStyle: CSSProperties = {
  background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 7,
  padding: '6px 9px', fontSize: 11.5, color: 'var(--text-primary)', fontFamily: 'var(--font-sans)',
};

export function TradesTab() {
  const [rows, setRows] = useState<MergedTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [tickerFilter, setTickerFilter] = useState('');
  const [directionFilter, setDirectionFilter] = useState<'all' | 'long' | 'short'>('all');
  const [statusFilter, setStatusFilter] = useState<'all' | 'open' | 'closed'>('all');

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [journalRows, positions] = await Promise.all([
          api.getJournalGlobal({ limit: 500, start: dateFrom || undefined, end: dateTo || undefined }),
          api.getAllPositions(),
        ]);
        if (cancelled) return;
        const closed: MergedTrade[] = journalRows
          .filter((r) => r.action && r.outcome)
          .map((r) => ({
            key: `closed-${r.id}`,
            status: 'closed',
            ticker: r.ticker,
            direction: (r.direction ?? 'long') as Direction,
            pattern: r.pattern_name,
            entry: r.action!.entry_price,
            exit: r.outcome!.exit_price,
            stop: r.action!.stop_price ?? r.outcome!.exit_price,
            target: r.action!.target_price ?? r.outcome!.exit_price,
            shares: r.action!.shares ?? 0,
            investment: (r.action!.shares ?? 0) * r.action!.entry_price,
            netPnl: r.outcome!.net_pnl,
            exitReason: r.outcome!.exit_reason,
            barsHeld: r.outcome!.bars_held ?? 0,
            score: r.composite_score,
            zone: r.smc_zone,
            rationale: r.claude_rationale ?? r.rule_reason ?? '',
            ts: r.bar_ts,
          }));
        const open: MergedTrade[] = positions.map((p) => ({
          key: `open-${p.id}`,
          status: 'open',
          ticker: p.ticker,
          direction: p.direction,
          pattern: 'open position',
          entry: p.entry_price,
          exit: p.current_price,
          stop: p.stop_price,
          target: p.target_price,
          shares: p.shares,
          investment: p.shares * p.entry_price,
          netPnl: p.unrealized_pnl, // live unrealized — null only if this ticker has no price data yet
          exitReason: null,
          barsHeld: p.bars_held,
          score: null,
          zone: null,
          rationale: '',
          ts: p.opened_at,
        }));
        const merged = [...open, ...closed].sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime());
        setRows(merged);
      } catch {
        // transiently unavailable — keep showing the last known set
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    const timer = setInterval(load, 10000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [dateFrom, dateTo]);

  const filtered = useMemo(() => {
    return rows.filter((r) => {
      if (statusFilter !== 'all' && r.status !== statusFilter) return false;
      if (directionFilter !== 'all' && r.direction !== directionFilter) return false;
      if (tickerFilter && !r.ticker.toLowerCase().includes(tickerFilter.toLowerCase())) return false;
      // dateFrom/dateTo already applied server-side for closed trades (via
      // /api/journal's start/end params); applied here too for open
      // positions, which come from /api/positions and have no server-side
      // date filter of their own.
      if (dateFrom && new Date(r.ts) < new Date(dateFrom)) return false;
      if (dateTo && new Date(r.ts) > new Date(dateTo + 'T23:59:59')) return false;
      return true;
    });
  }, [rows, statusFilter, directionFilter, tickerFilter, dateFrom, dateTo]);

  const closedFiltered = filtered.filter((r) => r.status === 'closed');
  const openFiltered = filtered.filter((r) => r.status === 'open');
  const realizedPnl = closedFiltered.reduce((a, r) => a + (r.netPnl ?? 0), 0);
  const unrealizedPnl = openFiltered.reduce((a, r) => a + (r.netPnl ?? 0), 0);
  const totalInvested = openFiltered.reduce((a, r) => a + r.investment, 0);
  const winRate = closedFiltered.length
    ? Math.round((100 * closedFiltered.filter((r) => (r.netPnl ?? 0) >= 0).length) / closedFiltered.length) + '%'
    : '—';

  const card: CSSProperties = { background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 9, padding: '10px 11px' };
  const cardLabel: CSSProperties = { fontSize: 9.5, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 4 };
  const cardValue: CSSProperties = { fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' };

  return (
    <div style={{ position: 'absolute', inset: 0, overflowY: 'auto', padding: '14px 16px' }}>
      <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginBottom: 11 }}>
        Every trade execution across all tickers — open and closed.
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8, marginBottom: 11 }}>
        <div style={card}>
          <div style={cardLabel}>Realized P&amp;L</div>
          <div style={{ ...cardValue, color: realizedPnl >= 0 ? 'var(--profit)' : 'var(--loss)' }}>{fmtMoney(realizedPnl)}</div>
        </div>
        <div style={card}>
          <div style={cardLabel}>Unrealised P&amp;L</div>
          <div style={{ ...cardValue, color: unrealizedPnl >= 0 ? 'var(--profit)' : 'var(--loss)' }}>{fmtMoney(unrealizedPnl)}</div>
        </div>
        <div style={card}>
          <div style={cardLabel}>Invested (open)</div>
          <div style={cardValue}>${totalInvested.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
        </div>
        <div style={card}>
          <div style={cardLabel}>Win rate</div>
          <div style={cardValue}>{winRate}</div>
        </div>
        <div style={card}>
          <div style={cardLabel}>Trades</div>
          <div style={cardValue}>{filtered.length}</div>
        </div>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginBottom: 13 }}>
        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} style={inputStyle} title="From date" />
        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} style={inputStyle} title="To date" />
        <input
          type="text" value={tickerFilter} onChange={(e) => setTickerFilter(e.target.value)}
          placeholder="Filter by ticker…" style={{ ...inputStyle, width: 130 }}
        />
        <select value={directionFilter} onChange={(e) => setDirectionFilter(e.target.value as typeof directionFilter)} style={inputStyle}>
          <option value="all">All directions</option>
          <option value="long">Long</option>
          <option value="short">Short</option>
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)} style={inputStyle}>
          <option value="all">All status</option>
          <option value="open">Open</option>
          <option value="closed">Closed</option>
        </select>
      </div>

      {loading && <div style={{ textAlign: 'center', color: 'var(--text-tertiary)', padding: '30px 20px', fontSize: 12 }}>Loading trades…</div>}

      {!loading && filtered.length === 0 && (
        <div style={{ textAlign: 'center', color: 'var(--text-tertiary)', padding: '40px 20px' }}>
          <div style={{ fontSize: 26, marginBottom: 8 }}>▤</div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>No trades match these filters</div>
        </div>
      )}

      {filtered.map((t) => {
        const isL = t.direction === 'long';
        const isOpen = t.status === 'open';
        const win = (t.netPnl ?? 0) >= 0;
        const isExpanded = expanded === t.key;
        const dirStyle: CSSProperties = {
          display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 10, fontWeight: 700, letterSpacing: '.03em',
          padding: '2px 7px', borderRadius: 5,
          background: isL ? 'var(--profit-dim)' : 'var(--loss-dim)', color: isL ? 'var(--profit)' : 'var(--loss)',
        };
        const statusStyle: CSSProperties = {
          display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10, fontWeight: 700, letterSpacing: '.03em',
          padding: '2px 7px', borderRadius: 5,
          background: isOpen ? 'var(--warning-dim)' : 'var(--bg-tertiary)', color: isOpen ? 'var(--warning)' : 'var(--text-tertiary)',
        };
        return (
          <div key={t.key} style={{ border: '1px solid var(--border)', borderRadius: 10, marginBottom: 9, overflow: 'hidden', background: 'var(--bg-tertiary)' }}>
            <button
              onClick={() => setExpanded((cur) => (cur === t.key ? null : t.key))}
              style={{
                width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10,
                background: 'none', border: 'none', padding: '11px 13px', cursor: 'pointer', textAlign: 'left', color: 'inherit',
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4 }}>
                  <span style={dirStyle}>{isL ? '▲ LONG' : '▼ SHORT'}</span>
                  <span style={statusStyle}>{isOpen ? '● OPEN' : 'CLOSED'}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 12.5, color: 'var(--text-primary)' }}>{t.ticker}</span>
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--text-secondary)' }}>
                  {t.pattern} · <span style={{ color: 'var(--text-tertiary)' }}>{fmtDate(t.ts)}</span>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 'none' }}>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600, color: t.netPnl == null ? 'var(--text-tertiary)' : (win ? 'var(--profit)' : 'var(--loss)'), fontVariantNumeric: 'tabular-nums' }}>
                    {t.netPnl == null ? '—' : fmtMoney(t.netPnl)}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
                    {isOpen ? (t.netPnl == null ? 'no price yet' : 'unrealised') : (t.exitReason ?? '')}
                  </div>
                </div>
                <span style={{ color: 'var(--text-tertiary)', fontSize: 10 }}>{isExpanded ? '▲' : '▼'}</span>
              </div>
            </button>
            {isExpanded && (
              <div style={{ padding: '0 13px 13px', animation: 'rcaiIn .2s ease-out' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 7, margin: '2px 0 11px' }}>
                  <div style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 7, padding: '7px 8px' }}>
                    <div style={{ fontSize: 9, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 3 }}>Entry</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>${t.entry.toFixed(2)}</div>
                  </div>
                  <div style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 7, padding: '7px 8px' }}>
                    <div style={{ fontSize: 9, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 3 }}>{isOpen ? 'Current stop' : 'Exit'}</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600, color: isOpen ? 'var(--loss)' : (win ? 'var(--profit)' : 'var(--loss)') }}>
                      ${(isOpen ? t.stop : t.exit ?? 0).toFixed(2)}
                    </div>
                  </div>
                  <div style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 7, padding: '7px 8px' }}>
                    <div style={{ fontSize: 9, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 3 }}>Target</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600, color: 'var(--profit)' }}>${t.target.toFixed(2)}</div>
                  </div>
                  <div style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 7, padding: '7px 8px' }}>
                    <div style={{ fontSize: 9, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 3 }}>Shares</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{t.shares.toFixed(2)}</div>
                  </div>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 14px', fontSize: 11, color: 'var(--text-tertiary)', marginBottom: t.rationale ? 11 : 0, fontFamily: 'var(--font-mono)' }}>
                  <span>${t.investment.toLocaleString(undefined, { maximumFractionDigits: 0 })} invested</span>
                  {!isOpen && <span>held {t.barsHeld} bars</span>}
                  {t.score != null && <span>score {Math.round(t.score)}/100</span>}
                  {t.zone && <span>{t.zone} zone</span>}
                </div>
                {t.rationale && (
                  <div style={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 12px' }}>
                    <div style={{ fontSize: 9.5, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 5 }}>
                      Why the system took it
                    </div>
                    <div style={{ fontSize: 12, lineHeight: 1.55, color: 'var(--text-secondary)' }}>{t.rationale}</div>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
