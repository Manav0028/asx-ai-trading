import { useCallback, useEffect, useRef, useState } from 'react';
import type { Candle, Direction, JournalEntry, Message, Phase, Tab, Trade } from '../types';
import { ema } from '../lib/candles';
import { answerQuestion } from '../lib/copilot';
import { api, connectCandleSocket, type ApiJournalRow, type WsMessage } from '../lib/liveApi';

interface LiveSignal {
  patternName: string;
  direction: Direction;
  entry: number;
  stop: number;
  target: number;
  rr: number | null;
}

function rr(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
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
  const [ticker, setTicker] = useState<string>('BHP.AX');
  const [activeSource, setActiveSource] = useState<string>('connecting');
  const [tf, setTf] = useState('1m');
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

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const feedRef = useRef<HTMLDivElement | null>(null);
  const midRef = useRef(0);
  const beginnerRef = useRef(beginner);
  useEffect(() => { beginnerRef.current = beginner; }, [beginner]);

  const candlesRef = useRef<Candle[]>([]);
  const openPositionRef = useRef<{ direction: Direction; entry: number; shares: number } | null>(null);
  const signalRef = useRef<LiveSignal | null>(null);
  useEffect(() => { signalRef.current = signal; }, [signal]);

  const ctxRef = useRef<CanvasRenderingContext2D | null>(null);
  const sizeRef = useRef({ w: 0, h: 0 });

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
        setPhase('active');
        setChartStatus('active');
        setSignal((s) => s ?? { patternName: '', direction: pos.direction, entry: pos.entry_price, stop: pos.stop_price, target: pos.target_price, rr: null });
        setPosMeta(`${pos.shares.toFixed(0)} sh · $${(pos.shares * pos.entry_price).toLocaleString(undefined, { maximumFractionDigits: 0 })}`);
      } else {
        openPositionRef.current = null;
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

  const draw = useCallback(() => {
    const ctx = ctxRef.current;
    const { w: W, h: H } = sizeRef.current;
    const candles = candlesRef.current;
    if (!ctx || !W || candles.length < 2) return;
    const sig = signalRef.current;

    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = '#0f0f12';
    ctx.fillRect(0, 0, W, H);

    const VIS = 62;
    const vis = candles.slice(-VIS);
    const emaAll = ema(candles, 20);
    const emaVis = emaAll.slice(-VIS);
    const padL = 8, padR = 66, padT = 14, padB = 22;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    let pmin = Infinity, pmax = -Infinity;
    vis.forEach((c) => { pmin = Math.min(pmin, c.l); pmax = Math.max(pmax, c.h); });
    if (sig) { pmin = Math.min(pmin, sig.stop); pmax = Math.max(pmax, sig.target); }
    const pad = (pmax - pmin) * 0.1 || 0.1;
    pmin -= pad; pmax += pad;
    const slot = plotW / VIS;
    const bodyW = Math.min(slot * 0.62, 9);
    const X = (i: number) => padL + i * slot + slot / 2;
    const Y = (p: number) => padT + ((pmax - p) / (pmax - pmin)) * plotH;

    ctx.font = '10px "JetBrains Mono", monospace';
    ctx.textBaseline = 'middle';
    for (let g = 0; g <= 4; g++) {
      const yy = padT + g * (plotH / 4);
      const pv = pmax - (g * (pmax - pmin)) / 4;
      ctx.strokeStyle = '#1a1a1e'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(padL, yy); ctx.lineTo(padL + plotW, yy); ctx.stroke();
      ctx.fillStyle = '#78787e'; ctx.textAlign = 'left';
      ctx.fillText(pv.toFixed(2), padL + plotW + 6, yy);
    }

    ctx.strokeStyle = 'rgba(105,147,255,0.55)'; ctx.lineWidth = 1.3; ctx.beginPath();
    emaVis.forEach((e, i) => { const x = X(i), y = Y(e); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
    ctx.stroke();

    vis.forEach((c, i) => {
      const up = c.c >= c.o;
      const col = up ? '#00c48c' : '#ff5a5a';
      const x = X(i);
      ctx.strokeStyle = col; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x, Y(c.h)); ctx.lineTo(x, Y(c.l)); ctx.stroke();
      const yo = Y(c.o), yc = Y(c.c);
      ctx.fillStyle = col;
      ctx.fillRect(x - bodyW / 2, Math.min(yo, yc), bodyW, Math.max(1.5, Math.abs(yc - yo)));
    });

    if (sig) {
      const drawLine = (pr: number, color: string, label: string) => {
        const y = Y(pr);
        ctx.strokeStyle = color; ctx.setLineDash([5, 4]); ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(padL + plotW, y); ctx.stroke();
        ctx.setLineDash([]);
        ctx.font = '9px "JetBrains Mono", monospace';
        const txt = label; const w = ctx.measureText(txt).width + 12;
        ctx.fillStyle = color; ctx.beginPath();
        rr(ctx, padL + plotW - w, y - 8, w, 16, 4); ctx.fill();
        ctx.fillStyle = '#0b0b0d'; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
        ctx.fillText(txt, padL + plotW - w + 6, y);
      };
      drawLine(sig.target, '#00c48c', (sig.direction === 'long' ? '▲ ' : '▼ ') + sig.target.toFixed(2));
      drawLine(sig.entry, '#6993ff', '• ' + sig.entry.toFixed(2));
      drawLine(sig.stop, '#ff5a5a', (sig.direction === 'long' ? '▼ ' : '▲ ') + sig.stop.toFixed(2));
    }

    const live = candles[candles.length - 1].c;
    const ly = Y(live);
    ctx.fillStyle = '#6993ff'; ctx.font = '10px "JetBrains Mono", monospace';
    const lt = live.toFixed(2); const lw = ctx.measureText(lt).width + 12;
    rr(ctx, padL + plotW - lw, ly - 8, lw, 16, 4); ctx.fill();
    ctx.fillStyle = '#fff'; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    ctx.fillText(lt, padL + plotW - lw + 6, ly);
    ctx.strokeStyle = 'rgba(105,147,255,0.4)'; ctx.setLineDash([2, 3]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(padL, ly); ctx.lineTo(padL + plotW - lw, ly); ctx.stroke(); ctx.setLineDash([]);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let raf = 0;
    let ro: ResizeObserver | null = null;
    let stopSocket: (() => void) | null = null;
    let pollTimer: ReturnType<typeof setInterval> | null = null;

    const loop = () => { draw(); raf = requestAnimationFrame(loop); };
    raf = requestAnimationFrame(loop);

    const canvas = canvasRef.current;
    if (canvas) {
      ctxRef.current = canvas.getContext('2d');
      const resize = () => {
        const wrap = canvas.parentElement; if (!wrap) return;
        const w = wrap.clientWidth, h = wrap.clientHeight;
        const dpr = window.devicePixelRatio || 1;
        canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
        ctxRef.current?.setTransform(dpr, 0, 0, dpr, 0, 0);
        sizeRef.current = { w, h };
      };
      resize();
      ro = new ResizeObserver(resize);
      ro.observe(canvas.parentElement!);
    }

    (async () => {
      const { tickers, active_source, signal_threshold } = await api.getTickers();
      if (cancelled) return;
      const threshold = signal_threshold ?? 65;
      const tk = tickers[0] ?? 'BHP.AX';
      setTicker(tk);
      setActiveSource(active_source);
      pushSystem(`Connected · ${active_source} · ${tk} · 1-minute bars`);
      pushAI(`Reading ${tk} live. Watching for a confirmed setup — nothing to do until a pattern, the trend and the higher timeframe all agree.`, false);

      const [{ candles }, autoTradeStatus] = await Promise.all([api.getCandles(tk, 200), api.getAutoTrade()]);
      if (cancelled) return;
      candlesRef.current = candles.map((c) => ({ o: c.open, c: c.close, h: c.high, l: c.low }));
      if (candles.length) setPrice(candles[candles.length - 1].close);
      setAutoTradeState(autoTradeStatus.enabled);
      await refreshJournal(tk);
      await refreshPositions(tk);

      stopSocket = connectCandleSocket(tk, (msg: WsMessage) => {
        if (msg.type === 'candle_update') {
          if (msg.timeframe !== '1m') return;
          const c: Candle = { o: msg.open, c: msg.close, h: msg.high, l: msg.low };
          candlesRef.current = [...candlesRef.current, c].slice(-260);
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
          if (msg.composite_score >= threshold) {
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
            }
            setPhase('active');
          }
          refreshJournal(tk);
        } else if (msg.type === 'trade_exit') {
          openPositionRef.current = null;
          setPhase('closed');
          setChartStatus('closed');
          const win = msg.net_pnl >= 0;
          pushAI(
            `Position closed — ${msg.direction.toUpperCase()} exited at $${msg.exit_price.toFixed(3)} after ${msg.bars_held} bars (${msg.exit_reason.replace('_', ' ')}). Net ${win ? '+' : ''}$${msg.net_pnl.toFixed(2)}.`,
            false,
          );
          refreshJournal(tk);
          setTimeout(() => { setPhase('watching'); setChartStatus('watching'); setSignal(null); setPnl(0); }, 6000);
        }
      });

      pollTimer = setInterval(() => refreshPositions(tk), 5000);
    })();

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      ro?.disconnect();
      stopSocket?.();
      if (pollTimer) clearInterval(pollTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    tf, setTf,
    beginner, autoTrade, toggleBeginner, toggleAutoTrade,
    canvasRef, chartStatus,
    phase, dispScore, bd, price, pnl,
    tab, setTab,
    messages, typing, draft, setDraft, feedRef, ask, send,
    journal,
    trades, expandedTrade, toggleTrade: (id: number) => setExpandedTrade((cur) => (cur === id ? null : id)),
    ticker, activeSource,
    entry: signal?.entry ?? 0, stop: signal?.stop ?? 0, target: signal?.target ?? 0,
    rr: signal?.rr ?? null, patternName: signal?.patternName ?? '', direction: signal?.direction ?? 'long',
    posMeta,
  };
}
