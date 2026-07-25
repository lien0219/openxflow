from pathlib import Path

path = Path("src/backend/base/langflow/channels/services/dispatch.py")
content = path.read_text(encoding="utf-8")
marker = "        context_mode = effective_context_mode(self.connection, binding)\n"
replacement = (
    "        if isinstance(principal, ChannelExecutionPrincipal):\n"
    "            execution_user = principal.user\n"
    "            execution_identity_type = principal.identity_type\n"
    "        else:\n"
    "            execution_user = principal\n"
    "            execution_identity_type = \"bound_user\"\n"
    "        context_mode = effective_context_mode(self.connection, binding)\n"
)
if marker not in content:
    raise RuntimeError("Missing workflow principal compatibility marker")
content = content.replace(marker, replacement, 1)
content = content.replace("principal.user.id", "execution_user.id")
content = content.replace("principal.user", "execution_user")
content = content.replace("principal.identity_type", "execution_identity_type")
path.write_text(content, encoding="utf-8")
