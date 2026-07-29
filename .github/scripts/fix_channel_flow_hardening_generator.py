from pathlib import Path

path = Path(__file__).with_name("apply_channel_flow_hardening.py")
content = path.read_text(encoding="utf-8")

old_types = '''for old, new in (
    (
        "  flow_selection_ttl_hours: number;\\n  default_response_mode: ChannelResponseMode;",
        "  flow_selection_ttl_hours: number;\\n  system_commands_require_mention: boolean;\\n  default_response_mode: ChannelResponseMode;",
    ),
    (
        "  flow_selection_ttl_hours?: number;\\n  default_response_mode?: ChannelResponseMode;",
        "  flow_selection_ttl_hours?: number;\\n  system_commands_require_mention?: boolean;\\n  default_response_mode?: ChannelResponseMode;",
    ),
):
    replace_once("src/frontend/src/controllers/API/queries/channels/types.ts", old, new)
'''
new_types = '''replace_once(
    "src/frontend/src/controllers/API/queries/channels/types.ts",
    "  flow_selection_ttl_hours: number;\\n  default_response_mode: ChannelResponseMode;",
    "  flow_selection_ttl_hours: number;\\n  system_commands_require_mention: boolean;\\n  default_response_mode: ChannelResponseMode;",
)
types_path = "src/frontend/src/controllers/API/queries/channels/types.ts"
types_content = read(types_path)
optional_old = "  flow_selection_ttl_hours?: number;\\n  default_response_mode?: ChannelResponseMode;"
optional_new = "  flow_selection_ttl_hours?: number;\\n  system_commands_require_mention?: boolean;\\n  default_response_mode?: ChannelResponseMode;"
if types_content.count(optional_old) != 2:
    raise RuntimeError(
        f"Expected two optional connection type matches, found {types_content.count(optional_old)}"
    )
write(types_path, types_content.replace(optional_old, optional_new))
'''
if content.count(old_types) != 1:
    raise RuntimeError(f"Expected one frontend type generator block, found {content.count(old_types)}")
content = content.replace(old_types, new_types, 1)

old_doc_source = '    "- whether bound users may create personal commands.",'
new_doc_source = '''    "- whether bound users may create personal commands;\\n"
    "- whether members may persistently select an allowed workflow;\\n"
    "- how long a persistent workflow selection remains valid.",'''
if content.count(old_doc_source) != 1:
    raise RuntimeError(f"Expected one routing policy source line, found {content.count(old_doc_source)}")
content = content.replace(old_doc_source, new_doc_source, 1)

old_migration_source = (
    '    "The final migration adds persistent member workflow selections, execution linkage, and workflow-specific context indexing.",'
)
new_migration_source = (
    '    "It follows `b5d8e1f3a6c9`, adds the active-selection table, connection and command policy fields, execution audit references, and the workflow-scoped context index. Apply all pending migrations and restart the backend before beginning provider-level manual acceptance.",'
)
if content.count(old_migration_source) != 1:
    raise RuntimeError(
        f"Expected one migration documentation source line, found {content.count(old_migration_source)}"
    )
content = content.replace(old_migration_source, new_migration_source, 1)

old_boolean_query = '    "    permanent_only: Annotated[bool, Query()] = False,\\n"'
new_boolean_query = '    "    permanent_only: Annotated[bool | None, Query()] = None,\\n"'
if content.count(old_boolean_query) != 1:
    raise RuntimeError(f"Expected one permanent-only query declaration, found {content.count(old_boolean_query)}")
content = content.replace(old_boolean_query, new_boolean_query, 1)

old_boolean_forward = '    "        permanent_only=permanent_only,\\n"'
new_boolean_forward = '    "        permanent_only=bool(permanent_only),\\n"'
if content.count(old_boolean_forward) != 1:
    raise RuntimeError(f"Expected one permanent-only forwarding line, found {content.count(old_boolean_forward)}")
content = content.replace(old_boolean_forward, new_boolean_forward, 1)

old_model_imports = '''from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa'''
new_model_imports = '''from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import sqlalchemy as sa'''
if content.count(old_model_imports) < 1:
    raise RuntimeError("Expected generated flow-selection model imports")
content = content.replace(old_model_imports, new_model_imports, 1)

old_model_runtime_import = '''from langflow.services.database.models.channel.model import utc_now


class ChannelActiveWorkflowSelection'''
new_model_runtime_import = '''from langflow.services.database.models.channel.model import utc_now

if TYPE_CHECKING:
    from datetime import datetime


class ChannelActiveWorkflowSelection'''
if content.count(old_model_runtime_import) != 1:
    raise RuntimeError(
        f"Expected one generated flow-selection model import anchor, found {content.count(old_model_runtime_import)}"
    )
content = content.replace(old_model_runtime_import, new_model_runtime_import, 1)

path.write_text(content, encoding="utf-8")
