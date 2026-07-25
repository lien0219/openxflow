from pathlib import Path

path = Path("src/backend/tests/unit/channels/test_dispatch.py")
content = path.read_text(encoding="utf-8")
old = '''        assert response == ChannelMessage(title="Workflow", markdown="final answer")
        assert session.commits == 1
'''
new = '''        assert response == ChannelMessage(title="Workflow", markdown="final answer")
        # One commit exposes channel state before workflow execution; the second
        # persists the final channel message and response metadata.
        assert session.commits == 2
'''
if old not in content:
    raise RuntimeError("Missing dispatch commit expectation")
path.write_text(content.replace(old, new, 1), encoding="utf-8")
