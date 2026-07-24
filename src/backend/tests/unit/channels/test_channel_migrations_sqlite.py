from __future__ import annotations

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from langflow.alembic.versions import (
    a8e1c6d4f5b7_add_channel_outbound_delivery as outbound_delivery_migration,
)
from langflow.alembic.versions import (
    b9f2d7e6c4a1_add_channel_routing_and_discovery as routing_migration,
)
from langflow.alembic.versions import (
    c0a3e8f7d5b2_add_channel_commands_and_execution_logs as command_migration,
)
from langflow.alembic.versions import (
    c4a9e2d7f1b0_add_channel_gateway_schema as gateway_schema_migration,
)
from langflow.alembic.versions import (
    d1e4f9a8b6c3_ensure_channel_conversation_status_index as status_index_repair_migration,
)
from langflow.alembic.versions import (
    d5b8f3a1c2e4_add_channel_file_asset_tracking as file_asset_migration,
)
from langflow.alembic.versions import (
    e6c9a4b2d3f5_widen_channel_file_identifier as widen_file_identifier_migration,
)
from langflow.alembic.versions import (
    f7d0b5c3e4a6_add_channel_webhook_jobs as webhook_job_migration,
)

_MIGRATIONS = (
    gateway_schema_migration,
    file_asset_migration,
    widen_file_identifier_migration,
    webhook_job_migration,
    outbound_delivery_migration,
    routing_migration,
    command_migration,
    status_index_repair_migration,
)


def _create_parent_tables(connection: sa.Connection) -> None:
    connection.exec_driver_sql('CREATE TABLE "user" (id CHAR(32) PRIMARY KEY)')
    connection.exec_driver_sql("CREATE TABLE flow (id CHAR(32) PRIMARY KEY)")
    connection.exec_driver_sql("CREATE TABLE knowledge_base (id CHAR(32) PRIMARY KEY)")
    connection.exec_driver_sql('CREATE TABLE "file" (id CHAR(32) PRIMARY KEY)')
    connection.exec_driver_sql("CREATE TABLE job (job_id CHAR(32) PRIMARY KEY)")


def test_channel_migration_revision_chain() -> None:
    assert [migration.revision for migration in _MIGRATIONS] == [
        "c4a9e2d7f1b0",
        "d5b8f3a1c2e4",
        "e6c9a4b2d3f5",
        "f7d0b5c3e4a6",
        "a8e1c6d4f5b7",
        "b9f2d7e6c4a1",
        "c0a3e8f7d5b2",
        "d1e4f9a8b6c3",
    ]
    assert [migration.down_revision for migration in _MIGRATIONS] == [
        "e1705947c729",
        "c4a9e2d7f1b0",
        "d5b8f3a1c2e4",
        "e6c9a4b2d3f5",
        "f7d0b5c3e4a6",
        "a8e1c6d4f5b7",
        "b9f2d7e6c4a1",
        "c0a3e8f7d5b2",
    ]


def test_channel_migrations_upgrade_and_downgrade_on_sqlite(monkeypatch) -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        _create_parent_tables(connection)
        context = MigrationContext.configure(connection, opts={"render_as_batch": True})
        operations = Operations(context)
        for migration in _MIGRATIONS:
            monkeypatch.setattr(migration, "op", operations)
            migration.upgrade()

        expected_tables = {
            "channel_connection",
            "channel_identity",
            "channel_conversation_binding",
            "channel_event_receipt",
            "channel_binding_code",
            "channel_file_asset",
            "channel_webhook_job",
            "channel_outbound_delivery",
            "channel_workflow_command",
            "channel_execution_log",
        }
        inspector = sa.inspect(connection)
        assert expected_tables.issubset(set(inspector.get_table_names()))

        file_columns = {column["name"]: column for column in sa.inspect(connection).get_columns("channel_file_asset")}
        assert file_columns["external_file_id"]["type"].length == 1024

        outbound_columns = {
            column["name"]: column for column in sa.inspect(connection).get_columns("channel_outbound_delivery")
        }
        assert outbound_columns["delivery_kind"]["type"].length == 32
        assert outbound_columns["response_digest"]["type"].length == 64

        outbound_unique = {
            constraint["name"]: tuple(constraint["column_names"])
            for constraint in sa.inspect(connection).get_unique_constraints("channel_outbound_delivery")
        }
        assert outbound_unique["uq_channel_outbound_delivery_event_kind"] == (
            "connection_id",
            "external_event_id",
            "delivery_kind",
        )

        outbound_indexes = {
            index["name"]: tuple(index["column_names"])
            for index in sa.inspect(connection).get_indexes("channel_outbound_delivery")
        }
        assert outbound_indexes["ix_channel_outbound_delivery_status_updated"] == (
            "status",
            "updated_at",
        )

        conversation_indexes = {
            index["name"]: tuple(index["column_names"])
            for index in sa.inspect(connection).get_indexes("channel_conversation_binding")
        }
        assert conversation_indexes["ix_channel_conversation_binding_status"] == ("status",)

        for migration in reversed(_MIGRATIONS):
            migration.downgrade()

        remaining_tables = set(sa.inspect(connection).get_table_names())
        assert expected_tables.isdisjoint(remaining_tables)
        assert {"user", "flow", "knowledge_base", "file", "job"}.issubset(remaining_tables)


def test_status_index_repair_handles_already_migrated_sqlite_database(monkeypatch) -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE channel_conversation_binding "
            "(id CHAR(32) PRIMARY KEY, status VARCHAR(32) NOT NULL DEFAULT 'pending')"
        )
        context = MigrationContext.configure(connection, opts={"render_as_batch": True})
        operations = Operations(context)
        monkeypatch.setattr(status_index_repair_migration, "op", operations)

        status_index_repair_migration.upgrade()
        status_index_repair_migration.upgrade()

        indexes = {
            index["name"]: tuple(index["column_names"])
            for index in sa.inspect(connection).get_indexes("channel_conversation_binding")
        }
        assert indexes["ix_channel_conversation_binding_status"] == ("status",)

        status_index_repair_migration.downgrade()
        indexes_after_downgrade = {
            index["name"]: tuple(index["column_names"])
            for index in sa.inspect(connection).get_indexes("channel_conversation_binding")
        }
        assert indexes_after_downgrade["ix_channel_conversation_binding_status"] == ("status",)
