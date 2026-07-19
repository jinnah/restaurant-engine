import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  server: {
    // Same-origin development invariant (ADR-015): the UI is served at
    // http://localhost:5173 and every API call is an origin-relative
    // `/api/...` request. The proxy forwards to the backend without
    // rewriting the Host header (`changeOrigin: false`): KnownHostGuard
    // accepts `localhost` outside production, and the browser Origin
    // stays `http://localhost:5173`, which the backend trusts by
    // default. No CORS surface exists anywhere. Accessing the UI as
    // http://127.0.0.1:5173 is unsupported — it is a different origin.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
});
