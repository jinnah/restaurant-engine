import { useState } from 'react';
import type {
  DesignAssignmentResult,
  DesignVariant,
} from '@restaurant-engine/api-client';
import { asApiFailure } from '../api/failure';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { mapFailure, type FormFailure } from '../components/formErrors';
import { ErrorSummary } from '../components/StatusPanels';
import { useSetDesign } from './businessData';
import styles from './platform.module.css';

/**
 * The platform-facing naming of the structural design registry.
 *
 * Keyed by the generated contract union, so a fourth variant added to the
 * backend registry fails this file's typecheck until it is named — the
 * same discipline the renderer's exhaustive dispatch uses, applied to the
 * one surface that assigns them. The record's own key order is the offer
 * order; `classic` is the platform default and leads.
 */
const VARIANT_CHOICES: Record<
  DesignVariant,
  { label: string; description: string }
> = {
  classic: {
    label: 'Classic',
    description:
      'Warm and familiar, with a clear hierarchy and an image-first static hero.',
  },
  editorial: {
    label: 'Editorial',
    description:
      'Premium typography, larger imagery, spacious composition, and the strongest scroll-linked storytelling.',
  },
  express: {
    label: 'Express',
    description:
      'Compact and action-oriented: the menu and primary action lead, with dense spacing and minimal motion.',
  },
};

const VARIANT_ORDER = Object.keys(VARIANT_CHOICES) as DesignVariant[];

/**
 * What the server actually did, in its own terms.
 *
 * The three acknowledgments are genuinely different outcomes and are
 * reported as such. `previous_variant: null` is the first-draft creation
 * path (§5.7) — state came into existence. An equal previous and new
 * variant is the command's **exact no-op**: no mutation, no lock
 * increment, no audit event, so calling it a change would be false.
 */
function assignmentMessage(result: DesignAssignmentResult): string {
  const assigned = VARIANT_CHOICES[result.design_variant].label;
  if (result.previous_variant === null) {
    return `Created the first storefront draft and assigned the ${assigned} design.`;
  }
  if (result.previous_variant === result.design_variant) {
    return `${assigned} was already assigned. No changes were made.`;
  }
  const previous = VARIANT_CHOICES[result.previous_variant].label;
  return `Design changed from ${previous} to ${assigned}.`;
}

/**
 * The first platform design-assignment UI (M4G-C, ADR-024 §2).
 *
 * The structural variant is platform authority (blueprint §12.3): this is
 * the only write path, and owners never submit one — their workspace shows
 * the variant as read-only metadata.
 *
 * **No current variant is shown, and none is preselected.** The platform
 * business representation does not carry it, and a platform administrator
 * holds no storefront read at all (ADR-020 §7) — so there is no value here
 * that could be displayed honestly. Rather than infer one, guess a
 * default, or reach for a read this role is denied, the panel presents
 * itself as a command and says plainly where the current design *is*
 * visible. The acknowledgment after a successful assignment is the only
 * fact it states about what was there before.
 */
export function DesignAssignmentPanel({ businessId }: { businessId: string }) {
  const assign = useSetDesign(businessId);
  const [selected, setSelected] = useState<DesignVariant | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState<DesignAssignmentResult | null>(null);
  const [failure, setFailure] = useState<FormFailure | null>(null);

  function runAssignment(variant: DesignVariant) {
    if (assign.isPending) {
      return;
    }
    setFailure(null);
    assign.mutate(
      { design_variant: variant },
      {
        onSuccess: (acknowledgment) => {
          setConfirming(false);
          setResult(acknowledgment);
        },
        onError: (error: unknown) => {
          setConfirming(false);
          setResult(null);
          setFailure(
            mapFailure(
              asApiFailure(error),
              'The design could not be assigned.',
            ),
          );
        },
      },
    );
  }

  return (
    <section className={styles.section} aria-labelledby="design-title">
      <h2 id="design-title">Design</h2>
      {failure !== null && <ErrorSummary failure={failure} />}
      <p className={styles.hint}>
        The structural design is assigned by the platform. The design this
        business currently uses is not shown here — platform administrators have
        no access to a business&rsquo;s storefront content. Its owner sees it as
        read-only information in their storefront workspace.
      </p>

      <fieldset className={styles.choiceFieldset}>
        <legend>Assign a design</legend>
        {VARIANT_ORDER.map((variant) => {
          const inputId = `design-${variant}`;
          const hintId = `${inputId}-hint`;
          return (
            <div className={styles.check} key={variant}>
              <input
                id={inputId}
                type="radio"
                name="design-variant"
                value={variant}
                checked={selected === variant}
                aria-describedby={hintId}
                disabled={assign.isPending}
                onChange={() => {
                  setSelected(variant);
                }}
              />
              <div>
                <label htmlFor={inputId}>
                  {VARIANT_CHOICES[variant].label}
                </label>
                <p id={hintId} className={styles.hint}>
                  {VARIANT_CHOICES[variant].description}
                </p>
              </div>
            </div>
          );
        })}
      </fieldset>

      {result !== null && (
        <p role="status" className={styles.hint}>
          {assignmentMessage(result)}
        </p>
      )}

      <div className={styles.actions}>
        <button
          type="button"
          className={styles.submit}
          disabled={selected === null || assign.isPending}
          onClick={() => {
            setResult(null);
            setFailure(null);
            setConfirming(true);
          }}
        >
          Assign design
        </button>
      </div>

      {confirming && selected !== null && (
        <ConfirmDialog
          title="Assign this design?"
          confirmLabel="Assign design"
          pending={assign.isPending}
          onConfirm={() => {
            runAssignment(selected);
          }}
          onCancel={() => {
            setConfirming(false);
          }}
        >
          <p>
            Assigning <strong>{VARIANT_CHOICES[selected].label}</strong> changes
            the structural design of this business&rsquo;s saved storefront
            draft.
          </p>
          <p>
            If this business has no storefront draft yet, this creates the first
            one from the platform defaults. If {VARIANT_CHOICES[selected].label}{' '}
            is already assigned, nothing changes.
          </p>
          <p>
            The design becomes public only when an owner publishes the draft.
          </p>
        </ConfirmDialog>
      )}
    </section>
  );
}
