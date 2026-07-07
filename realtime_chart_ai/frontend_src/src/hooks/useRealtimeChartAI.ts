import { useCallback, useEffect, useRef, useState } from 'react';
import type { Candle, Direction, JournalEntry, Message, Phase, Tab, Trade } from '../types';
import { buildCandles, ema } from '../lib/candles';
import { answerQuestion } from '../lib/copilot';

export const ENTRY = 42.08;
export const STOP = 41.88;
export const TARGET = 42.48;
export const SHARES = 190;
export const NOTIONAL = 8000;
export const RISK = 38;
export const BD_TARGET = [72, 68, 62, 100, 100];
export const SCORE_TARGET = 78;

const SEED_TRADES: Trade[] = [
  { id: 1, ticker: 'BHP', dir: 'long', pattern: 'Order-block retest', time: 'Today 11:42', ts: new Date().toISOString(), entry: 41.62, exit: 42.03, stop: 41.44, target: 42.03, shares: 240, barsHeld: 34, exitReason: 'target', score: 76, zone: 'discount', netPnl: 78.45, rationale: 'Bought the demand zone with the 5-minute trend up. Buyers defended the block and price ran clean to target. Profit locked in.' },
  { id: 2, ticker: 'CSL', dir: 'short', pattern: 'Shooting star', time: 'Today 10:18', ts: new Date().toISOString(), entry: 248.1, exit: 249.95, stop: 249.95, target: 243.8, shares: 12, barsHeld: 12, exitReason: 'stop', score: 71, zone: 'premium', netPnl: -41.9, rationale: 'Shorted a shooting star into the highs, but price reclaimed the level and stopped it out. A small, planned loss — small losses protect capital.' },
  { id: 3, ticker: 'WBC', dir: 'long', pattern: 'Hammer bounce', time: 'Yesterday 14:55', ts: new Date(Date.now() - 86400000).toISOString(), entry: 33.18, exit: 33.35, stop: 33.02, target: 33.6, shares: 110, barsHeld: 60, exitReason: 'time', score: 68, zone: 'equilibrium', netPnl: 18.6, rationale: 'Hammer at the lows bounced but lost momentum before target. Closed at max hold to free up capital rather than let it drift.' },
];

interface Sim {
  candles: Candle[];
  forming: Candle | null;
  obIndex: number;
  obTop: number;
  obBottom: number;
  live: number;
  drift: number;
  lerp: number;
  t: number;
  signal: { fireIndex: number } | null;
  fireBar: number;
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

export function useRealtimeChartAI(beginnerMode: boolean, autoTradeDefault: boolean) {
  const [phase, setPhase] = useState<Phase>('watching');
  const [tf, setTf] = useState('1m');
  const [tab, setTab] = useState<Tab>('copilot');
  const [beginner, setBeginner] = useState(beginnerMode);
  const [autoTrade, setAutoTrade] = useState(autoTradeDefault);
  const [dispScore, setDispScore] = useState(0);
  const [bd, setBd] = useState([0, 0, 0, 0, 0]);
  const [price, setPrice] = useState(ENTRY);
  const [pnl, setPnl] = useState(0);
  const [messages, setMessages] = useState<Message[]>([]);
  const [journal, setJournal] = useState<JournalEntry[]>([]);
  const [trades, setTrades] = useState<Trade[]>(SEED_TRADES);
  const [expandedTrade, setExpandedTrade] = useState<number | null>(1);
  const [draft, setDraft] = useState('');
  const [typing, setTyping] = useState(false);
  const [chartStatus, setChartStatus] = useState<Phase>('watching');

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const feedRef = useRef<HTMLDivElement | null>(null);

  const autoTradeRef = useRef(autoTrade);
  const beginnerRef = useRef(beginner);
  const phaseRef = useRef(phase);
  useEffect(() => { autoTradeRef.current = autoTrade; }, [autoTrade]);
  useEffect(() => { beginnerRef.current = beginner; }, [beginner]);
  useEffect(() => { phaseRef.current = phase; }, [phase]);

  const midRef = useRef(0);
  const simRef = useRef<Sim | null>(null);
  const ctxRef = useRef<CanvasRenderingContext2D | null>(null);
  const sizeRef = useRef({ w: 0, h: 0 });

  const append = useCallback((msg: Omit<Message, 'id'>) => {
    const id = midRef.current++;
    setMessages((s) => [...s, { ...msg, id }]);
    setTimeout(() => {
      if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }, 30);
  }, []);

  const pushSystem = useCallback((text: string) => append({ isSystem: true, text }), [append]);
  const pushUser = useCallback((text: string) => append({ isUser: true, text }), [append]);
  const pushAI = useCallback((text: string, teach: Message['teach'], narration: boolean) => {
    append({
      isAI: true,
      text,
      isNarration: !!narration,
      showTeach: !!(teach && beginnerRef.current),
      teachTerm: teach ? teach.term : '',
      teachBody: teach ? teach.body : '',
      teach: teach || null,
    });
  }, [append]);

  const addJournal = useCallback((pattern: string, dir: Direction, score: number, zone: string, action: JournalEntry['action']) => {
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    setJournal((s) => [{ pattern, dir, score, zone, action, time, timeframe: '1m' }, ...s]);
  }, []);

  const toggleTrade = useCallback((id: number) => {
    setExpandedTrade((cur) => (cur === id ? null : id));
  }, []);

  const toggleBeginner = useCallback(() => {
    setBeginner((prev) => {
      const b = !prev;
      setMessages((ms) => ms.map((m) => (m.isAI && m.teach ? { ...m, showTeach: b } : m)));
      return b;
    });
  }, []);

  const toggleAutoTrade = useCallback(() => setAutoTrade((p) => !p), []);

  const closeAtTarget = useCallback(() => {
    if (phaseRef.current === 'closed') return;
    phaseRef.current = 'closed';
    setPhase('closed');
    setChartStatus('closed');
    const sim = simRef.current!;
    sim.drift = TARGET;
    const net = (TARGET - ENTRY) * SHARES - 9.95 * 2;
    const bars = Math.max(1, sim.candles.length - (sim.fireBar || sim.candles.length));
    if (autoTradeRef.current) {
      pushAI(
        `Target reached — the position closed at $42.48 for +$${net.toFixed(2)} net after costs. That's the 2-to-1 payoff doing its job: risk a little, aim for double. Profit locked in — scanning for the next one.`,
        null,
        false,
      );
      addJournal('Target reached', 'long', 78, 'discount', 'exit');
      setTrades((prev) => [
        {
          id: Date.now(),
          ticker: 'BHP',
          dir: 'long',
          pattern: 'Order-block retest',
          time: 'Just now',
          ts: new Date().toISOString(),
          entry: ENTRY,
          exit: TARGET,
          stop: STOP,
          target: TARGET,
          shares: SHARES,
          barsHeld: bars,
          exitReason: 'target',
          score: 78,
          zone: 'discount',
          netPnl: net,
          rationale: 'Tapped a bullish order block with the higher timeframe in agreement, then ran to target as buyers held the zone. Textbook — profit locked in.',
        },
        ...prev,
      ]);
    } else {
      pushAI(
        'Price just hit the $42.48 target. Auto-trade was off, so nothing was taken — but that’s exactly how the setup was meant to play out. Flip auto-trade on to let the system act on the next one.',
        null,
        false,
      );
    }
  }, [addJournal, pushAI]);

  const fire = useCallback(() => {
    const sim = simRef.current!;
    sim.signal = { fireIndex: sim.candles.length - 1 };
    sim.drift = TARGET;
    sim.lerp = 0.028;
    sim.fireBar = sim.candles.length;
    setPhase('active');
    phaseRef.current = 'active';
    setChartStatus('active');
    pushAI(
      "Setup confirmed — BHP tapped a bullish order block and held. Three things line up: price is sitting in a demand zone, the 5-minute trend is up, and volume ticked up on the bounce. When the higher timeframe agrees with what I see on the 1-minute, the odds improve — so this reads LONG. Entry $42.08, stop $41.88, target $42.48.",
      { term: 'Order block', body: 'The last down-candle before a strong push up. Big players often leave unfilled buy orders there, so price tends to bounce when it returns to that zone.' },
      true,
    );
    addJournal('Bullish OB retest', 'long', 78, 'discount', autoTradeRef.current ? 'entry' : 'watch');
    const start = performance.now();
    const dur = 1000;
    const step = () => {
      const k = Math.min(1, (performance.now() - start) / dur);
      const e = 1 - Math.pow(1 - k, 3);
      setDispScore(Math.round(SCORE_TARGET * e));
      setBd(BD_TARGET.map((v) => Math.round(v * e)));
      if (k < 1) setTimeout(step, 40);
    };
    step();
  }, [addJournal, pushAI]);

  const answer = useCallback((q: string) => answerQuestion(q, RISK), []);

  const ask = useCallback((q: string) => {
    pushUser(q);
    setTyping(true);
    setTimeout(() => {
      const a = answer(q);
      setTyping(false);
      pushAI(a.text, a.teach, false);
    }, 650);
  }, [answer, pushAI, pushUser]);

  const send = useCallback(() => {
    const t = draft.trim();
    if (!t) return;
    setDraft('');
    ask(t);
  }, [draft, ask]);

  const draw = useCallback(() => {
    const ctx = ctxRef.current;
    const sim = simRef.current;
    const { w: W, h: H } = sizeRef.current;
    if (!ctx || !sim || !W) return;

    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = '#0f0f12';
    ctx.fillRect(0, 0, W, H);

    const VIS = 62;
    const all = sim.candles;
    const vis = all.slice(-VIS);
    const emaAll = ema(all, 20);
    const emaVis = emaAll.slice(-VIS);
    const offset = all.length - vis.length;
    const padL = 8, padR = 66, padT = 14, padB = 22;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    let pmin = Infinity, pmax = -Infinity;
    vis.forEach((c) => { pmin = Math.min(pmin, c.l); pmax = Math.max(pmax, c.h); });
    if (sim.signal) { pmin = Math.min(pmin, STOP); pmax = Math.max(pmax, TARGET); }
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

    if (sim.signal) {
      const obX = X(Math.max(0, sim.obIndex - offset));
      ctx.fillStyle = 'rgba(105,147,255,0.10)';
      ctx.fillRect(obX - slot / 2, Y(sim.obTop), padL + plotW - (obX - slot / 2), Y(sim.obBottom) - Y(sim.obTop));
      ctx.strokeStyle = 'rgba(105,147,255,0.35)'; ctx.setLineDash([3, 3]); ctx.lineWidth = 1;
      ctx.strokeRect(obX - slot / 2, Y(sim.obTop), padL + plotW - (obX - slot / 2), Y(sim.obBottom) - Y(sim.obTop));
      ctx.setLineDash([]);
      ctx.fillStyle = 'rgba(105,147,255,0.9)'; ctx.font = '9px "JetBrains Mono", monospace'; ctx.textAlign = 'left';
      ctx.fillText('ORDER BLOCK', obX - slot / 2 + 5, Y(sim.obTop) + 8);
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

    if (sim.signal) {
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
      drawLine(TARGET, '#00c48c', '▲ ' + TARGET.toFixed(2));
      drawLine(ENTRY, '#6993ff', '• ' + ENTRY.toFixed(2));
      drawLine(STOP, '#ff5a5a', '▼ ' + STOP.toFixed(2));
      const fx = X(vis.length - 1 - (all.length - 1 - sim.signal.fireIndex));
      if (fx > padL && fx < padL + plotW) {
        const fy = Y(sim.obBottom) + 14;
        const pr2 = 5 + 3 * Math.abs(Math.sin(performance.now() / 380));
        ctx.fillStyle = 'rgba(0,196,140,0.18)'; ctx.beginPath(); ctx.arc(fx, fy, pr2 + 4, 0, 7); ctx.fill();
        ctx.fillStyle = '#00c48c'; ctx.beginPath();
        ctx.moveTo(fx, fy - 6); ctx.lineTo(fx - 5, fy + 4); ctx.lineTo(fx + 5, fy + 4); ctx.closePath(); ctx.fill();
      }
    }

    const ly = Y(sim.live);
    ctx.fillStyle = '#6993ff'; ctx.font = '10px "JetBrains Mono", monospace';
    const lt = sim.live.toFixed(2); const lw = ctx.measureText(lt).width + 12;
    rr(ctx, padL + plotW - lw, ly - 8, lw, 16, 4); ctx.fill();
    ctx.fillStyle = '#fff'; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    ctx.fillText(lt, padL + plotW - lw + 6, ly);
    ctx.strokeStyle = 'rgba(105,147,255,0.4)'; ctx.setLineDash([2, 3]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(padL, ly); ctx.lineTo(padL + plotW - lw, ly); ctx.stroke(); ctx.setLineDash([]);
  }, []);

  useEffect(() => {
    const built = buildCandles();
    const sim: Sim = {
      candles: built.candles,
      forming: built.candles[built.candles.length - 1],
      obIndex: built.obIndex,
      obTop: built.obTop,
      obBottom: built.obBottom,
      live: ENTRY,
      drift: ENTRY,
      lerp: 0.1,
      t: 0,
      signal: null,
      fireBar: 0,
    };
    simRef.current = sim;

    pushSystem('Connected · IBKR real-time feed · BHP · 1-minute bars');
    pushAI(
      "I'm reading BHP live. Price is easing back into a demand zone left by an earlier push up — I'll call it the moment a real setup confirms. Until then, nothing to do.",
      null,
      false,
    );

    let raf = 0;
    const loop = () => { draw(); raf = requestAnimationFrame(loop); };

    const canvas = canvasRef.current;
    let ro: ResizeObserver | null = null;
    if (canvas) {
      ctxRef.current = canvas.getContext('2d');
      const resize = () => {
        const wrap = canvas.parentElement;
        if (!wrap) return;
        const w = wrap.clientWidth, h = wrap.clientHeight;
        const dpr = window.devicePixelRatio || 1;
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
        ctxRef.current?.setTransform(dpr, 0, 0, dpr, 0, 0);
        sizeRef.current = { w, h };
      };
      resize();
      ro = new ResizeObserver(resize);
      ro.observe(canvas.parentElement!);
    }
    raf = requestAnimationFrame(loop);

    const priceTimer = setInterval(() => {
      sim.t++;
      const f = sim.forming;
      if (!f) return;
      const noise = (Math.random() - 0.5) * 0.018;
      sim.live += (sim.drift - sim.live) * sim.lerp + noise;
      if (sim.signal) sim.live = Math.max(STOP + 0.01, sim.live);
      f.c = +sim.live.toFixed(3);
      f.h = Math.max(f.h, f.c);
      f.l = Math.min(f.l, f.c);
      if (sim.t % 10 === 0) {
        sim.candles.push({ o: f.c, c: f.c, h: f.c, l: f.c });
        sim.forming = sim.candles[sim.candles.length - 1];
        if (sim.candles.length > 130) sim.candles.shift();
      }
      if (sim.t % 5 === 0) {
        const p = +sim.live.toFixed(3);
        setPrice(p);
        setPnl((p - ENTRY) * SHARES);
      }
      if (sim.signal && phaseRef.current === 'active' && sim.live >= TARGET - 0.005) {
        closeAtTarget();
      }
    }, 180);

    const fireTimer = setTimeout(() => fire(), 4200);

    return () => {
      cancelAnimationFrame(raf);
      clearInterval(priceTimer);
      clearTimeout(fireTimer);
      ro?.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    // header
    tf, setTf,
    beginner, autoTrade, toggleBeginner, toggleAutoTrade,
    // chart
    canvasRef, chartStatus,
    // signal
    phase, dispScore, bd, price, pnl,
    // tabs
    tab, setTab,
    // copilot
    messages, typing, draft, setDraft, feedRef, ask, send,
    // journal
    journal,
    // history
    trades, expandedTrade, toggleTrade,
  };
}
