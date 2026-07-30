import { useState } from 'react';
import { useFieldArray, useForm, useWatch } from 'react-hook-form';
import { useQueryClient } from '@tanstack/react-query';
import { asApiFailure } from '../../api/failure';
import { classifyFailure } from '../../api/failures';
import type { FormFailure } from '../../components/formErrors';
import { useNotify } from '../../components/NotificationProvider';
import { ErrorSummary } from '../../components/StatusPanels';
import { UnsavedChangesPrompt } from '../../components/UnsavedChangesPrompt';
import {
  composerValuesFromConfig,
  defaultSectionValues,
  SECTION_TYPES,
  SECTION_TYPE_LABELS,
  toDraftPut,
  type ComposerValues,
  type SectionType,
} from '../composition';
import { mapDraftSaveFailure, type MappedFieldError } from '../fieldErrors';
import type { StorefrontPermissions } from '../permissions';
import {
  markOverviewStale,
  useSaveDraft,
  useStorefrontOverview,
} from '../storefrontData';
import { SectionCard } from './SectionCard';
import { SectionEditDialog } from './SectionEditDialog';
import styles from '../storefront.module.css';

type DialogState =
  { mode: 'add'; type: SectionType } | { mode: 'edit'; index: number } | null;

interface ConflictState {
  message: string;
  /** The current server lock version when the 409 carried one. */
  serverLock: number | null;
}

/**
 * The draft composer (ADR-022 §4): ONE parent React Hook Form holding the
 * complete configuration, summary cards with focused edit dialogs, and
 * one explicit Save Draft performing the full-document PUT with the D-5
 * intent (no cached draft → create by omission; otherwise the saved
 * draft's exact lock version). No autosave, no optimistic update, no
 * silent retry or merge — a stale write enters the §6 conflict state,
 * which preserves the form values and the stale token, disables further
 * mutations, and offers only the explicit "Reload current draft" exit.
 *
 * The form is seeded from `defaultValues` once at mount and reset only by
 * a successful save (to the server-normalized result) or the explicit
 * reload — background refetches can never rebind it.
 */
export function DraftComposer({
  businessId,
  permissions,
}: {
  businessId: string;
  permissions: StorefrontPermissions;
}) {
  const queryClient = useQueryClient();
  const notify = useNotify();
  const overview = useStorefrontOverview(businessId, permissions.canRead);
  const saveDraft = useSaveDraft(businessId);

  const draft = overview.data?.draft ?? null;
  const form = useForm<ComposerValues>({
    defaultValues: composerValuesFromConfig(draft?.config ?? null),
  });
  const sections = useFieldArray({ control: form.control, name: 'sections' });

  const watchedSections = useWatch({
    control: form.control,
    name: 'sections',
  });
  const watchedAccent = useWatch({ control: form.control, name: 'accent' });

  const [dialog, setDialog] = useState<DialogState>(null);
  const [serverErrors, setServerErrors] = useState<MappedFieldError[]>([]);
  const [summary, setSummary] = useState<FormFailure | null>(null);
  const [conflict, setConflict] = useState<ConflictState | null>(null);

  if (overview.data === undefined) {
    return null; // The page renders the composer only after the overview.
  }

  const sectionsValue = watchedSections ?? [];
  const accentValue = watchedAccent ?? '';
  const presentTypes = new Set(sectionsValue.map((section) => section.type));
  const missingTypes = SECTION_TYPES.filter((type) => !presentTypes.has(type));
  const canEdit = permissions.canEdit && conflict === null;

  function sectionServerErrors(index: number): MappedFieldError[] {
    const prefix = `sections.${String(index)}.`;
    return serverErrors
      .filter((entry) => entry.path.startsWith(prefix))
      .map((entry) => ({
        path: entry.path.slice(prefix.length),
        message: entry.message,
      }));
  }

  /** Structural mutations orphan indexed server errors; drop them all. */
  function clearSectionServerErrors() {
    setServerErrors((previous) =>
      previous.filter((entry) => !entry.path.startsWith('sections.')),
    );
  }

  const save = form.handleSubmit((submitted) => {
    setSummary(null);
    saveDraft.mutate(toDraftPut(submitted, draft?.lock_version ?? null), {
      onSuccess: (saved) => {
        setServerErrors([]);
        form.clearErrors();
        // The baseline becomes the server-normalized result, pristine.
        form.reset(composerValuesFromConfig(saved.config));
        notify({ message: 'Draft saved.' });
      },
      onError: (error: unknown) => {
        const failure = asApiFailure(error);
        const kind = classifyFailure(failure);
        if (kind === 'conflict') {
          // §6: preserve values and the stale token; mark the overview
          // stale WITHOUT refetching; nothing is retried or merged.
          setConflict({
            message: failure.message,
            serverLock: conflictLimitLockVersion(failure),
          });
          markOverviewStale(queryClient, businessId);
          return;
        }
        if (kind === 'invalid') {
          const mapped = mapDraftSaveFailure(
            failure,
            submitted.sections.map((section) => section.type),
          );
          setServerErrors(mapped.fields);
          for (const field of mapped.fields) {
            if (field.path === 'accent') {
              form.setError('accent', {
                type: 'server',
                message: field.message,
              });
            }
          }
          setSummary({
            summary:
              mapped.unmapped.length > 0
                ? mapped.unmapped.join(' ')
                : 'Some fields need attention. Open the affected section to fix them.',
            fields: {},
          });
          return;
        }
        setSummary({ summary: failure.message, fields: {} });
      },
    });
  });

  async function reloadDraft() {
    const result = await overview.refetch();
    const freshDraft = result.data?.draft ?? null;
    form.reset(composerValuesFromConfig(freshDraft?.config ?? null));
    setServerErrors([]);
    setSummary(null);
    form.clearErrors();
    setConflict(null);
  }

  const accentError = form.formState.errors.accent?.message;

  return (
    <section aria-labelledby="composer-title" className={styles.panel}>
      <h3 id="composer-title">Draft</h3>

      {conflict !== null && (
        <div role="alert" className={styles.conflictPanel}>
          <p>
            <strong>This draft changed somewhere else.</strong>{' '}
            {conflict.message}
            {conflict.serverLock !== null &&
              ` (the saved draft is now at version ${String(conflict.serverLock)})`}
          </p>
          <p>
            Your edits are still here, but they can’t be saved over the newer
            draft. Reloading replaces everything in this editor with the current
            saved draft — your unsaved edits will be lost.
          </p>
          <button
            type="button"
            className={styles.secondary}
            onClick={() => {
              void reloadDraft();
            }}
          >
            Reload current draft
          </button>
        </div>
      )}

      {summary !== null && <ErrorSummary failure={summary} />}

      {sectionsValue.length === 0 ? (
        <p className={styles.note}>
          No sections yet. Add your first section below — your storefront
          renders your business name and navigation even without sections.
        </p>
      ) : (
        <ul className={styles.sectionRows}>
          {sectionsValue.map((section, index) => (
            <SectionCard
              key={section.type}
              section={section}
              index={index}
              count={sectionsValue.length}
              serverErrorCount={sectionServerErrors(index).length}
              canEdit={canEdit}
              onEdit={() => {
                setDialog({ mode: 'edit', index });
              }}
              onRemove={() => {
                sections.remove(index);
                clearSectionServerErrors();
              }}
              onMoveUp={() => {
                sections.move(index, index - 1);
                clearSectionServerErrors();
              }}
              onMoveDown={() => {
                sections.move(index, index + 1);
                clearSectionServerErrors();
              }}
              onToggleEnabled={(enabled) => {
                form.setValue(`sections.${index}.enabled`, enabled, {
                  shouldDirty: true,
                });
                clearSectionServerErrors();
              }}
            />
          ))}
        </ul>
      )}

      {canEdit && missingTypes.length > 0 && (
        <div className={styles.addRow}>
          {missingTypes.map((type) => (
            <button
              key={type}
              type="button"
              className={styles.secondary}
              onClick={() => {
                setDialog({ mode: 'add', type });
              }}
            >
              Add {SECTION_TYPE_LABELS[type].toLowerCase()} section
            </button>
          ))}
        </div>
      )}

      <div className={styles.accentField}>
        <label htmlFor="accent-input">Accent color</label>
        {canEdit ? (
          <input id="accent-input" type="color" {...form.register('accent')} />
        ) : (
          <span
            className={styles.accentSwatch}
            style={{ background: accentValue }}
            aria-hidden="true"
          />
        )}
        <code>{accentValue}</code>
        {accentError !== undefined && (
          <p role="alert" className={styles.fieldErrorText}>
            {accentError}
          </p>
        )}
      </div>

      {permissions.canEdit && (
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.submit}
            disabled={saveDraft.isPending || conflict !== null}
            onClick={() => {
              void save();
            }}
          >
            {saveDraft.isPending ? 'Saving…' : 'Save draft'}
          </button>
          {form.formState.isDirty && !saveDraft.isPending && (
            <span className={styles.note} role="status">
              You have unsaved changes.
            </span>
          )}
        </div>
      )}

      {dialog !== null && (
        <SectionEditDialog
          businessId={businessId}
          type={
            dialog.mode === 'add'
              ? dialog.type
              : (sectionsValue[dialog.index]?.type ?? 'hero')
          }
          sectionId={
            dialog.mode === 'add'
              ? defaultSectionValues(dialog.type).id
              : (sectionsValue[dialog.index]?.id ??
                defaultSectionValues('hero').id)
          }
          initial={structuredClone(
            dialog.mode === 'add'
              ? defaultSectionValues(dialog.type)
              : (sectionsValue[dialog.index] ?? defaultSectionValues('hero')),
          )}
          mode={dialog.mode}
          serverErrors={
            dialog.mode === 'edit' ? sectionServerErrors(dialog.index) : []
          }
          canManageLibrary={permissions.canEdit}
          onCancel={() => {
            setDialog(null);
          }}
          onApply={(value) => {
            if (dialog.mode === 'add') {
              sections.append(value);
              clearSectionServerErrors();
            } else {
              form.setValue(`sections.${dialog.index}`, value, {
                shouldDirty: true,
                shouldValidate: true,
                shouldTouch: true,
              });
              setServerErrors((previous) =>
                previous.filter(
                  (entry) =>
                    !entry.path.startsWith(`sections.${String(dialog.index)}.`),
                ),
              );
            }
            setDialog(null);
          }}
        />
      )}

      <UnsavedChangesPrompt
        when={form.formState.isDirty && !saveDraft.isPending}
        message="Your storefront draft has unsaved changes."
      />
    </section>
  );
}

/**
 * The current `lock_version` a stale-write 409 carries in its envelope
 * details (M4B contract). Narrowed, never trusted.
 */
function conflictLimitLockVersion(
  failure: ReturnType<typeof asApiFailure>,
): number | null {
  const details = failure.envelope?.error.details;
  if (details === null || details === undefined) {
    return null;
  }
  const lock = (details as Record<string, unknown>)['lock_version'];
  return typeof lock === 'number' && Number.isInteger(lock) && lock >= 0
    ? lock
    : null;
}
