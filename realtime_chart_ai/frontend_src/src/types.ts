export type Phase = 'watching' | 'active' | 'closed';
export type Tab = 'copilot' | 'history' | 'journal';
export type Direction = 'long' | 'short';
export type ExitReason = 'target' | 'stop' | 'time';

export interface Candle {
  o: number;
  c: number;
  h: number;
  l: number;
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
