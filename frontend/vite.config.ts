import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  root: '.',
  build: { outDir: 'dist' },
  server: {
    port: 3000,
    host: true,
    proxy: {
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true
      },
      '/chat': 'http://localhost:8000',
      '/tts': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/computer': 'http://localhost:8000',
      '/execute': 'http://localhost:8000',
    },
  },
})
