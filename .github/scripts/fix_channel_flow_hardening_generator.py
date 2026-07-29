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

from datetime import datetime  # noqa: TC003
from uuid import UUID, uuid4

import sqlalchemy as sa'''
if content.count(old_model_imports) < 1:
    raise RuntimeError("Expected generated flow-selection model imports")
content = content.replace(old_model_imports, new_model_imports, 1)

compatibility_updates = r'''
# Keep regression fixtures aligned with the current authorization and provider contracts.
runtime_test_path = "src/backend/tests/unit/channels/test_channel_runtime.py"
runtime_test = read(runtime_test_path)
if runtime_test.count("import pytest") != 1:
    raise RuntimeError("Expected one pytest import in channel runtime tests")
runtime_test = runtime_test.replace(
    "import pytest",
    "from types import SimpleNamespace\\n\\nimport pytest",
    1,
)
if runtime_test.count("object()") != 2:
    raise RuntimeError(f"Expected two runtime authorization fixtures, found {runtime_test.count('object()')}")
runtime_test = runtime_test.replace("object()", "SimpleNamespace(is_superuser=True)")
write(runtime_test_path, runtime_test)

replace_once(
    "src/backend/tests/unit/channels/test_channel_capabilities_policy.py",
    '    assert wecom is not None and wecom.conversation_types == ("private",)\\n'
    '    assert validate_provider_conversation_type("wecom", "group") is False',
    '    assert wecom is not None and wecom.conversation_types == ("private", "group")\\n'
    '    assert wecom.supports_group_chat is True\\n'
    '    assert validate_provider_conversation_type("wecom", "group") is True\\n'
    '    assert validate_provider_conversation_type("wecom", "supergroup") is False',
)

replace_once(
    "src/backend/tests/unit/channels/test_dispatch.py",
    '    message = ChannelDispatchService._help_message(bound=True)\\n\\n'
    '    assert message.message_type == ChannelMessageType.CARD\\n'
    '    assert [action.value for action in message.actions] == ["/bind", "/commands"]',
    '    message = ChannelDispatchService._help_message(\\n'
    '        bound_user=SimpleNamespace(username="tester"),\\n'
    '        is_admin=False,\\n'
    '        access_policy="hybrid",\\n'
    '        conversation_type="private",\\n'
    '    )\\n\\n'
    '    assert message.message_type == ChannelMessageType.CARD\\n'
    '    assert [action.value for action in message.actions] == [\\n'
    '        "/commands",\\n'
    '        "/whoami",\\n'
    '        "/files",\\n'
    '        "/knowledge",\\n'
    '    ]',
)
'''
marker = 'print("Channel flow hardening changes applied.")'
if content.count(marker) != 1:
    raise RuntimeError(f"Expected one generator completion marker, found {content.count(marker)}")
content = content.replace(marker, compatibility_updates + "\n" + marker, 1)

path.write_text(content, encoding="utf-8")
