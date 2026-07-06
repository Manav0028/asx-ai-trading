import { useEffect, useState } from 'react';
import type { CSSProperties } from 'react';
import type { Direction } from '../types';
import { api } from '../lib/liveApi';

const inputStyle: CSSProperties = {
  background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 7,
  padding: '7px 9px', fontSize: 12, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', width: '100%',
};
const label: CSSProperties = {
  fontSize: 9.5, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 4, display: 'block',
};
const btnBase: CSSProperties = {
  border: 'none', borderRadius: 8, padding: '9px 12px', fontSize: 12.5, fontWeight: 600, cursor: 'pointer', fontFamily: 'var(--font-sans)',
};

function fmtPnl(v: number): string {
  return (v >= 0 ? '+' : '−') + '$' + Math.abs(v).toFixed(2);
}

export function ManualControls({
  ticker, price, hasOpenPosition, entry, stop, target, shares, pnl, onChanged,
}: {
  ticker: string;
  price: number;
  hasOpenPosition: boolean;
  entry: number;
  stop: number;
  target: number;
  shares: number;
  pnl: number;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Entry-form state
  const [direction, setDirection] = useState<Direction>('long');
  const [investment, setInvestment] = useState('2000');
  const [stopOverride, setStopOverride] = useState('');
  const [targetOverride, setTargetOverride] = useState('');

  // Edit-form state (open position) — reseeded whenever the live values change underneath it.
  const [editStop, setEditStop] = useState(String(stop || ''));
  const [editTarget, setEditTarget] = useState(String(target || ''));
  const [editShares, setEditShares] = useState(String(shares || ''));
  useEffect(() => { setEditStop(stop ? stop.toFixed(3) : ''); }, [stop]);
  useEffect(() => { setEditTarget(target ? target.toFixed(3) : ''); }, [target]);
  useEffect(() => { setEditShares(shares ? shares.toFixed(2) : ''); }, [shares]);

  // Reset the entry form's ticker-dependent state when the selected ticker changes.
  useEffect(() => { setError(null); setSuccess(null); setOpen(false); }, [ticker]);

  // Success confirmation is transient (auto-clears) and shown independent of
  // whatever the SignalCard above happens to display — a save/buy/exit that
  // succeeds needs to be UNMISTAKABLE right where the click happened, since
  // the SignalCard's own refresh (via onChanged -> refreshPositions) runs on
  // its own poll/async timing and shouldn't be the only signal that the
  // click actually did something.
  const flashSuccess = (msg: string) => {
    setSuccess(msg);
    setTimeout(() => setSuccess(null), 3000);
  };

  const doBuy = async () => {
    const notional = Number(investment);
    if (!notional || notional <= 0 || !price) {
      setError('Enter a valid investment amount.');
      return;
    }
    const shares = notional / price;
    setBusy(true);
    setError(null);
    try {
      await api.manualEntry({
        ticker, direction, shares,
        stop_price: stopOverride ? Number(stopOverride) : undefined,
        target_price: targetOverride ? Number(targetOverride) : undefined,
      });
      onChanged();
      setOpen(false);
      flashSuccess(`Opened ${direction} ${ticker} — ${shares.toFixed(2)} sh @ $${price.toFixed(3)}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to open position.');
    } finally {
      setBusy(false);
    }
  };

  const doExit = async () => {
    if (!window.confirm(`Close the open ${ticker} position now at the current market price?`)) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.manualExit(ticker);
      onChanged();
      flashSuccess(`Closed ${ticker} — net ${fmtPnl(result.net_pnl ?? 0)}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to close position.');
    } finally {
      setBusy(false);
    }
  };

  const doSave = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.updatePosition(ticker, {
        stop_price: editStop ? Number(editStop) : undefined,
        target_price: editTarget ? Number(editTarget) : undefined,
        shares: editShares ? Number(editShares) : undefined,
      });
      onChanged();
      flashSuccess('Saved — stop/target/shares updated.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update position.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ flex: 'none', padding: '0 16px 15px' }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 9,
          padding: '9px 12px', cursor: 'pointer', color: 'var(--text-secondary)', fontSize: 12, fontWeight: 500,
        }}
      >
        <span>Manual override — {hasOpenPosition ? 'edit or exit position' : 'buy manually'}</span>
        <span style={{ color: 'var(--text-tertiary)', fontSize: 10 }}>{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div style={{ marginTop: 9, background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 9, padding: 12 }}>
          {error && (
            <div style={{ fontSize: 11.5, color: 'var(--loss)', background: 'var(--loss-dim)', borderRadius: 7, padding: '7px 9px', marginBottom: 10 }}>
              {error}
            </div>
          )}
          {success && (
            <div style={{ fontSize: 11.5, color: 'var(--profit)', background: 'var(--profit-dim)', borderRadius: 7, padding: '7px 9px', marginBottom: 10 }}>
              ✓ {success}
            </div>
          )}

          {!hasOpenPosition && (
            <>
              <div style={{ display: 'flex', gap: 8, marginBottom: 9 }}>
                <button
                  onClick={() => setDirection('long')}
                  style={{ ...btnBase, flex: 1, background: direction === 'long' ? 'var(--profit-dim)' : 'var(--bg-tertiary)', color: direction === 'long' ? 'var(--profit)' : 'var(--text-tertiary)' }}
                >
                  ▲ Long
                </button>
                <button
                  onClick={() => setDirection('short')}
                  style={{ ...btnBase, flex: 1, background: direction === 'short' ? 'var(--loss-dim)' : 'var(--bg-tertiary)', color: direction === 'short' ? 'var(--loss)' : 'var(--text-tertiary)' }}
                >
                  ▼ Short
                </button>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 8, marginBottom: 9 }}>
                <div>
                  <span style={label}>Investment ($)</span>
                  <input style={inputStyle} type="number" value={investment} onChange={(e) => setInvestment(e.target.value)} />
                  {price > 0 && investment && Number(investment) > 0 && (
                    <div style={{ fontSize: 10.5, color: 'var(--text-tertiary)', marginTop: 4 }}>
                      ≈ {(Number(investment) / price).toFixed(2)} sh @ ${price.toFixed(3)}
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <div style={{ flex: 1 }}>
                    <span style={label}>Stop (optional)</span>
                    <input style={inputStyle} type="number" placeholder="auto" value={stopOverride} onChange={(e) => setStopOverride(e.target.value)} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <span style={label}>Target (optional)</span>
                    <input style={inputStyle} type="number" placeholder="auto" value={targetOverride} onChange={(e) => setTargetOverride(e.target.value)} />
                  </div>
                </div>
              </div>
              <button
                onClick={doBuy}
                disabled={busy}
                style={{ ...btnBase, width: '100%', background: direction === 'long' ? 'var(--profit)' : 'var(--loss)', color: '#0f0f12', opacity: busy ? 0.6 : 1 }}
              >
                {busy ? 'Placing…' : `${direction === 'long' ? 'Buy' : 'Sell'} ${ticker} now`}
              </button>
            </>
          )}

          {hasOpenPosition && (
            <>
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 9,
                background: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: 7, padding: '8px 10px',
              }}>
                <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>Unrealised P&amp;L</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600, color: pnl >= 0 ? 'var(--profit)' : 'var(--loss)' }}>
                  {fmtPnl(pnl)}
                </span>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginBottom: 9 }}>
                Entry ${entry.toFixed(3)} · adjust stop/target/shares below, or exit immediately at the current price.
              </div>
              <div style={{ display: 'flex', gap: 8, marginBottom: 9 }}>
                <div style={{ flex: 1 }}>
                  <span style={label}>Stop</span>
                  <input style={inputStyle} type="number" value={editStop} onChange={(e) => setEditStop(e.target.value)} />
                </div>
                <div style={{ flex: 1 }}>
                  <span style={label}>Target</span>
                  <input style={inputStyle} type="number" value={editTarget} onChange={(e) => setEditTarget(e.target.value)} />
                </div>
                <div style={{ flex: 1 }}>
                  <span style={label}>Shares</span>
                  <input style={inputStyle} type="number" value={editShares} onChange={(e) => setEditShares(e.target.value)} />
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={doSave} disabled={busy} style={{ ...btnBase, flex: 1, background: 'var(--accent)', color: '#0f0f12', opacity: busy ? 0.6 : 1 }}>
                  {busy ? 'Saving…' : 'Save changes'}
                </button>
                <button onClick={doExit} disabled={busy} style={{ ...btnBase, flex: 1, background: 'var(--loss-dim)', color: 'var(--loss)', opacity: busy ? 0.6 : 1 }}>
                  Exit now
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
