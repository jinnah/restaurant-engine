"""Media domain (M3C, ADR-017): tenant-owned image assets.

Owns upload validation, processing, metadata, storage keys, variants,
lifecycle, and deletion policy. Consumers (catalog now; storefront
branding later) store media identifiers through composite tenant-safe
foreign keys — never storage keys or filesystem paths.
"""
