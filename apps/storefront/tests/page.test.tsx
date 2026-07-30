import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { metadata as layoutMetadata } from '../app/layout';
import HomePage, { metadata as pageMetadata } from '../app/page';

test('the home page renders the storefront placeholder', () => {
  render(<HomePage />);

  expect(
    screen.getByRole('heading', {
      level: 1,
      name: /restaurant engine — storefront/i,
    }),
  ).toBeInTheDocument();
  expect(screen.getByText(/public storefront foundation/i)).toBeInTheDocument();
});

test('the root layout declares only the neutral fallback title', () => {
  expect(layoutMetadata.title).toBe('Storefront');
  expect(pageMetadata.title).toBe('Storefront — Restaurant Engine');
});
