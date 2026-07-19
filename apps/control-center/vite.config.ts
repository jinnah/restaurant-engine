import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// The config runs under Node; this narrow declaration avoids pulling
// @types/node into an app that otherwise never touches Node globals.
declare const process: { env: Record<string, string | undefined> };

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
    //
    // CC_API_PROXY_TARGET (ADR-016) lets the E2E orchestrator point the
    // same proxy at its isolated backend (127.0.0.1:8100); development
    // behavior without it is unchanged.
    proxy: {
      '/api': {
        target: process.env['CC_API_PROXY_TARGET'] ?? 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
});
