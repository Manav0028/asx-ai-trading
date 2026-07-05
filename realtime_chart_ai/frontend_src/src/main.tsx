import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import LiveApp from './LiveApp.tsx'

// VITE_LIVE=true is set for the build that gets copied into
// realtime_chart_ai/frontend/ (see app/README or the build script) so that
// deployment talks to the real FastAPI backend instead of the client-side
// scripted demo. `npm run dev` defaults to the live app too, proxied to
// localhost:8800 (see vite.config.ts) — pass VITE_LIVE=false to see the
// original self-contained design demo instead.
const useLive = import.meta.env.VITE_LIVE !== 'false'

createRoot(document.getElementById('root')!).render(useLive ? <LiveApp /> : <App />)
