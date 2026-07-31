import { useState } from 'react';
import { useWatch, type UseFormReturn } from 'react-hook-form';
import { useApiClient } from '../../api/ClientProvider';
import { SelectField } from '../../components/FormField';
import {
  DEFAULT_PALETTE,
  DEFAULT_TYPE_PAIRING,
  type ComposerValues,
} from '../composition';
import {
  brandChoiceText,
  PALETTE_CHOICES,
  PALETTE_ORDER,
  paletteSwatchStyle,
  TYPE_PAIRING_CHOICES,
  TYPE_PAIRING_ORDER,
  typeSampleStyle,
} from '../themeChoices';
import { ThemeLogoDialog } from './ThemeLogoDialog';
import styles from '../storefront.module.css';

export type ComposerForm = UseFormReturn<ComposerValues>;

interface Props {
  businessId: string;
  form: ComposerForm;
  /** Whether this member may mutate the draft at all (role + lifecycle). */
  canEdit: boolean;
}

/**
 * The brand surface of the draft (M4G-C, ADR-024 §2): the curated palette,
 * the curated typography pairing, the tenant accent, and the optional
 * decorative logo.
 *
 * All four are **tenant content**, not structure. They live in the
 * configuration's `theme`, they are edited by owners *and* managers, and
 * they travel through the one full-document draft save the composer
 * already performs — so they are versioned, published, archived, restored,
 * and snapshot-preserved by machinery that already exists. The structural
 * design variant is deliberately absent: it is platform-assigned, and the
 * workspace shows it as read-only metadata on the overview above.
 *
 * Nothing here previews. The saved-draft preview is a server projection of
 * the *saved* draft (ADR-022 §3), so a choice made here changes the
 * storefront only after Save draft — the swatch and type sample beside
 * each control are form affordances, not a rendering of the storefront.
 *
 * A member who cannot edit (a manager or owner of a closed business) gets
 * the same facts as a plain description list rather than disabled inputs:
 * a control that looks editable and refuses is worse than no control.
 */
export function BrandFields({ businessId, form, canEdit }: Props) {
  const client = useApiClient();
  const [picking, setPicking] = useState(false);

  const palette =
    useWatch({ control: form.control, name: 'palette' }) ?? DEFAULT_PALETTE;
  const typePairing =
    useWatch({ control: form.control, name: 'typePairing' }) ??
    DEFAULT_TYPE_PAIRING;
  const accent = useWatch({ control: form.control, name: 'accent' }) ?? '';
  const logo = useWatch({ control: form.control, name: 'logo' }) ?? null;

  // Subscribed during render on purpose: RHF's formState is a proxy, and a
  // value read only inside a handler is never tracked (the M4E trap).
  const { errors } = form.formState;
  const paletteError = errors.palette?.message;
  const pairingError = errors.typePairing?.message;
  const accentError = errors.accent?.message;
  const logoError = errors.logo?.message;

  const logoThumb =
    logo === null ? null : (
      <img
        src={client.media.fileUrl(businessId, logo.media_id, 'canonical')}
        // Decorative here for the same reason it is decorative on the
        // storefront: the label beside it already says what it is.
        alt=""
        width={72}
        height={72}
        className={styles.imageThumb}
      />
    );

  return (
    <>
      <fieldset className={styles.brandFieldset}>
        <legend>Brand and appearance</legend>

        {canEdit ? (
          <>
            <div className={styles.brandRow}>
              <SelectField
                id="palette-select"
                label="Color palette"
                hint="Platform-designed color schemes, each checked for readable contrast."
                error={paletteError}
                {...form.register('palette')}
              >
                {PALETTE_ORDER.map((id) => (
                  <option key={id} value={id}>
                    {brandChoiceText(PALETTE_CHOICES[id])}
                  </option>
                ))}
              </SelectField>
              <span
                className={styles.paletteSwatch}
                style={paletteSwatchStyle(palette)}
                aria-hidden="true"
              >
                Aa
              </span>
            </div>

            <div className={styles.brandRow}>
              <SelectField
                id="type-pairing-select"
                label="Typography"
                hint="Font pairings already on your visitors' devices — nothing is downloaded."
                error={pairingError}
                {...form.register('typePairing')}
              >
                {TYPE_PAIRING_ORDER.map((id) => (
                  <option key={id} value={id}>
                    {brandChoiceText(TYPE_PAIRING_CHOICES[id])}
                  </option>
                ))}
              </SelectField>
              <span
                className={styles.typeSample}
                style={typeSampleStyle(typePairing)}
                aria-hidden="true"
              >
                Aa
              </span>
            </div>

            <div className={styles.accentField}>
              <label htmlFor="accent-input">Accent color</label>
              <input
                id="accent-input"
                type="color"
                {...form.register('accent')}
              />
              <code>{accent}</code>
              {accentError !== undefined && (
                <p role="alert" className={styles.fieldErrorText}>
                  {accentError}
                </p>
              )}
            </div>

            <div className={styles.imageField}>
              <span className={styles.imageFieldLabel}>Logo (optional)</span>
              {logo === null ? (
                <div>
                  <button
                    type="button"
                    className={styles.secondary}
                    onClick={() => {
                      setPicking(true);
                    }}
                  >
                    Choose a logo
                  </button>
                </div>
              ) : (
                <div className={styles.imageRow}>
                  {logoThumb}
                  <span className={styles.imageAlt}>
                    Decorative — your business name is always shown as text
                  </span>
                  <div className={styles.actions}>
                    <button
                      type="button"
                      className={styles.secondary}
                      onClick={() => {
                        setPicking(true);
                      }}
                    >
                      Replace
                    </button>
                    <button
                      type="button"
                      className={styles.quiet}
                      onClick={() => {
                        // Only the reference goes. The asset stays in the
                        // library; nothing is deleted or unclaimed here.
                        form.setValue('logo', null, { shouldDirty: true });
                      }}
                    >
                      Remove
                    </button>
                  </div>
                </div>
              )}
              <p className={styles.note}>
                Your logo appears next to your business name. The name is never
                replaced.
              </p>
              {logoError !== undefined && (
                <p role="alert" className={styles.fieldErrorText}>
                  {logoError}
                </p>
              )}
            </div>
          </>
        ) : (
          <dl className={styles.statusList}>
            <dt>Color palette</dt>
            <dd>{brandChoiceText(PALETTE_CHOICES[palette])}</dd>
            <dt>Typography</dt>
            <dd>{brandChoiceText(TYPE_PAIRING_CHOICES[typePairing])}</dd>
            <dt>Accent color</dt>
            <dd>
              <span
                className={styles.accentSwatch}
                style={{ background: accent }}
                aria-hidden="true"
              />{' '}
              <code>{accent}</code>
            </dd>
            <dt>Logo</dt>
            <dd>
              {logo === null ? (
                'None'
              ) : (
                <span className={styles.imageRow}>
                  {logoThumb}
                  <span className={styles.imageAlt}>
                    Decorative — your business name is always shown as text
                  </span>
                </span>
              )}
            </dd>
          </dl>
        )}
      </fieldset>

      {picking && (
        <ThemeLogoDialog
          businessId={businessId}
          current={
            logo === null ? null : { assetId: logo.media_id, altText: null }
          }
          pending={false}
          error={null}
          canManageLibrary={canEdit}
          onCancel={() => {
            setPicking(false);
          }}
          onAttach={(assetId) => {
            // Staging only: the claim happens when the draft is saved, and
            // publication is what makes it public (ADR-020 §10).
            form.setValue('logo', { media_id: assetId }, { shouldDirty: true });
            setPicking(false);
          }}
        />
      )}
    </>
  );
}
