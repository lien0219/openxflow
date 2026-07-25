from pathlib import Path

path = Path("src/backend/base/langflow/channels/services/access_control.py")
content = path.read_text(encoding="utf-8")
replacements = {
    "binding.access_policy != ChannelAccessPolicy.INHERIT.value": (
        'getattr(binding, "access_policy", ChannelAccessPolicy.INHERIT.value) '
        "!= ChannelAccessPolicy.INHERIT.value"
    ),
    "return binding.access_policy": (
        'return getattr(binding, "access_policy", ChannelAccessPolicy.INHERIT.value)'
    ),
    "return connection.access_policy": (
        'return getattr(connection, "access_policy", ChannelAccessPolicy.HYBRID.value)'
    ),
    "binding.context_mode != ChannelContextMode.INHERIT.value": (
        'getattr(binding, "context_mode", ChannelContextMode.INHERIT.value) '
        "!= ChannelContextMode.INHERIT.value"
    ),
    "return binding.context_mode": (
        'return getattr(binding, "context_mode", ChannelContextMode.INHERIT.value)'
    ),
    "return connection.default_context_mode": (
        'return getattr(connection, "default_context_mode", ChannelContextMode.ISOLATED.value)'
    ),
}
for old, new in replacements.items():
    if old not in content:
        raise RuntimeError(f"Missing policy compatibility target: {old}")
    content = content.replace(old, new, 1)
path.write_text(content, encoding="utf-8")
