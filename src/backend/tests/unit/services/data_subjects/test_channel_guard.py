"""Channel data must not be silently orphaned or erased across participant boundaries."""

import pytest
from langflow.channels.security.credentials import encrypt_credentials
from langflow.services.data_subjects.dry_run import builder_dry_run
from langflow.services.data_subjects.engine import run_request
from langflow.services.data_subjects.errors import ChannelDataError
from langflow.services.data_subjects.requests import approve, create_builder_request
from langflow.services.database.models.channel import (
    ChannelConfigurationAudit,
    ChannelConnection,
    ChannelExecutionLog,
    ChannelFileAsset,
    ChannelIdentity,
    ChannelWorkflowCommand,
)
from langflow.services.database.models.data_subject_request import DataSubjectRequestSource
from langflow.services.database.models.flow.model import Flow
from langflow.services.database.models.user.model import User
from langflow.services.deps import session_scope

from tests.unit.services.data_subjects._seed import create_user, seed_builder


@pytest.mark.usefixtures("client")
@pytest.mark.parametrize("reference", ["owner", "service", "identity", "execution", "file", "command", "audit"])
async def test_channel_references_block_approval_without_erasing_shared_data(reference):
    seeded = await seed_builder()
    admin_id = await create_user("channel-erasure-admin", superuser=True)
    async with session_scope() as session:
        subject = await session.get(User, seeded.user_id)
        connection = ChannelConnection(
            name="shared",
            channel_type="mock",
            user_id=seeded.user_id if reference == "owner" else seeded.colleague_id,
            service_user_id=seeded.user_id if reference == "service" else None,
            credentials_encrypted=encrypt_credentials({"token": "fixture-token"}),
        )
        session.add(connection)
        await session.flush()
        rows = {
            "identity": ChannelIdentity(
                connection_id=connection.id,
                channel_type="mock",
                external_user_id="person",
                openxflow_user_id=subject.id,
            ),
            "execution": ChannelExecutionLog(
                connection_id=connection.id, openxflow_user_id=subject.id, external_event_id="event"
            ),
            "file": ChannelFileAsset(
                connection_id=connection.id,
                openxflow_user_id=subject.id,
                external_conversation_id="room",
                external_message_id="message",
                external_file_id="file",
                filename="private.txt",
            ),
            "command": ChannelWorkflowCommand(
                connection_id=connection.id,
                created_by=subject.id,
                command="/run",
                flow_id=seeded.flow_id,
                scope_key="shared",
                normalized_command="/run",
            ),
            "audit": ChannelConfigurationAudit(
                connection_id=connection.id,
                connection_reference=connection.id,
                actor_user_id=subject.id,
                action="update",
                resource_type="connection",
            ),
        }
        if reference in rows:
            session.add(rows[reference])
        await session.flush()
        request, _ = await create_builder_request(
            session,
            subject=subject,
            requested_by=admin_id,
            source=DataSubjectRequestSource.ADMIN,
        )
        assert (await builder_dry_run(session, subject)).blocked_by == "channel_data_remaining"
        with pytest.raises(ChannelDataError):
            await approve(session, request, admin_id)
        assert request.status == "requested"
        assert subject.is_active
        assert await session.get(Flow, seeded.flow_id) is not None
        assert await session.get(Flow, seeded.colleague_flow_id) is not None


@pytest.mark.usefixtures("client")
async def test_previously_approved_request_rechecks_channel_data_before_removing_rows():
    seeded = await seed_builder()
    admin_id = await create_user("channel-erasure-admin", superuser=True)
    async with session_scope() as session:
        subject = await session.get(User, seeded.user_id)
        request, _ = await create_builder_request(
            session,
            subject=subject,
            requested_by=admin_id,
            source=DataSubjectRequestSource.ADMIN,
        )
        await approve(session, request, admin_id)
        request_id = request.id
        session.add(
            ChannelConnection(
                name="late",
                channel_type="mock",
                user_id=subject.id,
                credentials_encrypted=encrypt_credentials({"token": "fixture-token"}),
            )
        )

    assert await run_request(request_id) == "erasing"
    async with session_scope() as session:
        assert await session.get(User, seeded.user_id) is not None
        assert await session.get(Flow, seeded.flow_id) is not None
