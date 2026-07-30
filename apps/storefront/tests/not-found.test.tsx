import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import NotFound, { metadata } from '../app/not-found';

test('the not-found page is one neutral, structured experience', () => {
  render(<NotFound />);

  expect(screen.getByRole('main')).toBeInTheDocument();
  expect(
    screen.getByRole('heading', { level: 1, name: /page not found/i }),
  ).toBeInTheDocument();
  expect(screen.getByText(/this page does not exist/i)).toBeInTheDocument();
  // Neutral by contract (ADR-013/ADR-021): no tenant data, no cause, no
  // platform branding — every public failure renders identically.
  expect(document.body.textContent).not.toMatch(/restaurant engine/i);
});

test('the not-found page is titled neutrally and not indexable', () => {
  expect(metadata.title).toBe('Page not found');
  expect(metadata.robots).toEqual({ index: false, follow: false });
});
