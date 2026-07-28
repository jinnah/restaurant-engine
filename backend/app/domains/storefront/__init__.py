"""Storefront domain (M4A/M4B, ADR-020): governed composition and publication.

Owns design variants, the section registry, composition configuration,
draft/published/archived versions, publication history, and the public
projection (blueprint §7.4). The platform controls structural variants and
the available section types; restaurant users control content, media,
ordering, and visibility inside validated boundaries — never CSS,
JavaScript, or arbitrary HTML (§12.3).

M4A shipped the foundation: registries, the composition contract, and
``storefront_versions`` persistence. M4B adds the administrative surface —
tenant-scoped repository, the draft/publish/restore/design workflows, and
their APIs. Preview, the public projection, and caching are M4C and
deliberately absent here.

Catalog items and media assets are referenced **by id**, never copied: a
storefront must render the current menu. Immutable transactional snapshots
belong to Orders (M6), where frozen history is the correct behavior.
"""
