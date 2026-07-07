import type { ChartZone } from '../types';

export interface ApiCandle {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  source: string;
  delayed: boolean;
  ema20: number | null;
  ema50: number | null;
}

export interface ApiTradeAction {
  action_type: string;
  mode: string;
  entry_price: number;
  shares?: number;
  stop_price?: number;
  target_price?: number;
}

export interface ApiTradeOutcome {
  exit_price: number;
  exit_reason: string;
  gross_pnl?: number;
  net_pnl: number;
  bars_held?: number;
}

export interface ApiJournalRow {
  id: number;
  ticker: string;
  bar_ts: string;
  timeframe: string;
  pattern_name: string;
  pattern_type: string | null;
  direction: 'long' | 'short' | null;
  confidence: number | null;
  composite_score: number | null;
  rule_reason: string | null;
  smc_zone: string | null;
  claude_rationale: string | null;
  action: ApiTradeAction | null;
  outcome: ApiTradeOutcome | null;
}

export interface ApiPosition {
  id: number;
  ticker: string;
  trade_action_id: number;
  direction: 'long' | 'short';
  entry_price: number;
  shares: number;
  stop_price: number;
  target_price: number;
  peak_price: number;
  atr_at_entry: number;
  trail_activate_pct: number;
  trail_distance_pct: number;
  max_hold_bars: number;
  bars_held: number;
  opened_at: string;
  current_price: number | null;
  unrealized_pnl: number | null;
}

export interface WsCandleUpdate {
  type: 'candle_update';
  ticker: string;
  timeframe: string;
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  source: string;
  delayed: boolean;
  ema20: number | null;
  ema50: number | null;
}

export interface WsPatternSignal {
  type: 'pattern_signal';
  ticker: string;
  pattern_name: string;
  pattern_type: string;
  direction: 'long' | 'short';
  confidence: number;
  composite_score: number;
  rule_reason: string;
  mtf_confluence: boolean;
  mtf_summary: string;
  smc_zone: string;
  claude_rationale: string | null;
  claude_model: string | null;
  price_at_signal: number;
  interpretation_id: number;
  entry_price: number;
  stop_price: number;
  target_price: number;
  rr_ratio: number | null;
  trade_action: { entry_price: number; shares: number; stop_price: number; target_price: number } | null;
  breakdown: {
    pattern_confidence: number;
    trend_alignment: number;
    volume_confirmation: number;
    mtf_confluence: number;
    zone_quality: number;
  };
}

export interface WsTradeExit {
  type: 'trade_exit';
  ticker: string;
  direction: 'long' | 'short';
  entry_price: number;
  exit_price: number;
  exit_reason: string;
  shares: number;
  gross_pnl: number;
  net_pnl: number;
  bars_held: number;
}

export type WsMessage = WsCandleUpdate | WsPatternSignal | WsTradeExit;

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
  return res.json();
}

export const api = {
  getTickers: () =>
    getJson<{ tickers: string[]; active_source: string; signal_threshold: number; sectors: Record<string, string> }>(
      '/api/tickers',
    ),
  getCandles: (ticker: string, timeframe = '1m', limit = 200) =>
    getJson<{ ticker: string; timeframe: string; candles: ApiCandle[] }>(
      `/api/candles/${encodeURIComponent(ticker)}?timeframe=${encodeURIComponent(timeframe)}&limit=${limit}`,
    ),
  getJournal: (ticker: string, limit = 50) =>
    getJson<ApiJournalRow[]>(`/api/journal?ticker=${encodeURIComponent(ticker)}&limit=${limit}`),
  // No ticker filter — every tracked ticker's history, for the global
  // Trades tab. start/end are 'YYYY-MM-DD' strings (inclusive).
  getJournalGlobal: (opts: { limit?: number; start?: string; end?: string } = {}) => {
    const params = new URLSearchParams();
    params.set('limit', String(opts.limit ?? 500));
    if (opts.start) params.set('start', opts.start);
    if (opts.end) params.set('end', opts.end);
    return getJson<ApiJournalRow[]>(`/api/journal?${params.toString()}`);
  },
  getPositions: (ticker: string) => getJson<ApiPosition[]>(`/api/positions?ticker=${encodeURIComponent(ticker)}`),
  getAllPositions: () => getJson<ApiPosition[]>('/api/positions'),
  getZones: (ticker: string) => getJson<{ ticker: string; zones: ChartZone[] }>(`/api/zones/${encodeURIComponent(ticker)}`),
  getPrevClose: (ticker: string) =>
    getJson<{ ticker: string; prev_close: number | null; prev_high: number | null; prev_low: number | null }>(
      `/api/prev-close/${encodeURIComponent(ticker)}`,
    ),
  prioritize: (ticker: string) =>
    fetch(`/api/prioritize/${encodeURIComponent(ticker)}`, { method: 'POST' }).then((res) => {
      if (!res.ok) throw new Error(`POST /api/prioritize/${ticker} -> HTTP ${res.status}`);
      return res.json() as Promise<{ ticker: string; prioritized: boolean }>;
    }),
  getAutoTrade: () => getJson<{ enabled: boolean }>('/api/auto-trade'),
  setAutoTrade: async (enabled: boolean) => {
    const res = await fetch('/api/auto-trade', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    });
    if (!res.ok) throw new Error(`POST /api/auto-trade -> HTTP ${res.status}`);
    return res.json() as Promise<{ enabled: boolean }>;
  },
  manualEntry: async (body: { ticker: string; direction: 'long' | 'short'; shares: number; stop_price?: number; target_price?: number }) => {
    const res = await fetch('/api/positions/manual-entry', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data?.detail ?? `POST /api/positions/manual-entry -> HTTP ${res.status}`);
    return data as { trade_action_id: number; entry_price: number; shares: number; stop_price: number; target_price: number };
  },
  manualExit: async (ticker: string) => {
    const res = await fetch(`/api/positions/${encodeURIComponent(ticker)}/exit`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data?.detail ?? `POST /api/positions/${ticker}/exit -> HTTP ${res.status}`);
    return data;
  },
  updatePosition: async (ticker: string, body: { stop_price?: number; target_price?: number; shares?: number }) => {
    const res = await fetch(`/api/positions/${encodeURIComponent(ticker)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data?.detail ?? `PATCH /api/positions/${ticker} -> HTTP ${res.status}`);
    return data as { ticker: string; stop_price: number; target_price: number; shares: number };
  },
};

export function connectCandleSocket(ticker: string, onMessage: (msg: WsMessage) => void): () => void {
  let ws: WebSocket | null = null;
  let closedByUs = false;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;

  const open = () => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${window.location.host}/ws/candles/${encodeURIComponent(ticker)}`);
    ws.onmessage = (event) => {
      try {
        onMessage(JSON.parse(event.data));
      } catch {
        // ignore malformed frames
      }
    };
    ws.onclose = () => {
      if (!closedByUs) retryTimer = setTimeout(open, 2000);
    };
    ws.onerror = () => ws?.close();
  };
  open();

  return () => {
    closedByUs = true;
    if (retryTimer) clearTimeout(retryTimer);
    ws?.close();
  };
}
