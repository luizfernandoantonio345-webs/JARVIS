import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendTarget = process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'
const backendWsTarget = backendTarget.replace(/^http/i, 'ws')

function httpProxy() {
  return {
    target: backendTarget,
    changeOrigin: true,
  }
}

export default defineConfig({
  plugins: [react()],
  root: '.',
  build: { outDir: 'dist' },
  server: {
    port: 3000,
    host: true,
    proxy: {
      '/ws': {
        target: backendWsTarget,
        ws: true,
        changeOrigin: true,
      },
      '/agents': httpProxy(),
      '/audit': httpProxy(),
      '/autonomy': httpProxy(),
      '/chat': httpProxy(),
      '/cockpit': httpProxy(),
      '/computer': httpProxy(),
      '/dashboard': httpProxy(),
      '/health': httpProxy(),
      '/jarvis': httpProxy(),
      '/memory': httpProxy(),
      '/sentinel': httpProxy(),
      '/system': httpProxy(),
      '/tasks': httpProxy(),
      '/telemetry': httpProxy(),
      '/voice': httpProxy(),
    }
  }
})
