import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import type {
  ApiResult,
  DesignAssignmentResult,
} from '@restaurant-engine/api-client';
import {
  adminSessionView,
  apiError,
  business,
  envelope,
  makeClient,
  ok,
  sessionView,
} from './support/mockClient';
import { renderApp } from './support/render';

// The first platform design-assignment UI (M4G-C): the M4B command has
// existed without a UI since ADR-020 §6. The structural variant is
// platform authority — this is the only write path, and it deliberately
// displays no "current" variant, because a platform administrator holds
// no storefront read at all.

const BIZ_ID = '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001';
const DETAIL_PATH = `/platform/businesses/${BIZ_ID}`;

function adminClient(overrides: Parameters<typeof makeClient>[0] = {}) {
  return makeClient({
    auth: { getSession: vi.fn(async () => ok(adminSessionView())) },
    ...overrides,
    platform: {
      getBusiness: vi.fn(async () => ok(business({ status: 'active' }))),
      listInvitations: vi.fn(async () =>
        ok({ items: [], total: 0, limit: 10, offset: 0 }),
      ),
      ...overrides.platform,
    },
  });
}

function result(
  overrides: Partial<DesignAssignmentResult> = {},
): DesignAssignmentResult {
  return {
    design_variant: 'editorial',
    previous_variant: 'classic',
    ...overrides,
  };
}

async function chooseEditorial() {
  fireEvent.click(await screen.findByRole('radio', { name: /^Editorial/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Assign design' }));
  return screen.findByRole('dialog', { name: /assign this design/i });
}

describe('presentation', () => {
  test('offers every registered variant, described, with none preselected', async () => {
    renderApp(DETAIL_PATH, adminClient());

    const group = await screen.findByRole('group', { name: 'Assign a design' });
    const radios = within(group).getAllByRole('radio');
    expect(radios.map((radio) => (radio as HTMLInputElement).value)).toEqual([
      'classic',
      'editorial',
      'express',
    ]);
    for (const radio of radios) {
      expect(radio).not.toBeChecked();
    }
    // Each choice carries its own description, associated with its control.
    expect(
      within(group).getByRole('radio', { name: /^Editorial/ }),
    ).toHaveAccessibleDescription(/Premium typography/);
  });

  test('states plainly that the current design is not shown here', async () => {
    renderApp(DETAIL_PATH, adminClient());

    const section = await screen.findByRole('region', { name: 'Design' });
    expect(section).toHaveTextContent(/not shown here/i);
    expect(section).toHaveTextContent(/no access to a business/i);
    expect(section).toHaveTextContent(/storefront workspace/i);
  });

  test('Assign design is disabled until a variant is chosen', async () => {
    renderApp(DETAIL_PATH, adminClient());

    const assign = await screen.findByRole('button', { name: 'Assign design' });
    expect(assign).toBeDisabled();
    fireEvent.click(screen.getByRole('radio', { name: /^Express/ }));
    expect(assign).toBeEnabled();
  });
});

describe('assignment', () => {
  test('confirms, then sends exactly one command with the CSRF token', async () => {
    const setDesign = vi.fn(async () => ok(result()));
    renderApp(DETAIL_PATH, adminClient({ platform: { setDesign } }));

    const dialog = await chooseEditorial();
    expect(dialog).toHaveTextContent(/saved storefront draft/i);
    expect(dialog).toHaveTextContent(/creates the first one/i);
    expect(dialog).toHaveTextContent(/only when an owner publishes/i);

    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Assign design' }),
    );
    await waitFor(() => {
      expect(setDesign).toHaveBeenCalledWith(
        BIZ_ID,
        { design_variant: 'editorial' },
        'csrf-token-1',
      );
    });
    expect(setDesign).toHaveBeenCalledTimes(1);
    // No lock version is part of this command's contract.
    const [, body] = setDesign.mock.calls[0] as unknown as [
      string,
      Record<string, unknown>,
    ];
    expect(Object.keys(body)).toEqual(['design_variant']);
  });

  test('an effective change is reported as a change', async () => {
    const setDesign = vi.fn(async () => ok(result()));
    renderApp(DETAIL_PATH, adminClient({ platform: { setDesign } }));

    const dialog = await chooseEditorial();
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Assign design' }),
    );

    expect(
      await screen.findByText('Design changed from Classic to Editorial.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  test('a first-draft creation says so instead of naming a previous design', async () => {
    const setDesign = vi.fn(async () => ok(result({ previous_variant: null })));
    renderApp(DETAIL_PATH, adminClient({ platform: { setDesign } }));

    const dialog = await chooseEditorial();
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Assign design' }),
    );

    expect(
      await screen.findByText(
        'Created the first storefront draft and assigned the Editorial design.',
      ),
    ).toBeInTheDocument();
  });

  test("the server's exact no-op is never described as a change", async () => {
    const setDesign = vi.fn(async () =>
      ok(
        result({ design_variant: 'editorial', previous_variant: 'editorial' }),
      ),
    );
    renderApp(DETAIL_PATH, adminClient({ platform: { setDesign } }));

    const dialog = await chooseEditorial();
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Assign design' }),
    );

    expect(
      await screen.findByText(
        'Editorial was already assigned. No changes were made.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/changed from/i)).toBeNull();
  });

  test('the command cannot be double-submitted while pending', async () => {
    let release: () => void = () => {};
    const setDesign = vi.fn(
      () =>
        new Promise<ApiResult<DesignAssignmentResult>>((resolve) => {
          release = () => {
            resolve(ok(result()));
          };
        }),
    );
    renderApp(DETAIL_PATH, adminClient({ platform: { setDesign } }));

    const dialog = await chooseEditorial();
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Assign design' }),
    );
    const working = await within(dialog).findByRole('button', {
      name: /working/i,
    });
    expect(working).toBeDisabled();
    fireEvent.click(working);
    release();

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
    expect(setDesign).toHaveBeenCalledTimes(1);
  });

  test('Escape cancels the confirmation and returns focus to the trigger', async () => {
    renderApp(DETAIL_PATH, adminClient());

    fireEvent.click(await screen.findByRole('radio', { name: /^Classic/ }));
    const trigger = screen.getByRole('button', { name: 'Assign design' });
    trigger.focus(); // jsdom does not focus on click; a real browser does.
    fireEvent.click(trigger);
    const dialog = await screen.findByRole('dialog');
    fireEvent.keyDown(dialog, { key: 'Escape' });

    expect(screen.queryByRole('dialog')).toBeNull();
    await waitFor(() => {
      expect(trigger).toHaveFocus();
    });
  });
});

describe('failures are rendered honestly', () => {
  async function failWith(status: number, code: string, message: string) {
    const setDesign = vi.fn(async () =>
      apiError(status, envelope(code, message)),
    );
    renderApp(DETAIL_PATH, adminClient({ platform: { setDesign } }));
    const dialog = await chooseEditorial();
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Assign design' }),
    );
    return screen.findAllByRole('alert');
  }

  test('a closed business answers 409 invalid_state in the page error panel', async () => {
    const alerts = await failWith(
      409,
      'invalid_state',
      'cannot modify the storefront of a closed business',
    );
    expect(alerts[0]).toHaveTextContent(/closed business/i);
    expect(alerts[0]).toHaveFocus();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  test('a 403 is reported rather than treated as impossible', async () => {
    const alerts = await failWith(
      403,
      'permission_denied',
      'You do not have permission to do that.',
    );
    expect(alerts[0]).toHaveTextContent(/do not have permission/i);
  });

  test('a 404 is reported without inferring why', async () => {
    const alerts = await failWith(404, 'not_found', 'Business not found.');
    expect(alerts[0]).toHaveTextContent(/not found/i);
  });
});

describe('authorization', () => {
  test('an authenticated non-administrator never reaches the panel', async () => {
    const client = makeClient({
      auth: { getSession: vi.fn(async () => ok(sessionView())) },
    });
    renderApp(DETAIL_PATH, client);

    expect(
      await screen.findByRole('heading', { name: /not found/i }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: 'Assign a design' })).toBeNull();
    expect(client.platform.setDesign).not.toHaveBeenCalled();
  });
});
