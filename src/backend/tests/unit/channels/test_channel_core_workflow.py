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


def test_channel_core_workflow_validates_workflow_syntax() -> None:
    content = _CORE_WORKFLOW.read_text(encoding="utf-8")

    assert "workflow-syntax:" in content
    assert "docker://rhysd/actionlint:1.7.7" in content
    assert "docker://rhysd/actionlint:latest" not in content
    assert ".github/workflows/channel-gateway-core.yml" in content
    assert ".github/workflows/channel-gateway-frontend.yml" in content


def test_channel_core_workflow_runs_resilient_adapter_contracts() -> None:
    content = _CORE_WORKFLOW.read_text(encoding="utf-8")

    assert "adapter-contracts:" in content
    assert "--with 'pytest-asyncio>=0.23'" in content
    assert "--with 'cryptography>=48.0.1'" in content
    assert "--with 'defusedxml>=0.7.1,<1.0.0'" in content
    assert "test_resilient_adapter_factory.py" in content
    assert "test_resilient_token_cache_delegation.py" in content
    assert "test_resilient_token_contracts.py" in content


def test_channel_core_workflow_runs_database_contracts() -> None:
    content = _CORE_WORKFLOW.read_text(encoding="utf-8")

    assert "database-contracts:" in content
    assert "--with 'sqlalchemy>=2.0.38,<3.0.0'" in content
    assert "--with 'sqlmodel==0.0.37'" in content
    assert "--with 'alembic>=1.13,<2.0.0'" in content
    assert "--with 'aiosqlite>=0.20,<1.0.0'" in content
    assert "test_channel_migrations_sqlite.py" in content
    assert "test_outbound_delivery_model.py" in content


def test_channel_core_workflow_limits_branch_and_paths() -> None:
    content = _CORE_WORKFLOW.read_text(encoding="utf-8")

    assert "feature/channel-gateway" in content
    assert '"src/backend/base/langflow/channels/**"' in content
    assert '"src/backend/base/langflow/services/database/models/channel/**"' in content
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


def test_channel_frontend_workflow_runs_checks_independently() -> None:
    content = _FRONTEND_WORKFLOW.read_text(encoding="utf-8")

    assert "format-lint:" in content
    assert "unit-tests:" in content
    assert "type-check:" in content
    assert content.count("npm ci --ignore-scripts") == 3


def test_channel_frontend_workflow_limits_branch_and_paths() -> None:
    content = _FRONTEND_WORKFLOW.read_text(encoding="utf-8")

    assert "feature/channel-gateway" in content
    assert '"src/frontend/src/controllers/API/queries/channels/**"' in content
    assert '"src/frontend/src/pages/SettingsPage/pages/ChannelsPage/**"' in content
    assert "cancel-in-progress: true" in content
