import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import type { BusinessSummary } from '@restaurant-engine/api-client';
import { asApiFailure, type ApiFailure } from '../api/failure';
import { mapFailure, type FormFailure } from '../components/formErrors';
import { ErrorSummary, SuccessPanel } from '../components/StatusPanels';
import { useCreateBusiness, usePlatformBusinesses } from './businessData';
import { FormField } from './FormField';
import { statusBadgeClass } from './statusBadge';
import styles from './platform.module.css';

const PAGE_SIZE = 25;
const CREATE_FALLBACK = 'The business could not be created.';

/**
 * A 409 on creation is the slug uniqueness conflict (the only creation
 * conflict the backend defines), so it is surfaced on the slug field.
 */
function mapCreateFailure(failure: ApiFailure): FormFailure {
  if (failure.status === 409) {
    return {
      summary: 'Some fields need attention.',
      fields: {
        slug: failure.envelope?.error.message ?? 'That slug is already taken.',
      },
    };
  }
  return mapFailure(failure, CREATE_FALLBACK);
}

export function BusinessesListPage() {
  const [offset, setOffset] = useState(0);
  const businesses = usePlatformBusinesses({ limit: PAGE_SIZE, offset });

  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [failure, setFailure] = useState<FormFailure | null>(null);
  const [created, setCreated] = useState<BusinessSummary | null>(null);
  const create = useCreateBusiness();

  useEffect(() => {
    document.title = 'Businesses — Restaurant Engine';
  }, []);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (create.isPending) {
      return;
    }
    setFailure(null);
    setCreated(null);
    create.mutate(
      { name, slug },
      {
        onSuccess: (business) => {
          setName('');
          setSlug('');
          setCreated(business);
        },
        onError: (error: unknown) => {
          setFailure(mapCreateFailure(asApiFailure(error)));
        },
      },
    );
  }

  return (
    <div>
      <section className={styles.section} aria-labelledby="create-business">
        <h2 id="create-business">Create a business</h2>
        <p className={styles.hint}>
          The business starts in provisioning. Currency and timezone use the
          platform defaults; the slug becomes its subdomain.
        </p>
        {failure !== null && <ErrorSummary failure={failure} />}
        {created !== null && (
          <SuccessPanel heading="Business created">
            <p>
              <strong>{created.name}</strong> ({created.slug}) is provisioning.
              Invite an owner from its detail page, then activate it.
            </p>
          </SuccessPanel>
        )}
        <form noValidate onSubmit={onSubmit}>
          <FormField
            id="business-name"
            label="Name"
            name="name"
            type="text"
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
            error={failure?.fields['name']}
          />
          <FormField
            id="business-slug"
            label="Slug"
            name="slug"
            type="text"
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            required
            value={slug}
            onChange={(event) => setSlug(event.target.value)}
            error={failure?.fields['slug']}
          />
          <button
            type="submit"
            className={styles.submit}
            disabled={create.isPending}
          >
            {create.isPending ? 'Creating…' : 'Create business'}
          </button>
        </form>
      </section>

      <section className={styles.section} aria-labelledby="all-businesses">
        <h2 id="all-businesses">All businesses</h2>
        {businesses.isPending && (
          <p role="status" className={styles.loading}>
            Loading businesses…
          </p>
        )}
        {businesses.isError && (
          <div role="alert" className={styles.errorPanel}>
            <p>The businesses list could not be loaded.</p>
            <button
              type="button"
              className={styles.secondary}
              onClick={() => {
                void businesses.refetch();
              }}
            >
              Try again
            </button>
          </div>
        )}
        {businesses.isSuccess && businesses.data.items.length === 0 && (
          <p className={styles.empty}>
            No businesses exist yet. Create the first one above.
          </p>
        )}
        {businesses.isSuccess && businesses.data.items.length > 0 && (
          <>
            <ul className={styles.list}>
              {businesses.data.items.map((business) => (
                <li key={business.id} className={styles.row}>
                  <Link
                    to={`/platform/businesses/${business.id}`}
                    className={styles.rowLink}
                  >
                    {business.name}{' '}
                    <span className={styles.slug}>({business.slug})</span>
                  </Link>
                  <span className={statusBadgeClass(business.status)}>
                    {business.status}
                  </span>
                </li>
              ))}
            </ul>
            <div className={styles.pager}>
              <button
                type="button"
                className={styles.secondary}
                disabled={offset === 0}
                onClick={() => {
                  setOffset(Math.max(0, offset - PAGE_SIZE));
                }}
              >
                Previous
              </button>
              <p className={styles.pagerInfo}>
                Showing {offset + 1}–{offset + businesses.data.items.length} of{' '}
                {businesses.data.total}
              </p>
              <button
                type="button"
                className={styles.secondary}
                disabled={offset + PAGE_SIZE >= businesses.data.total}
                onClick={() => {
                  setOffset(offset + PAGE_SIZE);
                }}
              >
                Next
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
