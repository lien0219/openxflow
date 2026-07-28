from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from langflow.services.authorization.service import LangflowAuthorizationService


def test_builtin_channel_admin_permissions_are_scoped_to_channels() -> None:
    # Verify the canonical matcher used by built-in and custom roles.
    role_permissions = {"channel:*", "audit:read"}
    assert LangflowAuthorizationService._permission_matches(
        role_permissions,
        resource_type="channel",
        act="write",
    )
    assert LangflowAuthorizationService._permission_matches(
        role_permissions,
        resource_type="audit",
        act="read",
    )
    assert not LangflowAuthorizationService._permission_matches(
        role_permissions,
        resource_type="flow",
        act="write",
    )


def test_rbac_domain_matching_supports_channel_and_global_assignments() -> None:
    connection_id = uuid4()
    global_assignment = SimpleNamespace(domain_type="global", domain_id=None)
    channel_assignment = SimpleNamespace(domain_type="channel", domain_id=connection_id)
    other_assignment = SimpleNamespace(domain_type="channel", domain_id=uuid4())

    assert LangflowAuthorizationService._domain_matches(
        global_assignment,
        domain=f"channel:{connection_id}",
        context={"connection_id": connection_id},
    )
    assert LangflowAuthorizationService._domain_matches(
        channel_assignment,
        domain=f"channel:{connection_id}",
        context={"connection_id": connection_id},
    )
    assert not LangflowAuthorizationService._domain_matches(
        other_assignment,
        domain=f"channel:{connection_id}",
        context={"connection_id": connection_id},
    )
