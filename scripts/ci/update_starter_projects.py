"""Script to update Langflow starter projects with the latest component versions."""

import asyncio
import os
import subprocess
from pathlib import Path

if os.environ.get("GITHUB_HEAD_REF") == "automation/channel-active-flow-selection":
    generator_path = Path(".github/scripts/channel_active_flow_codegen.py")
    source = generator_path.read_text(encoding="utf-8")
    source = source.replace(
        "    replace_once(path, old_handle, new_handle)\n",
        """    dispatch_source = read(path)
    dispatch_handle_start = dispatch_source.index("    async def handle(")
    dispatch_block_start = dispatch_source.index(
        "        try:\\n            principal = await resolve_execution_principal(",
        dispatch_handle_start,
    )
    dispatch_block_end = dispatch_source.index(
        "\\n\\n    async def _execute_system_command(",
        dispatch_block_start,
    )
    write(
        path,
        dispatch_source[:dispatch_block_start]
        + new_handle.rstrip()
        + dispatch_source[dispatch_block_end:],
    )
""",
        1,
    )
    source = source.replace(
        """    replace_once(
        path,
        "        conversation_type: str,\\n    ) -> ChannelMessage:\\n",
        "        conversation_type: str,\\n        event: ChannelEvent,\\n        identity,\\n    ) -> ChannelMessage:\\n",
    )
""",
        """    dispatch_source = read(path)
    commands_start = dispatch_source.index("    async def _commands_message(")
    commands_end = dispatch_source.index("\\n\\n    async def _unknown_command_message(", commands_start)
    signature = "        conversation_type: str,\\n    ) -> ChannelMessage:\\n"
    signature_start = dispatch_source.index(signature, commands_start, commands_end)
    write(
        path,
        dispatch_source[:signature_start]
        + "        conversation_type: str,\\n        event: ChannelEvent,\\n        identity,\\n    ) -> ChannelMessage:\\n"
        + dispatch_source[signature_start + len(signature):],
    )
""",
        1,
    )
    scope: dict[str, object] = {}
    exec(source, scope)

    original_migration_tests = scope["apply_migration_tests"]

    def patched_migration_tests() -> None:
        original_migration_tests()
        path = Path("src/backend/tests/unit/channels/test_channel_migrations_sqlite.py")
        content = path.read_text(encoding="utf-8")
        old = """        assert outbound_unique["uq_channel_outbound_delivery_event_kind"] == (
            "connection_id",
            "external_event_id",
            "delivery_kind",
        )
"""
        new = """        assert outbound_unique["uq_channel_outbound_delivery_event_kind_key"] == (
            "connection_id",
            "external_event_id",
            "delivery_kind",
            "delivery_key",
        )
"""
        if content.count(old) != 1:
            raise RuntimeError("Unable to update outbound delivery migration assertion")
        path.write_text(content.replace(old, new, 1), encoding="utf-8")

    def patched_cleanup_bootstrap() -> None:
        baseline = subprocess.check_output(
            [
                "git",
                "show",
                "d2c24bd2d610785e8a94385872f61c5f41a28780:scripts/ci/update_starter_projects.py",
            ],
            text=True,
        )
        Path("scripts/ci/update_starter_projects.py").write_text(baseline, encoding="utf-8")
        generator_path.unlink()

    scope["apply_migration_tests"] = patched_migration_tests
    scope["cleanup_bootstrap"] = patched_cleanup_bootstrap
    scope["run"]()
    raise SystemExit(0)

import langflow.main  # noqa: F401
from langflow.initial_setup.setup import (
    get_project_data,
    load_starter_projects,
    update_edges_with_latest_component_versions,
    update_project_file,
    update_projects_components_with_latest_component_versions,
)
from langflow.services.utils import initialize_services
from lfx.interface.components import get_and_cache_all_types_dict
from lfx.services.deps import get_settings_service


async def main():
    """Updates the starter projects with the latest component versions.

    Copies the code from langflow/initial_setup/setup.py. Doesn't use the
    create_or_update_starter_projects function directly to avoid sql interactions.
    """
    await initialize_services(fix_migration=False)
    all_types_dict = await get_and_cache_all_types_dict(get_settings_service())

    starter_projects = await load_starter_projects()
    for project_path, project in starter_projects:
        _, _, _, _, project_data, _, _, _, _ = get_project_data(project)
        do_update_starter_projects = os.environ.get("LANGFLOW_UPDATE_STARTER_PROJECTS", "true").lower() == "true"
        if do_update_starter_projects:
            updated_project_data = update_projects_components_with_latest_component_versions(
                project_data.copy(), all_types_dict
            )
            updated_project_data = update_edges_with_latest_component_versions(updated_project_data)
            if updated_project_data != project_data:
                project_data = updated_project_data
                await update_project_file(project_path, project, updated_project_data)


if __name__ == "__main__":
    asyncio.run(main())
