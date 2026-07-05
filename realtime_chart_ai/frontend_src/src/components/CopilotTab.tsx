import type { RefObject } from 'react';
import type { Message } from '../types';

const CHIPS = ['Why is this a long?', "What's an order block?", 'Explain the score', "Where's my stop?", 'Is this real money?'];

const chipStyle = {
  flex: 'none' as const,
  whiteSpace: 'nowrap' as const,
  background: 'var(--bg-tertiary)',
  border: '1px solid var(--border)',
  borderRadius: 999,
  padding: '6px 12px',
  fontSize: 12,
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  fontFamily: 'var(--font-sans)',
};

export function CopilotTab({
  messages,
  typing,
  draft,
  setDraft,
  feedRef,
  ask,
  send,
}: {
  messages: Message[];
  typing: boolean;
  draft: string;
  setDraft: (v: string) => void;
  feedRef: RefObject<HTMLDivElement | null>;
  ask: (q: string) => void;
  send: () => void;
}) {
  return (
    <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column' }}>
      <div ref={feedRef} style={{ flex: 1, overflowY: 'auto', padding: '15px 16px', display: 'flex', flexDirection: 'column', gap: 11 }}>
        {messages.map((m) => (
          <div key={m.id}>
            {m.isSystem && (
              <div
                style={{
                  alignSelf: 'center', fontSize: 11, color: 'var(--text-tertiary)', background: 'var(--bg-primary)',
                  border: '1px solid var(--border)', borderRadius: 999, padding: '4px 12px', fontFamily: 'var(--font-mono)',
                  animation: 'rcaiIn .25s ease-out', margin: '0 auto', width: 'fit-content',
                }}
              >
                {m.text}
              </div>
            )}
            {m.isUser && (
              <div
                style={{
                  alignSelf: 'flex-end', maxWidth: '82%', marginLeft: 'auto', background: 'var(--accent)', color: '#fff',
                  borderRadius: '13px 13px 3px 13px', padding: '9px 13px', fontSize: 13, lineHeight: 1.5, animation: 'rcaiIn .25s ease-out',
                }}
              >
                {m.text}
              </div>
            )}
            {m.isAI && (
              <div style={{ alignSelf: 'flex-start', maxWidth: '92%', animation: 'rcaiIn .25s ease-out' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
                  <span
                    style={{
                      width: 18, height: 18, borderRadius: 5, background: 'var(--accent-dim)', color: 'var(--accent)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11,
                    }}
                  >
                    ✦
                  </span>
                  <span style={{ fontSize: 10.5, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--text-tertiary)' }}>
                    Copilot
                  </span>
                  {m.isNarration && (
                    <span
                      style={{
                        fontSize: 9.5, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--profit)',
                        background: 'var(--profit-dim)', borderRadius: 4, padding: '1px 6px',
                      }}
                    >
                      live read
                    </span>
                  )}
                </div>
                <div
                  style={{
                    background: 'var(--bg-tertiary)', border: '1px solid var(--border)', borderRadius: '3px 13px 13px 13px',
                    padding: '11px 13px', fontSize: 13, lineHeight: 1.58, color: 'var(--text-primary)',
                  }}
                >
                  {m.text}
                </div>
                {m.showTeach && (
                  <div
                    style={{
                      marginTop: 7, background: 'var(--warning-dim)', borderLeft: '2px solid var(--warning)',
                      borderRadius: '0 8px 8px 0', padding: '9px 12px',
                    }}
                  >
                    <div style={{ fontSize: 10, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--warning)', fontWeight: 600, marginBottom: 3 }}>
                      🎓 {m.teachTerm}
                    </div>
                    <div style={{ fontSize: 12, lineHeight: 1.5, color: 'var(--text-secondary)' }}>{m.teachBody}</div>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
        {typing && (
          <div
            style={{
              alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: 4, background: 'var(--bg-tertiary)',
              border: '1px solid var(--border)', borderRadius: '3px 13px 13px 13px', padding: '11px 14px', width: 'fit-content',
            }}
          >
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--text-tertiary)', animation: 'rcaiDots 1.2s infinite' }} />
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--text-tertiary)', animation: 'rcaiDots 1.2s .2s infinite' }} />
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--text-tertiary)', animation: 'rcaiDots 1.2s .4s infinite' }} />
          </div>
        )}
      </div>

      <div style={{ flex: 'none', padding: '0 16px 14px', background: 'var(--bg-secondary)' }}>
        <div style={{ display: 'flex', gap: 7, overflowX: 'auto', padding: '11px 0 12px' }}>
          {CHIPS.map((c) => (
            <button key={c} onClick={() => ask(c)} style={chipStyle}>
              {c}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                send();
              }
            }}
            placeholder="Ask about this chart…"
            style={{
              flex: 1, background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 9,
              padding: '10px 13px', color: 'var(--text-primary)', fontFamily: 'var(--font-sans)', fontSize: 13, outline: 'none',
            }}
          />
          <button
            onClick={send}
            aria-label="Send"
            style={{
              flex: 'none', width: 38, height: 38, borderRadius: 9, background: 'var(--accent)', border: 'none',
              color: '#fff', fontSize: 15, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          >
            ➤
          </button>
        </div>
      </div>
    </div>
  );
}
