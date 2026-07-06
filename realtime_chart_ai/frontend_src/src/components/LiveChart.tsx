import { useEffect, useMemo, useRef } from 'react';
import {
  createChart, CandlestickSeries, HistogramSeries,
  type IChartApi, type ISeriesApi, type UTCTimestamp,
} from 'lightweight-charts';
import type { Candle, Direction, Phase } from '../types';

const STATUS_LABEL: Record<Phase, string> = {
  watching: 'Watching for setup',
  active: 'signal firing',
  closed: 'Target reached',
};

function fmtVolume(v: number): string {
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(2) + 'M';
  if (v >= 1_000) return (v / 1_000).toFixed(1) + 'K';
  return String(Math.round(v));
}

export function LiveChart({
  candles,
  ticker = 'BHP',
  chartStatus,
  direction = 'long',
  entry = 0,
  stop = 0,
  target = 0,
}: {
  candles: Candle[];
  ticker?: string;
  chartStatus: Phase;
  direction?: Direction;
  entry?: number;
  stop?: number;
  target?: number;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const priceLinesRef = useRef<ReturnType<ISeriesApi<'Candlestick'>['createPriceLine']>[]>([]);

  const displayTicker = ticker.replace(/\.(AX|NS)$/i, '');
  const label = chartStatus === 'active' ? `${direction.toUpperCase()} ${STATUS_LABEL[chartStatus]}` : STATUS_LABEL[chartStatus];
  const dotColor = chartStatus === 'watching' ? 'var(--warning)' : 'var(--profit)';

  // Chart + series setup — created once per mount, independent of data.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, {
      autoSize: true,
      layout: { background: { color: '#0f0f12' }, textColor: '#9a9aa2', fontFamily: '"JetBrains Mono", monospace', fontSize: 10 },
      grid: { vertLines: { color: '#1a1a1e' }, horzLines: { color: '#1a1a1e' } },
      crosshair: { mode: 0 },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#26262b' },
      rightPriceScale: { borderColor: '#26262b' },
    });
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#00c48c', downColor: '#ff5a5a', borderVisible: false,
      wickUpColor: '#00c48c', wickDownColor: '#ff5a5a',
      priceFormat: { type: 'price', precision: 3, minMove: 0.001 },
    });
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });
    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
    candleSeries.priceScale().applyOptions({ scaleMargins: { top: 0.08, bottom: 0.22 } });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    return () => {
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      priceLinesRef.current = [];
    };
  }, []);

  // Data updates — full replace on ticker/timeframe switch or bulk backfill.
  // lightweight-charts keeps whatever time-scale range the user last had —
  // it does NOT auto-fit to new data. Switching tickers/timeframes without
  // fitContent() left the chart visually blank whenever the new series'
  // bars didn't overlap the previous ticker's view window (found testing
  // against real data: BHP -> MQG showed a completely empty chart despite
  // valid data loading, because the old view was scrolled to a time range
  // MQG had no bars in).
  //
  // Separately, an empty `candles` array (a ticker with no data yet — e.g.
  // one still waiting its turn in the ASX200 round-robin scan, or hit a
  // transient Yahoo rate limit) used to just skip the update entirely,
  // leaving whichever ticker's candles were on screen BEFORE the switch
  // still rendered — silently showing the wrong ticker's prices under the
  // new ticker's label/header. Now explicitly clears both series when
  // there's nothing to show, so an empty ticker reads as empty, not stale.
  useEffect(() => {
    const chart = chartRef.current;
    const candleSeries = candleSeriesRef.current;
    const volumeSeries = volumeSeriesRef.current;
    if (!chart || !candleSeries || !volumeSeries) return;
    if (candles.length === 0) {
      candleSeries.setData([]);
      volumeSeries.setData([]);
      return;
    }
    const bars = candles.filter((c) => c.time != null);
    candleSeries.setData(bars.map((c) => ({
      time: c.time as UTCTimestamp, open: c.o, high: c.h, low: c.l, close: c.c,
    })));
    volumeSeries.setData(bars.map((c) => ({
      time: c.time as UTCTimestamp, value: c.v ?? 0, color: c.c >= c.o ? 'rgba(0,196,140,0.5)' : 'rgba(255,90,90,0.5)',
    })));
    chart.timeScale().fitContent();
  }, [candles]);

  // Entry/stop/target price lines — redrawn whenever the active signal changes.
  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!series) return;
    priceLinesRef.current.forEach((l) => series.removePriceLine(l));
    priceLinesRef.current = [];
    if (chartStatus !== 'active' || !entry) return;
    const lines: [number, string, string][] = [
      [target, '#00c48c', 'target'],
      [entry, '#6993ff', 'entry'],
      [stop, '#ff5a5a', 'stop'],
    ];
    priceLinesRef.current = lines.map(([price, color, title]) =>
      series.createPriceLine({ price, color, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title }),
    );
  }, [chartStatus, entry, stop, target]);

  const stats = useMemo(() => {
    if (candles.length === 0) return null;
    const last = candles[candles.length - 1];
    const first = candles[0];
    const high = Math.max(...candles.map((c) => c.h));
    const low = Math.min(...candles.map((c) => c.l));
    const volume = candles.reduce((sum, c) => sum + (c.v ?? 0), 0);
    const change = last.c - first.o;
    const changePct = first.o ? (change / first.o) * 100 : 0;
    return { last: last.c, high, low, volume, change, changePct };
  }, [candles]);

  return (
    <section
      id="rcai-chartwrap"
      style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', padding: '14px 14px 8px', gap: 9 }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)' }} />
            {displayTicker} · 1-minute execution timeframe
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-tertiary)' }}>
            <span style={{ width: 14, height: 9, borderRadius: 2, background: 'var(--accent-dim)', border: '1px solid rgba(105,147,255,.4)' }} />
            order block
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-tertiary)' }}>
            <span style={{ width: 16, borderTop: '1.5px dashed var(--profit)' }} />
            target
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-tertiary)' }}>
            <span style={{ width: 16, borderTop: '1.5px dashed var(--loss)' }} />
            stop
          </span>
        </div>
      </div>
      <div
        id="rcai-canvaswrap"
        style={{ position: 'relative', flex: 1, minHeight: 300, border: '1px solid var(--border)', borderRadius: 12, overflow: 'hidden', background: '#0f0f12' }}
      >
        <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />
        <div
          style={{
            position: 'absolute', top: 12, left: 12, display: 'inline-flex', alignItems: 'center', gap: 7,
            background: 'rgba(18,18,20,0.82)', border: '1px solid var(--border)', borderRadius: 999, padding: '5px 12px',
            fontSize: 11.5, fontWeight: 600, color: 'var(--text-primary)', backdropFilter: 'blur(2px)', zIndex: 2,
          }}
        >
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: dotColor }} />
          {label}
        </div>
        {stats && (
          <div
            style={{
              position: 'absolute', top: 12, right: 12, zIndex: 2, textAlign: 'right',
              background: 'rgba(18,18,20,0.82)', border: '1px solid var(--border)', borderRadius: 10,
              padding: '8px 12px', backdropFilter: 'blur(2px)', fontFamily: 'var(--font-mono)',
            }}
          >
            <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.2 }}>
              {stats.last.toFixed(3)}
            </div>
            <div style={{ fontSize: 11.5, fontWeight: 600, color: stats.change >= 0 ? 'var(--profit)' : 'var(--loss)' }}>
              {stats.change >= 0 ? '+' : ''}{stats.change.toFixed(3)} ({stats.change >= 0 ? '+' : ''}{stats.changePct.toFixed(2)}%)
            </div>
            <div style={{ fontSize: 10.5, color: 'var(--text-tertiary)', marginTop: 4 }}>
              H {stats.high.toFixed(3)} · L {stats.low.toFixed(3)}
            </div>
            <div style={{ fontSize: 10.5, color: 'var(--text-tertiary)' }}>
              Vol {fmtVolume(stats.volume)}
            </div>
          </div>
        )}
        {!stats && (
          <div
            style={{
              position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 12.5, color: 'var(--text-tertiary)', zIndex: 2, pointerEvents: 'none',
            }}
          >
            No data yet for {displayTicker} — still waiting its turn in the scan rotation
          </div>
        )}
      </div>
    </section>
  );
}
