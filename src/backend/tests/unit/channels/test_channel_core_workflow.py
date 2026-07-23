from pathlib import Path


_WORKFLOW = Path(__file__).parents[4] / ".github" / "workflows" / "channel-gateway-core.yml"


def test_channel_core_workflow_uses_isolated_dependencies() -> None:
    content = _WORKFLOW.read_text(encoding="utf-8")

    assert "uv run --no-project" in content
    assert "--with 'lfx==1.10.2'" in content
    assert "--with 'pytest==9.0.3'" in content
    assert "--with 'pytest-asyncio>=0.23'" in content
    assert "uv sync" not in content
    assert "uv.lock" not in content


def test_channel_core_workflow_limits_branch_and_paths() -> None:
    content = _WORKFLOW.read_text(encoding="utf-8")

    assert "feature/channel-gateway" in content
    assert '"src/backend/base/langflow/channels/**"' in content
    assert '"src/backend/tests/unit/channels/**"' in content
    assert "cancel-in-progress: true" in content
