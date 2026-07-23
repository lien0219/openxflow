from pathlib import Path


_WORKFLOW_DIR = Path(__file__).parents[5] / ".github" / "workflows"
_CORE_WORKFLOW = _WORKFLOW_DIR / "channel-gateway-core.yml"
_FRONTEND_WORKFLOW = _WORKFLOW_DIR / "channel-gateway-frontend.yml"


def test_channel_core_workflow_uses_isolated_dependencies() -> None:
    content = _CORE_WORKFLOW.read_text(encoding="utf-8")

    assert "uv run --no-project" in content
    assert "--with 'lfx==1.10.2'" in content
    assert "--with 'pytest==9.0.3'" in content
    assert "--with 'pytest-asyncio>=0.23'" in content
    assert "uv sync" not in content
    assert "uv.lock" not in content


def test_channel_core_workflow_limits_branch_and_paths() -> None:
    content = _CORE_WORKFLOW.read_text(encoding="utf-8")

    assert "feature/channel-gateway" in content
    assert '"src/backend/base/langflow/channels/**"' in content
    assert '"src/backend/tests/unit/channels/**"' in content
    assert '".github/workflows/channel-gateway-frontend.yml"' in content
    assert "cancel-in-progress: true" in content


def test_channel_frontend_workflow_uses_locked_toolchain() -> None:
    content = _FRONTEND_WORKFLOW.read_text(encoding="utf-8")

    assert 'node-version: "20.19.0"' in content
    assert "cache-dependency-path: src/frontend/package-lock.json" in content
    assert "npm ci --ignore-scripts" in content
    assert "npx --no-install biome check" in content
    assert "npm test --" in content
    assert "npx --no-install tsc --noEmit" in content
    assert "npm install" not in content


def test_channel_frontend_workflow_limits_branch_and_paths() -> None:
    content = _FRONTEND_WORKFLOW.read_text(encoding="utf-8")

    assert "feature/channel-gateway" in content
    assert '"src/frontend/src/controllers/API/queries/channels/**"' in content
    assert '"src/frontend/src/pages/SettingsPage/pages/ChannelsPage/**"' in content
    assert "cancel-in-progress: true" in content
