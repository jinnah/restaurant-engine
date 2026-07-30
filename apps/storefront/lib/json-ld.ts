// The one audited JSON-LD serialization boundary (ADR-021).
//
// JSON-LD must be embedded as an inline script, which is the single
// approved exception to the storefront's dangerouslySetInnerHTML
// prohibition - and only through this serializer. Every angle bracket and
// ampersand in the serialized JSON is emitted as a JSON \uXXXX escape, so
// tenant text can never terminate the script element or open markup: a
// literal script-closing tag inside a value survives only in the form
// backslash-u003c + "/script" + backslash-u003e. The line and paragraph
// separators (U+2028/U+2029) are escaped for strict JS-string-context
// safety. The escaping happens on the fully serialized JSON, so nesting
// cannot bypass it.

const LINE_SEPARATOR = String.fromCharCode(0x2028);
const PARAGRAPH_SEPARATOR = String.fromCharCode(0x2029);

export function safeJsonLdSerialize(value: unknown): string {
  return JSON.stringify(value)
    .replaceAll('<', '\\u003c')
    .replaceAll('>', '\\u003e')
    .replaceAll('&', '\\u0026')
    .replaceAll(LINE_SEPARATOR, '\\u2028')
    .replaceAll(PARAGRAPH_SEPARATOR, '\\u2029');
}
