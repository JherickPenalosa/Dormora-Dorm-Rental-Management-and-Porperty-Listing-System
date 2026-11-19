
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const securityHeaders = {
  'X-Frame-Options': 'DENY',
  'X-Content-Type-Options': 'nosniff',
}

export default defineConfig({
  plugins: [react()],
  server: {
    headers: securityHeaders,
  },
  preview: {
    headers: securityHeaders,
  },
})
