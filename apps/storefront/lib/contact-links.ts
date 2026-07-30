// Safe link derivation for contact fields (ADR-021).
//
// Phone and email arrive as bounded plain text — validated for length and
// control characters, not for dialability or deliverability (the backend
// contract). A `tel:`/`mailto:` link is derived only when the value has an
// unambiguous link form; anything else renders as text. The scheme is
// fixed here, so tenant text can never choose a URL scheme.

const PHONE_ALLOWED = /^[+0-9()\-.  ]+$/;
const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** `tel:` href for a phone value, or null to render plain text. */
export function telHref(phone: string): string | null {
  if (!PHONE_ALLOWED.test(phone)) {
    return null;
  }
  const dialable = phone.replace(/[^+0-9]/g, '');
  const digits = dialable.replace(/\D/g, '');
  if (digits.length < 3) {
    return null;
  }
  return `tel:${dialable}`;
}

/** `mailto:` href for an email value, or null to render plain text. */
export function mailtoHref(email: string): string | null {
  return EMAIL_SHAPE.test(email) ? `mailto:${email}` : null;
}
