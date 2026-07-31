import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import { renderApp } from './support/render';
import {
  apiError,
  draftView,
  envelope,
  makeClient,
  mediaAsset,
  membership,
  ok,
  sessionView,
  storefrontConfig,
  storefrontOverview,
} from './support/mockClient';

// The M4G-C brand surface: the curated palette, the curated typography
// pairing, the tenant accent, and the decorative logo — all tenant content
// inside the one full-document draft save, none of it structural.

const BUSINESS = '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001';
const LOGO_ID = '9f1d2c3b-4a5e-4f60-8b71-2c3d4e5f6a7b';

function authedClient(
  role: 'owner' | 'manager' | 'staff',
  overrides: Parameters<typeof makeClient>[0] = {},
  businessStatus = 'active',
) {
  return makeClient({
    auth: {
      getSession: vi.fn(async () =>
        ok(
          sessionView({
            memberships: [
              membership({ role, business_status: businessStatus }),
            ],
          }),
        ),
      ),
    },
    ...overrides,
  });
}

function heroSections(heading = 'Welcome') {
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
  }).sections;
}

/** A stored draft whose theme is entirely non-default. */
function brandedConfig() {
  return storefrontConfig({
    sections: heroSections(),
    theme: {
      accent: '#3355ff',
      palette: 'midnight',
      type_pairing: 'serif_display',
      logo: { media_id: LOGO_ID },
    },
  });
}

async function openComposer(client: ReturnType<typeof makeClient>) {
  renderApp(`/businesses/${BUSINESS}/storefront`, client);
  await screen.findByRole('heading', { name: 'Draft' });
}

/** The theme of the Nth PUT the composer sent (default: the first). */
function savedTheme(putDraft: ReturnType<typeof vi.fn>, call = 0): unknown {
  const [, body] = putDraft.mock.calls[call] as unknown as [
    string,
    { config: { theme: unknown } },
  ];
  return body.config.theme;
}

describe('brand controls: initialization', () => {
  test('a first-use draft offers the platform defaults', async () => {
    const client = authedClient('owner', {
      storefront: { get: vi.fn(async () => ok(storefrontOverview())) },
    });
    await openComposer(client);

    const group = screen.getByRole('group', { name: 'Brand and appearance' });
    expect(
      within(group).getByLabelText<HTMLSelectElement>('Color palette').value,
    ).toBe('warm');
    expect(
      within(group).getByLabelText<HTMLSelectElement>('Typography').value,
    ).toBe('humanist');
    expect(
      within(group).getByLabelText<HTMLInputElement>('Accent color').value,
    ).toBe('#a34b2a');
    expect(
      within(group).getByRole('button', { name: 'Choose a logo' }),
    ).toBeInTheDocument();
  });

  test('a stored draft shows its own palette, pairing, accent, and logo', async () => {
    const client = authedClient('owner', {
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({ config: brandedConfig() }),
            }),
          ),
        ),
      },
    });
    await openComposer(client);

    const group = screen.getByRole('group', { name: 'Brand and appearance' });
    expect(
      within(group).getByLabelText<HTMLSelectElement>('Color palette').value,
    ).toBe('midnight');
    expect(
      within(group).getByLabelText<HTMLSelectElement>('Typography').value,
    ).toBe('serif_display');
    expect(
      within(group).getByLabelText<HTMLInputElement>('Accent color').value,
    ).toBe('#3355ff');
    // The stored logo is present, decorative, and addressed through the
    // authenticated member media route.
    const thumb = within(group).getByRole('presentation');
    expect(thumb).toHaveAttribute('alt', '');
    expect(thumb).toHaveAttribute(
      'src',
      `/api/v1/businesses/${BUSINESS}/media/${LOGO_ID}/file/canonical`,
    );
  });

  test('every registered palette and pairing is offered, described, never colour alone', async () => {
    const client = authedClient('owner', {
      storefront: { get: vi.fn(async () => ok(storefrontOverview())) },
    });
    await openComposer(client);

    const group = screen.getByRole('group', { name: 'Brand and appearance' });
    const palette = within(group).getByLabelText('Color palette');
    expect(
      within(palette)
        .getAllByRole('option')
        .map((option) => (option as HTMLOptionElement).value),
    ).toEqual(['warm', 'ember', 'slate', 'olive', 'midnight']);
    // Each option names the palette AND says what it looks like, so the
    // swatch beside the control is never the only cue.
    expect(
      within(palette).getByRole('option', {
        name: 'Midnight — a dark page with light text',
      }),
    ).toBeInTheDocument();

    const typography = within(group).getByLabelText('Typography');
    expect(
      within(typography)
        .getAllByRole('option')
        .map((option) => (option as HTMLOptionElement).value),
    ).toEqual(['humanist', 'serif_display', 'geometric']);
  });
});

describe('brand controls: dirtiness and save payload', () => {
  test('changing the palette marks the draft dirty and blocks publishing', async () => {
    const client = authedClient('owner', {
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({ config: storefrontConfig() }),
            }),
          ),
        ),
      },
    });
    await openComposer(client);
    expect(screen.queryByText(/You have unsaved changes/)).toBeNull();

    fireEvent.change(screen.getByLabelText('Color palette'), {
      target: { value: 'slate' },
    });

    expect(
      await screen.findByText(/You have unsaved changes/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Publish…' })).toBeDisabled();
  });

  test('changing the typography pairing marks the draft dirty', async () => {
    const client = authedClient('owner', {
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({ config: storefrontConfig() }),
            }),
          ),
        ),
      },
    });
    await openComposer(client);

    fireEvent.change(screen.getByLabelText('Typography'), {
      target: { value: 'geometric' },
    });

    expect(
      await screen.findByText(/You have unsaved changes/),
    ).toBeInTheDocument();
  });

  test('accent and palette changed together are both sent in one save', async () => {
    const putDraft = vi.fn(async () =>
      ok(draftView({ config: storefrontConfig(), lock_version: 4 })),
    );
    const client = authedClient('owner', {
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({
                config: storefrontConfig({ sections: heroSections() }),
                lock_version: 3,
              }),
            }),
          ),
        ),
        putDraft,
      },
    });
    await openComposer(client);

    fireEvent.change(screen.getByLabelText('Color palette'), {
      target: { value: 'olive' },
    });
    fireEvent.change(screen.getByLabelText('Typography'), {
      target: { value: 'geometric' },
    });
    fireEvent.change(screen.getByLabelText('Accent color'), {
      target: { value: '#112233' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));

    await waitFor(() => {
      expect(putDraft).toHaveBeenCalledTimes(1);
    });
    expect(savedTheme(putDraft)).toEqual({
      accent: '#112233',
      palette: 'olive',
      type_pairing: 'geometric',
      logo: null,
    });
  });

  test('a stored logo survives an unrelated brand change', async () => {
    const putDraft = vi.fn(async () =>
      ok(draftView({ config: brandedConfig(), lock_version: 4 })),
    );
    const client = authedClient('owner', {
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({ config: brandedConfig(), lock_version: 3 }),
            }),
          ),
        ),
        putDraft,
      },
    });
    await openComposer(client);

    fireEvent.change(screen.getByLabelText('Color palette'), {
      target: { value: 'ember' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    await waitFor(() => {
      expect(putDraft).toHaveBeenCalledTimes(1);
    });

    expect(savedTheme(putDraft)).toEqual({
      accent: '#3355ff',
      palette: 'ember',
      type_pairing: 'serif_display',
      logo: { media_id: LOGO_ID },
    });
  });

  test('a successful save resets to the server-normalized pristine baseline', async () => {
    const saved = storefrontConfig({
      sections: heroSections(),
      theme: {
        accent: '#a34b2a',
        palette: 'slate',
        type_pairing: 'humanist',
        logo: null,
      },
    });
    const client = authedClient('owner', {
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({
                config: storefrontConfig({ sections: heroSections() }),
                lock_version: 3,
              }),
            }),
          ),
        ),
        putDraft: vi.fn(async () => ok(draftView({ config: saved }))),
      },
    });
    await openComposer(client);

    fireEvent.change(screen.getByLabelText('Color palette'), {
      target: { value: 'slate' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));

    expect(await screen.findByText('Draft saved.')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText(/You have unsaved changes/)).toBeNull();
    });
    expect(
      screen.getByLabelText<HTMLSelectElement>('Color palette').value,
    ).toBe('slate');
  });
});

describe('theme-logo staging', () => {
  function libraryClient(config = storefrontConfig()) {
    return authedClient('owner', {
      storefront: {
        get: vi.fn(async () =>
          ok(storefrontOverview({ draft: draftView({ config }) })),
        ),
      },
      media: {
        listAssets: vi.fn(async () =>
          ok({ items: [mediaAsset()], total: 1, limit: 50, offset: 0 }),
        ),
      },
    });
  }

  test('choosing a logo stages the reference and claims nothing', async () => {
    const client = libraryClient();
    await openComposer(client);

    fireEvent.click(screen.getByRole('button', { name: 'Choose a logo' }));
    expect(await screen.findByText('logo.png')).toBeInTheDocument();
    // Pending honesty and the staging contract, in logo wording.
    expect(screen.getByText(/Not used yet — expires/)).toBeInTheDocument();
    expect(
      screen.getByText(/kept in the editor until you save the draft/),
    ).toBeInTheDocument();
    expect(screen.getByText(/never replaces it/)).toBeInTheDocument();

    fireEvent.click(screen.getByText('logo.png'));
    fireEvent.click(screen.getByRole('button', { name: 'Use this logo' }));

    expect(
      await screen.findByRole('button', { name: 'Replace' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/You have unsaved changes/)).toBeInTheDocument();
    // Staging is not saving: no draft PUT happened.
    expect(client.storefront.putDraft).not.toHaveBeenCalled();
  });

  test('the logo picker offers no description choice at all', async () => {
    const client = libraryClient();
    await openComposer(client);

    fireEvent.click(screen.getByRole('button', { name: 'Choose a logo' }));
    await screen.findByText('logo.png');
    fireEvent.click(screen.getByText('logo.png'));

    // No describe/decorative pair, no description field, and the confirm
    // needs only the selected asset.
    expect(screen.queryByText('Describe this image')).toBeNull();
    expect(screen.queryByLabelText('Description')).toBeNull();
    expect(screen.queryByRole('radio')).toBeNull();
    expect(screen.getByRole('button', { name: 'Use this logo' })).toBeEnabled();
  });

  test('cancelling the picker leaves the draft untouched', async () => {
    const client = libraryClient();
    await openComposer(client);

    fireEvent.click(screen.getByRole('button', { name: 'Choose a logo' }));
    await screen.findByText('logo.png');
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(
      await screen.findByRole('button', { name: 'Choose a logo' }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/You have unsaved changes/)).toBeNull();
  });

  test('replacing swaps the staged reference; removing clears it', async () => {
    const other = '11111111-2222-4333-8444-555555555555';
    const putDraft = vi.fn(async () =>
      ok(draftView({ config: brandedConfig() })),
    );
    const client = authedClient('owner', {
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({ config: brandedConfig(), lock_version: 3 }),
            }),
          ),
        ),
        putDraft,
      },
      media: {
        listAssets: vi.fn(async () =>
          ok({
            items: [mediaAsset({ id: other, original_filename: 'mark.png' })],
            total: 1,
            limit: 50,
            offset: 0,
          }),
        ),
      },
    });
    await openComposer(client);

    fireEvent.click(screen.getByRole('button', { name: 'Replace' }));
    fireEvent.click(await screen.findByText('mark.png'));
    fireEvent.click(screen.getByRole('button', { name: 'Use this logo' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Save draft' }));
    await waitFor(() => {
      expect(putDraft).toHaveBeenCalledTimes(1);
    });
    expect(savedTheme(putDraft)).toMatchObject({ logo: { media_id: other } });

    // Removing drops only the reference — no media call is made at all.
    fireEvent.click(screen.getByRole('button', { name: 'Remove' }));
    expect(
      await screen.findByRole('button', { name: 'Choose a logo' }),
    ).toBeInTheDocument();
    expect(client.media.deleteAsset).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    await waitFor(() => {
      expect(putDraft).toHaveBeenCalledTimes(2);
    });
    expect(savedTheme(putDraft, 1)).toMatchObject({ logo: null });
  });

  test('an upload failure is reported inside the picker and can be retried', async () => {
    const uploadAsset = vi
      .fn()
      .mockResolvedValueOnce(
        apiError(413, envelope('payload_too_large', 'Too large.')),
      )
      .mockResolvedValueOnce(ok(mediaAsset()));
    const client = authedClient('owner', {
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({ config: brandedConfig() }),
            }),
          ),
        ),
      },
      media: {
        listAssets: vi.fn(async () =>
          ok({ items: [], total: 0, limit: 50, offset: 0 }),
        ),
        uploadAsset,
      },
    });
    await openComposer(client);

    fireEvent.click(screen.getByRole('button', { name: 'Replace' }));
    const file = new File(['x'], 'logo.png', { type: 'image/png' });
    fireEvent.change(await screen.findByLabelText('Upload a new image'), {
      target: { files: [file] },
    });

    expect(
      await screen.findByText(/larger than this server accepts/),
    ).toBeInTheDocument();
    // The dialog stayed open and the input is live again, so the same
    // choice can simply be made a second time.
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByLabelText('Upload a new image')).toBeEnabled();

    fireEvent.change(screen.getByLabelText('Upload a new image'), {
      target: { files: [file] },
    });
    // The retry succeeded: the failure is gone and the upload is selected,
    // which in decorative mode is the whole confirm condition.
    await waitFor(() => {
      expect(screen.queryByText(/larger than this server accepts/)).toBeNull();
    });
    expect(screen.getByRole('button', { name: 'Use this logo' })).toBeEnabled();
  });
});

describe('the shared picker is unchanged for describing consumers', () => {
  test('a section image still requires the describe/decorative choice', async () => {
    // The logo opts out of the description step because the product ruled
    // it permanently decorative. Nothing else did: a section photograph
    // conveys something the surrounding text does not, so its picker keeps
    // demanding an explicit choice before it can be attached.
    const client = authedClient('owner', {
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({
                config: storefrontConfig({ sections: heroSections() }),
              }),
            }),
          ),
        ),
      },
      media: {
        listAssets: vi.fn(async () =>
          ok({
            items: [mediaAsset({ original_filename: 'terrace.jpg' })],
            total: 1,
            limit: 50,
            offset: 0,
          }),
        ),
      },
    });
    await openComposer(client);

    fireEvent.click(screen.getByRole('button', { name: 'Edit Hero' }));
    fireEvent.click(
      await screen.findByRole('button', { name: 'Choose a photo' }),
    );
    fireEvent.click(await screen.findByText('terrace.jpg'));

    // The fieldset is present and the attach is withheld until answered.
    expect(
      screen.getByRole('group', { name: 'Describe this image' }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole('radio')).toHaveLength(2);
    expect(
      screen.getByRole('button', { name: 'Use this image' }),
    ).toBeDisabled();

    fireEvent.click(
      screen.getByLabelText(
        'This image is decorative — it adds nothing beyond the surrounding text',
      ),
    );
    expect(
      screen.getByRole('button', { name: 'Use this image' }),
    ).toBeEnabled();
  });
});

type PutDraft = NonNullable<
  NonNullable<Parameters<typeof makeClient>[0]>['storefront']
>['putDraft'];

describe('save failures keep brand work recoverable', () => {
  const conflictClient = (putDraft: PutDraft) =>
    authedClient('owner', {
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({ config: brandedConfig(), lock_version: 3 }),
            }),
          ),
        ),
        putDraft,
      },
    });

  test('a true stale conflict preserves every brand value and the staged logo', async () => {
    const putDraft = vi.fn(async () =>
      apiError(
        409,
        envelope('conflict', 'The draft has changed since it was read.'),
      ),
    );
    await openComposer(conflictClient(putDraft));

    fireEvent.change(screen.getByLabelText('Color palette'), {
      target: { value: 'slate' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));

    expect(
      await screen.findByText('This draft changed somewhere else.'),
    ).toBeInTheDocument();

    // §6 disables every mutation until the explicit reload, so the brand
    // controls become the same read-only presentation a closed business
    // gets — exactly as the accent control has always behaved. What the
    // rule protects is the *values*, and they are all still here: the
    // edited palette, the untouched pairing and accent, and the staged
    // logo.
    const group = screen.getByRole('group', { name: 'Brand and appearance' });
    expect(
      within(group).getByText('Slate — cool gray neutrals'),
    ).toBeInTheDocument();
    expect(
      within(group).getByText(
        'Serif display — serif headings above sans-serif text',
      ),
    ).toBeInTheDocument();
    expect(within(group).getByText('#3355ff')).toBeInTheDocument();
    expect(within(group).getByRole('presentation')).toHaveAttribute(
      'src',
      `/api/v1/businesses/${BUSINESS}/media/${LOGO_ID}/file/canonical`,
    );
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
  });

  test('an expired staged asset is NOT reported as a concurrent draft change', async () => {
    // The claim path answers 409 `invalid_state` when a staged asset
    // expired before the save reached it. Nothing about the draft moved,
    // so the stale panel would be a false claim — and its only exit
    // discards the very reference that needs replacing.
    const putDraft = vi.fn(async () =>
      apiError(
        409,
        envelope(
          'invalid_state',
          'this media asset has expired and cannot be attached',
        ),
      ),
    );
    await openComposer(conflictClient(putDraft));

    fireEvent.change(screen.getByLabelText('Color palette'), {
      target: { value: 'slate' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));

    expect(
      await screen.findByText(
        'this media asset has expired and cannot be attached',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText('This draft changed somewhere else.')).toBeNull();
    // Values and the staged reference survive, and the editor stays usable
    // so the expired logo can be replaced or removed and the save retried.
    expect(
      screen.getByLabelText<HTMLSelectElement>('Color palette').value,
    ).toBe('slate');
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Replace' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove' })).toBeInTheDocument();
  });

  test('an exact theme field path lands on the control that owns it', async () => {
    const putDraft = vi.fn(async () =>
      apiError(
        422,
        envelope('validation_error', 'Request validation failed.', [
          {
            field: 'body.config.theme.palette',
            code: 'value_error',
            message: 'That palette is not available.',
          },
        ]),
      ),
    );
    await openComposer(conflictClient(putDraft));

    fireEvent.change(screen.getByLabelText('Color palette'), {
      target: { value: 'slate' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));

    expect(
      await screen.findByText('That palette is not available.'),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Color palette')).toHaveAccessibleDescription(
      /That palette is not available\./,
    );
  });

  test('an exact logo.media_id field path lands on the Logo control', async () => {
    // The other half of the ruling the test below states: when the server
    // *does* address the logo by its exact published path, the message
    // belongs on the control and must not be left in the general summary.
    const putDraft = vi.fn(async () =>
      apiError(
        422,
        envelope('validation_error', 'Request validation failed.', [
          {
            field: 'body.config.theme.logo.media_id',
            code: 'value_error',
            message: 'That logo image is no longer usable.',
          },
        ]),
      ),
    );
    await openComposer(conflictClient(putDraft));

    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));

    // Rendered by the Logo control itself, inside the brand group.
    const group = await screen.findByRole('group', {
      name: 'Brand and appearance',
    });
    await waitFor(() => {
      expect(within(group).getByRole('alert')).toHaveTextContent(
        'That logo image is no longer usable.',
      );
    });
    // The message is the Logo control's alone — the persistent summary
    // carries only the generic prompt, never the field message.
    const summaries = screen
      .getAllByRole('alert')
      .filter((alert) => !group.contains(alert));
    expect(summaries).toHaveLength(1);
    expect(summaries[0]).not.toHaveTextContent(
      'That logo image is no longer usable.',
    );
    // ...and the owner can still act on it without losing anything.
    expect(
      within(group).getByRole('button', { name: 'Replace' }),
    ).toBeEnabled();
    expect(within(group).getByRole('button', { name: 'Remove' })).toBeEnabled();
  });

  test('a service-level media rejection stays in the summary, unattributed', async () => {
    // The backend answers unknown, cross-business, and non-image references
    // with ONE indistinguishable 422 carrying `details.media_ids` and no
    // field error. Guessing a control from it would mean inferring which
    // reference was refused — exactly what the response hides.
    const putDraft = vi.fn(async () =>
      apiError(
        422,
        envelope('validation_error', 'config references unknown media assets'),
      ),
    );
    await openComposer(conflictClient(putDraft));

    fireEvent.change(screen.getByLabelText('Color palette'), {
      target: { value: 'slate' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));

    const summary = await screen.findByRole('alert');
    expect(summary).toHaveTextContent('config references unknown media assets');
    expect(
      screen.getByLabelText('Color palette'),
    ).not.toHaveAccessibleDescription(/unknown media assets/);
  });
});

describe('brand controls by role and lifecycle', () => {
  test('a closed business shows readable values with no editable control', async () => {
    const client = authedClient(
      'owner',
      {
        storefront: {
          get: vi.fn(async () =>
            ok(
              storefrontOverview({
                draft: draftView({ config: brandedConfig() }),
              }),
            ),
          ),
        },
      },
      'closed',
    );
    await openComposer(client);

    const group = screen.getByRole('group', { name: 'Brand and appearance' });
    expect(
      within(group).getByText('Midnight — a dark page with light text'),
    ).toBeInTheDocument();
    expect(
      within(group).getByText(
        'Serif display — serif headings above sans-serif text',
      ),
    ).toBeInTheDocument();
    // Nothing here pretends to be editable.
    expect(within(group).queryByRole('combobox')).toBeNull();
    expect(within(group).queryByLabelText('Accent color')).toBeNull();
    expect(within(group).queryByRole('button')).toBeNull();
  });

  test('a manager may edit the brand fields but may not publish', async () => {
    const client = authedClient('manager', {
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({ config: storefrontConfig() }),
            }),
          ),
        ),
      },
    });
    await openComposer(client);

    fireEvent.change(screen.getByLabelText('Color palette'), {
      target: { value: 'ember' },
    });
    expect(
      await screen.findByText(/You have unsaved changes/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'Publish…' })).toBeNull();
  });

  test('staff never reach the composer at all', async () => {
    const client = authedClient('staff', {
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({ config: brandedConfig() }),
            }),
          ),
        ),
      },
    });
    renderApp(`/businesses/${BUSINESS}/storefront`, client);

    expect(
      await screen.findByText(
        /Storefront management is available to owners and managers/,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText('Brand and appearance')).toBeNull();
    expect(client.storefront.get).not.toHaveBeenCalled();
  });
});
