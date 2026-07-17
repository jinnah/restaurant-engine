"""Capability policy (M2B): pure mapping and platform enforcement."""

import uuid

import pytest

from app.core.errors import PermissionDeniedError
from app.domains.identity.actor import ActorContext, AuthenticatedUser
from app.domains.identity.policies import (
    CAPABILITIES_BY_ROLE,
    PLATFORM_CAPABILITIES,
    Capability,
    Role,
    require_platform_capability,
    role_has_capability,
)


def _actor(*, is_platform_admin: bool) -> ActorContext:
    return ActorContext(
        user=AuthenticatedUser(
            id=uuid.uuid4(),
            email="a@b.co",
            display_name="A",
            is_platform_admin=is_platform_admin,
        ),
        session_id=uuid.uuid4(),
        csrf_token="csrf",
    )


class TestRoleCapabilityMap:
    def test_every_role_is_mapped(self) -> None:
        assert set(CAPABILITIES_BY_ROLE) == set(Role)

    def test_all_roles_can_view_their_business(self) -> None:
        for role in Role:
            assert role_has_capability(role, Capability.BUSINESS_VIEW)

    def test_no_business_role_holds_a_platform_capability(self) -> None:
        # Platform authority never comes from a membership role.
        for role in Role:
            assert not (CAPABILITIES_BY_ROLE[role] & PLATFORM_CAPABILITIES)


class TestRequirePlatformCapability:
    def test_platform_admin_passes(self) -> None:
        require_platform_capability(
            _actor(is_platform_admin=True), Capability.PLATFORM_BUSINESSES_MANAGE
        )

    def test_non_admin_is_denied(self) -> None:
        with pytest.raises(PermissionDeniedError):
            require_platform_capability(
                _actor(is_platform_admin=False), Capability.PLATFORM_BUSINESSES_MANAGE
            )

    def test_asking_for_a_non_platform_capability_is_a_programming_error(self) -> None:
        # business.view is not a platform capability; requesting it through
        # the platform gate is a bug, not an authorization outcome.
        with pytest.raises(ValueError, match="not a platform capability"):
            require_platform_capability(_actor(is_platform_admin=True), Capability.BUSINESS_VIEW)
