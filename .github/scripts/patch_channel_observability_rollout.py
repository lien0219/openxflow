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
