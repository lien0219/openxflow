from pathlib import Path

_WORKFLOW_DIR = Path(__file__).parents[5] / ".github" / "workflows"
_CORE_WORKFLOW = _WORKFLOW_DIR / "channel-gateway-core.yml"
_FRONTEND_WORKFLOW = _WORKFLOW_DIR / "channel-gateway-frontend.yml"


def test_channel_core_workflow_uses_locked_backend_environment() -> None:
    content = _CORE_WORKFLOW.read_text(encoding="utf-8")

    assert "uv sync --quiet --frozen --project src/backend/base --group dev" in content
    assert content.count("uv run --frozen --project src/backend/base --group dev") == 3
    assert '      - "uv.lock"' in content
    assert '      - "src/backend/base/pyproject.toml"' in content
    assert "uv run --no-project" not in content
    assert "--with '" not in content


def test_channel_core_workflow_validates_workflow_syntax() -> None:
    content = _CORE_WORKFLOW.read_text(encoding="utf-8")

    assert "workflow-syntax:" in content
    assert "docker://rhysd/actionlint:1.7.7" in content
    assert "docker://rhysd/actionlint:latest" not in content
    assert ".github/workflows/channel-gateway-core.yml" in content
    assert ".github/workflows/channel-gateway-frontend.yml" in content


def test_channel_core_workflow_runs_resilient_adapter_contracts() -> None:
    content = _CORE_WORKFLOW.read_text(encoding="utf-8")

    assert "Run all channel contract suites" in content
    assert "test_resilient_adapter_factory.py" in content
    assert "test_resilient_token_cache_delegation.py" in content
    assert "test_resilient_token_contracts.py" in content
    assert "/tmp/channel-adapters.log" in content
    assert "adapter_status=${PIPESTATUS[0]}" in content


def test_channel_core_workflow_runs_database_contracts() -> None:
    content = _CORE_WORKFLOW.read_text(encoding="utf-8")

    assert "test_channel_migrations_sqlite.py" in content
    assert "test_outbound_delivery_model.py" in content
    assert "/tmp/channel-database.log" in content
    assert "database_status=${PIPESTATUS[0]}" in content


def test_channel_core_workflow_publishes_complete_failure_logs() -> None:
    content = _CORE_WORKFLOW.read_text(encoding="utf-8")

    assert "uses: actions/upload-artifact@v4" in content
    assert "name: channel-contract-logs" in content
    assert "if: always()" in content
    assert "/tmp/channel-core.log" in content
    assert "/tmp/channel-status.log" in content


def test_channel_core_workflow_limits_target_branch_and_paths() -> None:
    content = _CORE_WORKFLOW.read_text(encoding="utf-8")

    assert "branches:\n      - main" in content
    assert "feature/channel-gateway" not in content
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


def test_channel_frontend_workflow_limits_target_branch_and_paths() -> None:
    content = _FRONTEND_WORKFLOW.read_text(encoding="utf-8")

    assert "branches:\n      - main" in content
    assert "feature/channel-gateway" not in content
    assert '"src/frontend/src/controllers/API/queries/channels/**"' in content
    assert '"src/frontend/src/pages/SettingsPage/pages/ChannelsPage/**"' in content
    assert "cancel-in-progress: true" in content
