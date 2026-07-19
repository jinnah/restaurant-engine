import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Vitest globals are disabled in this workspace, so Testing Library's
// automatic cleanup never registers itself; register it explicitly to
// keep each test's DOM isolated.
afterEach(() => {
  cleanup();
});
