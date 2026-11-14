"""Regression checks for CI workflow configuration."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
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


@pytest.mark.parametrize(
    ("title", "valid"),
    [
        ("feat(deploy): 完善生产配置并兼容同机单实例测试", True),
        ("fix(ci): pin the Playwright runner", True),
        ("feat(api)!: 调整 API / SSE 行为", True),
        ("docs: 更新部署说明 (单实例测试)", True),
        ("fix: 修复登录", True),
        ("完善生产配置", False),
        ("feat(deploy) 完善生产配置", False),
        ("feat(deploy):", False),
        ("feat(deploy):   ", False),
        ("prefix feat(deploy): valid description", False),
        ("feat(): empty scope", False),
    ],
)
def test_conventional_pr_title_validation(title: str, *, valid: bool) -> None:
    workflow = _load(".github/workflows/conventional-labels.yml")
    validator = next(
        step
        for step in workflow["jobs"]["validate-pr"]["steps"]
        if step.get("uses", "").startswith("Namchee/conventional-pr@")
    )
    # The pinned action uses Go regexp, whose \w character class is ASCII.
    # Keep its v0.16.0 default here to exercise the unset-override regression.
    pattern = validator["with"].get("title_pattern", r"([\w\-]+)(\([\w\-]+\))?!?: [\w\s:\-]+")

    assert bool(re.search(pattern, title, flags=re.ASCII)) is valid
