from pathlib import Path

path = Path("src/backend/base/langflow/channels/services/dispatch.py")
content = path.read_text(encoding="utf-8")
start_marker = "    async def _execute_workflow(\n"
end_marker = "    async def _send_processing_message("
start = content.find(start_marker)
end = content.find(end_marker, start)
if start < 0 or end < 0:
    raise RuntimeError("Unable to locate workflow execution block")

block = content[start:end]
context_marker = "        context_mode = effective_context_mode(self.connection, binding)\n"
principal_setup = (
    "        if isinstance(principal, ChannelExecutionPrincipal):\n"
    "            execution_user = principal.user\n"
    "            execution_identity_type = principal.identity_type\n"
    "        else:\n"
    "            execution_user = principal\n"
    "            execution_identity_type = \"bound_user\"\n"
    "        context_mode = effective_context_mode(self.connection, binding)\n"
)
if context_marker not in block:
    raise RuntimeError("Missing workflow principal compatibility marker")
block = block.replace("principal.user.id", "execution_user.id")
block = block.replace("principal.user", "execution_user")
block = block.replace("principal.identity_type", "execution_identity_type")
block = block.replace(context_marker, principal_setup, 1)
content = content[:start] + block + content[end:]
path.write_text(content, encoding="utf-8")
