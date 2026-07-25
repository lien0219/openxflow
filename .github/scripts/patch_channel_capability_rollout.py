from pathlib import Path

apply_path = Path(".github/scripts/apply_channel_capability_response_scope.py")
apply_content = apply_path.read_text(encoding="utf-8")
old_marker = '    "def build_channel_session_id(\\n",\n'
new_marker = '    "def build_channel_session_id(",\n'
if old_marker in apply_content:
    apply_content = apply_content.replace(old_marker, new_marker, 1)

old_escape = '        normalized = "\\n".join(line for line in normalized_lines if line)'
new_escape = '        normalized = "\\\\n".join(line for line in normalized_lines if line)'
if old_escape in apply_content and new_escape not in apply_content:
    apply_content = apply_content.replace(old_escape, new_escape, 1)

apply_path.write_text(apply_content, encoding="utf-8")

queue_path = Path("src/backend/base/langflow/channels/services/queueing.py")
if queue_path.exists():
    queue_content = queue_path.read_text(encoding="utf-8")
    if "class ChannelQueueDescriptor:" not in queue_content:
        marker = "def _bounded_queue_key("
        descriptor = """@dataclass(frozen=True)
class ChannelQueueDescriptor:
    queue_key: str
    external_conversation_id: str
    external_user_id: str
    conversation_type: str
    conversation_scope_id: str
    context_mode: str
    serialized_by_conversation: bool


"""
        if marker not in queue_content:
            raise RuntimeError("Missing queue descriptor insertion marker")
        queue_path.write_text(queue_content.replace(marker, descriptor + marker, 1), encoding="utf-8")
