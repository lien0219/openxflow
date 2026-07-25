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
for expression in (
    'select(__import__("sqlalchemy").func.count()).select_from(ChannelConfigurationAudit).where(*filters)',
    "select(sa.func.count()).select_from(ChannelConfigurationAudit).where(*filters)",
):
    if expression in audit_content:
        audit_content = audit_content.replace(
            expression,
            "select(sa.func.count())\n"
            "                .select_from(ChannelConfigurationAudit)\n"
            "                .where(*filters)",
            1,
        )
audit_path.write_text(audit_content, encoding="utf-8")
