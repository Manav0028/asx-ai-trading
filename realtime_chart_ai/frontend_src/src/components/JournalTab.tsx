import type { CSSProperties } from 'react';
import type { JournalEntry } from '../types';

const th: CSSProperties = {
  fontWeight: 600,
  color: 'var(--text-tertiary)',
  fontSize: 10,
  letterSpacing: '.05em',
  textTransform: 'uppercase',
  padding: '0 6px 8px',
};

const td: CSSProperties = {
  padding: '9px 6px',
  borderTop: '1px solid var(--border-subtle)',
};

export function JournalTab({ journal }: { journal: JournalEntry[] }) {
  const hasJournal = journal.length > 0;

  return (
    <div style={{ position: 'absolute', inset: 0, overflowY: 'auto', padding: '14px 16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>Every interpretation, logged — actioned or not.</span>
      </div>

      {hasJournal && (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, fontVariantNumeric: 'tabular-nums' }}>
          <thead>
            <tr>
              <th style={{ ...th, textAlign: 'left' }}>Time</th>
              <th style={{ ...th, textAlign: 'left' }}>Pattern</th>
              <th style={{ ...th, textAlign: 'right' }}>Score</th>
              <th style={{ ...th, textAlign: 'left' }}>Zone</th>
              <th style={{ ...th, textAlign: 'right' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {journal.map((j, i) => {
              const dirArrow = j.dir === 'long' ? '▲' : '▼';
              const dirColor = j.dir === 'long' ? 'var(--profit)' : 'var(--loss)';
              const actionStyle: CSSProperties = {
                display: 'inline-block',
                padding: '2px 8px',
                borderRadius: 999,
                fontSize: 10.5,
                whiteSpace: 'nowrap',
                ...(j.action === 'watch'
                  ? { background: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-tertiary)' }
                  : { background: 'var(--accent-dim)', color: 'var(--accent)' }),
              };
              return (
                <tr key={i}>
                  <td style={{ ...td, fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)', fontSize: 11 }}>{j.time}</td>
                  <td style={{ ...td, color: 'var(--text-secondary)' }}>
                    <span style={{ color: dirColor, fontWeight: 600 }}>{dirArrow}</span> {j.pattern}
                  </td>
                  <td style={{ ...td, textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>{j.score}</td>
                  <td style={{ ...td, color: 'var(--text-tertiary)', fontSize: 11 }}>{j.zone}</td>
                  <td style={{ ...td, textAlign: 'right' }}>
                    <span style={actionStyle}>{j.action}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {!hasJournal && (
        <div style={{ textAlign: 'center', color: 'var(--text-tertiary)', padding: '40px 20px' }}>
          <div style={{ fontSize: 26, marginBottom: 8 }}>▤</div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 3 }}>No interpretations yet</div>
          <div style={{ fontSize: 12 }}>Signals get journaled here the moment they're confirmed.</div>
        </div>
      )}
    </div>
  );
}
