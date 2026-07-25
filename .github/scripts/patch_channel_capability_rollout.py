from pathlib import Path

path = Path(".github/scripts/apply_channel_capability_response_scope.py")
content = path.read_text(encoding="utf-8")
old = '    "def build_channel_session_id(\\n",\n'
new = '    "def build_channel_session_id(",\n'
if old not in content:
    raise RuntimeError("Missing channel session rollout marker")
path.write_text(content.replace(old, new, 1), encoding="utf-8")
