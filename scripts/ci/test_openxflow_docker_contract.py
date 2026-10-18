"""Static contract checks for the OpenXFlow production image."""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "docker" / "build_and_push.Dockerfile"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "openxflow-production-release.yml"


def test_product_version_is_independent_and_strictly_seeded() -> None:
    value = (REPO_ROOT / "deploy" / "IMAGE_VERSION").read_text(encoding="utf-8")
    assert re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\n", value)


def test_runtime_image_has_openxflow_provenance_and_upstream_attribution() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    for label in (
        "org.opencontainers.image.title",
        "org.opencontainers.image.description",
        "org.opencontainers.image.version",
        "org.opencontainers.image.revision",
        "org.opencontainers.image.created",
        "org.opencontainers.image.source",
        "org.opencontainers.image.url",
    ):
        assert label in dockerfile
    assert 'org.opencontainers.image.title="OpenXFlow"' in dockerfile
    assert 'com.openxflow.upstream.source="https://github.com/langflow-ai/langflow"' in dockerfile
    assert "USER user" in dockerfile
    assert "FROM runtime AS full" in dockerfile


def test_production_workflow_never_emits_latest() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert ":latest" not in workflow.lower()
    assert "type=raw,value=latest" not in workflow.lower()


def _stage(name: str) -> str:
    source = DOCKERFILE.read_text(encoding="utf-8")
    return re.split(r"(?m)^FROM ", source.split(f" AS {name}\n", 1)[1], maxsplit=1)[0]


@pytest.mark.parametrize("stage", ["full-dependencies", "full-builder", "full-bundles-builder"])
def test_full_distribution_installs_shared_vector_backend(stage: str) -> None:
    commands = re.findall(r"uv sync\b(.*?)(?:&&|\n\n)", _stage(stage), flags=re.DOTALL)
    assert commands, f"{stage} no longer resolves the full dependency environment"
    for command in commands:
        assert "--extra postgresql" in command
        assert "--extra pgvector" in command
        assert "--frozen" in command


def test_frontend_dependency_cache_precedes_source_copy() -> None:
    stage = _stage("frontend-builder")
    metadata_copy = re.search(r"COPY[^\n]*package\.json[^\n]*package-lock\.json", stage)
    assert metadata_copy is not None
    install = stage.index("npm ci")
    source_copy = stage.index("COPY ./src/frontend /tmp/src/frontend")
    assert metadata_copy.start() < install < source_copy < stage.index("npm run build")


def test_runtime_retains_the_actual_upstream_license() -> None:
    assert "Copyright (c) 2024 Langflow" in (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "COPY ./LICENSE /usr/share/licenses/openxflow/LICENSE" in _stage("runtime")


def test_base_image_is_immutable_and_node_download_is_checked() -> None:
    source = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(
        r"ARG PYTHON_IMAGE=registry\.access\.redhat\.com/ubi10/python-314-minimal@sha256:[a-f0-9]{64}", source
    )
    builder = _stage("builder-base")
    assert "sha256sum --check" in builder
    assert builder.index("sha256sum --check") < builder.index("tar -xJf /tmp/node.tar.xz")
    for arch in ("x64", "arm64"):
        assert re.search(rf"{arch}\).*?NODE_SHA256=[a-f0-9]{{64}}", builder)


def test_context_excludes_local_state_and_secret_files() -> None:
    patterns = set((REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines())
    assert {
        "**/.git",
        "**/.venv*",
        "**/.cache",
        "**/.env",
        "**/.env.*",
        "**/*.env",
        "**/node_modules",
        "**/*.pem",
        "**/*.key",
        "**/.npmrc",
        "**/.pypirc",
        "**/*.db",
        "**/*.sqlite*",
    } <= patterns
    # Ordinary source builds still need the checked-in artifact directory and LICENSE.
    assert ".release-artifacts" not in patterns
    assert "LICENSE" not in patterns
