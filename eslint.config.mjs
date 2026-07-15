// ESLint flat-config baseline (ADR-006).
// Milestone 0 has no TypeScript sources; the typescript-eslint layer is added
// in Milestone 1 together with the first .ts/.tsx files, extending this file.
import js from '@eslint/js';

export default [
  {
    ignores: ['**/node_modules/', '**/dist/', '**/.next/', '**/coverage/'],
  },
  {
    files: ['**/*.{js,mjs,cjs}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
    },
    rules: {
      ...js.configs.recommended.rules,
    },
  },
];
