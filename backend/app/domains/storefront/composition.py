"""Storefront composition contract (M4A, ADR-020).

The versioned, schema-validated configuration persisted in
``storefront_versions.config``. The shape is the blueprint §7.4 contract::

    {
      "schema_version": 1,
      "theme": {
        "accent": "#a34b2a",
        "palette": "warm",
        "type_pairing": "humanist",
        "logo": null
      },
      "sections": [
        {"id": "hero-main", "type": "hero", "enabled": true, "props": {}}
      ]
    }

``schema_version`` is explicit and stored, so a future registry change can
migrate or reject an older configuration deliberately rather than guessing
from shape. It is a ``Literal`` today: exactly one version exists, and the
change that introduces a second is the change that decides how the first is
handled.

**M4G-A extended the theme additively and deliberately did not bump that
version** (ADR-024 §4). ``extra="forbid"`` rejects unknown keys on
submission, but *missing* keys parse to defaults, so every configuration
stored before M4G reads as ``palette: warm``, ``type_pairing: humanist``,
``logo: null`` — exactly its current appearance. No schema v2, no
migration, no backfill, and no adoption workflow: nothing rewrites a stored
configuration and nothing asks an owner to accept a new schema. A future
*incompatible* change still requires the version bump and an explicit
migrate-or-reject decision.

Validation is deterministic and total — the same input always produces the
same accepted value or the same error — and serialization round-trips:
``dump`` then ``parse`` then ``dump`` is byte-identical, which is what lets
a stored configuration be compared, hashed, and diffed.
"""

import re
import uuid
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field, field_validator

from app.domains.storefront import policies
from app.domains.storefront.sections import (
    AnySection,
    Section,
    SectionType,
    StorefrontModel,
)
from app.domains.storefront.sections import (
    referenced_media_ids as section_media_ids,
)
from app.domains.storefront.theme_registries import (
    DEFAULT_PALETTE,
    DEFAULT_TYPE_PAIRING,
    PaletteId,
    TypePairingId,
)

# The only schema version that exists. See the module docstring. Typed as
# the literal so the constant and the field annotation cannot drift apart.
SCHEMA_VERSION: Literal[1] = 1

# At most one section per registered type. This is the standing guard
# against drifting into a general-purpose page builder: a storefront is a
# curated set of known sections the owner arranges and fills, not an
# arbitrary tree of repeated blocks.
MAX_SECTIONS = len(SectionType)


def _accent(value: object) -> object:
    """A curated six-digit hex accent token, canonicalized to lowercase."""
    if not isinstance(value, str):
        return value
    candidate = value.strip().lower()
    if re.fullmatch(policies.ACCENT_PATTERN, candidate) is None:
        msg = "must be a six-digit hex colour such as '#a34b2a'"
        raise ValueError(msg)
    return candidate


Accent = Annotated[str, BeforeValidator(_accent)]


class ThemeLogo(StorefrontModel):
    """An optional tenant logo: one media asset id, and nothing else.

    Deliberately carries **no ``alt_text`` field** (ADR-024 §4, §7). The
    logo is permanently decorative — it renders ``alt=""`` beside the
    business name, which every variant keeps as the visible semantic
    ``h1`` — so alt text here would produce a duplicate accessible name for
    the same fact, the redundancy screen-reader users report as noise.
    Publishing a field whose value can never affect rendering would invite
    owners to write alt text the product then ignores.

    Contrast this with ``SectionImage``, which *does* carry contextual alt
    text: a hero or gallery photograph conveys something the surrounding
    text does not.
    """

    media_id: uuid.UUID


class Theme(StorefrontModel):
    """The tenant-adjustable presentation tokens.

    Blueprint §12.3 permits curated tokens and forbids tenant CSS,
    JavaScript, and arbitrary HTML; every field here is either a validated
    token or a selection from a closed platform registry, so nothing a
    tenant submits ever reaches a stylesheet as authored text.

    ``accent`` remains the single arbitrary value — one validated
    ``#rrggbb`` — and is grandfathered exactly as stored: it overrides only
    the accent token and never participates in a palette's colours
    (ADR-024 §5). ``palette`` and ``type_pairing`` select from the
    code-owned registries; ``logo`` is an optional decorative image staged
    and claimed exactly like section media (ADR-020 §10 as amended).

    All three additions default to the delivered presentation, which is what
    keeps ``schema_version`` at 1: a configuration written before M4G parses
    to ``warm`` / ``humanist`` / ``null`` and renders unchanged.
    """

    accent: Accent = policies.DEFAULT_ACCENT
    palette: PaletteId = DEFAULT_PALETTE
    type_pairing: TypePairingId = DEFAULT_TYPE_PAIRING
    logo: ThemeLogo | None = None


class StorefrontConfig(StorefrontModel):
    """One complete, validated storefront composition.

    Array order is the contract — sections render in the order given, so no
    ``position`` field is exposed (the catalog projection convention).
    """

    schema_version: Literal[1] = SCHEMA_VERSION
    theme: Theme = Field(default_factory=Theme)
    sections: list[Section] = Field(default_factory=list, max_length=MAX_SECTIONS)

    @field_validator("sections", mode="after")
    @classmethod
    def _distinct_ids_and_types(cls, sections: list[AnySection]) -> list[AnySection]:
        ids = [section.id for section in sections]
        if len(set(ids)) != len(ids):
            msg = "section ids must be unique within a configuration"
            raise ValueError(msg)
        types = [section.type for section in sections]
        if len(set(types)) != len(types):
            msg = "at most one section of each type is allowed"
            raise ValueError(msg)
        return sections


def default_config() -> StorefrontConfig:
    """The registry's initial configuration for a newly created draft.

    Deliberately **empty of sections**: the platform default variant and
    accent, and nothing else. Seeding placeholder copy would fabricate
    tenant content in code — and in one language, for a market the product
    documents as Bengali-capable. The owner composes the page; the renderer
    is required to present an empty published configuration coherently
    rather than assuming at least one section exists.
    """
    return StorefrontConfig()


def parse_config(raw: object) -> StorefrontConfig:
    """Validate stored or submitted configuration data.

    Raises ``pydantic.ValidationError`` for anything the registry does not
    declare — an unknown section type, an unknown property, a bad accent, a
    duplicate id, out-of-bound copy. Callers translate that into the
    project's 422 envelope; nothing here decides HTTP behavior.
    """
    return StorefrontConfig.model_validate(raw)


def dump_config(config: StorefrontConfig) -> dict[str, Any]:
    """The canonical JSON-compatible mapping stored in ``config``.

    ``mode="json"`` so UUIDs and enums become strings that PostgreSQL JSONB
    accepts unchanged, and field order follows declaration order, making the
    output stable for comparison and diffing.
    """
    return config.model_dump(mode="json")


# --- Media references ---------------------------------------------------------
# The document-level owner of "where images live in a configuration". M4A
# put that knowledge in ``sections.referenced_media_ids`` because sections
# were the only place an image could appear; M4G-A added ``theme.logo``,
# which is not a section, so the authoritative answer moved up here and the
# section function became the per-section detail it delegates to.


def theme_media_ids(theme: Theme) -> list[uuid.UUID]:
    """Every media asset the theme references, in stable order.

    The theme's counterpart to ``sections.referenced_media_ids``: one place
    that knows where images live in the theme, so the claim path, the public
    projection, and the ADR-020 §10 authorization predicate cannot disagree.
    """
    return [theme.logo.media_id] if theme.logo is not None else []


def referenced_media_ids(config: StorefrontConfig) -> list[uuid.UUID]:
    """Every media asset this configuration references, in document order.

    Theme first, then each section in display order — the canonical field
    order, so the walk is deterministic and a claim sequence is reproducible.
    Duplicates are preserved rather than collapsed: this is a faithful walk
    of the document, and callers that need a set de-duplicate explicitly.

    Sections are walked **regardless of ``enabled``**, because claiming
    follows what the owner stored, not what currently renders; the public
    projection and the §10 predicate use the enabled-only collection in
    ``public_service`` instead.

    A permanent test asserts this function reaches every ``media_id`` in the
    canonical dump, so an image-bearing field added anywhere in the registry
    — theme or section — cannot silently escape the claim path.
    """
    ids = theme_media_ids(config.theme)
    for section in config.sections:
        ids.extend(section_media_ids(section))
    return ids
