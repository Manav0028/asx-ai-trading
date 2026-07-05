import type { Candle } from '../types';

export function makeRng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

export interface BuiltCandles {
  candles: Candle[];
  obIndex: number;
  obTop: number;
  obBottom: number;
}

export function buildCandles(): BuiltCandles {
  const r = makeRng(20260705);
  const c: Candle[] = [];
  let p = 41.9;
  for (let i = 0; i < 52; i++) {
    const o = p;
    p = p + (41.95 - p) * 0.06 + (r() - 0.5) * 0.05;
    p = Math.max(41.82, Math.min(42.06, p));
    c.push({ o, c: p, h: Math.max(o, p) + r() * 0.02, l: Math.min(o, p) - r() * 0.02 });
  }
  const script: [number, number][] = [
    [41.98, 42.03],
    [42.03, 42.06],
    [42.07, 42.02],
    [42.05, 41.97], // bullish order block (last down candle)
    [41.98, 42.3], // displacement up
    [42.29, 42.21],
    [42.21, 42.14],
    [42.14, 42.1],
    [42.11, 42.075],
    [42.08, 42.08],
  ];
  const obIndex = c.length + 3;
  script.forEach(([o, cl], k) => {
    const disp = k === 4;
    c.push({ o, c: cl, h: Math.max(o, cl) + (disp ? 0.02 : 0.015), l: Math.min(o, cl) - (disp ? 0.015 : 0.02) });
  });
  return { candles: c, obIndex, obTop: 42.05, obBottom: 41.97 };
}

export function ema(arr: Candle[], period: number): number[] {
  const k = 2 / (period + 1);
  const out: number[] = [];
  let e = arr[0].c;
  for (let i = 0; i < arr.length; i++) {
    e = arr[i].c * k + e * (1 - k);
    out.push(e);
  }
  return out;
}
