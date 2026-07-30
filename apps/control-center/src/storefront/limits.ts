/**
 * The ONLY mirrored storefront bounds (ADR-022 §7): the two the committed
 * OpenAPI document publishes as JSON-Schema constraints (`maxItems`). A
 * build-time test pins each constant to `packages/api-client/openapi.json`,
 * so drift fails CI instead of silently overriding the server.
 *
 * The text-length bounds (`backend .. storefront/policies.py`) are
 * enforced by backend validators and do NOT reach the contract, so they
 * are deliberately not mirrored here: the server's 422 field errors are
 * the authority and are mapped onto the exact inputs instead.
 */
export const MAX_ADDRESS_LINES = 4;
export const MAX_GALLERY_IMAGES = 12;
