"""Storefront composition contract (M4A, ADR-020).

The versioned, schema-validated configuration persisted in
``storefront_versions.config``. The shape is the blueprint §7.4 contract::

    {
      "schema_version": 1,
      "theme": {"accent": "#a34b2a"},
      "sections": [
        {"id": "hero-main", "type": "hero", "enabled": true, "props": {}}
      ]
    }

``schema_version`` is explicit and stored, so a future registry change can
migrate or reject an older configuration deliberately rather than guessing
from shape. It is a ``Literal`` today: exactly one version exists, and the
change that introduces a second is the change that decides how the first is
handled.

Validation is deterministic and total — the same input always produces the
same accepted value or the same error — and serialization round-trips:
``dump`` then ``parse`` then ``dump`` is byte-identical, which is what lets
a stored configuration be compared, hashed, and diffed.
"""

import re
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field, field_validator

from app.domains.storefront import policies
from app.domains.storefront.sections import (
    AnySection,
    Section,
    SectionType,
    StorefrontModel,
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


class Theme(StorefrontModel):
    """The tenant-adjustable presentation tokens.

    Exactly one accent colour in M4 — the whole of the tenant's styling
    surface. Blueprint §12.3 permits accent tokens and forbids tenant CSS,
    JavaScript, and arbitrary HTML; anything richer than a token here would
    cross that line.
    """

    accent: Accent = policies.DEFAULT_ACCENT


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
