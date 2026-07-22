import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    // Both extensions: component tests are .tsx, but the pure utilities
    // (money conversion, reorder permutations) carry no JSX and would be
    // silently skipped by a .tsx-only pattern — a test that never runs is
    // worse than no test at all.
    include: ['tests/**/*.test.{ts,tsx}'],
    setupFiles: ['tests/setup.ts'],
  },
});
