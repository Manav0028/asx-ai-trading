# Realtime Chart AI — frontend

React + TypeScript + Vite. Replaces the original vanilla-JS `frontend/` — same
FastAPI backend (`server/app.py`), same wire contract (`server/schemas.py`).

## Two modes

- **Live** (`VITE_LIVE` unset or not `"false"`, the default): fetches
  `/api/tickers`, `/api/candles/{ticker}`, `/api/journal`, `/api/positions`,
  `/api/auto-trade`, and connects `/ws/candles/{ticker}` — talks to the real
  backend. This is what ships to `../frontend/`.
- **Demo** (`VITE_LIVE=false`): the original self-contained, client-side
  scripted BHP order-block-retest walkthrough, no backend required. Useful for
  design review or offline demoing.

## Commands

```bash
npm install
npm run dev      # http://localhost:5173, proxies /api and /ws to
                  # localhost:8800 (see vite.config.ts) — start the backend
                  # (bash run.sh) alongside it
npm run build     # -> dist/
npm run deploy    # build + copy dist/ into ../frontend/ (what FastAPI serves)
```

## Layout

- `src/hooks/useRealtimeChartAI.ts` + `src/App.tsx` — the demo mode.
- `src/hooks/useRealtimeChartAILive.ts` + `src/LiveApp.tsx` — the live mode,
  via `src/lib/liveApi.ts` (REST + WebSocket client).
- `src/components/*` — shared between both modes (Header, Chart, Rail,
  SignalCard, CopilotTab, JournalTab, HistoryTab).
- `src/styles/*` — design tokens lifted from the `manav-ai-trading-design-system`
  Claude Design bundle (colors/typography/spacing/fonts).

## Known gaps vs. a full production frontend

- The order-block shaded zone isn't drawn in live mode — the WS
  `pattern_signal` payload doesn't currently carry the zone's price bounds,
  only entry/stop/target. Candlestick + EMA + entry/target/stop lines +
  fire marker all render from real data.
- The Copilot chat's free-text Q&A (`src/lib/copilot.ts`) is a local
  scripted answer engine, not a real NLU/LLM endpoint — the backend has no
  chat API. The *automatic* narration (system-connect message, per-signal
  commentary, trade-exit summary) uses the real `claude_rationale` text from
  the backend.
- Reloading mid-position shows the open position's entry/stop/target and
  live P&L (from `/api/positions`), but not that signal's original
  score/breakdown bars, since those only arrive via the WS `pattern_signal`
  event and aren't replayed on reconnect.
