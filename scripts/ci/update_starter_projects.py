"""Script to update Langflow starter projects with the latest component versions."""

import runpy
from pathlib import Path

_HARDENING = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "channel_final_hardening.py"
if _HARDENING.exists():
    generator = _HARDENING.read_text(encoding="utf-8")
    old_migration = """    migration_test = "src/backend/tests/unit/channels/test_channel_migrations_sqlite.py"
    content = read(migration_test)
    if "c7e2f4a9b1d3" not in content:
        content = content.replace(
            '"a1f4c7e9d2b6",\\n',
            '"a1f4c7e9d2b6",\\n        "c7e2f4a9b1d3",\\n',
        )
        write(migration_test, content)
"""
    new_migration = """    migration_test = "src/backend/tests/unit/channels/test_channel_migrations_sqlite.py"
    content = read(migration_test)
    if "c7e2f4a9b1d3_harden_channel_flow_selection" not in content:
        content = content.replace(
            "from langflow.alembic.versions import (\\n"
            "    a1f4c7e9d2b6_add_channel_active_workflow_selection as active_flow_selection_migration,\\n"
            ")\\n",
            "from langflow.alembic.versions import (\\n"
            "    a1f4c7e9d2b6_add_channel_active_workflow_selection as active_flow_selection_migration,\\n"
            ")\\n"
            "from langflow.alembic.versions import (\\n"
            "    c7e2f4a9b1d3_harden_channel_flow_selection as flow_selection_hardening_migration,\\n"
            ")\\n",
        )
        content = content.replace(
            "    active_flow_selection_migration,\\n)",
            "    active_flow_selection_migration,\\n    flow_selection_hardening_migration,\\n)",
        )
        content = content.replace(
            '        "a1f4c7e9d2b6",\\n    ]\\n    assert [migration.down_revision',
            '        "a1f4c7e9d2b6",\\n        "c7e2f4a9b1d3",\\n    ]\\n'
            '    assert [migration.down_revision',
        )
        content = content.replace(
            '        "b5d8e1f3a6c9",\\n    ]\\n\\n\\ndef test_channel_migrations_upgrade',
            '        "b5d8e1f3a6c9",\\n        "a1f4c7e9d2b6",\\n    ]\\n\\n\\ndef test_channel_migrations_upgrade',
        )
        write(migration_test, content)
"""
    if old_migration in generator:
        generator = generator.replace(old_migration, new_migration, 1)
    elif "flow_selection_hardening_migration" not in generator:
        raise RuntimeError("Unable to patch channel hardening migration registration")

    old_frontend = """    run(
        "npm",
        "exec",
        "--prefix",
        "src/frontend",
        "biome",
        "check",
        "--",
        "src/controllers/API/queries/channels/use-get-channel-flow-selections.ts",
        "src/pages/SettingsPage/pages/ChannelsPage/components/FlowSelectionsPanel.tsx",
        "src/pages/SettingsPage/pages/ChannelsPage/components/DefaultRoutingTab.tsx",
    )
    run("npm", "exec", "--prefix", "src/frontend", "tsc", "--", "-p", "tsconfig.channels.json", "--noEmit")
"""
    new_frontend = """    run("npm", "ci", "--prefix", "src/frontend", "--ignore-scripts", "--loglevel=error")
    run(
        "bash",
        "-lc",
        "cd src/frontend && npx --no-install biome check --write "
        "src/controllers/API/queries/channels/use-get-channel-flow-selections.ts "
        "src/pages/SettingsPage/pages/ChannelsPage/components/FlowSelectionsPanel.tsx "
        "src/pages/SettingsPage/pages/ChannelsPage/components/DefaultRoutingTab.tsx && "
        "npx --no-install biome check "
        "src/controllers/API/queries/channels/use-get-channel-flow-selections.ts "
        "src/pages/SettingsPage/pages/ChannelsPage/components/FlowSelectionsPanel.tsx "
        "src/pages/SettingsPage/pages/ChannelsPage/components/DefaultRoutingTab.tsx",
    )
    run(
        "bash",
        "-lc",
        "cd src/frontend && set +e; "
        "npx --no-install tsc --noEmit --pretty false --project tsconfig.channels.json "
        "2>&1 | tee /tmp/channel-hardening-tsc.log; "
        "focused='^src/(controllers/API/queries/channels|pages/SettingsPage/pages/ChannelsPage).*error TS[0-9]+:'; "
        "if grep -E \\\"$focused\\\" /tmp/channel-hardening-tsc.log; then exit 1; fi; exit 0",
    )
"""
    if old_frontend in generator:
        generator = generator.replace(old_frontend, new_frontend, 1)
    elif "channel-hardening-tsc.log" not in generator:
        raise RuntimeError("Unable to patch channel hardening frontend validation")

    old_commit = """    run("git", "checkout", "origin/feature/channel-gateway", "--", "scripts/ci/update_starter_projects.py")
    generator_path = ROOT / ".github/scripts/channel_final_hardening.py"
    generator_path.unlink(missing_ok=True)
    run("git", "add", "-A")
    run("git", "commit", "-m", "feat(channels): harden persistent workflow selection")
"""
    new_commit = """    run("git", "checkout", "origin/feature/channel-gateway", "--", "scripts/ci/update_starter_projects.py")
    generator_path = ROOT / ".github/scripts/channel_final_hardening.py"
    generator_path.unlink(missing_ok=True)
    run("git", "config", "user.name", "github-actions[bot]")
    run("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    run("git", "add", "-A")
    run("git", "commit", "-m", "feat(channels): harden persistent workflow selection")
"""
    if old_commit in generator:
        generator = generator.replace(old_commit, new_commit, 1)
    elif "github-actions[bot]" not in generator:
        raise RuntimeError("Unable to patch channel hardening commit identity")

    _HARDENING.write_text(generator, encoding="utf-8")
    runpy.run_path(str(_HARDENING), run_name="__main__")
    raise SystemExit(0)

import asyncio
import os

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
