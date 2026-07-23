from __future__ import annotations

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from langflow.alembic.versions import (
    a8e1c6d4f5b7_add_channel_outbound_delivery as outbound_delivery_migration,
)
from langflow.alembic.versions import (
    c4a9e2d7f1b0_add_channel_gateway_schema as gateway_schema_migration,
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
    ]
    assert [migration.down_revision for migration in _MIGRATIONS] == [
        "e1705947c729",
        "c4a9e2d7f1b0",
        "d5b8f3a1c2e4",
        "e6c9a4b2d3f5",
        "f7d0b5c3e4a6",
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

        for migration in reversed(_MIGRATIONS):
            migration.downgrade()

        remaining_tables = set(sa.inspect(connection).get_table_names())
        assert expected_tables.isdisjoint(remaining_tables)
        assert {"user", "flow", "knowledge_base", "file", "job"}.issubset(remaining_tables)
