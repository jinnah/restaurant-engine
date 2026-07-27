"""Storefront domain (M4A, ADR-020): governed composition and publication.

Owns design variants, the section registry, composition configuration,
draft/published/archived versions, publication history, and the public
projection (blueprint §7.4). The platform controls structural variants and
the available section types; restaurant users control content, media,
ordering, and visibility inside validated boundaries — never CSS,
JavaScript, or arbitrary HTML (§12.3).

M4A is the foundation only: registries, the composition contract, and
``storefront_versions`` persistence. Services, routers, publication and
restore commands, media claiming, preview, and the public projection are
M4B/M4C and deliberately absent here.

Catalog items and media assets are referenced **by id**, never copied: a
storefront must render the current menu. Immutable transactional snapshots
belong to Orders (M6), where frozen history is the correct behavior.
"""
