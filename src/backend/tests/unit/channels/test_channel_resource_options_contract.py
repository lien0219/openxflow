from pathlib import Path

_ROOT = Path(__file__).parents[5]
_BACKEND = _ROOT / "src" / "backend" / "base" / "langflow" / "api" / "v1" / "channel_resources.py"
_FRONTEND = (
    _ROOT
    / "src"
    / "frontend"
    / "src"
    / "pages"
    / "SettingsPage"
    / "pages"
    / "ChannelsPage"
    / "components"
    / "ChannelResourceSelect.tsx"
)
_HOOK = (
    _ROOT
    / "src"
    / "frontend"
    / "src"
    / "controllers"
    / "API"
    / "queries"
    / "channels"
    / "use-get-channel-resource-options.ts"
)


def test_channel_flow_options_exclude_starter_templates() -> None:
    content = _BACKEND.read_text(encoding="utf-8")

    assert "STARTER_FOLDER_NAME" in content
    assert "Folder.name != STARTER_FOLDER_NAME" in content
    assert "project_name" in content


def test_channel_flow_options_resolve_selected_workflow_by_id() -> None:
    backend = _BACKEND.read_text(encoding="utf-8")
    hook = _HOOK.read_text(encoding="utf-8")
    frontend = _FRONTEND.read_text(encoding="utf-8")

    assert "selected_id" in backend
    assert "selected_item" in backend
    assert "selected_id: params.selectedId" in hook
    assert "selectedId: value || undefined" in frontend
    assert "flowQuery.data?.selected_item" in frontend


def test_channel_flow_picker_displays_workflow_and_project_names() -> None:
    content = _FRONTEND.read_text(encoding="utf-8")

    assert "flow.project_name" in content
    assert "`${flow.name} · ${flow.project_name}`" in content
    assert 'formatResourceOption("flow", selectedFlow, copy)' in content
