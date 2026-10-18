"""Executable policy checks for the main-only production workflow."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/openxflow-production-release.yml"


def load():
    # PyYAML 1.1 treats the YAML 1.2 ``on`` key as a boolean.
    class Loader(yaml.SafeLoader):
        pass

    Loader.add_constructor("tag:yaml.org,2002:bool", lambda loader, node: loader.construct_scalar(node))
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=Loader)


def test_only_closed_merged_main_pr_can_start_workflow():
    workflow = load()
    assert set(workflow["on"]) == {"pull_request"}
    assert workflow["on"]["pull_request"] == {"types": ["closed"], "branches": ["main"]}
    admission = workflow["jobs"]["validate-merge"]["if"]
    for expression in [
        "github.repository == 'lien0219/openxflow'",
        "github.event_name == 'pull_request'",
        "github.event.action == 'closed'",
        "github.event.pull_request.merged == true",
        "github.event.pull_request.base.ref == 'main'",
        "github.event.pull_request.merge_commit_sha != ''",
    ]:
        assert expression in admission
    for forbidden in ["workflow_dispatch", "workflow_call", "workflow_run", "schedule", "pull_request_target"]:
        assert forbidden not in workflow["on"]


def test_build_has_no_registry_write_before_scan():
    source = WORKFLOW.read_text(encoding="utf-8")
    build_start = source.index("  build-and-verify:")
    publish_start = source.index("  publish-immutable:")
    build = source[build_start:publish_start]
    assert "push: false" in build
    assert "outputs: type=oci,dest=/tmp/openxflow.oci.tar" in build
    assert build.index("Scan the unpushed OCI archive") > build.index("Build a multi-architecture OCI archive")
    assert 'skopeo copy --all --preserve-digests "oci-archive:' not in build


def test_publication_order_and_immutable_coordinates():
    workflow = load()
    jobs = workflow["jobs"]
    assert jobs["publish-immutable"]["needs"] == ["validate-merge", "build-and-verify"]
    assert jobs["create-release"]["needs"] == ["validate-merge", "publish-immutable"]
    assert jobs["promote-main"]["needs"] == ["validate-merge", "publish-immutable", "create-release"]
    source = WORKFLOW.read_text(encoding="utf-8").lower()
    assert ":latest" not in source
    assert "sha-${source}" in source
    assert "--preserve-digests" in source
    assert "org.opencontainers.image.revision" in source


def test_retry_runtime_probes_use_the_verified_reuse_coordinate():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert 'docker run --rm --entrypoint python "${REUSE_REF}"' in source
    assert 'docker run --rm --entrypoint langflow "${REUSE_REF}" --help' in source
    assert 'docker run --rm --entrypoint python "${REGISTRY}/${IMAGE_NAME}:sha-${SOURCE}"' not in source
    assert 'docker run --rm --entrypoint langflow "${REGISTRY}/${IMAGE_NAME}:sha-${SOURCE}"' not in source


def test_workflow_has_no_untrusted_code_trigger_or_manual_sha_input():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request_target" not in source
    assert "workflow_dispatch" not in source
    assert "inputs:" not in source
    assert "github.event.pull_request.head.sha" not in source
