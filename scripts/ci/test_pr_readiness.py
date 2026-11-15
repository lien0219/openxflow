"""Keep branch preflight coverage and generated metadata reproducible."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import orjson
import pytest
import yaml

from scripts import build_component_index as index_builder

ROOT = Path(__file__).resolve().parents[2]


def _workflow(filename: str) -> dict:
    return yaml.load(
        (ROOT / ".github/workflows" / filename).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,  # noqa: S506
    )


def test_branch_preflight_reuses_pr_ci_script_tests() -> None:
    shared = _workflow("ci-scripts-test.yml")
    assert "workflow_call" in shared["on"]
    assert shared["on"]["workflow_call"]["inputs"]["ref"]["type"] == "string"
    branch = _workflow("branch-ci.yml")
    preflight = branch["jobs"]["ci-scripts"]
    assert preflight["uses"] == "./.github/workflows/ci-scripts-test.yml"
    assert preflight["with"]["ref"] == "${{ github.sha }}"
    assert preflight["needs"] == "plan"
    assert preflight["if"] == branch["jobs"]["ci"]["if"]
    checkout = next(s for s in shared["jobs"]["test"]["steps"] if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["ref"] == "${{ inputs.ref || github.event.pull_request.head.sha || github.sha }}"


def test_sync_branches_request_complete_main_ci() -> None:
    inputs = _workflow("branch-ci.yml")["jobs"]["ci"]["with"]
    assert inputs["run-all-tests"] == "${{ startsWith(github.ref, 'refs/heads/sync/') }}"


def test_pr_script_filters_cover_generated_and_security_inputs() -> None:
    paths = _workflow("ci-scripts-test.yml")["on"]["pull_request"]["paths"]
    assert {
        "docker/**",
        "uv.lock",
        "src/lfx/pyproject.toml",
        "scripts/build_component_index.py",
        "src/lfx/src/lfx/_assets/component_index.json",
    } <= set(paths)


@pytest.mark.parametrize("installed_version", [None, "1.12.0", "9.9.9"])
def test_component_index_dependency_versions_come_from_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, installed_version: str | None
) -> None:
    lock_path = tmp_path / "uv.lock"
    lock_path.write_text(
        'version = 1\n[[package]]\nname = "jq"\nversion = "1.12.0"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
        '[[package]]\nname = "pyyaml"\nversion = "6.0.3"\n'
        'source = { registry = "https://pypi.org/simple" }\n',
        encoding="utf-8",
    )
    original = {
        "data": {
            "Example": {
                "metadata": {
                    "dependencies": {
                        "total_dependencies": 3,
                        "dependencies": [
                            {"name": "jq", "version": installed_version},
                            {"name": "yaml", "version": installed_version},
                            {"name": "unlocked_package", "version": installed_version},
                        ],
                    }
                }
            }
        }
    }
    source = copy.deepcopy(original)
    monkeypatch.setattr(index_builder, "LOCK_PATH", lock_path, raising=False)
    monkeypatch.setattr(index_builder, "_import_components", lambda: (source, 1))
    monkeypatch.setattr(index_builder, "_get_lfx_version", lambda: "1.13.2")
    index = index_builder.build_component_index()
    dependencies = index["entries"][0][1]["Example"]["metadata"]["dependencies"]["dependencies"]
    assert dependencies == [
        {"name": "jq", "version": "1.12.0"},
        {"name": "yaml", "version": "6.0.3"},
        {"name": "unlocked_package", "version": None},
    ]
    expected_hash = index.pop("sha256")
    assert hashlib.sha256(orjson.dumps(index, option=orjson.OPT_SORT_KEYS)).hexdigest() == expected_hash
    assert source == original


def test_index_lock_resolution_uses_canonical_python_and_ignores_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = tmp_path / "uv.lock"
    lock_path.write_text(
        "version = 1\n"
        '[[package]]\nname = "numpy"\nversion = "2.2.6"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
        "resolution-markers = [\"python_full_version < '3.11'\"]\n"
        '[[package]]\nname = "numpy"\nversion = "2.4.6"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
        "resolution-markers = [\"python_full_version == '3.13.*' and sys_platform == 'linux'\"]\n"
        '[[package]]\nname = "numpy"\nversion = "2.5.1"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
        "resolution-markers = [\"python_full_version >= '3.14'\"]\n"
        '[[package]]\nname = "lfx"\nversion = "1.13.2"\n'
        'source = { editable = "src/lfx" }\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(index_builder, "LOCK_PATH", lock_path)
    monkeypatch.setattr(
        index_builder,
        "_import_components",
        lambda: (
            {
                "data": {
                    "Example": {
                        "metadata": {
                            "dependencies": {
                                "total_dependencies": 2,
                                "dependencies": [
                                    {"name": "numpy", "version": "host"},
                                    {"name": "lfx", "version": "host"},
                                ],
                            }
                        }
                    }
                }
            },
            1,
        ),
    )
    monkeypatch.setattr(index_builder, "_get_lfx_version", lambda: "1.13.2")
    index = index_builder.build_component_index()
    dependencies = index["entries"][0][1]["Example"]["metadata"]["dependencies"]["dependencies"]
    assert dependencies == [{"name": "numpy", "version": "2.4.6"}, {"name": "lfx", "version": None}]


def test_index_lock_resolution_rejects_ambiguous_versions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock_path = tmp_path / "uv.lock"
    lock_path.write_text(
        "version = 1\n"
        '[[package]]\nname = "jq"\nversion = "1.11.0"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
        '[[package]]\nname = "jq"\nversion = "1.12.0"\n'
        'source = { registry = "https://pypi.org/simple" }\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(index_builder, "LOCK_PATH", lock_path)
    monkeypatch.setattr(index_builder, "_import_components", lambda: ({}, 0))
    monkeypatch.setattr(index_builder, "_get_lfx_version", lambda: "1.13.2")
    with pytest.raises(ValueError, match="Ambiguous component-index dependency"):
        index_builder.build_component_index()
