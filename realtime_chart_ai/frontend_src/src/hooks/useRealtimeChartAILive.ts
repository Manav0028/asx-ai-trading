import { useCallback, useEffect, useRef, useState } from 'react';
import type { Candle, Direction, JournalEntry, Message, Phase, Tab, Trade } from '../types';
import { answerQuestion } from '../lib/copilot';
import { api, connectCandleSocket, type ApiCandle, type WsMessage, type ApiJournalRow } from '../lib/liveApi';

interface LiveSignal {
  patternName: string;
  direction: Direction;
  entry: number;
  stop: number;
  target: number;
  rr: number | null;
}

// Backend timeframe keys are lowercase ('1d'); the header's timeframe pills
// use '1D' for display — normalize once at the boundary rather than
// threading two spellings through the rest of the hook.
const toBackendTf = (t: string) => (t === '1D' ? '1d' : t);

function apiCandleToCandle(c: ApiCandle): Candle {
  return { time: Math.floor(new Date(c.ts).getTime() / 1000), o: c.open, c: c.close, h: c.high, l: c.low, v: c.volume };
}

function journalRowToEntry(row: ApiJournalRow): JournalEntry {
  const time = new Date(row.bar_ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const action: JournalEntry['action'] = row.action
    ? row.action.action_type === 'entry'
      ? 'entry'
      : 'exit'
    : 'watch';
  return {
    time, pattern: row.pattern_name, dir: (row.direction ?? 'long') as Direction,
    score: Math.round(row.composite_score ?? 0), zone: row.smc_zone ?? 'equilibrium', action,
  };
}

function journalRowToTrade(row: ApiJournalRow): Trade | null {
  if (!row.action || !row.outcome) return null;
  const exitReason = row.outcome.exit_reason === 'target' ? 'target' : row.outcome.exit_reason === 'stop_loss' ? 'stop' : 'time';
  return {
    id: row.id, ticker: row.ticker, dir: (row.direction ?? 'long') as Direction, pattern: row.pattern_name,
    time: new Date(row.bar_ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    entry: row.action.entry_price, exit: row.outcome.exit_price,
    stop: row.action.stop_price ?? row.outcome.exit_price, target: row.action.target_price ?? row.outcome.exit_price,
    shares: row.action.shares ?? 0, barsHeld: row.outcome.bars_held ?? 0, exitReason,
    score: Math.round(row.composite_score ?? 0), zone: row.smc_zone ?? 'equilibrium',
    netPnl: row.outcome.net_pnl, rationale: row.claude_rationale ?? row.rule_reason ?? '',
  };
}

export function useRealtimeChartAILive(beginnerMode: boolean) {
  const [ticker, setTicker] = useState<string>('');
  const [availableTickers, setAvailableTickers] = useState<string[]>([]);
  const [sectors, setSectors] = useState<Record<string, string>>({});
  const [heldTickers, setHeldTickers] = useState<Set<string>>(new Set());
  const [activeSource, setActiveSource] = useState<string>('connecting');
  const activeSourceRef = useRef('connecting');
  useEffect(() => { activeSourceRef.current = activeSource; }, [activeSource]);
  const thresholdRef = useRef(65);
  const [tf, setTf] = useState('1m');
  const tfRef = useRef('1m');
  useEffect(() => { tfRef.current = tf; }, [tf]);
  const [tab, setTab] = useState<Tab>('copilot');
  const [beginner, setBeginner] = useState(beginnerMode);
  const [autoTrade, setAutoTradeState] = useState(false);
  const [phase, setPhase] = useState<Phase>('watching');
  const [chartStatus, setChartStatus] = useState<Phase>('watching');
  const [dispScore, setDispScore] = useState(0);
  const [bd, setBd] = useState([0, 0, 0, 0, 0]);
  const [price, setPrice] = useState(0);
  const [pnl, setPnl] = useState(0);
  const [signal, setSignal] = useState<LiveSignal | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [journal, setJournal] = useState<JournalEntry[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [expandedTrade, setExpandedTrade] = useState<number | null>(null);
  const [draft, setDraft] = useState('');
  const [typing, setTyping] = useState(false);
  const [posMeta, setPosMeta] = useState('');
  const [posShares, setPosShares] = useState(0);
  // Whether THIS ticker actually has an open (simulated) position right
  // now — independent of the global auto-trade toggle. A position opened
  // while auto-trade was on keeps running after the toggle is flipped off
  // (the toggle only gates new entries), so "is a position open" and "is
  // auto-trade currently on" are different facts and must not be conflated.
  const [hasOpenPosition, setHasOpenPosition] = useState(false);

  const feedRef = useRef<HTMLDivElement | null>(null);
  const midRef = useRef(0);
  const beginnerRef = useRef(beginner);
  useEffect(() => { beginnerRef.current = beginner; }, [beginner]);

  const [candles, setCandles] = useState<Candle[]>([]);
  const openPositionRef = useRef<{ direction: Direction; entry: number; shares: number } | null>(null);
  const priceRef = useRef(0);
  useEffect(() => { priceRef.current = price; }, [price]);

  const append = useCallback((msg: Omit<Message, 'id'>) => {
    const id = midRef.current++;
    setMessages((s) => [...s, { ...msg, id }]);
    setTimeout(() => { if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight; }, 30);
  }, []);
  const pushSystem = useCallback((text: string) => append({ isSystem: true, text }), [append]);
  const pushAI = useCallback((text: string, narration: boolean) => {
    append({ isAI: true, text, isNarration: narration, showTeach: false });
  }, [append]);

  const refreshJournal = useCallback(async (tk: string) => {
    try {
      const rows = await api.getJournal(tk, 50);
      setJournal(rows.map(journalRowToEntry));
      setTrades(rows.map(journalRowToTrade).filter((t): t is Trade => t !== null));
    } catch {
      // journal endpoint transiently unavailable — keep showing the last known state
    }
  }, []);

  const refreshPositions = useCallback(async (tk: string) => {
    try {
      const positions = await api.getPositions(tk);
      const pos = positions[0];
      if (pos) {
        openPositionRef.current = { direction: pos.direction, entry: pos.entry_price, shares: pos.shares };
        setHasOpenPosition(true);
        setPhase('active');
        setChartStatus('active');
        setSignal((s) => s ?? { patternName: '', direction: pos.direction, entry: pos.entry_price, stop: pos.stop_price, target: pos.target_price, rr: null });
        setPosMeta(`${pos.shares.toFixed(0)} sh · $${(pos.shares * pos.entry_price).toLocaleString(undefined, { maximumFractionDigits: 0 })}`);
        setPosShares(pos.shares);
        // P&L used to only recompute inside the WS candle_update handler —
        // i.e. only when a brand-new live bar arrives for THIS ticker. With
        // the ASX200 round-robin scanner, that can be minutes away, so it
        // sat frozen at its initial 0 the whole time a position was open
        // (reported as a stuck "+$0.00"). Recomputing here too means it
        // refreshes at least every 5s (this function's poll interval)
        // against whatever price is currently known, not just on live ticks.
        if (priceRef.current) {
          const diff = pos.direction === 'long' ? priceRef.current - pos.entry_price : pos.entry_price - priceRef.current;
          setPnl(diff * pos.shares);
        }
      } else {
        openPositionRef.current = null;
        setHasOpenPosition(false);
        setPnl(0);
        setPosShares(0);
      }
    } catch {
      // positions endpoint transiently unavailable
    }
  }, []);

  const toggleBeginner = useCallback(() => {
    setBeginner((prev) => {
      const b = !prev;
      setMessages((ms) => ms.map((m) => (m.isAI && m.teach ? { ...m, showTeach: b } : m)));
      return b;
    });
  }, []);

  const toggleAutoTrade = useCallback(() => {
    setAutoTradeState((prev) => {
      const next = !prev;
      api.setAutoTrade(next).then((r) => setAutoTradeState(r.enabled)).catch(() => setAutoTradeState(prev));
      return next;
    });
  }, []);

  const answer = useCallback((q: string) => answerQuestion(q, 38), []);
  const ask = useCallback((q: string) => {
    append({ isUser: true, text: q });
    setTyping(true);
    setTimeout(() => {
      const a = answer(q);
      setTyping(false);
      append({ isAI: true, text: a.text, showTeach: !!(a.teach && beginnerRef.current), teachTerm: a.teach?.term ?? '', teachBody: a.teach?.body ?? '', teach: a.teach });
    }, 650);
  }, [answer, append]);
  const send = useCallback(() => {
    const t = draft.trim();
    if (!t) return;
    setDraft('');
    ask(t);
  }, [draft, ask]);

  // Chart rendering (scroll/zoom/crosshair/price-lines) is now handled
  // internally by LiveChart.tsx (lightweight-charts) — it re-renders off the
  // `candles` prop like any other React data, no manual canvas/RAF loop
  // needed here anymore.

  // One-time: discover the tracked watchlist and pick a starting ticker.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const { tickers, active_source, signal_threshold, sectors } = await api.getTickers();
      if (cancelled) return;
      thresholdRef.current = signal_threshold ?? 65;
      setAvailableTickers(tickers);
      setSectors(sectors ?? {});
      setActiveSource(active_source);
      setTicker((cur) => cur || tickers[0] || 'BHP.AX');
    })();
    return () => { cancelled = true; };
  }, []);

  // Which tickers currently have an open (simulated) position, for the
  // dropdown's "held" highlight — polled independently of whichever ticker
  // is on screen, since a position on ticker A can open/close while the
  // user is looking at ticker B.
  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const positions = await api.getAllPositions();
        if (!cancelled) setHeldTickers(new Set(positions.map((p) => p.ticker)));
      } catch {
        // transiently unavailable — keep showing the last known set
      }
    };
    refresh();
    const timer = setInterval(refresh, 8000);
    return () => { cancelled = true; clearInterval(timer); };
  }, []);

  const switchTicker = useCallback((tk: string) => {
    setTicker((cur) => (cur === tk ? cur : tk));
  }, []);

  // Re-runs whenever the selected ticker changes: tears down the previous
  // ticker's WS/candles/journal/positions and reconnects for the new one.
  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    let stopSocket: (() => void) | null = null;
    let pollTimer: ReturnType<typeof setInterval> | null = null;

    setCandles([]);
    openPositionRef.current = null;
    setHasOpenPosition(false);
    setPosShares(0);
    setSignal(null);
    setPhase('watching');
    setChartStatus('watching');
    setPnl(0);
    setPrice(0);
    setMessages([]);

    function handleWsMessage(msg: WsMessage) {
      if (msg.type === 'candle_update') {
        if (msg.timeframe !== toBackendTf(tfRef.current)) return;
        const c: Candle = { time: Math.floor(new Date(msg.ts).getTime() / 1000), o: msg.open, c: msg.close, h: msg.high, l: msg.low, v: msg.volume };
        setCandles((prev) => [...prev, c].slice(-500));
        setPrice(msg.close);
        const pos = openPositionRef.current;
        if (pos) {
          const diff = pos.direction === 'long' ? msg.close - pos.entry : pos.entry - msg.close;
          setPnl(diff * pos.shares);
        }
      } else if (msg.type === 'pattern_signal') {
        // Below the system's own signal threshold, this fired pattern is
        // "observed, not actioned" — it's always in the Journal (refreshed
        // below), but doesn't take over the prominent signal card/chart
        // overlay/copilot narration, matching the "mostly does nothing,
        // patience is a position" ethos when real data fires lots of noise.
        if (msg.composite_score >= thresholdRef.current) {
          const sig: LiveSignal = {
            patternName: msg.pattern_name, direction: msg.direction,
            entry: msg.entry_price, stop: msg.stop_price, target: msg.target_price, rr: msg.rr_ratio,
          };
          setSignal(sig);
          setChartStatus('active');
          const start = performance.now();
          const targetScore = msg.composite_score;
          const targetBd = [
            msg.breakdown.pattern_confidence, msg.breakdown.trend_alignment,
            msg.breakdown.volume_confirmation, msg.breakdown.mtf_confluence, msg.breakdown.zone_quality,
          ];
          const dur = 800;
          const step = () => {
            const k = Math.min(1, (performance.now() - start) / dur);
            const e = 1 - Math.pow(1 - k, 3);
            setDispScore(Math.round(targetScore * e));
            setBd(targetBd.map((v) => Math.round(v * e)));
            if (k < 1) setTimeout(step, 40);
          };
          step();
          pushAI(msg.claude_rationale ?? msg.rule_reason, true);
          if (msg.trade_action) {
            openPositionRef.current = { direction: msg.direction, entry: msg.trade_action.entry_price, shares: msg.trade_action.shares };
            setHasOpenPosition(true);
            setPosShares(msg.trade_action.shares);
          }
          setPhase('active');
        }
        refreshJournal(ticker);
      } else if (msg.type === 'trade_exit') {
        openPositionRef.current = null;
        setHasOpenPosition(false);
        setPosShares(0);
        setPhase('closed');
        setChartStatus('closed');
        const win = msg.net_pnl >= 0;
        pushAI(
          `Position closed — ${msg.direction.toUpperCase()} exited at $${msg.exit_price.toFixed(3)} after ${msg.bars_held} bars (${msg.exit_reason.replace('_', ' ')}). Net ${win ? '+' : ''}$${msg.net_pnl.toFixed(2)}.`,
          false,
        );
        refreshJournal(ticker);
        setTimeout(() => { setPhase('watching'); setChartStatus('watching'); setSignal(null); setPnl(0); }, 6000);
      }
    }

    // Opened immediately, in parallel with the REST catch-up below, instead
    // of after — the socket doesn't depend on any of those responses, and
    // gating it behind three sequential round trips was the main source of
    // visible lag between picking a ticker and its signal panel filling in.
    stopSocket = connectCandleSocket(ticker, handleWsMessage);
    pollTimer = setInterval(() => refreshPositions(ticker), 5000);

    (async () => {
      const source = activeSourceRef.current;
      pushSystem(`Connected · ${source} · ${ticker} · 1-minute bars`);
      pushAI(`Reading ${ticker} live. Watching for a confirmed setup — nothing to do until a pattern, the trend and the higher timeframe all agree.`, false);

      const [autoTradeStatus] = await Promise.all([api.getAutoTrade(), refreshJournal(ticker), refreshPositions(ticker)]);
      if (cancelled) return;
      setAutoTradeState(autoTradeStatus.enabled);
    })();

    return () => {
      cancelled = true;
      stopSocket?.();
      if (pollTimer) clearInterval(pollTimer);
    };
  }, [ticker, refreshJournal, refreshPositions, pushSystem, pushAI]);

  // Candle history for the chart — separate from the ticker-connect effect
  // above so a timeframe switch (1m/5m/15m/1D) doesn't tear down and
  // reconnect the WebSocket, just refetches the REST history for the newly
  // selected timeframe.
  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    (async () => {
      // Forces an immediate out-of-band fetch for this ticker instead of
      // waiting for its next turn in the ASX200 round-robin scan (which can
      // otherwise be minutes away) — the background scan keeps covering
      // every other ticker unchanged. Best-effort: if this is slow/fails,
      // still fall through to the regular candle fetch below rather than
      // blocking the chart on it.
      await api.prioritize(ticker).catch(() => {});
      if (cancelled) return;
      const { candles: rows } = await api.getCandles(ticker, toBackendTf(tf), 500);
      if (cancelled) return;
      const mapped = rows.map(apiCandleToCandle);
      setCandles(mapped);
      if (mapped.length) setPrice(mapped[mapped.length - 1].c);
    })();
    return () => { cancelled = true; };
  }, [ticker, tf]);

  return {
    tf, setTf,
    beginner, autoTrade, toggleBeginner, toggleAutoTrade,
    candles, chartStatus,
    phase, dispScore, bd, price, pnl,
    tab, setTab,
    messages, typing, draft, setDraft, feedRef, ask, send,
    journal,
    trades, expandedTrade, toggleTrade: (id: number) => setExpandedTrade((cur) => (cur === id ? null : id)),
    ticker, availableTickers, switchTicker, activeSource, sectors, heldTickers,
    entry: signal?.entry ?? 0, stop: signal?.stop ?? 0, target: signal?.target ?? 0,
    rr: signal?.rr ?? null, patternName: signal?.patternName ?? '', direction: signal?.direction ?? 'long',
    posMeta, hasOpenPosition, posShares,
    refreshCurrentPosition: () => refreshPositions(ticker),
  };
}
