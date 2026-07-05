import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Lets `npm run dev` talk to the realtime_chart_ai FastAPI backend
    // (default port 8800) without any VITE_API_BASE env var — relative
    // /api and /ws paths work the same way here as they do once this app is
    // built and served same-origin by FastAPI's StaticFiles mount.
    proxy: {
      '/api': 'http://localhost:8800',
      '/ws': { target: 'ws://localhost:8800', ws: true },
    },
  },
})
