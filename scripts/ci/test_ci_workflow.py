"""Regression checks for CI checkout refs that differ between push and PR events."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load(path: str) -> dict:
    class Loader(yaml.SafeLoader):
        pass

    # PyYAML 1.1 treats the YAML 1.2 ``on`` key as a boolean.
    Loader.add_constructor("tag:yaml.org,2002:bool", lambda loader, node: loader.construct_scalar(node))
    return yaml.load((ROOT / path).read_text(encoding="utf-8"), Loader=Loader)  # noqa: S506


def test_object_storage_uses_a_stable_pr_checkout_ref() -> None:
    workflow = _load(".github/workflows/ci.yml")
    checkout = next(
        step for step in workflow["jobs"]["test-object-storage"]["steps"] if step.get("name") == "Checkout code"
    )

    assert checkout["with"]["ref"] == "${{ inputs.ref || github.event.pull_request.head.sha || github.sha }}"
