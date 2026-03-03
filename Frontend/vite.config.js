import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import basicSsl from '@vitejs/plugin-basic-ssl'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), basicSsl()],
  server: {
    host: true,   // Listen on 0.0.0.0 — accessible via LAN IP
    port: 5173,
    https: true,  // getUserMedia requires secure context (https or localhost)
    // Move Vite's HMR WebSocket off /ws so it doesn't collide with our proxy
    hmr: {
      path: '/__vite_hmr',
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        secure: false,
        configure: (proxy) => {
          proxy.on('error', (err, _req, res) => {
            if (res && !res.headersSent) {
              res.writeHead(502, { 'Content-Type': 'text/plain' })
              res.end('Backend unavailable')
            }
          })
        },
      },
      // /ws and /ws/camera → backend WebSockets
      '/ws': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        secure: false,
        ws: true,
        configure: (proxy) => {
          proxy.on('error', (err, _req, socket) => {
            // Gracefully close the client socket on proxy errors
            if (socket && !socket.destroyed) {
              socket.end()
            }
          })
        },
      },
    },
  },
})
