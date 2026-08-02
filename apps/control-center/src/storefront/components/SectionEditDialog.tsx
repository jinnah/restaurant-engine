import { useEffect, useState } from 'react';
import {
  useFieldArray,
  useForm,
  useWatch,
  type UseFormReturn,
} from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useApiClient } from '../../api/ClientProvider';
import { Dialog } from '../../components/Dialog';
import {
  CheckboxField,
  FormField,
  SelectField,
  TextAreaField,
} from '../../components/FormField';
import {
  SECTION_TYPE_LABELS,
  type ConfigSection,
  type SectionImageRef,
  type SectionType,
} from '../composition';
import { dialogFieldFor, type MappedFieldError } from '../fieldErrors';
import { MAX_ADDRESS_LINES, MAX_GALLERY_IMAGES } from '../limits';
import { StorefrontImageDialog } from './StorefrontImageDialog';
import styles from '../storefront.module.css';

/**
 * The dialog's editable model — a superset across the five section types;
 * the per-type Zod schema validates only the fields that type carries,
 * and the builder converts back to the canonical contract shape
 * (blank optional strings become null; required strings are trimmed).
 */
interface SectionFormValues {
  enabled: boolean;
  heading: string;
  subheading: string;
  primaryAction: 'none' | 'view_menu' | 'order_online';
  image: SectionImageRef | null;
  intro: string;
  body: string;
  addressLines: { value: string }[];
  phone: string;
  email: string;
  images: SectionImageRef[];
  showOpenNow: boolean;
}

const requiredText = (message: string) =>
  z.string().refine((value) => value.trim() !== '', message);

// UI shape only (ADR-022 §7): required, trimmed-nonempty, enum
// membership, and the two contract-published count bounds mirrored in
// limits.ts. No text-length bound is mirrored — the backend enforces
// those in validators the OpenAPI document does not publish, so the 422
// field errors are the authority and map back onto these same fields.
const baseShape = {
  enabled: z.boolean(),
  heading: z.string(),
  subheading: z.string(),
  primaryAction: z.enum(['none', 'view_menu', 'order_online']),
  image: z.custom<SectionImageRef | null>(() => true),
  intro: z.string(),
  body: z.string(),
  addressLines: z.array(z.object({ value: z.string() })),
  phone: z.string(),
  email: z.string(),
  images: z.array(z.custom<SectionImageRef>(() => true)),
  showOpenNow: z.boolean(),
};

function schemaFor(
  type: SectionType,
): z.ZodType<SectionFormValues, SectionFormValues> {
  switch (type) {
    case 'hero':
    case 'menu':
    case 'hours':
      return z.object({
        ...baseShape,
        heading: requiredText('Enter a heading.'),
      });
    case 'story':
      return z.object({
        ...baseShape,
        heading: requiredText('Enter a heading.'),
        body: requiredText('Enter the story text.'),
      });
    case 'contact':
      return z.object({
        ...baseShape,
        heading: requiredText('Enter a heading.'),
        addressLines: z
          .array(
            z.object({
              value: requiredText('Enter the address line, or remove it.'),
            }),
          )
          .max(MAX_ADDRESS_LINES),
      });
    case 'gallery':
      return z.object({
        ...baseShape,
        images: z
          .array(z.custom<SectionImageRef>(() => true))
          .max(MAX_GALLERY_IMAGES),
      });
  }
}

function formValuesFromSection(section: ConfigSection): SectionFormValues {
  const values: SectionFormValues = {
    enabled: section.enabled,
    heading: '',
    subheading: '',
    primaryAction: 'none',
    image: null,
    intro: '',
    body: '',
    addressLines: [],
    phone: '',
    email: '',
    images: [],
    showOpenNow: true,
  };
  switch (section.type) {
    case 'hero':
      values.heading = section.props.heading;
      values.subheading = section.props.subheading ?? '';
      values.primaryAction = section.props.primary_action;
      values.image =
        section.props.image === null || section.props.image === undefined
          ? null
          : {
              media_id: section.props.image.media_id,
              alt_text: section.props.image.alt_text ?? null,
            };
      break;
    case 'menu':
      values.heading = section.props.heading;
      values.intro = section.props.intro ?? '';
      break;
    case 'story':
      values.heading = section.props.heading;
      values.body = section.props.body;
      break;
    case 'contact':
      values.heading = section.props.heading;
      values.addressLines = (section.props.address_lines ?? []).map((line) => ({
        value: line,
      }));
      values.phone = section.props.phone ?? '';
      values.email = section.props.email ?? '';
      break;
    case 'gallery':
      values.heading = section.props.heading ?? '';
      values.images = (section.props.images ?? []).map((image) => ({
        media_id: image.media_id,
        alt_text: image.alt_text ?? null,
      }));
      break;
    case 'hours':
      values.heading = section.props.heading;
      values.intro = section.props.intro ?? '';
      values.showOpenNow = section.props.show_open_now ?? true;
      break;
  }
  return values;
}

const blankToNull = (value: string): string | null =>
  value.trim() === '' ? null : value.trim();

function buildSection(
  type: SectionType,
  id: string,
  data: SectionFormValues,
): ConfigSection {
  switch (type) {
    case 'hero':
      return {
        id,
        type,
        enabled: data.enabled,
        props: {
          heading: data.heading.trim(),
          subheading: blankToNull(data.subheading),
          image: data.image,
          primary_action: data.primaryAction,
        },
      };
    case 'menu':
      return {
        id,
        type,
        enabled: data.enabled,
        props: { heading: data.heading.trim(), intro: blankToNull(data.intro) },
      };
    case 'story':
      return {
        id,
        type,
        enabled: data.enabled,
        props: { heading: data.heading.trim(), body: data.body.trim() },
      };
    case 'contact':
      return {
        id,
        type,
        enabled: data.enabled,
        props: {
          heading: data.heading.trim(),
          address_lines: data.addressLines.map((line) => line.value.trim()),
          phone: blankToNull(data.phone),
          email: blankToNull(data.email),
        },
      };
    case 'gallery':
      return {
        id,
        type,
        enabled: data.enabled,
        props: { heading: blankToNull(data.heading), images: data.images },
      };
    case 'hours':
      return {
        id,
        type,
        enabled: data.enabled,
        props: {
          heading: data.heading.trim(),
          intro: blankToNull(data.intro),
          show_open_now: data.showOpenNow,
        },
      };
  }
}

interface Props {
  businessId: string;
  /** The section type being edited (fixed for the dialog's lifetime). */
  type: SectionType;
  /** The stored id to round-trip (or the new section's default). */
  sectionId: string;
  /** Deep snapshot of the parent's current value (or the add-mode seed). */
  initial: ConfigSection;
  mode: 'add' | 'edit';
  /** Server 422 errors for THIS section, paths relative to the section. */
  serverErrors: MappedFieldError[];
  canManageLibrary: boolean;
  onApply: (value: ConfigSection) => void;
  onCancel: () => void;
}

type SectionForm = UseFormReturn<SectionFormValues, unknown, SectionFormValues>;

function fieldError(form: SectionForm, name: string): string | undefined {
  return form.getFieldState(
    name as Parameters<UseFormReturn<SectionFormValues>['getFieldState']>[0],
    form.formState,
  ).error?.message;
}

/**
 * Focused section editing over the parent form (ADR-022 §4): this dialog
 * mounts its own isolated form seeded from a deep snapshot, renders no
 * nested native <form>, and commits exactly one complete section value on
 * Apply — Cancel/Escape discards only the dialog's uncommitted edits (a
 * dirty dialog asks first). Server errors recorded on the parent at this
 * section's indexed paths are injected into the corresponding fields
 * here, and clear when the field they name changes.
 *
 * The image picker is never nested inside this dialog: two modal focus
 * traps over one tree fight each other (the documented M3E hazard), so
 * while the picker is open it REPLACES this dialog on screen — the form
 * state lives in this component and survives the swap.
 */
export function SectionEditDialog({
  businessId,
  type,
  sectionId,
  initial,
  mode,
  serverErrors,
  canManageLibrary,
  onApply,
  onCancel,
}: Props) {
  const client = useApiClient();
  const form: SectionForm = useForm<
    SectionFormValues,
    unknown,
    SectionFormValues
  >({
    resolver: zodResolver(schemaFor(type)),
    defaultValues: formValuesFromSection(initial),
  });
  const addressLines = useFieldArray({
    control: form.control,
    name: 'addressLines',
  });
  const [picker, setPicker] = useState<
    { target: 'hero' } | { target: 'gallery'; index: number | null } | null
  >(null);
  const [confirmingDiscard, setConfirmingDiscard] = useState(false);
  // Injected server-error paths, computed once from the mount-time props
  // (the error set belongs to the payload that was saved) and thereafter
  // shrunk by change handlers.
  const [serverPaths, setServerPaths] = useState<ReadonlySet<string>>(() => {
    const injected = new Set<string>();
    for (const entry of serverErrors) {
      const field = dialogFieldFor(entry.path);
      if (field !== null) {
        injected.add(field);
      }
    }
    return injected;
  });
  const heroImage = useWatch({ control: form.control, name: 'image' });
  const galleryImages =
    useWatch({ control: form.control, name: 'images' }) ?? [];
  // Subscribed during render on purpose: RHF's formState is a proxy, and
  // dirtiness read only inside an event handler is never tracked.
  const { isDirty } = form.formState;

  // Inject the parent's server errors once on mount (reopen behavior).
  useEffect(() => {
    for (const entry of serverErrors) {
      const field = dialogFieldFor(entry.path);
      if (field !== null) {
        form.setError(field as Parameters<typeof form.setError>[0], {
          type: 'server',
          message: entry.message,
        });
      }
    }
    // Mount-only by design: the error set belongs to the payload that was
    // saved, not to anything that changes while the dialog is open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A server error clears when the field it names changes (ADR-022 §7):
  // local validation cannot re-confirm a domain judgment, so the message
  // goes when its input is edited and returns only from the next save.
  // Wired through register/handler `onChange` rather than a watch
  // subscription, so no unstable library callback is memoized.
  function clearServerError(changed: string) {
    const cleared = [...serverPaths].filter(
      (path) =>
        path === changed ||
        path.startsWith(`${changed}.`) ||
        changed.startsWith(`${path}.`),
    );
    if (cleared.length === 0) {
      return;
    }
    for (const path of cleared) {
      form.clearErrors(path as Parameters<typeof form.clearErrors>[0]);
    }
    setServerPaths(
      new Set([...serverPaths].filter((path) => !cleared.includes(path))),
    );
  }

  const registerClearing = (
    name: Parameters<typeof form.register>[0],
  ): ReturnType<typeof form.register> =>
    form.register(name, {
      onChange: () => {
        clearServerError(name);
      },
    });

  const label = SECTION_TYPE_LABELS[type];
  const title =
    mode === 'add' ? `Add ${label.toLowerCase()} section` : `${label} section`;

  function requestClose() {
    if (isDirty) {
      setConfirmingDiscard(true);
      return;
    }
    onCancel();
  }

  const apply = form.handleSubmit((data) => {
    onApply(buildSection(type, sectionId, data));
  });

  // While the picker is open it replaces this dialog entirely; the form
  // state stays alive in this component across the swap.
  if (picker !== null) {
    const current =
      picker.target === 'hero'
        ? form.getValues('image')
        : picker.index === null
          ? null
          : (form.getValues(`images.${picker.index}`) ?? null);
    return (
      <StorefrontImageDialog
        businessId={businessId}
        current={
          current === null
            ? null
            : { assetId: current.media_id, altText: current.alt_text ?? null }
        }
        pending={false}
        error={null}
        canManageLibrary={canManageLibrary}
        onCancel={() => {
          setPicker(null);
        }}
        onAttach={(assetId, altText) => {
          const staged: SectionImageRef = {
            media_id: assetId,
            alt_text: altText,
          };
          if (picker.target === 'hero') {
            form.setValue('image', staged, { shouldDirty: true });
            clearServerError('image');
          } else if (picker.index === null) {
            form.setValue('images', [...form.getValues('images'), staged], {
              shouldDirty: true,
            });
            clearServerError('images');
          } else {
            const next = [...form.getValues('images')];
            next[picker.index] = staged;
            form.setValue('images', next, { shouldDirty: true });
            clearServerError('images');
          }
          setPicker(null);
        }}
      />
    );
  }

  return (
    <Dialog title={title} onCancel={requestClose}>
      {confirmingDiscard ? (
        <div>
          <p>Discard your changes to this section?</p>
          <p className={styles.note}>
            Only this dialog&rsquo;s edits are discarded — everything already in
            the editor stays.
          </p>
          <div className={styles.actions}>
            <button type="button" className={styles.danger} onClick={onCancel}>
              Discard changes
            </button>
            <button
              type="button"
              className={styles.secondary}
              onClick={() => {
                setConfirmingDiscard(false);
              }}
            >
              Keep editing
            </button>
          </div>
        </div>
      ) : (
        <>
          {(type === 'hero' ||
            type === 'menu' ||
            type === 'story' ||
            type === 'contact' ||
            type === 'hours') && (
            <FormField
              id="section-heading"
              label="Heading"
              error={fieldError(form, 'heading')}
              {...registerClearing('heading')}
            />
          )}
          {type === 'gallery' && (
            <FormField
              id="section-heading"
              label="Heading (optional)"
              error={fieldError(form, 'heading')}
              {...registerClearing('heading')}
            />
          )}

          {type === 'hero' && (
            <>
              <FormField
                id="section-subheading"
                label="Supporting line (optional)"
                error={fieldError(form, 'subheading')}
                {...registerClearing('subheading')}
              />
              <SelectField
                id="section-action"
                label="Button"
                hint='"View menu" links to your menu page. "Order online" shows only while online ordering is available; otherwise visitors see the menu link.'
                error={fieldError(form, 'primaryAction')}
                {...registerClearing('primaryAction')}
              >
                <option value="none">No button</option>
                <option value="view_menu">View menu</option>
                <option value="order_online">Order online</option>
              </SelectField>
              <div className={styles.imageField}>
                <span className={styles.imageFieldLabel}>Photo (optional)</span>
                {heroImage === null ? (
                  <button
                    type="button"
                    className={styles.secondary}
                    onClick={() => {
                      setPicker({ target: 'hero' });
                    }}
                  >
                    Choose a photo
                  </button>
                ) : (
                  <div className={styles.imageRow}>
                    <img
                      src={client.media.fileUrl(
                        businessId,
                        heroImage.media_id,
                        'canonical',
                      )}
                      alt=""
                      width={72}
                      height={72}
                      className={styles.imageThumb}
                    />
                    <span className={styles.imageAlt}>
                      {heroImage.alt_text === null
                        ? 'Marked decorative'
                        : heroImage.alt_text}
                    </span>
                    <div className={styles.actions}>
                      <button
                        type="button"
                        className={styles.secondary}
                        onClick={() => {
                          setPicker({ target: 'hero' });
                        }}
                      >
                        Replace
                      </button>
                      <button
                        type="button"
                        className={styles.quiet}
                        onClick={() => {
                          form.setValue('image', null, { shouldDirty: true });
                        }}
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                )}
                {fieldError(form, 'image') !== undefined && (
                  <p role="alert" className={styles.fieldErrorText}>
                    {fieldError(form, 'image')}
                  </p>
                )}
              </div>
            </>
          )}

          {(type === 'menu' || type === 'hours') && (
            <TextAreaField
              id="section-intro"
              label="Introduction (optional)"
              rows={3}
              error={fieldError(form, 'intro')}
              {...registerClearing('intro')}
            />
          )}

          {type === 'hours' && (
            <>
              <CheckboxField
                id="section-show-open-now"
                label="Show whether you're open right now"
                hint="The live status comes from your hours; visitors see it update automatically."
                defaultChecked={form.getValues('showOpenNow')}
                onChange={(event) => {
                  form.setValue('showOpenNow', event.target.checked, {
                    shouldDirty: true,
                  });
                  clearServerError('showOpenNow');
                }}
              />
              <p className={styles.note}>
                Your weekly schedule, special dates, and open/closed status come
                from the Hours page — this section only chooses how they are
                introduced.
              </p>
            </>
          )}

          {type === 'story' && (
            <TextAreaField
              id="section-body"
              label="Story"
              hint="Blank lines separate paragraphs."
              rows={8}
              error={fieldError(form, 'body')}
              {...registerClearing('body')}
            />
          )}

          {type === 'contact' && (
            <>
              <fieldset className={styles.groupFieldset}>
                <legend>Address (optional)</legend>
                {addressLines.fields.map((line, index) => (
                  <div key={line.id} className={styles.lineRow}>
                    <FormField
                      id={`address-line-${String(index)}`}
                      label={`Line ${String(index + 1)}`}
                      error={fieldError(form, `addressLines.${index}.value`)}
                      {...registerClearing(`addressLines.${index}.value`)}
                    />
                    <button
                      type="button"
                      className={styles.quiet}
                      aria-label={`Remove address line ${String(index + 1)}`}
                      onClick={() => {
                        addressLines.remove(index);
                      }}
                    >
                      Remove
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  className={styles.secondary}
                  disabled={addressLines.fields.length >= MAX_ADDRESS_LINES}
                  onClick={() => {
                    addressLines.append({ value: '' });
                  }}
                >
                  Add address line
                </button>
                {addressLines.fields.length >= MAX_ADDRESS_LINES && (
                  <p className={styles.note}>
                    An address can have up to {MAX_ADDRESS_LINES} lines.
                  </p>
                )}
              </fieldset>
              <FormField
                id="section-phone"
                label="Phone (optional)"
                autoComplete="tel"
                error={fieldError(form, 'phone')}
                {...registerClearing('phone')}
              />
              <FormField
                id="section-email"
                label="Email (optional)"
                autoComplete="email"
                error={fieldError(form, 'email')}
                {...registerClearing('email')}
              />
            </>
          )}

          {type === 'gallery' && (
            <div className={styles.imageField}>
              <span className={styles.imageFieldLabel}>Photos</span>
              {galleryImages.length === 0 ? (
                <p className={styles.note}>No photos yet.</p>
              ) : (
                <ul className={styles.galleryRows}>
                  {galleryImages.map((image, index) => (
                    <li
                      key={`${image.media_id}-${String(index)}`}
                      className={styles.imageRow}
                    >
                      <img
                        src={client.media.fileUrl(
                          businessId,
                          image.media_id,
                          'canonical',
                        )}
                        alt=""
                        width={72}
                        height={72}
                        className={styles.imageThumb}
                      />
                      <span className={styles.imageAlt}>
                        {image.alt_text === null || image.alt_text === undefined
                          ? 'Marked decorative'
                          : image.alt_text}
                      </span>
                      <div className={styles.actions}>
                        <button
                          type="button"
                          className={styles.quiet}
                          disabled={index === 0}
                          aria-label={`Move photo ${String(index + 1)} up`}
                          onClick={() => {
                            const next = [...form.getValues('images')];
                            const [moved] = next.splice(index, 1);
                            if (moved !== undefined) {
                              next.splice(index - 1, 0, moved);
                              form.setValue('images', next, {
                                shouldDirty: true,
                              });
                            }
                          }}
                        >
                          Move up
                        </button>
                        <button
                          type="button"
                          className={styles.quiet}
                          disabled={index === galleryImages.length - 1}
                          aria-label={`Move photo ${String(index + 1)} down`}
                          onClick={() => {
                            const next = [...form.getValues('images')];
                            const [moved] = next.splice(index, 1);
                            if (moved !== undefined) {
                              next.splice(index + 1, 0, moved);
                              form.setValue('images', next, {
                                shouldDirty: true,
                              });
                            }
                          }}
                        >
                          Move down
                        </button>
                        <button
                          type="button"
                          className={styles.secondary}
                          aria-label={`Change photo ${String(index + 1)}`}
                          onClick={() => {
                            setPicker({ target: 'gallery', index });
                          }}
                        >
                          Change
                        </button>
                        <button
                          type="button"
                          className={styles.quiet}
                          aria-label={`Remove photo ${String(index + 1)}`}
                          onClick={() => {
                            form.setValue(
                              'images',
                              form
                                .getValues('images')
                                .filter((_, i) => i !== index),
                              { shouldDirty: true },
                            );
                          }}
                        >
                          Remove
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              <button
                type="button"
                className={styles.secondary}
                disabled={galleryImages.length >= MAX_GALLERY_IMAGES}
                onClick={() => {
                  setPicker({ target: 'gallery', index: null });
                }}
              >
                Add photo
              </button>
              {galleryImages.length >= MAX_GALLERY_IMAGES && (
                <p className={styles.note}>
                  A gallery can show up to {MAX_GALLERY_IMAGES} photos.
                </p>
              )}
              {fieldError(form, 'images') !== undefined && (
                <p role="alert" className={styles.fieldErrorText}>
                  {fieldError(form, 'images')}
                </p>
              )}
            </div>
          )}

          <CheckboxField
            id="section-enabled"
            label="Show this section on the storefront"
            hint="Hidden sections stay in the draft but never render publicly."
            defaultChecked={form.getValues('enabled')}
            onChange={(event) => {
              form.setValue('enabled', event.target.checked, {
                shouldDirty: true,
              });
              clearServerError('enabled');
            }}
          />

          <p className={styles.note}>
            Changes are kept in the editor until you save the draft.
          </p>
          <div className={styles.actions}>
            <button
              type="button"
              className={styles.secondary}
              onClick={requestClose}
            >
              Cancel
            </button>
            <button
              type="button"
              className={styles.submit}
              onClick={() => {
                void apply();
              }}
            >
              Apply
            </button>
          </div>
        </>
      )}
    </Dialog>
  );
}
