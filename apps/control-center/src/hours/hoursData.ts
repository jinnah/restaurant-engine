import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type {
  FulfillmentSet,
  ScheduleExceptionSet,
  WeeklyScheduleSet,
} from '@restaurant-engine/api-client';
import { useApiClient } from '../api/ClientProvider';
import { asApiFailure } from '../api/failure';
import { requireCsrf, unwrapPrivileged } from '../api/failures';
import type { FormFailure } from '../components/formErrors';
import { hoursKeys } from './keys';

/**
 * The complete operating configuration in one read (ADR-025): timezone,
 * weekly schedule, windowed exceptions, effective fulfillment settings.
 * Readable by every role — hours reads ride on `business.view` (D7).
 */
export function useHoursSettings(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: hoursKeys.settings(businessId),
    queryFn: async () =>
      unwrapPrivileged(queryClient, await client.hours.get(businessId)),
  });
}

/**
 * Replace the whole weekly schedule (idempotent full replacement). The
 * response is the complete updated settings document, written wholesale
 * into the one settings key — there is nothing partial to merge.
 */
export function useSetWeekly(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: WeeklyScheduleSet) =>
      unwrapPrivileged(
        queryClient,
        await client.hours.setWeekly(
          businessId,
          body,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: (settings) => {
      queryClient.setQueryData(hoursKeys.settings(businessId), settings);
    },
  });
}

/**
 * Create or replace one date's override. `intervals: []` means closed all
 * day; removing the override entirely is the delete mutation below.
 */
export function useSetException(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: { date: string; body: ScheduleExceptionSet }) =>
      unwrapPrivileged(
        queryClient,
        await client.hours.setException(
          businessId,
          input.date,
          input.body,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: (settings) => {
      queryClient.setQueryData(hoursKeys.settings(businessId), settings);
    },
  });
}

/**
 * Remove one date's override so the weekly schedule resumes. The response
 * is only `{status: 'deleted'}` — no settings document to write — so the
 * settings key is invalidated and refetched instead.
 */
export function useDeleteException(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (date: string) =>
      unwrapPrivileged(
        queryClient,
        await client.hours.deleteException(
          businessId,
          date,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: hoursKeys.settings(businessId),
      });
    },
  });
}

/** Write the complete fulfillment policy (full-document command). */
export function useSetFulfillment(businessId: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: FulfillmentSet) =>
      unwrapPrivileged(
        queryClient,
        await client.hours.setFulfillment(
          businessId,
          body,
          requireCsrf(queryClient),
        ),
      ),
    onSuccess: (settings) => {
      queryClient.setQueryData(hoursKeys.settings(businessId), settings);
    },
  });
}

/**
 * A failed hours mutation as one form-level sentence: the envelope's own
 * (neutral) message plus every field error's message, joined. The hours
 * forms deliberately do not map 422 paths onto individual inputs — the
 * client-side checks catch the shape problems first, and a server message
 * like "intervals overlap across days" belongs to the whole schedule, not
 * to one input.
 */
export function hoursFailure(error: unknown, fallback: string): FormFailure {
  const failure = asApiFailure(error);
  const messages = [failure.envelope?.error.message ?? fallback];
  for (const fieldError of failure.envelope?.error.field_errors ?? []) {
    messages.push(fieldError.message);
  }
  return { summary: messages.join(' '), fields: {} };
}

/**
 * The tenant-local exception window a 422 carried, when it carried one
 * (`error.details.window_start`/`window_end`). Narrowed, never trusted.
 */
export function exceptionWindow(
  error: unknown,
): { start: string; end: string } | null {
  const details = asApiFailure(error).envelope?.error.details;
  if (details === null || details === undefined) {
    return null;
  }
  const start = (details as Record<string, unknown>)['window_start'];
  const end = (details as Record<string, unknown>)['window_end'];
  return typeof start === 'string' && typeof end === 'string'
    ? { start, end }
    : null;
}
