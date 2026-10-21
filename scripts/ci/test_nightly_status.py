"""Regression checks for the CI nightly status gate."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load_ci_workflow() -> dict:
    class Loader(yaml.SafeLoader):
        pass

    # PyYAML 1.1 treats the YAML 1.2 ``on`` key as a boolean.
    Loader.add_constructor("tag:yaml.org,2002:bool", lambda loader, node: loader.construct_scalar(node))
    return yaml.load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"), Loader=Loader)  # noqa: S506


def test_nightly_gate_skips_noncanonical_repositories() -> None:
    workflow = _load_ci_workflow()
    check_step = next(
        step for step in workflow["jobs"]["check-nightly-status"]["steps"] if step.get("id") == "check-pypi"
    )
    run_script = check_step["run"]
    skip_condition = '"${{ github.repository }}" != "langflow-ai/langflow"'

    assert skip_condition in run_script
    assert run_script.index(skip_condition) < run_script.index("https://pypi.org/pypi/langflow/json")
    assert "success=true" in run_script
    assert 'echo "status=not-applicable" >> $GITHUB_OUTPUT' in run_script
    assert "https://pypi.org/pypi/langflow/json" in run_script
    outputs = workflow["jobs"]["check-nightly-status"]["outputs"]
    assert outputs["should-proceed"] == "${{ steps.check-pypi.outputs.success }}"
    assert outputs["status"] == "${{ steps.check-pypi.outputs.status }}"
    ci_success = workflow["jobs"]["ci_success"]
    assert "needs.check-nightly-status.outputs.should-proceed" in ci_success["env"]["EXIT_CODE"]
