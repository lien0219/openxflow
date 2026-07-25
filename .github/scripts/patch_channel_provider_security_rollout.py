from pathlib import Path

# Apply persistence/API integration against the current CRUD implementation,
# then remove the superseded section from the generic rollout script.
crud_path = Path("src/backend/base/langflow/services/database/models/channel/crud.py")
crud = crud_path.read_text(encoding="utf-8")
if "from langflow.channels.security.provider_credentials import validate_channel_provider_credentials\n" not in crud:
    crud = crud.replace(
        "from langflow.channels.security.credentials import decrypt_credentials, encrypt_credentials, list_credential_keys\n",
        "from langflow.channels.security.credentials import decrypt_credentials, encrypt_credentials, list_credential_keys\n"
        "from langflow.channels.security.provider_credentials import validate_channel_provider_credentials\n",
        1,
    )
create_marker = """async def create_channel_connection(
    session: AsyncSession,
    user_id: UUID,
    payload: ChannelConnectionCreate,
) -> ChannelConnectionRead:
    connection = ChannelConnection(
"""
create_replacement = """async def create_channel_connection(
    session: AsyncSession,
    user_id: UUID,
    payload: ChannelConnectionCreate,
) -> ChannelConnectionRead:
    validate_channel_provider_credentials(
        payload.channel_type,
        payload.connection_mode,
        payload.credentials,
    )
    connection = ChannelConnection(
"""
if create_replacement not in crud:
    if create_marker not in crud:
        raise RuntimeError("Missing current connection create marker")
    crud = crud.replace(create_marker, create_replacement, 1)

update_start = crud.find("async def update_channel_connection(\n")
update_end = crud.find("async def delete_channel_connection(\n", update_start)
if update_start < 0 or update_end < 0:
    raise RuntimeError("Missing current connection update block")
updated_function = """async def update_channel_connection(
    session: AsyncSession,
    connection: ChannelConnection,
    payload: ChannelConnectionUpdate,
) -> ChannelConnectionRead:
    existing_credentials = decrypt_credentials(connection.credentials_encrypted)
    merged_credentials = dict(existing_credentials)
    if payload.credentials is not None:
        merged_credentials.update(payload.credentials)
    next_connection_mode = payload.connection_mode or connection.connection_mode
    validate_channel_provider_credentials(
        connection.channel_type,
        next_connection_mode,
        merged_credentials,
    )

    changes = payload.model_dump(exclude_unset=True, exclude={"credentials", "service_user_id"})
    for key, value in changes.items():
        setattr(connection, key, value)

    if payload.credentials is not None:
        connection.credentials_encrypted = encrypt_credentials(merged_credentials)

    connection.updated_at = _utc_now()
    session.add(connection)
    await ensure_channel_service_identity(session, connection)

    if "default_flow_id" in changes:
        inherited_statement = select(ChannelConversationBinding).where(
            ChannelConversationBinding.connection_id == connection.id,
            ChannelConversationBinding.route_mode == ChannelConversationRouteMode.INHERIT.value,
            ChannelConversationBinding.status.notin_(
                [ChannelConversationStatus.IGNORED.value, ChannelConversationStatus.UNAVAILABLE.value]
            ),
        )
        inherited_rows = (await session.exec(inherited_statement)).all()
        for binding in inherited_rows:
            binding.status = _derive_conversation_status(connection, binding)
            binding.updated_at = _utc_now()
            session.add(binding)

    await session.flush()
    await session.refresh(connection)
    return _connection_read(connection)


"""
crud = crud[:update_start] + updated_function + crud[update_end:]
crud_path.write_text(crud, encoding="utf-8")

factory_path = Path("src/backend/base/langflow/channels/adapters/factory.py")
factory = factory_path.read_text(encoding="utf-8")
if "from langflow.channels.security.provider_credentials import validate_channel_provider_credentials\n" not in factory:
    factory = factory.replace(
        "from langflow.channels.security.credentials import decrypt_credentials\n",
        "from langflow.channels.security.credentials import decrypt_credentials\n"
        "from langflow.channels.security.provider_credentials import validate_channel_provider_credentials\n",
        1,
    )
factory_marker = """    channel_type = ChannelType(connection.channel_type)
    credentials = decrypt_credentials(connection.credentials_encrypted)

"""
factory_replacement = """    channel_type = ChannelType(connection.channel_type)
    credentials = decrypt_credentials(connection.credentials_encrypted)
    validate_channel_provider_credentials(
        connection.channel_type,
        connection.connection_mode,
        credentials,
    )

"""
if factory_replacement not in factory:
    if factory_marker not in factory:
        raise RuntimeError("Missing current adapter factory marker")
    factory = factory.replace(factory_marker, factory_replacement, 1)
factory_path.write_text(factory, encoding="utf-8")

api_path = Path("src/backend/base/langflow/api/v1/channels.py")
api = api_path.read_text(encoding="utf-8")
if "from langflow.channels.security.provider_credentials import ChannelProviderCredentialError\n" not in api:
    api = api.replace(
        "from langflow.channels.adapters.telegram import TelegramChannelAdapter\n",
        "from langflow.channels.adapters.telegram import TelegramChannelAdapter\n"
        "from langflow.channels.security.provider_credentials import ChannelProviderCredentialError\n",
        1,
    )
error_branch = """    except ChannelProviderCredentialError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
"""
integrity_marker = """    except IntegrityError as exc:
        await db.rollback()
"""
for route_name in ("async def create_channel_connection_route", "async def update_channel_connection_route"):
    route_start = api.find(route_name)
    route_end = api.find("\n\n@router.", route_start + 1)
    if route_end < 0:
        route_end = len(api)
    route_block = api[route_start:route_end]
    if error_branch in route_block:
        continue
    marker_index = api.find(integrity_marker, route_start, route_end)
    if marker_index < 0:
        raise RuntimeError(f"Missing credential error insertion marker for {route_name}")
    api = api[:marker_index] + error_branch + api[marker_index:]
api_path.write_text(api, encoding="utf-8")

apply_path = Path(".github/scripts/apply_channel_provider_security.py")
apply_content = apply_path.read_text(encoding="utf-8")
section_start = apply_content.find("# Validate provider credentials before persistence")
section_end = apply_content.find("# Telegram callback verification", section_start)
if section_start < 0 or section_end < 0:
    raise RuntimeError("Missing generic provider-security integration section")
apply_path.write_text(apply_content[:section_start] + apply_content[section_end:], encoding="utf-8")
