import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/ws': {
        target: 'ws://localhost:8002',
        ws: true,
      },
      '/health': {
        target: 'http://localhost:8002',
      },
      '/rooms': {
        target: 'http://localhost:8002',
      },
      '/api': {
        target: 'http://localhost:8002',
      },
    },
  },
})
