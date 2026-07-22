import { useNavigate } from 'react-router';
import type { MembershipSummary } from '@restaurant-engine/api-client';
import { useCurrentBusinessId } from './useCurrentBusinessId';
import styles from './switcher.module.css';

/**
 * Lifecycle is part of the option label rather than a colour, because a
 * native <option> renders text and nothing else — which makes the status
 * colour-independent by construction. An active business shows no status
 * word: absence means normal, matching the item chips in the menu.
 */
function optionLabel(membership: MembershipSummary): string {
  const suffix =
    membership.business_status === 'active'
      ? ''
      : ` · ${membership.business_status}`;
  return `${membership.business_name} — ${membership.role}${suffix}`;
}

/**
 * The current-business switcher (ADR-018 ruling 2).
 *
 * A native <select>, deliberately: arrow keys, Home/End, type-ahead, and
 * Escape are correct in every browser without a line of code, and on a phone
 * the operating system renders its own picker — which beats any custom
 * listbox at 320px, the width M3's exit criterion is judged at.
 *
 * Options come only from the session's memberships, and the value is derived
 * from the route, never from state. A business the session does not contain
 * cannot appear here, so a platform administrator — who holds no memberships
 * by architecture (ADR-011) — sees no switcher and gains no implicit access.
 * This is navigation, not authorization: the API stays the boundary.
 */
export function BusinessSwitcher({
  memberships,
}: {
  memberships: MembershipSummary[];
}) {
  const navigate = useNavigate();
  const currentId = useCurrentBusinessId();

  if (memberships.length === 0) {
    // Nothing to switch between. The home page already explains why.
    return null;
  }

  // A route id the session does not contain selects the placeholder rather
  // than inventing an option for it; the guard below has already rendered
  // the neutral not-found page in the outlet.
  const known = memberships.some(
    (membership) => membership.business_id === currentId,
  );
  const value = currentId !== null && known ? currentId : '';

  return (
    <div className={styles.switcher}>
      <label htmlFor="business-switcher">Business</label>
      <select
        id="business-switcher"
        value={value}
        onChange={(event) => {
          const next = event.target.value;
          if (next !== '') {
            void navigate(`/businesses/${next}/menu`);
          }
        }}
      >
        <option value="" disabled={value !== ''}>
          — Choose a business —
        </option>
        {memberships.map((membership) => (
          <option key={membership.business_id} value={membership.business_id}>
            {optionLabel(membership)}
          </option>
        ))}
      </select>
    </div>
  );
}
