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


def test_workflow_builds_pr_artifacts_and_publishes_only_after_merge():
    workflow = load()
    assert set(workflow["on"]) == {"pull_request"}
    assert workflow["on"]["pull_request"] == {
        "types": ["opened", "synchronize", "reopened", "closed"],
        "branches": ["main"],
    }
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
    preview = workflow["jobs"]["preview-package"]
    assert "github.event.action != 'closed'" in preview["if"]
    checkout = next(step for step in preview["steps"] if step.get("name") == "Check out PR head")
    assert checkout["with"]["ref"] == "${{ github.event.pull_request.head.sha }}"
    build = next(step for step in preview["steps"] if step.get("name") == "Build the PR OCI package")
    assert build["with"]["push"] == "false"
    assert build["with"]["outputs"] == "type=oci,dest=/tmp/openxflow-pr.oci.tar"
    assert any(step.get("uses", "").startswith("actions/upload-artifact@") for step in preview["steps"])
    for forbidden in ["workflow_dispatch", "workflow_call", "workflow_run", "schedule", "pull_request_target"]:
        assert forbidden not in workflow["on"]


def test_scanners_use_pinned_resolvable_trivy_action():
    workflow = load()
    expected = "aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25"
    for job_name, prefix in (
        ("preview-package", "/tmp/openxflow-pr"),  # noqa: S108 - workflow fixture path
        ("build-and-verify", "/tmp/openxflow"),  # noqa: S108 - workflow fixture path
    ):
        steps = workflow["jobs"][job_name]["steps"]
        prepare = next(step for step in steps if step.get("name", "").startswith("Prepare per-architecture Trivy"))
        assert "skopeo copy --override-os linux --override-arch" in prepare["run"]
        assert "docker-archive:" in prepare["run"]
        for arch in ("amd64", "arm64"):
            scans = [
                step
                for step in steps
                if step.get("name", "").endswith(f"{arch} image")
                and step.get("uses", "").startswith("aquasecurity/trivy-action@")
            ]
            assert len(scans) == 1
            assert scans[0]["uses"] == expected
            assert scans[0]["with"]["input"] == f"{prefix}-{arch}.docker.tar"
            assert scans[0]["with"]["exit-code"] == "1"
            assert scans[0]["with"]["severity"] == "CRITICAL,HIGH"
            assert scans[0]["with"]["scanners"] == "vuln,secret"


def test_build_has_no_registry_write_before_scan():
    source = WORKFLOW.read_text(encoding="utf-8")
    build_start = source.index("  build-and-verify:")
    publish_start = source.index("  publish-immutable:")
    build = source[build_start:publish_start]
    assert "push: false" in build
    assert "outputs: type=oci,dest=/tmp/openxflow.oci.tar" in build
    build_at = build.index("Build a multi-architecture OCI archive")
    prepare_at = build.index("Prepare per-architecture Trivy scan inputs (production)")
    amd64_at = build.index("Scan the unpushed production amd64 image")
    arm64_at = build.index("Scan the unpushed production arm64 image")
    verify_at = build.index("Verify OCI attestations, both architectures, and runtime probes")
    assert build_at < prepare_at < amd64_at < arm64_at < verify_at
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
    workflow = load()
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request_target" not in source
    assert "workflow_dispatch" not in source
    assert "inputs:" not in source
    assert "github.event.pull_request.head.sha" not in workflow["jobs"]["validate-merge"]["if"]
