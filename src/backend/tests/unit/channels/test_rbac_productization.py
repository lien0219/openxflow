from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from langflow.api.v1.authz_audit import _audit_domain_context
from langflow.api.v1.authz_me import _summary_domain_context
from langflow.api.v1.authz_role_assignments import _domain_context
from langflow.api.v1.schemas.authz_role_assignments import RoleAssignmentCreate
from langflow.services.authorization.bootstrap import (
    SYSTEM_ROLE_DEFINITIONS,
    is_managed_service_user,
)


def test_system_role_catalog_is_complete_and_least_privileged() -> None:
    by_name = {definition.name: set(definition.permissions) for definition in SYSTEM_ROLE_DEFINITIONS}

    assert set(by_name) == {
        "platform_admin",
        "organization_admin",
        "channel_admin",
        "resource_editor",
        "viewer",
        "auditor",
        "member",
    }
    assert "rbac:*" in by_name["platform_admin"]
    assert "rbac:assign" in by_name["organization_admin"]
    assert "rbac:assign" in by_name["channel_admin"]
    assert "rbac:*" not in by_name["channel_admin"]
    assert "flow:write" not in by_name["viewer"]
    assert by_name["member"] == set()


def test_role_assignment_schema_supports_channel_scope() -> None:
    connection_id = uuid4()
    payload = RoleAssignmentCreate(
        user_id=uuid4(),
        role_id=uuid4(),
        domain_type="channel",
        domain_id=connection_id,
    )
    assert payload.domain_id == connection_id


def test_role_assignment_schema_rejects_invalid_scope_pairs() -> None:
    with pytest.raises(ValidationError):
        RoleAssignmentCreate(
            user_id=uuid4(),
            role_id=uuid4(),
            domain_type="global",
            domain_id=uuid4(),
        )
    with pytest.raises(ValidationError):
        RoleAssignmentCreate(
            user_id=uuid4(),
            role_id=uuid4(),
            domain_type="project",
            domain_id=None,
        )


def test_domain_context_maps_channel_and_organization_aliases() -> None:
    domain_id = uuid4()
    expected_channel = (
        f"channel:{domain_id}",
        {"connection_id": domain_id},
    )
    expected_organization = (
        f"organization:{domain_id}",
        {"organization_id": domain_id},
    )

    assert _domain_context("channel", domain_id) == expected_channel
    assert _summary_domain_context("channel", domain_id) == expected_channel
    assert _audit_domain_context("channel", domain_id) == expected_channel
    assert _domain_context("organization", domain_id) == expected_organization
    assert _summary_domain_context("organization", domain_id) == expected_organization
    assert _audit_domain_context("organization", domain_id) == expected_organization
    assert _domain_context("global", None) == ("*", {})
    assert _summary_domain_context("global", None) == ("*", {})
    assert _audit_domain_context("global", None) == ("*", {})


def test_managed_channel_service_users_never_receive_default_roles() -> None:
    service_user = SimpleNamespace(optins={"channel_service_identity": True})
    human_user = SimpleNamespace(optins={})
    assert is_managed_service_user(service_user)
    assert not is_managed_service_user(human_user)
