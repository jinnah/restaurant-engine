import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { expect, test } from 'vitest';
import { routes } from '../src/router';

test('an unknown path renders the not-found page through the real route table', async () => {
  const router = createMemoryRouter(routes, {
    initialEntries: ['/definitely/not/a/route'],
  });
  render(<RouterProvider router={router} />);

  expect(
    await screen.findByRole('heading', { level: 1, name: /page not found/i }),
  ).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /home page/i })).toHaveAttribute(
    'href',
    '/',
  );
  expect(document.title).toBe('Page not found — Restaurant Engine');
});
