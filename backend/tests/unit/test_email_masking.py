"""Invitation email hints (ADR-014 correction E): the local part must never
be recoverable from a preview hint, including the one-character edge."""

import pytest

from app.domains.businesses.invitations import mask_email


@pytest.mark.parametrize(
    ("email", "hint"),
    [
        ("invitee@example.com", "i***@example.com"),
        # Two characters is the shortest local part that still leaks its
        # first character by design.
        ("ab@x.co", "a***@x.co"),
        # One character: disclosing the first character would disclose the
        # entire local part, so the hint degrades to all-asterisks.
        ("a@x.co", "****@x.co"),
    ],
)
def test_mask_email_hint_shapes(email: str, hint: str) -> None:
    assert mask_email(email) == hint


def test_single_character_local_part_is_not_disclosed() -> None:
    masked_local = mask_email("a@x.co").partition("@")[0]
    assert "a" not in masked_local
