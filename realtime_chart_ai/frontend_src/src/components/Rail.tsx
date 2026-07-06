import type { RefObject } from 'react';
import type { Direction, JournalEntry, Message, Phase, Tab, Trade } from '../types';
import { SignalCard } from './SignalCard';
import { CopilotTab } from './CopilotTab';
import { JournalTab } from './JournalTab';
import { HistoryTab } from './HistoryTab';

const TABS: { key: Tab; label: string; icon: string; iconSize: number }[] = [
  { key: 'copilot', label: 'Copilot', icon: '✦', iconSize: 13 },
  { key: 'history', label: 'History', icon: '↺', iconSize: 12 },
  { key: 'journal', label: 'Journal', icon: '▤', iconSize: 12 },
];

export function Rail(props: {
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
  tab: Tab;
  setTab: (t: Tab) => void;
  messages: Message[];
  typing: boolean;
  draft: string;
  setDraft: (v: string) => void;
  feedRef: RefObject<HTMLDivElement | null>;
  ask: (q: string) => void;
  send: () => void;
  journal: JournalEntry[];
  trades: Trade[];
  expandedTrade: number | null;
  toggleTrade: (id: number) => void;
}) {
  const { phase, dispScore, bd, pnl, tab, setTab } = props;

  return (
    <aside
      id="rcai-rail"
      style={{
        width: 456, flex: 'none', borderLeft: '1px solid var(--border)', background: 'var(--bg-secondary)',
        display: 'flex', flexDirection: 'column', minHeight: 0, overflowY: 'auto',
      }}
    >
      <SignalCard
        phase={phase} dispScore={dispScore} bd={bd} pnl={pnl}
        patternName={props.patternName} direction={props.direction}
        entry={props.entry} stop={props.stop} target={props.target} rr={props.rr} posMeta={props.posMeta}
        hasOpenPosition={props.hasOpenPosition}
      />

      <div style={{ flex: 'none', display: 'flex', borderBottom: '1px solid var(--border)' }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              flex: 1, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 7, padding: 12,
              background: 'none', border: 'none', borderBottom: '2px solid ' + (tab === t.key ? 'var(--accent)' : 'transparent'),
              color: tab === t.key ? 'var(--text-primary)' : 'var(--text-tertiary)', fontFamily: 'var(--font-sans)',
              fontSize: 13, fontWeight: 500, cursor: 'pointer',
            }}
          >
            <span style={{ fontSize: t.iconSize }}>{t.icon}</span> {t.label}
          </button>
        ))}
      </div>

      <div id="rcai-tabcontent" style={{ flex: 1, minHeight: 380, position: 'relative' }}>
        {tab === 'copilot' && (
          <CopilotTab
            messages={props.messages}
            typing={props.typing}
            draft={props.draft}
            setDraft={props.setDraft}
            feedRef={props.feedRef}
            ask={props.ask}
            send={props.send}
          />
        )}
        {tab === 'journal' && <JournalTab journal={props.journal} />}
        {tab === 'history' && (
          <HistoryTab trades={props.trades} expandedTrade={props.expandedTrade} toggleTrade={props.toggleTrade} />
        )}
      </div>
    </aside>
  );
}
