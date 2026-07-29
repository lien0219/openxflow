"""Publish the already verified channel hardening product tree as one clean commit."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCT_COMMIT = "2ee7adf3db1b237e5eda41a55abf8ca5eeac4901"
FORMAL_BRANCH = "feature/channel-gateway"
PRODUCT_FILES = (
    "docs/channel-gateway-routing.md",
    "src/backend/base/langflow/alembic/versions/c7e2f4a9b1d3_harden_channel_flow_selection.py",
    "src/backend/base/langflow/api/v1/channel_management.py",
    "src/backend/base/langflow/channels/services/dispatch.py",
    "src/backend/base/langflow/channels/services/flow_selection.py",
    "src/backend/base/langflow/channels/services/flow_selection_maintenance.py",
    "src/backend/base/langflow/main.py",
    "src/backend/base/langflow/services/database/models/channel/flow_selection_model.py",
    "src/backend/tests/unit/channels/test_channel_flow_selection.py",
    "src/backend/tests/unit/channels/test_channel_flow_selection_hardening.py",
    "src/backend/tests/unit/channels/test_channel_migrations_sqlite.py",
    "src/frontend/src/controllers/API/queries/channels/use-get-channel-flow-selections.ts",
    "src/frontend/src/pages/SettingsPage/pages/ChannelsPage/components/DefaultRoutingTab.tsx",
    "src/frontend/src/pages/SettingsPage/pages/ChannelsPage/components/FlowSelectionsPanel.tsx",
)


def run(*args: str) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, cwd=ROOT, check=True)


run("git", "fetch", "origin", FORMAL_BRANCH)
run("git", "checkout", "-B", "channel-final-hardening-publish", f"origin/{FORMAL_BRANCH}")
run("git", "checkout", PRODUCT_COMMIT, "--", *PRODUCT_FILES)
run("git", "config", "user.name", "github-actions[bot]")
run("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
run("git", "add", *PRODUCT_FILES)
run("git", "commit", "-m", "feat(channels): harden persistent workflow selection")
run("git", "push", "origin", f"HEAD:{FORMAL_BRANCH}")
