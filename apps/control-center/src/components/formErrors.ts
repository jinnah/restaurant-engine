import type { ApiFailure } from '../api/failure';

export interface FormFailure {
  /** Sentence for the focused error summary. */
  summary: string;
  /** Per-input messages keyed by the input's field name. */
  fields: Record<string, string>;
}

/**
 * Map an ApiFailure to inline form errors. Field errors from the ADR-008
 * envelope attach to inputs by the trailing segment of their field path;
 * everything else surfaces as the envelope's own (neutral) message or the
 * caller's fallback. Nothing from the request payload is ever echoed.
 */
export function mapFailure(failure: ApiFailure, fallback: string): FormFailure {
  const fields: Record<string, string> = {};
  if (failure.envelope !== null) {
    for (const fieldError of failure.envelope.error.field_errors) {
      const name = fieldError.field.split('.').at(-1) ?? fieldError.field;
      if (!(name in fields)) {
        fields[name] = fieldError.message;
      }
    }
  }
  if (Object.keys(fields).length > 0) {
    return { summary: 'Some fields need attention.', fields };
  }
  return {
    summary: failure.envelope?.error.message ?? fallback,
    fields,
  };
}
