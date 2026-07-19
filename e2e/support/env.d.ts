// The Playwright runner executes these files under Node, but the
// package deliberately avoids @types/node (no new dependencies beyond
// @playwright/test). This narrow ambient declaration covers the only
// Node global the suite touches.
declare const process: {
  env: Record<string, string | undefined>;
};
