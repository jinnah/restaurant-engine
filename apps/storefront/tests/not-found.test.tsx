import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import NotFound, { metadata } from '../app/not-found';

test('the not-found page renders a neutral message and a way home', () => {
  render(<NotFound />);

  expect(
    screen.getByRole('heading', { level: 1, name: /page not found/i }),
  ).toBeInTheDocument();
  expect(screen.getByText(/this page does not exist/i)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /home page/i })).toHaveAttribute(
    'href',
    '/',
  );
});

test('the not-found page declares its document title', () => {
  expect(metadata.title).toBe('Page not found — Restaurant Engine');
});
