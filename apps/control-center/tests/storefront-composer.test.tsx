import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import { renderApp } from './support/render';
import {
  apiError,
  draftView,
  envelope,
  makeClient,
  membership,
  ok,
  sessionView,
  storefrontConfig,
  storefrontOverview,
} from './support/mockClient';

const BUSINESS = '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001';

function ownerClient(overrides: Parameters<typeof makeClient>[0] = {}) {
  return makeClient({
    auth: {
      getSession: vi.fn(async () =>
        ok(sessionView({ memberships: [membership({ role: 'owner' })] })),
      ),
    },
    ...overrides,
  });
}

function heroConfig(heading = 'Welcome') {
  return storefrontConfig({
    sections: [
      {
        id: 'hero',
        type: 'hero',
        enabled: true,
        props: {
          heading,
          subheading: null,
          image: null,
          primary_action: 'none',
        },
      },
    ],
  });
}

async function openStorefront(client: ReturnType<typeof makeClient>) {
  renderApp(`/businesses/${BUSINESS}/storefront`, client);
  await screen.findByRole('heading', { name: 'Draft' });
}

describe('first draft save (create intent)', () => {
  test('adding a section and saving PUTs the full document with NO expected_lock_version', async () => {
    const putDraft = vi.fn(async () => ok(draftView({ config: heroConfig() })));
    const client = ownerClient({
      storefront: {
        get: vi.fn(async () => ok(storefrontOverview())),
        putDraft,
      },
    });
    await openStorefront(client);

    fireEvent.click(screen.getByRole('button', { name: 'Add hero section' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Heading'), {
      target: { value: 'Welcome' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply' }));
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    await waitFor(() => {
      expect(putDraft).toHaveBeenCalledTimes(1);
    });
    const [businessId, body] = putDraft.mock.calls[0] as unknown as [
      string,
      { config: unknown; expected_lock_version?: number },
      string,
    ];
    expect(businessId).toBe(BUSINESS);
    expect('expected_lock_version' in body).toBe(false);
    expect(body.config).toEqual({
      schema_version: 1,
      theme: { accent: '#a34b2a' },
      sections: [
        {
          id: 'hero',
          type: 'hero',
          enabled: true,
          props: {
            heading: 'Welcome',
            subheading: null,
            image: null,
            primary_action: 'none',
          },
        },
      ],
    });
    expect(await screen.findByText('Draft saved.')).toBeInTheDocument();
  });
});

describe('existing draft save (update intent)', () => {
  test('carries the saved draft exact lock version', async () => {
    const putDraft = vi.fn(async () =>
      ok(draftView({ config: heroConfig('Hello again'), lock_version: 4 })),
    );
    const client = ownerClient({
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({ config: heroConfig(), lock_version: 3 }),
            }),
          ),
        ),
        putDraft,
      },
    });
    await openStorefront(client);

    fireEvent.click(screen.getByRole('button', { name: 'Edit Hero' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Heading'), {
      target: { value: 'Hello again' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Save draft' }));
    await waitFor(() => {
      expect(putDraft).toHaveBeenCalledTimes(1);
    });
    const [, body] = putDraft.mock.calls[0] as unknown as [
      string,
      { expected_lock_version?: number },
    ];
    expect(body.expected_lock_version).toBe(3);
  });
});

describe('dialog Apply and Cancel against the single parent form', () => {
  test('Apply commits the section and marks the parent dirty', async () => {
    const client = ownerClient({
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({ draft: draftView({ config: heroConfig() }) }),
          ),
        ),
      },
    });
    await openStorefront(client);
    expect(screen.queryByText(/You have unsaved changes/)).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Edit Hero' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Heading'), {
      target: { value: 'A new heading' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply' }));

    expect(await screen.findByText('A new heading')).toBeInTheDocument();
    expect(screen.getByText(/You have unsaved changes/)).toBeInTheDocument();
  });

  test('Cancel discards only the dialog edits; a dirty dialog asks first', async () => {
    const client = ownerClient({
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({ draft: draftView({ config: heroConfig() }) }),
          ),
        ),
      },
    });
    await openStorefront(client);

    fireEvent.click(screen.getByRole('button', { name: 'Edit Hero' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Heading'), {
      target: { value: 'Typed but never applied' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    // Dirty dialog: deliberate discard required.
    fireEvent.click(
      await screen.findByRole('button', { name: 'Discard changes' }),
    );
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    expect(screen.getByText('Welcome')).toBeInTheDocument();
    expect(screen.queryByText('Typed but never applied')).toBeNull();
    expect(screen.queryByText(/You have unsaved changes/)).toBeNull();
  });
});

describe('nested 422 mapping', () => {
  test('a section field error lands on its card and inside the reopened dialog, and clears on change', async () => {
    const putDraft = vi.fn(async () =>
      apiError(
        422,
        envelope('validation_error', 'Request validation failed.', [
          {
            field: 'body.config.sections.0.hero.props.heading',
            code: 'value_error',
            message: 'Heading is too long.',
          },
        ]),
      ),
    );
    const client = ownerClient({
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({ draft: draftView({ config: heroConfig() }) }),
          ),
        ),
        putDraft,
      },
    });
    await openStorefront(client);

    // Make it dirty so Save proceeds, then fail with the mapped 422.
    fireEvent.click(screen.getByRole('button', { name: 'Edit Hero' }));
    let dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Heading'), {
      target: { value: 'X'.repeat(50) },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Save draft' }));

    expect(
      await screen.findByText(
        'One field needs attention — open Edit to fix it.',
      ),
    ).toBeInTheDocument();

    // Reopen: the server message sits on the exact field.
    fireEvent.click(screen.getByRole('button', { name: 'Edit Hero' }));
    dialog = await screen.findByRole('dialog');
    expect(
      within(dialog).getByText('Heading is too long.'),
    ).toBeInTheDocument();

    // Changing the field clears the server error (only a new save can
    // re-judge it).
    fireEvent.change(within(dialog).getByLabelText('Heading'), {
      target: { value: 'Shorter' },
    });
    await waitFor(() => {
      expect(within(dialog).queryByText('Heading is too long.')).toBeNull();
    });
  });

  test('reordering clears indexed server errors instead of misplacing them', async () => {
    const putDraft = vi.fn(async () =>
      apiError(
        422,
        envelope('validation_error', 'Request validation failed.', [
          {
            field: 'body.config.sections.1.story.props.body',
            code: 'value_error',
            message: 'Story is too long.',
          },
        ]),
      ),
    );
    const config = storefrontConfig({
      sections: [
        {
          id: 'hero',
          type: 'hero',
          enabled: true,
          props: {
            heading: 'Welcome',
            subheading: null,
            image: null,
            primary_action: 'none',
          },
        },
        {
          id: 'story',
          type: 'story',
          enabled: true,
          props: { heading: 'Our story', body: 'Long body.' },
        },
      ],
    });
    const client = ownerClient({
      storefront: {
        get: vi.fn(async () =>
          ok(storefrontOverview({ draft: draftView({ config }) })),
        ),
        putDraft,
      },
    });
    await openStorefront(client);

    fireEvent.click(screen.getByRole('button', { name: 'Edit Story' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Story'), {
      target: { value: 'Even longer body.' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Save draft' }));
    expect(
      await screen.findByText(
        'One field needs attention — open Edit to fix it.',
      ),
    ).toBeInTheDocument();

    // A structural mutation orphans indexed claims: they all clear, and
    // no card wears another section's error.
    fireEvent.click(screen.getByRole('button', { name: 'Move up Story' }));
    await waitFor(() => {
      expect(
        screen.queryByText('One field needs attention — open Edit to fix it.'),
      ).toBeNull();
    });
  });
});

describe('stale-write conflict (§6)', () => {
  test('preserves values and the stale token, disables saving, and only the explicit reload refetches', async () => {
    const putDraft = vi.fn(
      async (): Promise<
        ReturnType<typeof ok<import('@restaurant-engine/api-client').DraftView>>
      > =>
        apiError(
          409,
          envelope('conflict', 'The draft has changed since it was read.'),
        ),
    );
    const get = vi.fn(async () =>
      ok(
        storefrontOverview({
          draft: draftView({ config: heroConfig(), lock_version: 3 }),
        }),
      ),
    );
    const client = ownerClient({ storefront: { get, putDraft } });
    await openStorefront(client);
    const initialGetCalls = get.mock.calls.length;

    fireEvent.click(screen.getByRole('button', { name: 'Edit Hero' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Heading'), {
      target: { value: 'Mine' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Save draft' }));

    expect(
      await screen.findByText('This draft changed somewhere else.'),
    ).toBeInTheDocument();
    // Values preserved; mutations disabled; no background refetch.
    expect(screen.getByText('Mine')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
    expect(get.mock.calls.length).toBe(initialGetCalls);

    // The explicit reload is the only exit: it refetches, resets the form
    // from the fetched draft, and clears the conflict.
    get.mockImplementation(async () =>
      ok(
        storefrontOverview({
          draft: draftView({
            config: heroConfig('Someone else saved this'),
            lock_version: 9,
          }),
        }),
      ),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'Reload current draft' }),
    );
    expect(
      await screen.findByText('Someone else saved this'),
    ).toBeInTheDocument();
    expect(screen.queryByText('Mine')).toBeNull();
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeEnabled();

    // A save after the reload adopts the reloaded lock version — never
    // the stale one, never a silently attached newer one mid-conflict.
    putDraft.mockImplementation(async () =>
      ok(draftView({ config: heroConfig('x'), lock_version: 10 })),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Edit Hero' }));
    const dialog2 = await screen.findByRole('dialog');
    fireEvent.change(within(dialog2).getByLabelText('Heading'), {
      target: { value: 'After reload' },
    });
    fireEvent.click(within(dialog2).getByRole('button', { name: 'Apply' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Save draft' }));
    await waitFor(() => {
      expect(putDraft).toHaveBeenCalledTimes(2);
    });
    const [, body] = putDraft.mock.calls[1] as unknown as [
      string,
      { expected_lock_version?: number },
    ];
    expect(body.expected_lock_version).toBe(9);
  });

  test('a background overview refetch never rebinds a dirty form', async () => {
    const get = vi.fn(async () =>
      ok(
        storefrontOverview({
          draft: draftView({ config: heroConfig(), lock_version: 3 }),
        }),
      ),
    );
    const client = ownerClient({ storefront: { get } });
    const { queryClient } = renderApp(
      `/businesses/${BUSINESS}/storefront`,
      client,
    );
    await screen.findByRole('heading', { name: 'Draft' });

    fireEvent.click(screen.getByRole('button', { name: 'Edit Hero' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Heading'), {
      target: { value: 'Dirty local value' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply' }));
    expect(await screen.findByText('Dirty local value')).toBeInTheDocument();

    // Fresh server data arrives behind the form's back.
    get.mockImplementation(async () =>
      ok(
        storefrontOverview({
          draft: draftView({
            config: heroConfig('Server value'),
            lock_version: 8,
          }),
        }),
      ),
    );
    await queryClient.refetchQueries();
    // The form is seeded once and reset only explicitly: local values win.
    expect(screen.getByText('Dirty local value')).toBeInTheDocument();
    expect(screen.queryByText('Server value')).toBeNull();
  });
});
