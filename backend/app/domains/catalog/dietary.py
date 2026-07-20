"""Dietary-tag registry (M3A, ADR-017 ruling D6).

Append-only, like the feature-key and audit-action registries: a tag is
added in the change that first ships it, and the registry is code — not a
DB CHECK — so adding a tag is not a migration. Allergens, nutrition data,
and tenant-created tags are explicitly out of scope.

Writes reject unknown values (422); reads are fail-closed — a stored tag
missing from this registry (manual SQL, drift) is never surfaced.
"""

from enum import StrEnum


class DietaryTag(StrEnum):
    """Structured dietary attributes of a menu item (append-only).

    Seeded per ruling D6: halal (blueprint §2.1 names it as structured
    menu data), vegetarian, and vegan. Stored canonical lowercase (the
    DB CHECK is the storage invariant).
    """

    HALAL = "halal"
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"


_KNOWN_VALUES = frozenset(tag.value for tag in DietaryTag)


def is_known_tag(value: str) -> bool:
    """True when ``value`` is a registered dietary tag."""
    return value in _KNOWN_VALUES


def filter_known(values: list[str]) -> list[str]:
    """Fail-closed read projection: drop any unregistered stored value."""
    return [value for value in values if value in _KNOWN_VALUES]
