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
    role_outranks,
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


class TestM2dCapabilityAdditions:
    """ADR-014 rulings: invite/audit for owner+manager, staff excluded."""

    def test_owner_and_manager_can_invite_and_read_audit(self) -> None:
        for role in (Role.OWNER, Role.MANAGER):
            assert role_has_capability(role, Capability.BUSINESS_MEMBERS_INVITE)
            assert role_has_capability(role, Capability.BUSINESS_AUDIT_READ)

    def test_staff_cannot_invite_or_read_audit(self) -> None:
        assert not role_has_capability(Role.STAFF, Capability.BUSINESS_MEMBERS_INVITE)
        assert not role_has_capability(Role.STAFF, Capability.BUSINESS_AUDIT_READ)

    def test_platform_capability_set_is_exactly_the_approved_three(self) -> None:
        assert PLATFORM_CAPABILITIES == frozenset(
            {
                Capability.PLATFORM_BUSINESSES_MANAGE,
                Capability.PLATFORM_USERS_RECOVER,
                Capability.PLATFORM_AUDIT_READ,
            }
        )

    def test_recover_and_audit_are_platform_admin_only(self) -> None:
        for capability in (Capability.PLATFORM_USERS_RECOVER, Capability.PLATFORM_AUDIT_READ):
            require_platform_capability(_actor(is_platform_admin=True), capability)
            with pytest.raises(PermissionDeniedError):
                require_platform_capability(_actor(is_platform_admin=False), capability)


class TestRoleRank:
    """Invitation role ceiling (ADR-014): owner > manager > staff."""

    def test_strict_outranking(self) -> None:
        assert role_outranks(Role.OWNER, Role.MANAGER)
        assert role_outranks(Role.OWNER, Role.STAFF)
        assert role_outranks(Role.MANAGER, Role.STAFF)

    def test_no_role_outranks_itself_or_upward(self) -> None:
        for role in Role:
            assert not role_outranks(role, role)
        assert not role_outranks(Role.MANAGER, Role.OWNER)
        assert not role_outranks(Role.STAFF, Role.MANAGER)
