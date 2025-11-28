import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tsconfigPaths from 'vite-tsconfig-paths'
import fs from 'fs'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd())

  // Check if HTTPS certificates exist
  const certPath = path.resolve(__dirname, '../../certs/cert.pem')
  const keyPath = path.resolve(__dirname, '../../certs/key.pem')
  const httpsEnabled = env.VITE_HTTPS === 'true' && fs.existsSync(certPath) && fs.existsSync(keyPath)

  // Backend proxy target (for proxying API requests through Vite)
  const backendUrl = env.VITE_BACKEND_PROXY_URL || 'http://localhost:8071'

  return {
    plugins: [react(), tsconfigPaths()],
    build: {
      sourcemap: env.VITE_BUILD_SOURCEMAP === 'true',
    },
    server: {
      port: parseInt(env.VITE_PORT) || 3000,
      host: env.VITE_HOST ?? 'localhost',
      allowedHosts: ['.nip.io'],
      https: httpsEnabled ? {
        key: fs.readFileSync(keyPath),
        cert: fs.readFileSync(certPath),
      } : undefined,
      proxy: env.VITE_PROXY_API === 'true' ? {
        '/api': {
          target: backendUrl,
          changeOrigin: true,
          secure: false,
        },
      } : undefined,
    },
  }
})
