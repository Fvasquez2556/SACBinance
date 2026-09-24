import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const backend = process.env.SACBINANCE_BACKEND_URL ?? 'http://localhost:8000'

// En desarrollo, Vite proxea /api y /ws hacia el backend (puerto 8000).
// En produccion, FastAPI sirve el frontend y la API en el mismo origen,
// asi que el frontend usa siempre rutas relativas.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': backend,
      '/ws': { target: backend.replace(/^http/, 'ws'), ws: true },
    },
  },
})
