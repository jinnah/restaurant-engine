import { expect, test } from 'vitest';
import { metadata as layoutMetadata } from '../app/layout';

// The home page itself is an async server component over live backend
// state; its behavior is covered in home-page.test.tsx (mocked data
// boundary) and by the built-server verification script. What belongs
// here is the root layout's neutrality contract.
test('the root layout declares only the neutral fallback title', () => {
  expect(layoutMetadata.title).toBe('Storefront');
});
