import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The API is same-origin in production and proxied in development, so no
// provider credential is ever needed by, or reachable from, the browser bundle.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8099', changeOrigin: false } },
  },
  build: { outDir: 'dist', sourcemap: true, target: 'es2022' },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.{ts,tsx}'],
  },
});
