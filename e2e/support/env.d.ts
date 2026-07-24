// The Playwright runner executes these files under Node, but the
// package deliberately avoids @types/node (no new dependencies beyond
// @playwright/test). This narrow ambient declaration covers the only
// Node global the suite touches.
declare const process: {
  env: Record<string, string | undefined>;
};

// Reading the committed image fixture for an API-fixture upload. Declared
// as narrowly as the `process` shim above rather than pulling @types/node
// into the package for one function.
declare module 'node:fs' {
  export function readFileSync(path: string): Buffer;
}
