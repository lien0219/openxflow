from pathlib import Path

# Keep the one-shot observability rollout resilient to autofix formatting.
audit_path = Path("src/backend/base/langflow/channels/services/configuration_audit.py")
audit_content = audit_path.read_text(encoding="utf-8")
if "import sqlalchemy as sa\n" not in audit_content:
    audit_content = audit_content.replace(
        "from pydantic import BaseModel\n",
        "import sqlalchemy as sa\nfrom pydantic import BaseModel\n",
        1,
    )

compact_queries = (
    '(await session.exec(select(__import__("sqlalchemy").func.count()).select_from(ChannelConfigurationAudit).where(*filters))).one()',
    "(await session.exec(select(sa.func.count()).select_from(ChannelConfigurationAudit).where(*filters))).one()",
)
expanded_query = (
    "(\n"
    "            await session.exec(\n"
    "                select(sa.func.count())\n"
    "                .select_from(ChannelConfigurationAudit)\n"
    "                .where(*filters)\n"
    "            )\n"
    "        ).one()"
)
for expression in compact_queries:
    if expression in audit_content:
        audit_content = audit_content.replace(expression, expanded_query, 1)
        break

audit_path.write_text(audit_content, encoding="utf-8")

# SQLite batch table rebuilds must not attempt to restore indexes that depend on
# columns removed by this downgrade.
migration_path = Path(
    "src/backend/base/langflow/alembic/versions/e2f5a8c1d7b9_add_channel_production_controls.py"
)
migration_content = migration_path.read_text(encoding="utf-8")
index_cleanup = '''    for table_name, index_names in (
        (
            "channel_webhook_job",
            (
                "ix_channel_webhook_job_queue",
                "ix_channel_webhook_job_connection_status",
                "ix_channel_webhook_job_user_created",
            ),
        ),
        (
            "channel_execution_log",
            (
                "ix_channel_execution_external_user_id",
                "ix_channel_execution_session_id",
                "ix_channel_execution_external_user_created",
            ),
        ),
        ("channel_connection", ("ix_channel_connection_service_user_id",)),
    ):
        existing_indexes = _indexes(table_name, conn)
        for index_name in index_names:
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name=table_name)

'''
index_marker = '''    if migration.table_exists("channel_conversation_context_entry", conn):
        op.drop_table("channel_conversation_context_entry")

'''
if index_cleanup not in migration_content:
    if index_marker not in migration_content:
        raise RuntimeError("Missing production-control downgrade insertion marker")
    migration_content = migration_content.replace(index_marker, index_marker + index_cleanup, 1)
migration_path.write_text(migration_content, encoding="utf-8")

# SQLModel AsyncSession.add is synchronous, while lightweight test sessions may
# implement an awaitable add method. Support both without leaking coroutines.
message_path = Path("src/backend/base/langflow/channels/services/message_records.py")
message_content = message_path.read_text(encoding="utf-8")
if "import inspect\n" not in message_content:
    message_content = message_content.replace("import math\n", "import inspect\nimport math\n", 1)
add_helper = '''async def _add_to_session(session: AsyncSession, value: Any) -> None:
    result = session.add(value)
    if inspect.isawaitable(result):
        await result


'''
if add_helper not in message_content:
    helper_marker = "def _safe_scalar(value: Any) -> str | int | float | bool | None:\n"
    if helper_marker not in message_content:
        raise RuntimeError("Missing message-session helper insertion marker")
    message_content = message_content.replace(helper_marker, add_helper + helper_marker, 1)
message_content = message_content.replace("            session.add(existing)\n", "            await _add_to_session(session, existing)\n")
message_content = message_content.replace(
    "            session.add(\n                ChannelMessageRecord(\n",
    "            await _add_to_session(\n                session,\n                ChannelMessageRecord(\n",
)
message_path.write_text(message_content, encoding="utf-8")
