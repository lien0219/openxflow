from pathlib import Path

# SQLModel AsyncSession.add is synchronous, while lightweight test sessions may
# implement an awaitable add method. Support both without leaking coroutines.
message_path = Path("src/backend/base/langflow/channels/services/message_records.py")
message_content = message_path.read_text(encoding="utf-8")
if "import inspect\n" not in message_content:
    message_content = message_content.replace("import math\n", "import inspect\nimport math\n", 1)
add_helper = """async def _add_to_session(session: AsyncSession, value: Any) -> None:
    result = session.add(value)
    if inspect.isawaitable(result):
        await result


"""
if add_helper not in message_content:
    helper_marker = "def _safe_scalar(value: Any) -> str | int | float | bool | None:\n"
    if helper_marker not in message_content:
        raise RuntimeError("Missing message-session helper insertion marker")
    message_content = message_content.replace(helper_marker, add_helper + helper_marker, 1)
message_content = message_content.replace(
    "            session.add(existing)\n",
    "            await _add_to_session(session, existing)\n",
)
message_content = message_content.replace(
    "            session.add(\n                ChannelMessageRecord(\n",
    "            await _add_to_session(\n                session,\n                ChannelMessageRecord(\n",
)
message_path.write_text(message_content, encoding="utf-8")
