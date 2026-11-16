"""Official authentication and OpenXFlow histories must upgrade together safely."""

from uuid import uuid4

import pytest
from alembic import command
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData, Table, create_engine, inspect, text

from .test_migration_execution import _engine_url, _make_alembic_cfg, db_url  # noqa: F401


def test_upstream_and_openxflow_startup_have_one_migration_head():
    """Database startup must be able to resolve its unqualified head target."""
    scripts = ScriptDirectory.from_config(_make_alembic_cfg("sqlite+aiosqlite://"))
    assert scripts.get_current_head() is not None


@pytest.mark.parametrize(
    "prior_revision",
    [
        "base",
        "f5a7b9c2d4e6",  # pragma: allowlist secret -- Alembic revision
        "f7c2e91a4b63",  # pragma: allowlist secret -- Alembic revision
    ],
)
def test_upstream_and_openxflow_upgrade_preserves_custom_data(db_url, prior_revision):  # noqa: F811
    """Upgrade fresh and prior-head databases without losing RBAC or channel rows."""
    config = _make_alembic_cfg(db_url)
    command.upgrade(config, prior_revision)
    engine = create_engine(_engine_url(db_url))
    role_id, owner_id, channel_id = (uuid4().hex for _ in range(3))
    try:
        if prior_revision != "base":
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO authz_role (id, name, is_system, permissions, created_at, updated_at) "
                        "VALUES (:id, 'preserved-custom-role', :is_system, '[]', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ),
                    {"id": role_id, "is_system": False},
                )
                if prior_revision == "f7c2e91a4b63":  # pragma: allowlist secret -- Alembic revision
                    connection.execute(
                        text(
                            'INSERT INTO "user" '
                            "(id, username, password, is_active, is_superuser, create_at, updated_at) "
                            "VALUES (:id, 'preserved-channel-owner', 'unused', :active, :superuser, "
                            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                        ),
                        {"id": owner_id, "active": True, "superuser": False},
                    )
                    channel = Table("channel_connection", MetaData(), autoload_with=connection)
                    connection.execute(
                        channel.insert().values(
                            id=channel_id,
                            user_id=owner_id,
                            name="preserved-channel",
                            channel_type="feishu",
                            enabled=False,
                            connection_mode="webhook",
                            settings_data={"preserve": "settings"},
                            credentials_encrypted="preserved-ciphertext",
                            status="disconnected",
                        )
                    )

        command.upgrade(config, "head")

        with engine.connect() as connection:
            schema = inspect(connection)
            assert {"refresh_token_session", "authz_role", "casbin_rule", "channel_connection"} <= set(
                schema.get_table_names()
            )
            assert "completed_registration_id" in {column["name"] for column in schema.get_columns("connection_oauth")}
            if prior_revision != "base":
                assert (
                    connection.execute(text("SELECT name FROM authz_role WHERE id = :id"), {"id": role_id}).scalar_one()
                    == "preserved-custom-role"
                )
            if prior_revision == "f7c2e91a4b63":  # pragma: allowlist secret -- Alembic revision
                assert connection.execute(
                    text("SELECT name, credentials_encrypted FROM channel_connection WHERE id = :id"),
                    {"id": channel_id},
                ).one() == ("preserved-channel", "preserved-ciphertext")
            assert MigrationContext.configure(connection).get_current_heads() == (
                ScriptDirectory.from_config(config).get_current_head(),
            )
    finally:
        engine.dispose()
