export type Phase = 'watching' | 'active' | 'closed';
export type Tab = 'copilot' | 'history' | 'journal';
export type Direction = 'long' | 'short';
export type ExitReason = 'target' | 'stop' | 'time';

export interface Candle {
  o: number;
  c: number;
  h: number;
  l: number;
  // Only populated on the live path (LiveChart.tsx) — the static demo
  // (App.tsx/candles.ts) doesn't need a real time axis or volume.
  time?: number; // unix seconds — required by lightweight-charts for the time axis
  v?: number;
  // Trend overlay — same EMA20/50 the composite score's trend_alignment
  // term already uses server-side; undefined until enough bars exist.
  ema20?: number;
  ema50?: number;
}

export interface ChartZone {
  type: 'order_block' | 'fvg';
  direction: Direction;
  low: number;
  high: number;
}

export interface TeachNote {
  term: string;
  body: string;
}

export interface Message {
  id: number;
  isSystem?: boolean;
  isUser?: boolean;
  isAI?: boolean;
  text: string;
  isNarration?: boolean;
  showTeach?: boolean;
  teachTerm?: string;
  teachBody?: string;
  teach?: TeachNote | null;
}

export interface JournalEntry {
  time: string;
  timeframe: string;
  pattern: string;
  dir: Direction;
  score: number;
  zone: string;
  action: 'watch' | 'entry' | 'exit';
}

export interface Trade {
  id: number;
  ticker: string;
  dir: Direction;
  pattern: string;
  time: string;
  ts: string; // ISO bar_ts — the display-formatted `time` above isn't usable for chart marker positioning
  entry: number;
  exit: number;
  stop: number;
  target: number;
  shares: number;
  barsHeld: number;
  exitReason: ExitReason;
  score: number;
  zone: string;
  netPnl: number;
  rationale: string;
}
