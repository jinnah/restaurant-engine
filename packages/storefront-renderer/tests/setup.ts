import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Vitest globals are off, so Testing Library cannot auto-register its
// cleanup hook; without this, DOM from one test leaks into the next.
afterEach(() => {
  cleanup();
});
