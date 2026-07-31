"""Tenant-selected theme registries (M4G-A, ADR-024 §3).

Palette and typography pairing are code-owned, append-only ``StrEnum``
registries — the same pattern as ``DesignVariant``, the dietary-tag,
feature-key, and audit-action registries — published in the OpenAPI
document as closed enums so the generated client and the composer consume
them without mirroring a handwritten copy (blueprint §3.7).

They live beside ``variants.py`` rather than inside it because the
**governance split is the product** (blueprint §12.3, ADR-024 §2): the
structural ``DesignVariant`` is platform-assigned through the M4B command,
while palette and pairing are *tenant content* selected by owners and
managers inside the saved draft, the accent-token precedent. Two actors,
two modules.

The identifiers here are permanent contract values. They enter the OpenAPI
enum, stored configurations, and published snapshots, so renaming one later
would be a contract and data concern rather than an editorial one — which
is why ADR-024 fixed them rather than deferring them.

**Retirement rule (ADR-024 §10), recorded for both registries:** they are
append-only, and retiring an entry removes it from the *assignable* set
(writes reject it) while rendering support is retained indefinitely —
renderable ⊇ assignable — so historical versions and restores keep working.
Deleting rendering support for a value that may be stored is a separate,
migration-bearing decision. Writes reject unknown values; reads are
fail-closed, so a stored value missing from a registry is never silently
defaulted (ADR-024 §10).
"""

from enum import StrEnum


class PaletteId(StrEnum):
    """Platform-authored colour schemes (append-only, five permanent values).

    A palette is a curated set of the existing ``.tenantPage`` custom
    properties, not tenant input: contrast is a platform guarantee proved by
    build-time tests, which is only possible because the set is closed
    (ADR-024 §5). The tenant accent remains the single arbitrary token and
    overrides only the accent — it never participates in these five colours.
    """

    WARM = "warm"
    EMBER = "ember"
    SLATE = "slate"
    OLIVE = "olive"
    MIDNIGHT = "midnight"


class TypePairingId(StrEnum):
    """Curated heading/body font pairings (append-only, three permanent values).

    Every pairing is a pair of **system** font stacks plus a bounded scale —
    ADR-024 §6 ships no webfont, so each stack keeps the complex-script
    fallbacks the delivered stack carries and costs no request, no CLS, and
    no licensing or subsetting surface.

    ``serif_display`` is snake_case deliberately: no hyphenated enum value
    exists anywhere in the backend domains (the convention is ``view_menu``,
    ``online_ordering``), and naming it after the ``editorial`` design
    variant would imply a coupling that does not exist — variant and pairing
    are independent axes chosen by different actors (ADR-024 §3).
    """

    HUMANIST = "humanist"
    SERIF_DISPLAY = "serif_display"
    GEOMETRIC = "geometric"


# The explicit defaults, named rather than implied by enum position — the
# ``PLATFORM_DEFAULT_VARIANT`` precedent, so there is no "first member of
# the enum" rule to drift. Both reproduce the delivered presentation exactly
# (ADR-024 §5): every configuration stored before M4G reads as these values
# and therefore renders as it does today.
DEFAULT_PALETTE: PaletteId = PaletteId.WARM
DEFAULT_TYPE_PAIRING: TypePairingId = TypePairingId.HUMANIST

_KNOWN_PALETTES = frozenset(palette.value for palette in PaletteId)
_KNOWN_TYPE_PAIRINGS = frozenset(pairing.value for pairing in TypePairingId)


def is_known_palette(value: str) -> bool:
    """True when ``value`` is a registered palette id."""
    return value in _KNOWN_PALETTES


def is_known_type_pairing(value: str) -> bool:
    """True when ``value`` is a registered typography pairing id."""
    return value in _KNOWN_TYPE_PAIRINGS
